"""Reply classification.

Deterministic rules run FIRST and are final for the two buckets that carry
legal or data consequences. An LLM must never be the thing that decides
whether somebody opted out.

Ported from the proven `_api/mms_responses.py` classifier with one change that
matters for a conversational agent: OPT_OUT and NOT_INTERESTED are separate.
The batch classifier lumped "not interested" into opt-out, which is correct
when you only ever suppress, and wrong here: a soft no is a conversation a
closer handles, a legal opt-out is one you must honor and never text again.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from . import config

# Legal opt-out. Carrier keywords plus the natural-language forms a human would
# obviously understand. In a back-and-forth, ignoring "stop texting me" because
# it was not the literal word STOP is indefensible.
OPT_OUT = [
    # Every keyword on the registered 10DLC campaign's opt-out list (smrtPhone
    # Trust Center, checked 2026-09-07): OPTOUT CANCEL END QUIT UNSUBSCRIBE
    # REVOKE STOP STOPALL. The SMS footer tells people to "Reply END", so a
    # bare keyword is the most likely form an opt-out takes.
    r"^\s*(stop|stopall|quit|end|cancel|unsubscribe|revoke|opt\s*-?\s*out)\s*[.!]*\s*$",
    r"\bstop\s+(texting|messaging|contacting|calling|sending)\b",
    r"\bunsubscribe\b",
    r"\bopt\s*-?\s*out\b",
    r"\b(remove|take|delete)\s+(me|my\s+number|this\s+number)\s+(off|from)\b",
    r"\b(remove|delete)\s+(this\s+|my\s+)?(number|me)\b",
    r"\bdo\s*n[o']?t\s+(contact|text|message|call)\s+me\b",
    r"\bdon'?t\s+(contact|text|message|call)\s+me\b",
    r"\bno\s+more\s+(texts|messages|calls)\b",
    r"\bleave\s+me\s+alone\b",
    r"\blose\s+my\s+number\b",
    r"\bnever\s+(text|contact|message)\s+me\b",
]

# A carrier keyword as its own sentence inside a longer message: "Wrong number.
# STOP", "not mine, unsubscribe". The bare-keyword rule above is anchored to the
# whole message, so these used to fall through to WRONG_NUMBER and the STOP was
# dropped on the floor (2026-09-09, 7042226408). Sentence-bounded on both sides
# so "stop by the office" and "end of story" stay clear.
OPT_OUT_EMBEDDED = [
    r"(?:^|[.!?,;\n]\s*)(?:please\s+)?(stop|stopall|quit|end|cancel|unsubscribe|revoke|opt\s*-?\s*out)"
    r"\s*[.!]*\s*(?:$|[.!?\n])",
]

# Strong signals only. A wrong-number flip writes to the CRM and permanently
# suppresses a number, so it must not fire on "I don't think so".
WRONG_NUMBER = [
    r"\bwrong\s+(number|person|guy|gal|address)\b",
    r"\byou(?:'ve| have)?\s+(?:got|have)\s+the\s+wrong\b",
    r"\bi\s+(?:do\s*n[o']?t|don'?t)\s+own\b",
    r"\bnever\s+owned\b",
    r"\bdon'?t\s+own\s+(?:that|any|a\b|this)\b",
    r"\bnot\s+my\s+(house|home|property|address)\b",
    r"\bthat'?s\s+not\s+my\b",
    r"\bnot\s+mine\b",
    r"\bno\s+(?:such\s+)?property\b",
    r"\bi\s+don'?t\s+have\s+(?:a|any)\s+(?:house|home|property)\b",
    r"\bi'?m\s+not\b.*\b(the\s+owner|that\s+person)\b",
    r"\bwho(?:'s| is)\s+that\b.*\bnot\s+me\b",
    # The text opens "Hi <owner name>", so the tell that we reached the wrong
    # person is them asking about that name in the third person, or denying it
    # outright. Both landed unclassified on live threads (2026-08-11):
    # "Who the hell is Jonathan" and "this ain't joseph."
    # The lookahead keeps "who is this" as ASKING_WHO: asking who WE are is a
    # normal question from the right person, and must not disposition a good
    # number as wrong.
    r"\bwho(?:'s|\s+is|\s+the\s+(?:hell|heck|f\w*)\s+is)\s+(?!this\b|that\b|it\b|there\b)[a-z]{3,}\b",
    r"\b(?:this|that)\s+(?:ain'?t|is\s*n[o']?t|isn'?t)\s+(?!my\b|the\b|a\b)[a-z]{3,}\b",
    r"\bno\s*(?:one|body)\s+here\s+by\s+that\s+name\b",
    r"\bthere'?s\s+no\s+\w+\s+here\b",
]

# Soft no. Handled by a closer, not by suppression.
NOT_INTERESTED = [
    r"\bnot\s+interested\b",
    r"\bno\s+thanks?\b",
    r"\bnot\s+(selling|for\s+sale)\b",
    r"\bi'?m\s+good\b",
    r"\bnot\s+at\s+this\s+time\b",
    r"\bnot\s+right\s+now\b",
    r"\balready\s+(sold|listed|under\s+contract)\b",
    r"\bhave\s+an?\s+(agent|realtor)\b",
]

# Retention language: they are telling you they intend to KEEP the house.
#
# This exists because of a real miss (Jessica, 6956 Cardindale, 2026-08-11).
# Touch 1 asks an ownership question, so a reply often answers two questions at
# once: "It is. And it's staying that way." The first half confirms the number,
# the second half is the actual answer, and the classifier read only the first
# and paged the prospector on a homeowner who had just declined.
#
# Ty's read: mark the phone CORRECT and close it as not interested. Someone
# saying "it's staying that way" is expressing attachment to the house, and
# calling them as a hot lead is the fastest way to burn a number that a
# patient follow-up could still convert later.
KEEPING_IT = [
    r"\b(stay|stays|staying)\s+that\s+way\b",
    r"\bnot\s+going\s+anywhere\b",
    r"\b(plan|planning|plans|intend|want)\s+(on\s+|to\s+)?keep(ing)?\b",
    r"\b(keeping|gonna\s+keep|going\s+to\s+keep|will\s+keep)\s+(it|the\s+(house|property|home))\b",
    r"\bstay(s|ing)?\s+in\s+the\s+family\b",
    r"\b(never|not|won'?t|will\s+not)\s+(be\s+)?(going\s+to\s+|gonna\s+)?sell(ing)?\b",
    r"\bit'?s\s+not\s+for\s+sale\b",
]

# Confirming the number is right is NOT a signal about selling. Touch 1 asks
# "is <street> yours?", so these answer THAT question and nothing more.
OWNER_CONFIRMED = [
    r"^\s*(yes|yeah|yep|yup|correct|it\s+is|that'?s\s+(right|correct|me|mine)|sure\s+is)\b",
    r"^\s*(i|we)\s+(do|am|own\s+it)\b",
    r"\b(that|it)\s+is\s+(my|our)\s+(house|property|home|address)\b",
]

INTERESTED = [
    r"\binterested\b",
    r"\bhow\s+much\b",
    r"\bwhat'?s\s+(the|your)\s+offer\b",
    r"\bmake\s+an?\s+offer\b",
    r"\bcall\s+me\b",
    r"\btell\s+me\s+more\b",
    r"\bi\s+need\s+help\b",
    r"\bhow\s+can\s+you\s+help\b",
    r"\bwhat\s+can\s+you\s+do\b",
    r"\bwhat\s+do\s+you\s+(offer|do)\b",
    r"\bwhat\s+are\s+you\s+(offering|thinking)\b",
    r"\bcash\s+offer\b",
    r"\bdepends\s+on\s+the\s+(price|number|offer)\b",
]

ASKING_WHO = [
    r"\bwho\s+(is|'?s|are\s+you|dis|this)\b",
    r"\bwhat\s+is\s+this\b",
    r"\bwhat'?s\s+this\b",
    r"\bwhat\s+are\s+you\s+talking\b",
    r"\bhow\s+did\s+you\s+get\b",
    r"\bwhere\s+did\s+you\s+get\b",
    r"\bwhat\s+(property|address|house)\b",
    r"\bnew\s+phone\b",
    r"\bis\s+this\s+a\s+(bot|scam|robot)\b",
]

# Anything here forces a human regardless of what else matched. These are the
# situations where a wrong word from an automated system does real damage.
ESCALATE_NOW = [
    r"\b(lawyer|attorney|sue|suing|legal\s+action|cease\s+and\s+desist)\b",
    r"\b(passed\s+away|died|deceased|funeral|in\s+hospice)\b",
    r"\b(bankrupt|bankruptcy|chapter\s+(7|13))\b",
    r"\bauction\s+is\s+(today|tomorrow)\b",
    r"\b(harass|harassment|report\s+you|fcc|attorney\s+general)\b",
]

INTENTS = (
    "OPT_OUT",
    "WRONG_NUMBER",
    "INTERESTED",
    "NOT_INTERESTED",
    "ASKING_WHO",
    "ESCALATE",
    "OTHER",
    "EMPTY",
)


@dataclass
class Classification:
    intent: str
    confidence: float
    source: str  # rules | llm | fallback
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "rationale": self.rationale,
        }


def _hit(text: str, patterns: list[str]) -> Optional[str]:
    for p in patterns:
        if re.search(p, text):
            return p
    return None


def _hit_text(text: str, patterns: list[str]) -> Optional[str]:
    """Like `_hit`, but returns the words that matched rather than the regex.

    For anything a human reads: a Slack line saying they also said 'lose my
    number' is useful, one quoting `\\blose\\s+my\\s+number\\b` is not.
    """
    for p in patterns:
        m = re.search(p, text)
        if m:
            return " ".join(m.group(0).split()).strip(" .!?,;")
    return None


def price_in(text: str, strict: bool = False) -> float:
    """A price the owner named in their own message, or 0.0.

    Bare numbers count: sellers write "350,000" far more often than "$350,000"
    (Mark Pilkington, 401 W 1St St, 2026-08-22). A bare 4-digit number is a
    year or a house number far more often than a price ("built in 1962"), so it
    only counts when the writer marked it as money -- a dollar sign, a thousands
    comma, a k suffix -- or when it is too large to be either.

    `strict` is for decisions rather than display. Unmarked 5-digit numbers are
    ZIP codes and house numbers ("I'm in 28027", "12345 Main St"); showing one
    as an ask beside an estimate is a cosmetic miss, but letting it turn a
    wrong-number into a hot lead is not. Strict requires the money marker or
    six figures.
    """
    best = 0.0
    for m in re.finditer(r"(\$)?\s?(\d[\d,]*)\s*([kK])?", text or ""):
        dollar, raw, kilo = m.group(1), m.group(2).rstrip(","), m.group(3)
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            continue
        if kilo:
            n *= 1000
        # A comma marks money only as a thousands separator ("335,000"), not
        # as the punctuation after a year ("built in 1962, stop texting me").
        grouped = bool(re.fullmatch(r"\d{1,3}(,\d{3})+", raw))
        marked = bool(dollar) or grouped or bool(kilo)
        if not marked and n < (100_000 if strict else 10_000):
            continue
        if 1000 <= n <= 100_000_000:
            best = max(best, n)
    return best


def fmt_money(n: float) -> str:
    return f"${round(n):,}" if n else ""


def opt_out_signal(text: str) -> Optional[str]:
    """The opt-out phrase in this message, if there is one, in the writer's words.

    Used where an opt-out arrives alongside something else -- a price, a
    wrong-number -- and the message is routed on the something else, so the
    request to stop must be carried along rather than lost.
    """
    t = (text or "").strip().lower()
    return _hit_text(t, OPT_OUT) or _hit_text(t, OPT_OUT_EMBEDDED)


def classify_rules(text: str) -> Optional[Classification]:
    """Deterministic pass. Returns None when nothing fires with confidence."""
    t = (text or "").strip().lower()
    if not t:
        return Classification("EMPTY", 1.0, "rules")

    hit = _hit(t, ESCALATE_NOW)
    if hit:
        return Classification("ESCALATE", 1.0, "rules", f"sensitive: {hit}")

    # A named price beats a terminal phrase. "$335,000.00. Cash and if not
    # interested lose my number" (2026-09-10, 7046785412) is a seller making an
    # offer with a condition on it, and the rules read only the condition:
    # OPT_OUT, DNC written to the CRM, never shown to a person. A price is the
    # one thing a human must judge every time (see escalate._asking_price), so
    # it goes to the hot-lead post with the condition carried along in the
    # rationale and on the post itself. Deliberately narrow: a price with no
    # terminal phrase still goes to the model as before, because "I sold it
    # last year for 200k" is a no. A carrier keyword standing as its own
    # sentence (OPT_OUT_EMBEDDED) is not overridden -- that is the registered
    # opt-out and it wins regardless of what else the message says.
    price = price_in(text, strict=True)
    if price and not _hit(t, OPT_OUT_EMBEDDED):
        also = _hit_text(t, OPT_OUT) or _hit_text(t, WRONG_NUMBER) or _hit_text(t, KEEPING_IT)
        if also:
            return Classification(
                "INTERESTED", 0.7, "rules",
                f"names a price ({fmt_money(price)}); also says '{also}' - honor that if you pass",
            )

    hit = _hit(t, OPT_OUT) or _hit(t, OPT_OUT_EMBEDDED)
    if hit:
        return Classification("OPT_OUT", 1.0, "rules", f"opt-out: {hit}")
    hit = _hit(t, WRONG_NUMBER)
    if hit:
        return Classification("WRONG_NUMBER", 0.95, "rules", f"wrong-number: {hit}")

    # Decided here rather than by the model, because the model already got this
    # wrong once: an ownership confirmation sitting in front of a refusal read
    # as enthusiasm. Whoever confirms and then says the house is staying put has
    # answered, and the answer is no.
    hit = _hit(t, KEEPING_IT)
    if hit:
        return Classification(
            "NOT_INTERESTED", 0.9, "rules",
            f"soft no, intends to keep the property: {hit}",
        )
    return None


SYSTEM = """You classify one inbound SMS from a property owner replying to a real estate acquisition text.

