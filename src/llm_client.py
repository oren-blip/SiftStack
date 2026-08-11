"""Thin LLM abstraction layer — routes calls to Anthropic or Ollama.

Supports two backends:
  - anthropic: Claude Haiku via Anthropic API (production, paid)
  - ollama: Local model via Ollama OpenAI-compatible API (development, free)

Backend selection: LLM_BACKEND env var or config.LLM_BACKEND.
"""

import atexit
import json
import logging
import re

import config as cfg

logger = logging.getLogger(__name__)

# ── Per-process Anthropic usage accounting ────────────────────────────
#
# Why: the 8/3-8/7 spend blowout was only discovered on the Anthropic BILL
# ($10 auto-reloads). The nightly log had no way to answer "what did tonight
# cost?". Every Anthropic call now records its token usage; at process exit
# a one-line summary with an estimated dollar cost is printed to stdout (so
# the nightly run log captures it) and logged. Zero-call processes stay
# silent.
#
# Prices are per MTok (input, output) — update when Anthropic reprices.
_PRICES = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku": (1.00, 5.00),
    "claude-sonnet": (3.00, 15.00),   # sonnet 4-6 / sonnet-5
    "claude-opus": (15.00, 75.00),
    "claude-fable": (15.00, 75.00),
}
_USAGE: dict[str, dict] = {}  # model -> {calls, in_tok, out_tok}


def _record_usage(model: str, response) -> None:
    """Accumulate token usage from an Anthropic response (best-effort)."""
    try:
        u = getattr(response, "usage", None)
        stats = _USAGE.setdefault(model, {"calls": 0, "in_tok": 0, "out_tok": 0})
        stats["calls"] += 1
        if u is not None:
            stats["in_tok"] += getattr(u, "input_tokens", 0) or 0
            stats["out_tok"] += getattr(u, "output_tokens", 0) or 0
    except Exception:  # noqa: BLE001 — accounting must never break a call
        pass


def _est_cost(model: str, in_tok: int, out_tok: int) -> float:
    for prefix, (pin, pout) in _PRICES.items():
        if model.startswith(prefix):
            return (in_tok * pin + out_tok * pout) / 1_000_000
    return (in_tok * 3.00 + out_tok * 15.00) / 1_000_000  # unknown → sonnet rate


@atexit.register
def _report_usage() -> None:
    if not _USAGE:
        return
    total_calls = sum(s["calls"] for s in _USAGE.values())
    total_cost = sum(_est_cost(m, s["in_tok"], s["out_tok"]) for m, s in _USAGE.items())
    parts = ", ".join(
        f"{m}: {s['calls']} calls {s['in_tok']}/{s['out_tok']} tok"
        for m, s in sorted(_USAGE.items()))
    line = (f"LLM USAGE this process: {total_calls} Anthropic calls, "
            f"est ${total_cost:.2f} ({parts})")
    print(line, flush=True)
    logger.info(line)


# ── Backend dispatch ──────────────────────────────────────────────────


def chat_json(
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
    api_key: str | None = None,
    model: str | None = None,
) -> dict | None:
    """Send prompt, get parsed JSON response. Routes to configured backend.

    Returns parsed dict on success, None on failure.

    model: optional per-call Anthropic model override (e.g. a higher-quality
    model for accuracy-critical extraction). Defaults to config.LLM_MODEL.
    Ignored by the ollama / openrouter backends (they have their own model config).
    """
    backend = getattr(cfg, "LLM_BACKEND", "anthropic")
    if backend == "ollama":
        return _chat_ollama(prompt, system, max_tokens)
    elif backend == "openrouter":
        return _chat_openrouter(prompt, system, max_tokens)
    else:
        return _chat_anthropic(prompt, system, max_tokens, api_key, model)


def chat_json_async(
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
    api_key: str | None = None,
    model: str | None = None,
):
    """Async version — returns a coroutine. For llm_parser.py compatibility."""
    import asyncio
    backend = getattr(cfg, "LLM_BACKEND", "anthropic")
    if backend == "ollama":
        return _chat_ollama_async(prompt, system, max_tokens)
    elif backend == "openrouter":
        return _chat_openrouter_async(prompt, system, max_tokens)
    else:
        return _chat_anthropic_async(prompt, system, max_tokens, api_key, model)


# ── Anthropic backend ────────────────────────────────────────────────


