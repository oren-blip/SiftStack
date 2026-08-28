"""Prospector handoff.

Posts to the Slack (or Discord) channel the prospectors watch. Self-contained
rather than importing src/slack_notifier.py so the receiver can be deployed on
its own without the rest of the repo.

A note on the ceiling here: an incoming webhook can only post a message. If you
want the prospector to hit "I've got this" / "not a lead" / "wrong number" from
the channel and have that write back to the CRM, that needs a real Slack app
with interactive components, not a webhook URL. This module is deliberately
shaped so that upgrade is a swap of `_post`, not a rewrite.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

import requests

from . import config, store

log = logging.getLogger(__name__)

# The only alert kinds allowed to reach the channel. A live seller, and the
# daily campaign summary that was explicitly asked for. Everything else is
# bookkeeping and belongs in the digest.
ALWAYS_POST = {"handoff", "campaign", "needs_reply"}

RECORD_URL = "https://app.reisift.io/records/properties/{uuid}/details"


def _is_discord(url: str) -> bool:
    return "discord.com" in (url or "")


def _post(text: str, blocks: Optional[list] = None) -> bool:
    url = config.SLACK_WEBHOOK_URL
    if not url:
        log.warning("no SMS_AGENT_SLACK_WEBHOOK configured; escalation not delivered")
        return False
    payload: dict = {"text": text}
    if blocks and not _is_discord(url):
        payload["blocks"] = blocks
    try:
        resp = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        log.warning("escalation post failed: %s", exc)
        return False
    if resp.status_code >= 300:
        log.warning("escalation post failed: HTTP %s %s", resp.status_code, resp.text[:160])
        return False
    return True


def _fmt_phone(p: str) -> str:
    d = store.clean_phone(p)
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else p


def _fmt_money(value) -> str:
    """"$205,000" from whatever the CRM stored. Empty when it is not a number."""
    if value in (None, "", 0):
        return ""
    try:
        return f"${round(float(str(value).replace('$', '').replace(',', ''))):,}"
    except (TypeError, ValueError):
        return ""


def _is_vacant_land(ctx: dict) -> bool:
    """Is this raw land rather than a house?

    Matters because DataSift stamps a house-style `estimate_value` on vacant
    parcels and it is wildly wrong. 175 Organ Church Rd, Rockwell (Rowan, 1.03
    ac) carried $255,000; LandPortal's read on the same parcel was $69,196 with
    comps of $59.5K-$75K. Showing the $255,000 beside a $100,000 ask made an
    over-ask look like a bargain, which is worse than showing nothing.

    Two signals, either one is enough: the record says so, or it has a lot size
    and no dwelling at all.
    """
    st = str(ctx.get("structure_type") or "").lower()
    if "vacant land" in st or st.endswith("land") or "lot" in st:
        return True
    has_dwelling = any(ctx.get(k) for k in ("beds", "baths", "sqft"))
    return bool(ctx.get("lot_size")) and not has_dwelling


def _land_value(ctx: dict) -> Optional[dict]:
    """LandPortal's market read on a vacant parcel, or None. Never raises.

    DataSift's `estimate_value` is a dwelling number and is useless on raw land
    (see `_is_vacant_land`), so this is where a land ask gets something true to
    be measured against.

    Cost discipline matters here and is mostly handled inside the module: parcel
    search is effectively free, but `/property-data` allows ~10 calls a day
    before it draws on subscription export tokens, of which this account has
    none. `landportal_lookup` caches every result to disk, caches misses too,
    and latches on a 403 so an exhausted quota is not hammered. On top of that
    we only reach here for a hot lead that is also vacant land, which was 1 of
    90 records in the call queue. NC counties only — it returns None elsewhere.
    """
    parcel = str(ctx.get("parcel_id") or "").strip()
    county = str(ctx.get("county") or "").strip()
    if not parcel or not county:
        return None
    try:
        src = str(Path(__file__).resolve().parent.parent)
        if src not in sys.path:
            sys.path.insert(0, src)
        import landportal_lookup  # type: ignore
    except ImportError as exc:
        log.info("LandPortal unavailable: %s", exc)
        return None
    try:
        return landportal_lookup.get_vacant_market_value(parcel, county)
    except Exception as exc:  # noqa: BLE001 - a valuation must never block a handoff
        log.warning("LandPortal lookup failed for %s/%s: %s", county, parcel, exc)
        return None


def _asking_price(text: str) -> str:
    """A price the owner named in their own message, if they named one.

    Put beside the estimate so an over-ask is obvious without opening the
    record. Mark Pilkington (401 W 1St St, 2026-08-22) said "it can be yours for
    350,000"; the post carried beds and baths but no value, so triaging it meant
    going to look. Bare numbers count: sellers write "350,000" far more often
    than "$350,000".
    """
    best = 0.0
    for m in re.finditer(r"(\$)?\s?(\d[\d,]*)\s*([kK])?", text or ""):
        dollar, raw, kilo = m.group(1), m.group(2), m.group(3)
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            continue
        if kilo:
            n *= 1000
        # A bare 4-digit number is a year or a house number far more often than
        # a price ("built in 1962", "1998 flood"). Only count it when the writer
        # marked it as money -- a dollar sign, a thousands comma, a k suffix --
        # or when it is too large to be either.
        marked = bool(dollar) or "," in raw or bool(kilo)
        if not marked and n < 10_000:
            continue
        if 1000 <= n <= 100_000_000:
            best = max(best, n)
    return _fmt_money(best) if best else ""


def hot_lead(
    phone: str,
    inbound: str,
    intent: str,
    context: Optional[dict] = None,
    thread: Optional[list[dict]] = None,
    record_uuid: str = "",
    note: str = "",
) -> bool:
    """The one that matters: a positive response needs a human on it now."""
    ctx = context or {}
    who = ctx.get("owner_first") or "Unknown owner"
    where = ", ".join(x for x in (ctx.get("street"), ctx.get("city"), ctx.get("state")) if x)

    mention = f"<@{config.HANDOFF_SLACK_ID}> " if config.HANDOFF_SLACK_ID else ""
    lines = [
        f"{mention}*{config.HANDOFF_NAME}: yours. Call within 5 minutes.*",
        f"*Positive SMS reply - {who}*",
        f"{_fmt_phone(phone)}" + (f"  {where}" if where else ""),
        f"> {inbound.strip()[:400]}",
    ]

    # The triage line. Their ask against our estimate, so an over-priced reply
    # can be killed from Slack without opening the record.
    est = _fmt_money(ctx.get("estimated_value"))
    ask = _asking_price(inbound)
    if _is_vacant_land(ctx):
        # Never quote a house estimate on raw land: a wrong comparison is worse
        # than none, because it inverts the decision. LandPortal is the honest
        # number here; when it cannot answer we say so rather than substituting
        # DataSift's.
        lp = _land_value(ctx)
        acres = (lp or {}).get("acres") or ctx.get("lot_size")
        what = f"VACANT LAND{f', {acres:g} ac' if isinstance(acres, (int, float)) else ''}"
        land_est = _fmt_money((lp or {}).get("tlp_estimate"))
        if land_est:
            county_val = _fmt_money((lp or {}).get("county_value"))
            tail = f" (county {county_val})" if county_val else ""
            lines.append(
                f"*Asking {ask}*  vs LandPortal {land_est}  -  {what}{tail}"
                if ask else f"{what} - LandPortal {land_est}{tail}"
            )
        else:
            lines.append(
                f"*Asking {ask}*  -  {what}, no reliable estimate (check LandPortal)"
                if ask else f"{what} - DataSift estimate does not apply to raw land"
            )
    elif est and ask:
        lines.append(f"*Asking {ask}*  vs est. value {est}")
    elif est:
        lines.append(f"Est. value {est}")
    elif ask:
        lines.append(f"*Asking {ask}*  (no estimate on the record)")

    detail = []
    for key, label in (
        ("beds", "bd"),
        ("baths", "ba"),
        ("sqft", "sqft"),
        ("year_built", "built"),
    ):
        if ctx.get(key):
            detail.append(f"{ctx[key]} {label}")
    if ctx.get("vacant"):
        detail.append("vacant")
    if detail:
        lines.append(", ".join(detail))
    lines.append(f"Read: *{intent}*" + (f" - {note}" if note else ""))
    if record_uuid:
        lines.append(RECORD_URL.format(uuid=record_uuid))

    text = "\n".join(lines)
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]
    if thread:
        convo = "\n".join(
            f"{'them' if m.get('direction') == 'in' else 'us'}: {m.get('body', '')}"
            for m in thread[-6:]
        )
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"```{convo[:2500]}```"}]}
        )
    return _post(text, blocks)


def draft_for_approval(
    phone: str,
    inbound: str,
    proposed: str,
    confidence: float,
    reason: str = "",
    record_uuid: str = "",
    blocked: Optional[list[str]] = None,
) -> bool:
    """Phase 3: every reply goes here before anything is sent."""
    lines = [
        f"*Draft reply - {_fmt_phone(phone)}* (confidence {confidence:.0%})",
        f"> them: {inbound.strip()[:300]}",
        f"> us:   {proposed.strip()[:300]}" if proposed else "> us:   (nothing proposed)",
    ]
    if reason:
        lines.append(f"_{reason}_")
    if blocked:
        lines.append(f":warning: blocked by validator: {', '.join(blocked)}")
    if record_uuid:
        lines.append(RECORD_URL.format(uuid=record_uuid))
    lines.append(f"Approve with: `python src/sms_agent/cli.py approve {store.clean_phone(phone)}`")
    text = "\n".join(lines)
    return _post(text, [{"type": "section", "text": {"type": "mrkdwn", "text": text}}])


def alert(title: str, detail: str = "", record_uuid: str = "", kind: str = "ops") -> bool:
    """Something a human should see that is not itself a lead.

    The channel is for interested parties (Ty, 2026-08-11). Opt-out bookkeeping
    was posting there and burying the only messages that matter: a prospector
    who scrolls past four housekeeping notes stops reading the fifth, and the
    fifth is the seller. Anything not on ALWAYS_POST is logged and left for the
    digest instead of being posted.

    `kind="campaign"`, `kind="handoff"`, and `kind="needs_reply"` are the
    exceptions: the daily "here is what went out" that was explicitly asked
    for, a live seller, and a live thread waiting on a human answer.
    """
    if config.SLACK_INTERESTED_ONLY and kind not in ALWAYS_POST:
        log.info("slack suppressed (%s): %s | %s", kind, title, detail[:200])
        store.set_meta(f"last_notice_{kind}", f"{title} :: {detail[:300]}")
        return True

    text = f"*{title}*" + (f"\n{detail}" if detail else "")
    if record_uuid:
        text += f"\n{RECORD_URL.format(uuid=record_uuid)}"
    return _post(text, [{"type": "section", "text": {"type": "mrkdwn", "text": text}}])


def unknown_number(phone: str, inbound: str) -> bool:
    """Somebody texted a pool number and we have no record for them.

    Worth surfacing rather than dropping: it is usually a reply from a second
    line on a record we already know, or a referral.
    """
    return alert(
        f"Inbound from an unmapped number - {_fmt_phone(phone)}",
        f"> {inbound.strip()[:400]}\n_No record mapped to this number; nothing was sent._",
    )