Return exactly one intent:
- INTERESTED: engages about selling, asks price/offer/process, asks to be called, says yes, or gives any opening.
- NOT_INTERESTED: a soft no. Not selling, already listed, has an agent, "no thanks". This is NOT a legal opt-out.
- WRONG_NUMBER: says they are not the owner, do not own the property, or the number belongs to someone else - but NOT when they say they are a relative of the owner (sibling, child, spouse, parent) or that the property belonged to a family member. A relative is a lead, not a wrong number: label that OTHER.
- ASKING_WHO: does not know who is texting or how you got their info, asks what property, or asks if this is a bot or a scam.
- ESCALATE: mentions a lawyer, a death, bankruptcy, harassment, a regulator, or anything a human must handle personally.
- OTHER: anything that fits none of the above.

Rules:
- Judge only this message in the context of the thread. Do not infer motivation that is not there.
- The first text asks whether an address belongs to them. So "yes", "it is", "correct", "that's mine" answer the OWNERSHIP question. Confirming ownership is not a signal about selling, and on its own it is OTHER, never INTERESTED.
- When a reply confirms ownership AND says anything about keeping the house ("it is, and it's staying that way", "yes, but I'm not selling", "that's mine and I plan to keep it"), the second half is the answer. Label it NOT_INTERESTED. The confirmation only tells you the phone number is right.
- INTERESTED needs a signal about SELLING: a price question, an opening, a request to be called, a reason they might move. Attachment to the house is the opposite of that signal.
- If the message could plausibly be two intents, pick the more conservative one (ESCALATE over INTERESTED, ASKING_WHO over INTERESTED, NOT_INTERESTED over INTERESTED) and lower your confidence.
- confidence is your honest probability that a careful human would assign the same label. Do not inflate it.
- Never label a message OPT_OUT. Opt-outs are decided before you see the message."""

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["INTERESTED", "NOT_INTERESTED", "WRONG_NUMBER", "ASKING_WHO", "ESCALATE", "OTHER"],
        },
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["intent", "confidence", "rationale"],
    "additionalProperties": False,
}


def classify_llm(text: str, history: Optional[list[dict]] = None) -> Classification:
    if not config.ANTHROPIC_API_KEY:
        return Classification("OTHER", 0.0, "fallback", "no ANTHROPIC_API_KEY")
    try:
        import anthropic
    except ImportError:
        return Classification("OTHER", 0.0, "fallback", "anthropic SDK not installed")

    convo = ""
    for m in (history or [])[-8:]:
        who = "OWNER" if m.get("direction") == "in" else "US"
        convo += f"{who}: {m.get('body', '')}\n"

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_TOKENS,
            system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": f"Thread so far:\n{convo or '(none)'}\n\nClassify this new inbound message:\n{text}",
                }
            ],
        )
    except Exception as exc:  # network, rate limit, refusal-adjacent
        return Classification("OTHER", 0.0, "fallback", f"llm error: {exc}"[:200])

    if getattr(resp, "stop_reason", "") == "refusal":
        return Classification("OTHER", 0.0, "fallback", "model refused")

    body = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return Classification("OTHER", 0.0, "fallback", "unparseable model output")

    conf = float(data.get("confidence", 0.0))
    return Classification(
        data.get("intent", "OTHER"),
        max(0.0, min(1.0, conf)),
        "llm",
        str(data.get("rationale", ""))[:300],
    )


# ---- the guard on the model's answer -----------------------------------------
#
# The model is asked to be conservative (NOT_INTERESTED over INTERESTED when in
# doubt), and with REPLY_TO_NO off a NOT_INTERESTED closes the thread with no
# human look. Two live misses on 2026-09-10 came out of that pairing:
# "How much?... it's a 1989 mobile home with a somewhat new metal roof" closed
# as NOT_INTERESTED 0.65, and "Perhaps at some point" closed at 0.65 with no
# follow-up. A weak no that is really a question or a maybe goes to a person.
#
# A price question is always a lead.
PRICE_QUESTION = re.compile(
    r"\bhow\s+much\b|\bwhat(?:'s|\s+is|\s+are|\s+would|\s+do)?\b[^.?!]{0,40}\b(offer|price|pay|paying)\b|\$\s?\d",
    re.I,
)
# A maybe, a deferral, or a question: worth a human-approved reply, not a close.
WEAK_NO = re.compile(
    r"\?|\bmaybe\b|\bperhaps\b|\bsome\s+point\b|\blater\b|\bnot\s+right\s+now\b|\bnot\s+(?:yet|now)\b"
    r"|\btry\s+(?:me\s+)?(?:back|again)\b|\bin\s+a\s+(?:few|couple)\b|\bdown\s+the\s+road\b"
    r"|\bnext\s+(?:year|month|spring|summer|fall|winter)\b|\bcheck\s+back\b|\bpossibly\b",
    re.I,
)
# A plain no. The model puts these at 0.70-0.75 as often as at 0.90 ("No",
# "No bruh", "Sold" -- five of them on 2026-09-10 alone), and turning each
# into a held draft would spend the person's morning dismissing them.
BARE_NO = re.compile(
    r"^\W*(?:no+|nope|nah|naw|sold|no\s+thanks?|no\s+thank\s+you|not\s+interested|not\s+for\s+sale|pass)"
    r"(?:[\s,.!]+(?:thanks?|thank\s+you|sir|ma'?am|bruh|bro|man|dude|sorry|please|ty))?\W*$",
    re.I,
)
# A relative answering. The model is told "not the owner = WRONG_NUMBER", and
# there was no relative anywhere in its vocabulary, so "My name is Lisa Dana
# is my sister it's my mom's house" (7046748532, 2026-09-10) was suppressed
# for good. In an estate business the sibling who picks up IS the lead.
FAMILY = re.compile(
    r"\b(?:sister|brother|mom|mother|dad|father|son|daughter|husband|wife|aunt|uncle|cousin"
    r"|niece|nephew|grand(?:ma|pa|mother|father|son|daughter|parents?)|in[- ]laws?|late\s+(?:husband|wife)"
    r"|passed(?:\s+away)?|(?<!real\s)estate|executor|executrix|administrator|administratrix|heirs?|inherited)\b",
    re.I,
)
# A firm no in more words. Hostile, or a settled fact. Never drafted at.
FIRM_NO = re.compile(
    r"\bf+u+c+k|\bpiss\s+off\b|\bget\s+lost\b|\bgo\s+away\b|\bscrew\s+you\b|\bhell\s+no\b|\babsolutely\s+not\b"
    r"|\balready\s+(?:sold|listed|under\s+contract)\b|\bsold\s+it\b|\b(?:was|been|is)\s+sold\b"
    r"|\bnot\s+for\s+sale\b|\bhave\s+an?\s+(?:agent|realtor)\b|\bnot\s+interested\b",
    re.I,
)


def guard_llm(text: str, c: Classification) -> Classification:
    """Second-guess the model only where a wrong answer closes a door silently.

    Only a model answer is guarded (`source == "llm"`); a rules answer is
    authoritative and never comes through here. A guarded answer carries
    source "guard" so the log and the backfill report show it happened.
    """
    if c.source != "llm":
        return c
    t = (text or "").strip()

    if c.intent == "WRONG_NUMBER":
        fam = FAMILY.search(t)
        if fam:
            return Classification(
                "OTHER", 0.6, "guard",
                f"relative answered ('{fam.group(0)}') - a person decides; model said WRONG_NUMBER "
                f"{c.confidence:.2f}: {c.rationale}"[:300],
            )
        return c

    if c.intent == "NOT_INTERESTED":
        if BARE_NO.search(t) or FIRM_NO.search(t):
            return c
        if PRICE_QUESTION.search(t):
            return Classification(
                "INTERESTED", 0.7, "guard",
                f"asked for a price; model said NOT_INTERESTED {c.confidence:.2f}: {c.rationale}"[:300],
            )
        weak = WEAK_NO.search(t)
        if weak or c.confidence < 0.80:
            why = f"'{weak.group(0)}'" if weak else f"confidence {c.confidence:.2f}"
            return Classification(
                "OTHER", 0.6, "guard",
                f"soft/maybe ({why}) - a person decides; model said NOT_INTERESTED: {c.rationale}"[:300],
            )
    return c


def classify_rules_wrong_number(text: str) -> bool:
    """Does this message also carry a wrong-number signal?

    Used when an opt-out and a wrong number arrive in the same sentence, so the
    phone gets marked WRONG for the callers as well as suppressed for texting.
    """
    return bool(_hit((text or "").strip().lower(), WRONG_NUMBER))


def classify(text: str, history: Optional[list[dict]] = None) -> Classification:
    """Rules first, model second. The rules pass is authoritative when it fires."""
    ruled = classify_rules(text)
    if ruled is not None:
        return ruled

    llm = classify_llm(text, history)
    if llm.source == "llm" and llm.confidence >= 0.5:
        return guard_llm(text, llm)

    # Model unavailable or unsure. Fall back to the weak keyword buckets, which
    # only ever route to a human anyway.
    t = (text or "").strip().lower()
    for patterns, intent in (
        (NOT_INTERESTED, "NOT_INTERESTED"),
        (INTERESTED, "INTERESTED"),
        (ASKING_WHO, "ASKING_WHO"),
    ):
        hit = _hit(t, patterns)
        if hit:
            return Classification(intent, 0.6, "rules", f"keyword: {hit}")
    return Classification("OTHER", 0.3, llm.source, llm.rationale or "no signal")