def vision_json(
    prompt: str,
    images: list[bytes],
    system: str = "",
    max_tokens: int = 2048,
    api_key: str | None = None,
    model: str | None = None,
) -> dict | None:
    """Send page images + prompt to Claude and get parsed JSON back.

    Exists because Tesseract cannot read HANDWRITING. NC court estate forms
    (Family History Affidavit, Estates Action Cover Sheet) are printed forms
    filled in BY HAND — the applicant's phone, email, and the children/heirs
    table are all handwritten. OCR returns the printed field labels and drops
    every answer, which reads downstream as "the form has no phone number".
    Walsh 26E002826-590 (2026-08-02): Tesseract found zero phones; the form
    plainly shows "(704) 564-0605", an email, and three children with
    addresses and ages.

    Anthropic backend only (ollama/openrouter vision is not wired). Returns
    None when unavailable so callers can fall back to the OCR text path.
    """
    import base64

    backend = getattr(cfg, "LLM_BACKEND", "anthropic")
    if backend != "anthropic":
        logger.info("vision_json: backend %r has no vision path — skipping", backend)
        return None
    key = api_key or cfg.ANTHROPIC_API_KEY
    if not key:
        logger.warning("No Anthropic API key — skipping vision call")
        return None
    if not images:
        return None
    # Default to a strong model: handwriting is the hardest read in the
    # pipeline and a mis-read phone number is worse than no phone number.
    model = model or getattr(cfg, "LLM_VISION_MODEL", "claude-sonnet-5")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        content: list[dict] = []
        for img in images:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png",
                           "data": base64.standard_b64encode(img).decode()},
            })
        content.append({"type": "text", "text": prompt})
        response = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": content}],
        )
        _record_usage(model, response)
        # Thinking-capable models put a ThinkingBlock at content[0], so index 0
        # is not reliably the answer — take the first actual text block.
        text = next((b.text for b in response.content
                     if getattr(b, "type", None) == "text"), "")
        if not text:
            logger.warning("Vision call returned no text block (model=%s)", model)
            return None
        return _parse_json(text.strip())
    except Exception as e:  # noqa: BLE001
        logger.warning("Vision call failed (model=%s): %s", model, e)
        return None


def _chat_anthropic(
    prompt: str, system: str, max_tokens: int, api_key: str | None,
    model: str | None = None,
) -> dict | None:
    """Call Claude via Anthropic API (sync). model overrides config.LLM_MODEL."""
    import anthropic

    key = api_key or cfg.ANTHROPIC_API_KEY
    if not key:
        logger.warning("No Anthropic API key — skipping LLM call")
        return None

    model = model or getattr(cfg, "LLM_MODEL", "claude-haiku-4-5-20251001")
    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        _record_usage(model, response)
        result_text = response.content[0].text.strip()
        return _parse_json(result_text)
    except anthropic.NotFoundError as e:
        # Almost always a bad/retired model id. Surface loudly: silently returning
        # None here makes downstream extraction (e.g. heir maps) collapse to empty.
        logger.error("Anthropic rejected model %r (NotFoundError): %s", model, e)
        return None
    except Exception as e:
        logger.warning("Anthropic LLM call failed (model=%s): %s", model, e)
        return None


async def _chat_anthropic_async(
    prompt: str, system: str, max_tokens: int, api_key: str | None,
    model: str | None = None,
) -> dict | None:
    """Call Claude via Anthropic API (async). model overrides config.LLM_MODEL."""
    import anthropic

    key = api_key or cfg.ANTHROPIC_API_KEY
    if not key:
        logger.warning("No Anthropic API key — skipping LLM call")
        return None

    model = model or getattr(cfg, "LLM_MODEL", "claude-haiku-4-5-20251001")
    try:
        client = anthropic.AsyncAnthropic(api_key=key)
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        _record_usage(model, response)
        result_text = response.content[0].text.strip()
        return _parse_json(result_text)
    except anthropic.NotFoundError as e:
        logger.error("Anthropic rejected model %r (NotFoundError): %s", model, e)
        return None
    except Exception as e:
        logger.warning("Anthropic async LLM call failed (model=%s): %s", model, e)
        return None


# ── Ollama backend ───────────────────────────────────────────────────


