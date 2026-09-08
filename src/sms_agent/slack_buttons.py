"""Slack buttons for draft approval, over Socket Mode.

Why this exists: an incoming webhook can only post. Oren reads the channel on
his phone, and the answer to "what do I do with this?" was "walk to the desktop
and paste three lines" -- which is why thirteen drafts sat unsent for four days
(2026-09-06). A tap has to be able to do the whole job.

Why Socket Mode rather than a URL: Slack normally delivers a button click to an
HTTPS endpoint, which would mean a public host -- the Fly box, and with it the
JWT-refresh problem that needs Playwright and so cannot run headless. Socket
Mode inverts it. This process dials OUT to Slack and holds a websocket open, so
clicks arrive on a machine with no public address, no tunnel, and no inbound
firewall rule. The desktop already runs the ten-minute poll; it can hold this
too.

The handlers deliberately do exactly what the typed commands do, by calling the
same store/worker functions. A button that took a shortcut would be a second
implementation of the send rules, and the send rules are the safety model.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Optional

import requests

from . import config, escalate, store, worker

log = logging.getLogger(__name__)

# Slack gives an interactive app 3 seconds to acknowledge before it retries and
# then shows the user an error. Draining the outbox can take longer than that,
# so every path here acks FIRST and works second. A retry that slipped through
# would re-run the handler, which is why each one is written to be harmless
# twice: approve finds no held row the second time, the rest are idempotent.
ACK_FIRST = True

# One sender at a time. A tap and the clock below can both reach drain_outbox,
# and the per-number daily cap is a read-then-write.
_send_lock = threading.Lock()

# How often the listener re-checks the outbox for approved rows whose send
# window has opened. Found on the first live tap (2026-09-06, 11:33pm): approve
# correctly queued the draft for 8am, and then nothing in the system would ever
# look at the outbox again until the next tap. The 10-minute poll never sends
# by design; the listener is the one always-on process, so the clock lives here.
# Only `queued` rows are ever due -- a held draft still needs a human.
DRAIN_INTERVAL_SECONDS = 60


# How often the listener reads the smrtPhone SMS log for new replies. The
# 10-minute Task Scheduler poll did this before; Oren asked for 60s on 9/7 so a
# "yes" reaches Slack in about a minute rather than up to ten. Reading needs
# only the browser session cookies, no API token. 0 disables it (and then the
# poll task has to be re-enabled, or nothing reads inbound at all).
INBOUND_INTERVAL_SECONDS = int(config._env("SMS_AGENT_INBOUND_INTERVAL", "60"))

# Roughly hourly proof-of-life in the log, so "is it still running?" has an
# answer without waiting for a reply to arrive.
HEARTBEAT_EVERY_CYCLES = 60

_inbound_lock = threading.Lock()


def _drain() -> dict:
    with _send_lock:
        return worker.drain_outbox(limit=25)


def _clock(stop: threading.Event) -> None:
    while not stop.wait(DRAIN_INTERVAL_SECONDS):
        try:
            result = _drain()
            if result.get("sent") or result.get("failed"):
                log.info("clock drain: %s", json.dumps(result))
        except Exception:
            log.exception("clock drain failed")


def _inbound_once() -> dict:
    """One reconcile pass, identical to `cli.py reconcile --pages 1`.

    reconcile.run classifies anything new and QUEUES hot-lead handoffs;
    flush_escalations is what posts them (only after their debounce window,
    which a 60s clock finally makes meaningful -- the 10-minute poll always
    arrived after it had long expired). Deliberately not worker.run_once(),
    which also starts the campaign scheduler.
    """
    from . import reconcile
    with _inbound_lock:
        result = reconcile.run(pages=1, apply=True)
        if config.PHASE >= 2:
            result["handoffs_posted"] = worker.flush_escalations()
    return result


def _digest_clock(stop: threading.Event) -> None:
    """Post the day's readout once, at config.DIGEST_HOUR local time.

    The digest existed from day one and was never posted anywhere, which is
    how thirteen drafts waited four days unseen. One post a day, keyed on the
    date in the store so a restart inside the hour cannot post it twice.
    """
    from zoneinfo import ZoneInfo
    from . import digest

    tz = ZoneInfo(config.CAMPAIGN_TZ)
    while not stop.wait(60):
        try:
            now = datetime.now(tz)
            if config.DIGEST_HOUR < 0 or now.hour != config.DIGEST_HOUR:
                continue
            key = f"digest_posted:{now:%Y-%m-%d}"
            if store.get_meta(key):
                continue
            store.set_meta(key, store.now())
            digest.run(days=1, post=True)
            log.info("posted the %s:00 digest", config.DIGEST_HOUR)
        except Exception:
            log.exception("digest clock failed")


def _inbound_clock(stop: threading.Event) -> None:
    cycles = 0
    while not stop.wait(INBOUND_INTERVAL_SECONDS):
        cycles += 1
        try:
            result = _inbound_once()
            if result.get("replayed") or result.get("handoffs_posted"):
                log.info(
                    "inbound: %s",
                    json.dumps({k: v for k, v in result.items() if k != "results"}),
                )
            elif cycles % HEARTBEAT_EVERY_CYCLES == 0:
                log.info(
                    "inbound heartbeat: %s rows scanned, nothing new",
                    result.get("rows_scanned", "?"),
                )
        except Exception:
            log.exception("inbound clock failed")


# --------------------------------------------------------------- the actions

def _approve(phone: str, uuid: str) -> str:
    """Queue the newest held draft and send it. `approve` + `work`, in one tap.

    Older held drafts for the same phone are cancelled rather than left to send
    later out of order -- identical to cmd_approve, which is the point.
    """
    rows = list(store._conn().execute(
        "SELECT * FROM outbox WHERE phone=? AND status='held' ORDER BY id DESC", (phone,)
    ))
    if not rows:
        return "nothing was held for this number (already handled?)"

    row = dict(rows[0])
    with store.tx() as c:
        c.execute("UPDATE outbox SET status='queued' WHERE id=?", (row["id"],))
        c.execute(
            "UPDATE outbox SET status='cancelled', error='superseded'"
            " WHERE phone=? AND status='held' AND id<>?",
            (phone, row["id"]),
        )
    store.bump_ai_turns(phone)

    result = _drain()
    if result.get("sent"):
        return f"sent: \"{row['body'][:120]}\""
    if result.get("held"):
        # Quiet hours. The message is queued and real; it goes out at 8am.
        return "approved - outside 8am-9pm, so it sends first thing in the morning"
    if result.get("skipped") or result.get("failed"):
        return f"approved but NOT sent ({json.dumps(result)}) - check the log"
    return f"approved, nothing due to send ({json.dumps(result)})"


def _handle(phone: str, uuid: str, who: str) -> str:
    """Take the thread away from the agent. The most-used answer, by far."""
    store.ensure_conversation(phone)
    store.pause_conversation(phone, f"handed to {who or config.HANDOFF_NAME} from Slack")
    n = store.cancel_queued(phone, "handed to a human from Slack")
    return f"yours now - agent paused, {n} draft(s) dropped"


def _not_lead(phone: str, uuid: str) -> str:
    """A soft no. Closed and workable later, never texted back."""
    store.ensure_conversation(phone)
    store.update_conversation(phone, state="closed", paused_reason="soft no (Slack)")
    n = store.cancel_queued(phone, "not a lead")
    return f"closed as a soft no, {n} draft(s) dropped"


def _got_it(phone: str, uuid: str, who: str) -> str:
    """Acknowledge a hot lead from the phone. The engine already paused the
    thread at handoff; this records WHO took it so the digest and the next
    follow-up nudge can say so. Nothing is sent, nothing reaches the CRM."""
    store.ensure_conversation(phone)
    store.pause_conversation(phone, f"{who or config.HANDOFF_NAME} has it (Slack)")
    n = store.cancel_queued(phone, "taken from Slack")
    return f"noted - {who or 'you'} has it" + (f", {n} draft(s) dropped" if n else "")


def _wrong(phone: str, uuid: str) -> str:
    """Wrong number. Suppressed locally so nothing texts it again, ever.

    The CRM half (phone status WRONG on every record carrying this number) is
    deliberately NOT done here: WRITE_SCOPE=opt_out blocks it anyway, and a
    button that half-writes to the CRM would be worse than one that is honest
    about being local-only.
    """
    store.suppress(phone, "wrong_number")
    store.ensure_conversation(phone)
    store.update_conversation(phone, state="closed", paused_reason="wrong number (Slack)")
    n = store.cancel_queued(phone, "wrong number")
    return f"suppressed - nothing will text this number again, {n} draft(s) dropped"


def handle(action_id: str, phone: str, uuid: str = "", who: str = "") -> str:
    """Run one button. Returns the line that replaces the buttons in Slack.

    Kept free of any Slack object so the selftest can exercise every action
    with no network and no tokens.
    """
    phone = store.clean_phone(phone)
    if action_id not in escalate.ACTIONS:
        return f"ignored unknown action {action_id!r}"
    if not phone:
        return "ignored: no phone on the button"

    store.init()
    if action_id == "sms_approve":
        return _approve(phone, uuid)
    if action_id == "sms_handle":
        return _handle(phone, uuid, who)
    if action_id == "sms_got_it":
        return _got_it(phone, uuid, who)
    if action_id == "sms_not_lead":
        return _not_lead(phone, uuid)
    return _wrong(phone, uuid)


# --------------------------------------------------------------- the message

def resolved_blocks(blocks: list, summary: str, who: str, label: str) -> list:
    """Strip the buttons, leave a record of who pressed what.

    Rewriting the message rather than posting a reply is what makes the channel
    readable on a phone: a draft either still has buttons (needs you) or it
    does not (done). No scrolling to work out which.
    """
    kept = [b for b in (blocks or []) if b.get("type") != "actions"]
    kept.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f":white_check_mark: *{label}* by {who or 'someone'} - {summary}",
        }],
    })
    return kept


def _update_message(channel: str, ts: str, blocks: list, fallback: str) -> None:
    try:
        resp = requests.post(
            "https://slack.com/api/chat.update",
            json={"channel": channel, "ts": ts, "text": fallback, "blocks": blocks},
            headers={"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"},
            timeout=15,
        )
        body = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("chat.update failed: %s", exc)
        return
    if not body.get("ok"):
        log.warning("chat.update refused: %s", body.get("error"))


def on_action(payload: dict) -> Optional[str]:
    """One block_actions payload, start to finish. Returns the summary line."""
    actions = payload.get("actions") or []
    if not actions:
        return None
    action = actions[0]
    action_id = action.get("action_id", "")
    if action_id not in escalate.ACTIONS:
        return None

    try:
        value = json.loads(action.get("value") or "{}")
    except ValueError:
        value = {}
    phone = value.get("phone") or ""
    uuid = value.get("uuid") or ""
    user = payload.get("user") or {}
    who = user.get("name") or user.get("username") or user.get("id") or ""

    summary = handle(action_id, phone, uuid, who)
    log.info("slack button %s on %s by %s -> %s", action_id, phone, who, summary)

    message = payload.get("message") or {}
    channel = (payload.get("channel") or {}).get("id") or config.SLACK_CHANNEL
    ts = message.get("ts")
    if channel and ts:
        _update_message(
            channel, ts,
            resolved_blocks(message.get("blocks"), summary, who, escalate.ACTIONS[action_id]),
            f"{escalate.ACTIONS[action_id]}: {summary}",
        )
    return summary


# --------------------------------------------------------------- the listener

def listen() -> int:
    """Hold the websocket open until killed. This is the whole daemon."""
    try:
        from slack_sdk import WebClient
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.request import SocketModeRequest
        from slack_sdk.socket_mode.response import SocketModeResponse
    except ImportError:
        log.error("slack_sdk is not installed: pip install slack_sdk")
        return 2

    if not config.SLACK_APP_TOKEN or not config.SLACK_BOT_TOKEN:
        log.error(
            "need SMS_AGENT_SLACK_APP_TOKEN (xapp-, for the socket) and "
            "SMS_AGENT_SLACK_BOT_TOKEN (xoxb-, to post and update)"
        )
        return 2

    store.init()
    client = SocketModeClient(
        app_token=config.SLACK_APP_TOKEN,
        web_client=WebClient(token=config.SLACK_BOT_TOKEN),
    )

    def _on_request(cli: "SocketModeClient", req: "SocketModeRequest") -> None:
        # Ack before working, always. See ACK_FIRST.
        cli.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        if req.type != "interactive":
            return
        payload = req.payload or {}
        if payload.get("type") != "block_actions":
            return
        try:
            on_action(payload)
        except Exception:
            # A crash in a handler must not take the socket down with it, or
            # one bad draft ends approvals until someone notices.
            log.exception("slack button handler failed")

    client.socket_mode_request_listeners.append(_on_request)

    stop = threading.Event()
    threading.Thread(target=_clock, args=(stop,), daemon=True, name="outbox-clock").start()
    if INBOUND_INTERVAL_SECONDS > 0:
        threading.Thread(
            target=_inbound_clock, args=(stop,), daemon=True, name="inbound-clock"
        ).start()
    if config.DIGEST_HOUR >= 0:
        threading.Thread(
            target=_digest_clock, args=(stop,), daemon=True, name="digest-clock"
        ).start()

    client.connect()
    log.info(
        "slack button listener up; channel=%s; outbox clock every %ss; inbound every %s",
        config.SLACK_CHANNEL, DRAIN_INTERVAL_SECONDS,
        f"{INBOUND_INTERVAL_SECONDS}s" if INBOUND_INTERVAL_SECONDS > 0 else "OFF",
    )
    stop.wait()  # never set; killed from outside
    return 0
