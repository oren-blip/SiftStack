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
ALWAYS_POST = {"handoff", "campaign", "needs_reply", "followup"}

RECORD_URL = "https://app.reisift.io/records/properties/{uuid}/details"


def _is_discord(url: str) -> bool:
    return "discord.com" in (url or "")


def _post_api(text: str, blocks: Optional[list] = None) -> bool:
    """Post as the bot rather than through the webhook.

    Required for buttons: a webhook message has no identity we can come back
    to, and `chat.update` needs the channel + ts that only chat.postMessage
    hands back. Slack answers HTTP 200 with {"ok": false} on a refusal, so the
    status code alone is not the check.
    """
    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            json={
                "channel": config.SLACK_CHANNEL,
                "text": text,
                **({"blocks": blocks} if blocks else {}),
            },
            headers={"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"},
            timeout=15,
        )
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("slack chat.postMessage failed: %s", exc)
        return False
    if not body.get("ok"):
        # invalid_auth / channel_not_found / not_in_channel are the three that
        # actually happen, and all three are setup mistakes worth naming.
        log.warning("slack chat.postMessage refused: %s", body.get("error"))
        return False
    return True


def _post(text: str, blocks: Optional[list] = None) -> bool:
    if config.slack_buttons_enabled():
        return _post_api(text, blocks)
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
    # Clear it from the phone: "Got it" records who took it, "Not a lead"
    # closes it out. Both local-only; the CRM is untouched either way (Oren,
    # 2026-09-07). Same rule as drafts -- no buttons without a listener.
    if config.slack_listener_ready():
        blocks.append(hot_lead_buttons(phone, record_uuid))
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

    # Buttons when a tap can actually reach this machine, typed commands when
    # it cannot. Never buttons without a listener: a button that silently does
    # nothing is worse than no button, because it looks handled.
    if config.slack_listener_ready():
        text = "\n".join(lines)
        return _post(text, [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            action_buttons(phone, record_uuid),
        ])

    # Both commands, as one copy-paste block. `approve` only moves the draft
    # into the queue; `work` is the only thing that sends, and it is the step
    # that got forgotten -- 13 drafts sat approved-but-unsent for four days
    # (Oren, 2026-09-06) because the post named the first half of the job only.
    # Two lines rather than one chained line on purpose: this is pasted into
    # PowerShell, where `&&` is a parser error.
    lines.append("Approve and send - paste all three lines:")
    lines.append(
        "```\ncd {root}\npython src/sms_agent/cli.py approve {ph}\n"
        "python src/sms_agent/cli.py work\n```".format(
            root=config.ROOT, ph=store.clean_phone(phone)
        )
    )
    text = "\n".join(lines)
    return _post(text, [{"type": "section", "text": {"type": "mrkdwn", "text": text}}])


# The four answers a draft can get. Kept here beside the post that renders them
# so a new button cannot be added without deciding what it does: the listener
# refuses an action_id it does not recognise.
ACTIONS = {
    "sms_approve": "Approve & send",
    "sms_handle": "I'll handle it",
    "sms_not_lead": "Not a lead",
    "sms_wrong": "Wrong number",
    "sms_got_it": "Got it",
}
DRAFT_ACTIONS = ("sms_approve", "sms_handle", "sms_not_lead", "sms_wrong")
LEAD_ACTIONS = ("sms_got_it", "sms_not_lead")


def _button(action_id: str, value: str, style: str = "", confirm: str = "") -> dict:
    el = {
        "type": "button",
        "action_id": action_id,
        "text": {"type": "plain_text", "text": ACTIONS[action_id]},
        "value": value,
    }
    if style:
        el["style"] = style
    if confirm:
        el["confirm"] = {
            "title": {"type": "plain_text", "text": ACTIONS[action_id]},
            "text": {"type": "mrkdwn", "text": confirm},
            "confirm": {"type": "plain_text", "text": "Yes"},
            "deny": {"type": "plain_text", "text": "Cancel"},
        }
    return el


def _value(phone: str, record_uuid: str) -> str:
    # `value` carries everything the handler needs, because a Slack payload
    # arrives with no memory of what was posted and looking it up again by
    # channel+ts would be a second failure point.
    return json.dumps({"phone": store.clean_phone(phone), "uuid": record_uuid})[:1900]


def action_buttons(phone: str, record_uuid: str = "") -> dict:
    """The actions block under a draft.

    Approve and Wrong number confirm first. These get tapped on a phone, where
    a mis-tap is a text to a stranger or a suppressed number, and neither is
    reversible from the channel.
    """
    ph = store.clean_phone(phone)
    value = _value(ph, record_uuid)
    return {
        "type": "actions",
        "block_id": f"sms_draft:{ph}",
        "elements": [
            _button("sms_approve", value, "primary",
                    f"Text {_fmt_phone(ph)} the message above, right now?"),
            _button("sms_handle", value),
            _button("sms_not_lead", value),
            _button("sms_wrong", value, "danger",
                    f"Stop texting {_fmt_phone(ph)} for good? This cannot be undone from Slack."),
        ],
    }


def hot_lead_buttons(phone: str, record_uuid: str = "") -> dict:
    """The actions block under a hot-lead handoff. Two answers, no sending."""
    ph = store.clean_phone(phone)
    value = _value(ph, record_uuid)
    return {
        "type": "actions",
        "block_id": f"sms_lead:{ph}",
        "elements": [
            _button("sms_got_it", value, "primary"),
            _button("sms_not_lead", value),
        ],
    }


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