def _chat_ollama(
    prompt: str, system: str, max_tokens: int,
) -> dict | None:
    """Call local Ollama model via OpenAI-compatible API (sync)."""
    from openai import OpenAI

    base_url = getattr(cfg, "OLLAMA_BASE_URL", "http://localhost:11434/v1/")
    model = getattr(cfg, "OLLAMA_MODEL", "qwen2.5:7b")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        client = OpenAI(base_url=base_url, api_key="ollama")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        result_text = response.choices[0].message.content.strip()
        parsed = _parse_json(result_text)
        if parsed is None:
            # Retry once with explicit JSON instruction appended
            logger.debug("Ollama JSON parse failed, retrying with hint")
            retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no explanation."
            response = client.chat.completions.create(
                model=model,
                messages=[
                    *(([{"role": "system", "content": system}] if system else [])),
                    {"role": "user", "content": retry_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
            )
            result_text = response.choices[0].message.content.strip()
            parsed = _parse_json(result_text)
        return parsed
    except Exception as e:
        logger.warning("Ollama LLM call failed: %s", e)
        return None


async def _chat_ollama_async(
    prompt: str, system: str, max_tokens: int,
) -> dict | None:
    """Call local Ollama model via OpenAI-compatible API (async)."""
    from openai import AsyncOpenAI

    base_url = getattr(cfg, "OLLAMA_BASE_URL", "http://localhost:11434/v1/")
    model = getattr(cfg, "OLLAMA_MODEL", "qwen2.5:7b")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        client = AsyncOpenAI(base_url=base_url, api_key="ollama")
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        result_text = response.choices[0].message.content.strip()
        parsed = _parse_json(result_text)
        if parsed is None:
            logger.debug("Ollama async JSON parse failed, retrying with hint")
            retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no explanation."
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    *(([{"role": "system", "content": system}] if system else [])),
                    {"role": "user", "content": retry_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
            )
            result_text = response.choices[0].message.content.strip()
            parsed = _parse_json(result_text)
        return parsed
    except Exception as e:
        logger.warning("Ollama async LLM call failed: %s", e)
        return None


# ── OpenRouter backend ──────────────────────────────────────────────


def _chat_openrouter(
    prompt: str, system: str, max_tokens: int,
) -> dict | None:
    """Call OpenRouter model via OpenAI-compatible API (sync)."""
    from openai import OpenAI

    api_key = getattr(cfg, "OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("No OpenRouter API key — skipping LLM call")
        return None

    base_url = getattr(cfg, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = getattr(cfg, "OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        result_text = response.choices[0].message.content.strip()
        parsed = _parse_json(result_text)
        if parsed is None:
            logger.debug("OpenRouter JSON parse failed, retrying with hint")
            retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no explanation."
            response = client.chat.completions.create(
                model=model,
                messages=[
                    *(([{"role": "system", "content": system}] if system else [])),
                    {"role": "user", "content": retry_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
            )
            result_text = response.choices[0].message.content.strip()
            parsed = _parse_json(result_text)
        return parsed
    except Exception as e:
        logger.warning("OpenRouter LLM call failed: %s", e)
        return None


async def _chat_openrouter_async(
    prompt: str, system: str, max_tokens: int,
) -> dict | None:
    """Call OpenRouter model via OpenAI-compatible API (async)."""
    from openai import AsyncOpenAI

    api_key = getattr(cfg, "OPENROUTER_API_KEY", "")
    if not api_key:
        logger.warning("No OpenRouter API key — skipping LLM call")
        return None

    base_url = getattr(cfg, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = getattr(cfg, "OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        result_text = response.choices[0].message.content.strip()
        parsed = _parse_json(result_text)
        if parsed is None:
            logger.debug("OpenRouter async JSON parse failed, retrying with hint")
            retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No markdown, no explanation."
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    *(([{"role": "system", "content": system}] if system else [])),
                    {"role": "user", "content": retry_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
            )
            result_text = response.choices[0].message.content.strip()
            parsed = _parse_json(result_text)
        return parsed
    except Exception as e:
        logger.warning("OpenRouter async LLM call failed: %s", e)
        return None


# ── JSON parsing ─────────────────────────────────────────────────────


def _parse_json(text: str) -> dict | None:
    """Parse JSON from LLM response, stripping markdown fences."""
    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return {"items": result}  # Wrap list in dict for consistency
        return None
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.debug("Failed to parse JSON from LLM response: %.200s", text)
        return None
