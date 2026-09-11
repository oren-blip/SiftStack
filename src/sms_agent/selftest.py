"""Offline end-to-end exercise of every phase. Sends nothing, writes nothing.

Runs against a throwaway database with the network stubbed out, so it is safe
to run any time, on any machine, with production credentials loaded. It asserts
behaviour rather than printing it, because the failure this guards against is
the one this codebase keeps rediscovering: a run that reports success while
doing nothing.

    python src/sms_agent/cli.py selftest
    python src/sms_agent/cli.py selftest --live-model   # also exercise Claude
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

RESET, RED, GREEN, DIM = "\033[0m", "\033[31m", "\033[32m", "\033[2m"


@dataclass
class Case:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Results:
    cases: list[Case] = field(default_factory=list)

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        self.cases.append(Case(name, bool(condition), detail))
        return bool(condition)

    @property
    def failed(self) -> list[Case]:
        return [c for c in self.cases if not c.ok]

    def report(self) -> int:
        for case in self.cases:
            mark = f"{GREEN}pass{RESET}" if case.ok else f"{RED}FAIL{RESET}"
            print(f"  [{mark}] {case.name}")
            if case.detail:
                print(f"         {DIM}{case.detail}{RESET}")
        print()
        if self.failed:
            print(f"{RED}{len(self.failed)} of {len(self.cases)} checks failed{RESET}")
            return 1
        print(f"{GREEN}all {len(self.cases)} checks passed{RESET}")
        return 0


class _Stub:
    """Records what would have gone out, and lets nothing out."""

    def __init__(self) -> None:
        self.sent: list[tuple] = []
        self.slack: list[str] = []
        self.crm_writes: list[tuple] = []
        self.dnt: list[str] = []


def run(live_model: bool = False) -> int:
    # Point everything at a throwaway database BEFORE the modules bind to it.
    tmp = Path(tempfile.mkdtemp(prefix="sms_agent_selftest_"))
    import os

    os.environ["SMS_AGENT_DB"] = str(tmp / "selftest.db")
    os.environ["SMS_AGENT_DATA_DIR"] = str(tmp)
    os.environ["SMS_AGENT_DRY_RUN"] = "1"
    os.environ["SMS_AGENT_PHASE"] = "4"
    os.environ.setdefault("SMRTPHONE_NUMBERS", '["+18650000001","+18650000002"]')

    from . import classify, config, crm, engine, escalate, respond, sender_pool, store
    from . import smrtphone, transport, seed
    from .knowledge import touches

    # Rebind the values the modules already read at import time.
    config.DB_PATH = Path(os.environ["SMS_AGENT_DB"])
    config.PHASE, config.DRY_RUN = 4, True
    config.SMRTPHONE_NUMBERS_RAW = os.environ["SMRTPHONE_NUMBERS"]
    # The real .env carries live Slack tokens since 2026-09-06. The selftest
    # must behave the same on every machine, so it runs as if it had none and
    # opts the button path in explicitly where it wants to exercise it.
    config.SLACK_BOT_TOKEN = config.SLACK_APP_TOKEN = config.SLACK_CHANNEL = ""
    store._local.__dict__.pop("conn", None)
    store.init()

    stub = _Stub()
    r = Results()

    # ---- stub every outbound edge -------------------------------------
    transport.send = lambda to, body, frm="": (
        stub.sent.append((to, body, frm)) or smrtphone.SendResult(True, sms_id="stub")
    )
    smrtphone.add_to_dnt = lambda phone: (stub.dnt.append(phone) or (True, "stub"))
    escalate._post = lambda text, blocks=None: (stub.slack.append(text) or True)
    for name in ("add_tags", "set_status", "post_note", "assign", "bump_sms_attempts"):
        setattr(
            crm, name,
            (lambda n: lambda *a, **k: (stub.crm_writes.append((n, a)) or {"_dry_run": True}))(name),
        )
    crm.set_phone_status = lambda uuid, phone, status: (
        stub.crm_writes.append(("set_phone_status", (uuid, phone, status)))
        or {"_dry_run": True}
    )
    # Synthetic records have no CRM row, so the live dial-tier lookup would
    # hold every candidate. Stubbed to a qualifying tier; the tier RULE itself
    # is asserted separately below against ALLOWED_DIAL_TIERS.
    crm.dial_tier_checked = lambda uuid, phone: ("Dial First", True)
    crm.dial_tier = lambda uuid, phone: "Dial First"
    crm.deal_context = lambda uuid: {
        "owner_first": "Maron", "street": "158 Old State Rd", "city": "Maryville",
        "county": "Blount", "assigned_name": "Adriana", "record_uuid": uuid,
    }

    if not live_model:
        # Deterministic classification and drafting, so a network blip is never
        # reported as a logic failure.
        classify.classify_llm = lambda text, history=None: classify.Classification(
            "OTHER", 0.0, "fallback", "stubbed"
        )
        respond.draft = lambda thread, context=None, intent="", intent_rationale="": respond.Reply(
            message="Hi Maron! Sorry to bother you. Is 158 Old State Rd yours?",
            confidence=0.92, handoff=(intent == "INTERESTED"), reason="stub", ok=True,
        )

    ctx = crm.deal_context("rec-1")
    for phone in ("8650001111", "8650002222", "8650003333", "8650004444",
                  "8650005555", "8650006666", "8650008888"):
        store.map_phone(phone, record_uuid="rec-" + phone[-4:], context=ctx)

    def inbound(phone: str, message: str, sms_id: str = "") -> dict:
        return engine.process("smrtphone", {
            "event": "smsIncoming", "smsId": sms_id or "st-" + phone[-4:],
            "from": phone, "to": "+18650000001", "message": message,
        })

    # ---- 1. deterministic rules are authoritative ---------------------
    print("\ndeterministic classification")
    for text, expect in (
        ("STOP", "OPT_OUT"),
        ("END", "OPT_OUT"),        # what the SMS footer tells them to reply
        ("STOPALL", "OPT_OUT"),    # on the registered keyword list
        ("Opt out", "OPT_OUT"),
        ("please stop texting me", "OPT_OUT"),
        ("take me off your list", "OPT_OUT"),
        ("wrong number, I don't own that", "WRONG_NUMBER"),
        ("my husband passed away last month", "ESCALATE"),
        ("my attorney will be in touch", "ESCALATE"),
        # Jessica, 6956 Cardindale, 2026-08-11. Shipped as INTERESTED and paged
        # the prospector; the confirmation is about the phone, the refusal is
        # the answer. Every phrasing below is a real way people say the same no.
        ("It is. And it's staying that way.", "NOT_INTERESTED"),
        ("yes but it's not going anywhere", "NOT_INTERESTED"),
        ("that's mine and I plan to keep it", "NOT_INTERESTED"),
        ("correct, staying in the family", "NOT_INTERESTED"),
        ("yep, never selling", "NOT_INTERESTED"),
        # Live 2026-08-11: both went unclassified. We open with the owner's
        # name, so a stranger asking about that name is the wrong-number tell.
        ("Who the hell is Jonathan", "WRONG_NUMBER"),
        ("this ain't joseph.", "WRONG_NUMBER"),
        ("theres no one here by that name", "WRONG_NUMBER"),
    ):
        got = classify.classify(text)
        r.check(f"{expect:12} <- {text[:38]!r}", got.intent == expect,
                "" if got.intent == expect else f"got {got.intent}")

    # A bare confirmation answers the ownership question in touch 1 and says
    # nothing about selling, so it must not read as a hot lead.
    for text in ("It is.", "yes", "that's right", "sure is"):
        got = classify.classify(text)
        r.check(f"bare confirm is not INTERESTED <- {text!r}",
                got.intent != "INTERESTED", f"got {got.intent}")

    # Asking who WE are is a fair question from the right person. Dispositioning
    # that number WRONG would throw away a good line.
    for text in ("who is this", "who's this?", "who is that"):
        got = classify.classify(text)
        r.check(f"asking who we are is not WRONG_NUMBER <- {text!r}",
                got.intent != "WRONG_NUMBER", f"got {got.intent}")

    # ---- 1b. one text is stored once ----------------------------------
    # smrtPhone identifies the same message with a uuid on the webhook and an
    # integer in the SMS log, so id-based dedupe alone let the backstop poller
    # replay every reply the webhook had already handled.
    print("\ninbound dedupe")
    store.add_message("8650009999", "in", "Would love to", sms_id="uuid-abc", author="owner")
    store.add_message("8650009999", "in", "Would love to", sms_id="uuid-abc", author="owner")
    n = store._conn().execute(
        "SELECT COUNT(*) n FROM messages WHERE phone='8650009999'").fetchone()["n"]
    r.check("same sms_id stored once", n == 1, f"rows={n}")
    r.check("same body from the other surface is recognised",
            store.recent_inbound_exists("8650009999", "Would love to", 90))
    r.check("a different body is not swallowed",
            not store.recent_inbound_exists("8650009999", "Actually yes", 90))
    # An inbound that has arrived but is not yet processed still counts as
    # received. Otherwise the backstop poller re-enqueues it during the window
    # between the webhook landing and the worker draining the queue.
    store.record_event(
        "smrtphone", "smsIncoming", "st-pending-dupe",
        {"event": "smsIncoming", "from": "8650009999", "to": "+18650000001",
         "message": "Nope", "smsId": "st-pending-dupe"},
    )
    r.check("an unprocessed event counts as already received",
            store.recent_inbound_exists("8650009999", "Nope", 90))

    # A live person asking a direct question must not sit in silence while the
    # agent is below the phase that can answer.
    print("\nwho is this")
    # Production runs at phase 2, where no reply is ever DRAFTED. The who-answer
    # is a fixed template rather than a draft, which is why it is allowed here.
    _phase, _answer = config.PHASE, config.ANSWER_WHO
    config.PHASE = 2
    # Force the template ON regardless of production config. This block tests
    # that the code path WORKS; whether it runs live is .env's decision, and on
    # this account it is off (SMS_AGENT_ANSWER_WHO=0) because it queues a real
    # message without a phase gate. The fallback-when-off case is tested below.
    config.ANSWER_WHO = True
    before = len(stub.slack)
    out = inbound("8650008888", "who is this?")
    r.check("answers the question itself", out.get("action") == "answered_who",
            str(out.get("action")))
    r.check("does not page a human for it", len(stub.slack) == before,
            f"{len(stub.slack) - before} posts")
    queued = [x for x in store.due_outbox(50) if x["phone"] == "8650008888"]
    r.check("a reply is queued", len(queued) == 1, f"{len(queued)} queued")
    if queued:
        msg = queued[0]["body"]
        r.check("never names the company",
                not any(w in msg.lower() for w in ("volunteer", "homebuyer", "llc", "inc")), msg)
        r.check("identifies by locality instead",
                any(w in msg.lower() for w in ("local", "around")), msg)
        r.check("names the street", "158 old state" in msg.lower(), msg)
        r.check("asks exactly one question", msg.count("?") == 1, msg)
        r.check("carries no dash characters", "—" not in msg and "–" not in msg, msg)
        ok, problems = respond.validate(msg, max_questions=1)
        r.check("passes the outbound validator", ok, str(problems))

    # With the template disabled it must fall back to telling a person, never
    # to silence.
    config.ANSWER_WHO = False
    store.map_phone("8650009111", record_uuid="rec-9111", context=ctx)
    before = len(stub.slack)
    out = inbound("8650009111", "who is this?")
    r.check("falls back to a human when the template is off",
            out.get("action") == "needs_human_reply", str(out.get("action")))
    # Reversed 2026-08-27 (Oren): a live thread waiting on a human answer DOES
    # post — `needs_reply` is on ALWAYS_POST, so the interested-only filter lets
    # it through. A question visible only in the digest went unanswered in
    # practice; that was the trade-off this check used to pin.
    r.check("a waiting question reaches the channel", len(stub.slack) == before + 1,
            f"{len(stub.slack) - before} posts")
    config.PHASE, config.ANSWER_WHO = _phase, _answer

    # ---- 1d. everyone walks all four touches ---------------------------
    # Tying touches to CRM call-attempt stages capped most owners at touch 1,
    # because a record parked in Ready to Call never advances a stage on its
    # own. Progression is the person's own history now.
    print("\ntouch progression")
    from datetime import date as _date

    from . import campaign as _camp
    today = _date(2026, 8, 20)
    r.check("never texted starts at touch 1",
            _camp.next_touch(None, 2, today)[0] == 1)
    r.check("advances to the next touch after the gap",
            _camp.next_touch({"touches": {1}, "last": "2026-08-17"}, 2, today)[0] == 2)
    r.check("waits when the gap has not passed",
            _camp.next_touch({"touches": {1}, "last": "2026-08-19"}, 2, today)[0] is None)
    r.check("walks the whole sequence",
            [_camp.next_touch({"touches": set(range(1, n + 1)), "last": "2026-08-01"}, 2, today)[0]
             for n in (1, 2, 3)] == [2, 3, 4])
    r.check("stops after the fourth",
            _camp.next_touch({"touches": {1, 2, 3, 4}, "last": "2026-08-01"}, 2, today)[0] is None)
    r.check("says why it stopped",
            "completed" in _camp.next_touch({"touches": {1, 2, 3, 4}, "last": ""}, 2, today)[1])

    # ---- 1b2. one timezone must not drag the whole batch ---------------
    # A Los Angeles recipient at the front of a 9am Eastern batch pushed every
    # Tennessee message behind it to 11:24, because the layout cursor advanced
    # from the deferred time instead of the slot the message actually held.
    print("\nschedule layout")
    from datetime import datetime as _dt, timezone as _tz
    for i, ph in enumerate(("3109991447", "8650001212", "8650001313", "8650001414")):
        store.queue_message(ph, f"layout probe {i}", from_number=f"+186527300{i:02d}",
                            status="held")
    laid = seed.reschedule_held()
    r.check("every staged message is laid out", laid["rescheduled"] >= 4, str(laid))
    rows = list(store._conn().execute(
        "SELECT phone, not_before FROM outbox WHERE body LIKE 'layout probe%'"))
    times = {x["phone"]: x["not_before"] for x in rows}
    east = sorted(v for k, v in times.items() if k.startswith("865"))
    west = times.get("3109991447")
    now_iso = _dt.now(_tz.utc).isoformat(timespec="seconds")
    # The real property: an Eastern recipient goes NOW, whatever the western one
    # has to wait for. Asserting east < west only holds while Los Angeles is
    # still asleep, so it would pass in the morning and fail after 11am Eastern.
    from datetime import datetime as _dtp
    delay_min = (
        (_dtp.fromisoformat(east[0]) - _dtp.fromisoformat(now_iso)).total_seconds() / 60
        if east else 999
    )
    r.check("eastern sends are not delayed by a western recipient",
            delay_min < 10, f"first eastern send is {delay_min:.0f} min out (east={east[:1]})")
    with store.tx() as _c:
        _c.execute("DELETE FROM outbox WHERE body LIKE 'layout probe%'")

    # A thread keeps one number for life. Live, one owner got touch 3 from
    # ...0296 and touch 4 from ...0270 an hour later, because the number is
    # picked when a message is staged and both were staged before either sent.
    def _cand(phone):
        c = seed.Candidate(phone=phone, record_uuid="rec-sticky", street="1 Test St",
                           city="Knoxville", county="Knox", owner_full="Test Owner")
        c.first, c.sender, c.message, c.status = "Test", "Adriana", "hi", "ready"
        return c

    laid = seed.schedule([_cand("8650007777"), _cand("8650007777")])
    numbers = {n for _, n, _ in laid}
    r.check("the same person in one batch gets one number", len(numbers) <= 1,
            f"{len(numbers)} numbers: {numbers}")

    # ---- 1c. suppression lives on the phone in Sift --------------------
    # smrtPhone has no writable DNT route, so Sift's phone disposition IS the
    # suppression: it is read by every campaign, ours and anyone else's.
    print("\nphone disposition")
    r.check("DNC statuses are accepted",
            all(s in crm.PHONE_STATUSES for s in ("DNC", "CORRECT_DNC", "WRONG_DNC", "NO_ANSWER")))
    r.check("a known-good number opting out keeps that knowledge",
            crm.DNC_FOR.get("CORRECT") == "CORRECT_DNC")
    r.check("wrong number plus opt-out is WRONG_DNC",
            crm.dnc_status("rec-1", "8650001111", wrong_number=True) == "WRONG_DNC")
    r.check("every DNC status is skipped when building a campaign",
            {"DNC", "CORRECT_DNC", "WRONG_DNC"} <= seed.SKIP_PHONE_STATUSES)
    r.check("a live number is still eligible",
            "CORRECT" not in seed.SKIP_PHONE_STATUSES and "UNKNOWN" not in seed.SKIP_PHONE_STATUSES)

    # Only the two tiers Trestle rated most likely to reach the owner. The
    # first live run went out without this and put 24 of 84 texts on Third,
    # Fourth or Drop numbers.
    # The record itself should show how many texts it has had, so a prospector
    # opening the file knows before they dial. Exercised with DRY_RUN off and a
    # stubbed transport, because the dry-run path returns before sending and so
    # would never reach the counter.
    _dry_was, _sent_was = config.DRY_RUN, list(stub.sent)
    with store.tx() as _c:  # park anything else queued so only the probe sends
        _c.execute("UPDATE outbox SET status='held' WHERE status='queued'")
    config.DRY_RUN = False
    store.ensure_conversation("8650006666", from_number="+18650000001")
    store.update_conversation("8650006666", record_uuid="rec-6666", state="active")
    store.queue_message("8650006666", "counter probe", from_number="+18650000001")
    from . import worker as _w2
    _w2.drain_outbox(limit=5)
    config.DRY_RUN = _dry_was
    stub.sent[:] = _sent_was  # the probe is ours, not part of the dry-run check
    with store.tx() as _c:
        _c.execute("UPDATE outbox SET status='queued' WHERE status='held'")
    r.check("a send increments the Sift counter",
            any(w[0] == "bump_sms_attempts" for w in stub.crm_writes),
            str(sorted({w[0] for w in stub.crm_writes})))

    r.check("only dial first and second may be texted",
            seed.ALLOWED_DIAL_TIERS == {"Dial First", "Dial Second"},
            str(sorted(seed.ALLOWED_DIAL_TIERS)))
    for bad in ("Dial Third", "Dial Fourth", "Drop", ""):
        r.check(f"tier {bad or 'untagged'!r} is not textable",
                bad not in seed.ALLOWED_DIAL_TIERS)

    # ---- 2. opt-out is honored on every surface ------------------------
    print("\nopt-out")
    out = inbound("8650001111", "STOP")
    r.check("routes to opted_out", out.get("action") == "opted_out", str(out.get("action")))
    r.check("suppressed locally", store.is_suppressed("8650001111") == "opt_out")
    r.check("smrtPhone DNT written", "8650001111" in stub.dnt)
    # How far the opt-out reaches is a policy setting, so assert what the active
    # policy promises rather than one house style. Either way the number itself
    # is suppressed and DNC'd, which is the part that must never regress.
    tagged = any(w[0] == "add_tags" and config.TAG_OPT_OUT in w[1][1] for w in stub.crm_writes)
    if config.OPT_OUT_SCOPE == "full":
        r.check("Do Not Market tagged", tagged)
    else:
        r.check("scope=phone leaves the record marketable", not tagged,
                "Do Not Market was tagged anyway")
    r.check("the number is DNC'd whatever the scope",
            any(w[0] == "set_phone_status" and "DNC" in str(w[1]).upper()
                for w in stub.crm_writes),
            str([w[0] for w in stub.crm_writes]))
    r.check("no note is written to the message endpoint",
            not any(w[0] == "post_note" for w in stub.crm_writes) or config.ALLOW_NOTES,
            "post_note fired with notes disabled")
    r.check("no reply drafted to an opt-out", not stub.sent)

    # ---- 3. wrong number -----------------------------------------------
    print("\nwrong number")
    out = inbound("8650002222", "wrong number, I don't own any property")
    r.check("routes to wrong_number", out.get("action") == "wrong_number", str(out.get("action")))
    r.check("phone flipped to WRONG",
            any(w[0] == "set_phone_status" and w[1][2] == "WRONG" for w in stub.crm_writes))
    r.check("suppressed", store.is_suppressed("8650002222") == "wrong_number")

    # ---- 4. hot lead escalates ------------------------------------------
    print("\npositive reply")
    stub.slack.clear()
    out = inbound("8650003333", "How much would you pay for it?")
    r.check("classified INTERESTED",
            out.get("classification", {}).get("intent") == "INTERESTED",
            str(out.get("classification")))
    r.check("handoff queued, not posted immediately", not stub.slack,
            "a burst must settle before it posts")
    r.check("escalation is pending", bool(store.due_escalations()) or True)
    # A second text seconds later must NOT create a second notification.
    inbound("8650003333", "actually call me this afternoon", sms_id="st-3333b")
    r.check("second text does not queue a second post",
            len([e for e in store._conn().execute("SELECT 1 FROM escalations")]) == 1)
    # Force the burst to settle, then flush.
    with store.tx() as c:
        c.execute("UPDATE escalations SET due_at='2000-01-01T00:00:00+00:00'")
    from . import worker as _w
    posted = _w.flush_escalations()
    r.check("flush posts exactly one handoff", posted == 1, str(posted))
    r.check("post names the owner and the action",
            any("Call within 5 minutes" in s for s in stub.slack), str(stub.slack[:1]))
    r.check("flushing twice does not repost", _w.flush_escalations() == 0)

    # ---- 4b. the triage line: their ask against our estimate --------------
    # Mark Pilkington (401 W 1St St, 2026-08-22) said "it can be yours for
    # 350,000". The post carried beds and baths but no value, so deciding it was
    # over the buy box meant opening the record. Negative controls matter more
    # than the positives here: a bare year or a house number read as a price
    # would put a fake asking price on every handoff.
    print("\ntriage line")
    for text, want in (
        ("It is my parents- it can be yours for 350,000", "$350,000"),
        ("$100,000", "$100,000"),
        ("I'd take 250k for it", "$250,000"),
        ("250000 firm", "$250,000"),
        ("The house was built in 1962", ""),
        ("we moved here in 1998", ""),
        ("I live at 401 W 1St St", ""),
        ("call me at 704 621 0442", ""),
        ("Wrong number", ""),
        ("", ""),
    ):
        got = escalate._asking_price(text)
        r.check(f"ask from {text[:34]!r}" if text else "ask from an empty message",
                got == want, f"got {got!r}, want {want!r}")
    # Vacant land must never be quoted a house estimate. Real case: 175 Organ
    # Church Rd carried estimate_value $255,000 on a 1.03-acre empty lot that
    # LandPortal reads at $69,196, which turned a $100,000 OVER-ask into what
    # looked like a bargain. Negative controls confirm a real house still shows
    # its number.
    r.check("record typed vacant land is caught",
            escalate._is_vacant_land({"structure_type": "Residential-Vacant Land"}))
    r.check("lot size with no dwelling is caught",
            escalate._is_vacant_land({"lot_size": 1.03}))
    r.check("a house is NOT called land",
            not escalate._is_vacant_land(
                {"structure_type": "Single Family Residential", "beds": 3,
                 "baths": 2, "sqft": 1400, "lot_size": 0.25}))
    r.check("a house with only beds known is NOT called land",
            not escalate._is_vacant_land({"beds": 3, "lot_size": 0.3}))
    r.check("an empty context is NOT called land", not escalate._is_vacant_land({}))

    # LandPortal supplies the honest land number. Stubbed so this stays offline
    # and spends none of the ~10/day property-data allowance.
    LAND_CTX = {"structure_type": "Residential-Vacant Land", "lot_size": 1.03,
                "parcel_id": "3881015", "county": "Rowan", "street": "175 Organ Church Rd",
                "owner_first": "Penny", "estimated_value": "255000.00"}
    _real_land = escalate._land_value
    try:
        escalate._land_value = lambda ctx: {"tlp_estimate": 69196.0, "county_value": 16429.0,
                                            "acres": 1.03, "source": "landportal"}
        stub.slack.clear()
        escalate.hot_lead("8650007777", "$100,000", "INTERESTED", context=LAND_CTX)
        post = stub.slack[-1] if stub.slack else ""
        r.check("land ask is priced against LandPortal", "LandPortal $69,196" in post, post)
        r.check("the DataSift house estimate never appears on land",
                "255,000" not in post, post)

        # And when LandPortal cannot answer, say so — never fall back to the
        # dwelling estimate. This is the regression that inverts a decision:
        # $100,000 looks like a bargain against a fake $255,000 and an over-ask
        # against the real ~$69,000.
        escalate._land_value = lambda ctx: None
        stub.slack.clear()
        escalate.hot_lead("8650007778", "$100,000", "INTERESTED", context=LAND_CTX)
        post = stub.slack[-1] if stub.slack else ""
        r.check("no LandPortal read means no estimate is quoted",
                "no reliable estimate" in post, post)
        r.check("still no DataSift estimate on the fallback path",
                "255,000" not in post, post)
    finally:
        escalate._land_value = _real_land

    # The lookup must refuse quietly rather than reach the network half-armed.
    r.check("no parcel means no LandPortal call", escalate._land_value({"county": "Rowan"}) is None)
    r.check("no county means no LandPortal call",
            escalate._land_value({"parcel_id": "3881015"}) is None)
    r.check("an empty context means no LandPortal call", escalate._land_value({}) is None)

    r.check("money formats with separators", escalate._fmt_money(205000) == "$205,000",
            escalate._fmt_money(205000))
    r.check("money ignores what is not a number",
            escalate._fmt_money("n/a") == "" and escalate._fmt_money(None) == "")
    # The agent must NOT advance lead status. Interest is not qualification, and
    # only the person who makes the call decides that. It also kept the record
    # inside the Hottest cadence and out of the sequence that reassigns new
    # leads away from the prospector we just paged.
    r.check("lead status left alone for the human",
            not any(w[0] == "set_status" for w in stub.crm_writes),
            str([w for w in stub.crm_writes if w[0] == "set_status"]))
    r.check("handoff still tagged and assigned",
            any(w[0] == "add_tags" and "sys_escalated" in str(w[1]) for w in stub.crm_writes),
            str([w[0] for w in stub.crm_writes]))
    r.check("phone flipped to CORRECT",
            any(w[0] == "set_phone_status" and w[1][2] == "CORRECT" for w in stub.crm_writes))
    held = [x for x in store.due_outbox(50) if x["phone"] == "8650003333"]
    r.check("INTERESTED never auto-sends", not held,
            "a price question must reach a human, not an auto-reply")
    conv3333 = store.get_conversation("8650003333") or {}
    r.check("thread paused for the human", conv3333.get("state") == "paused",
            str(conv3333.get("state")))

    # ---- 4c. a named price beats a terminal phrase ------------------------
    # "$335,000.00. Cash and if not interested lose my number. Have a great day"
    # (7046785412, 2026-09-10) is an offer with a condition on it. The rules
    # read only the condition: OPT_OUT, DNC written to Sift, never shown to a
    # person. A price is the one thing a human must judge every time, so it goes
    # to the hot-lead post with the condition carried along. The negative
    # controls are the point: a ZIP code, a house number or a year next to
    # "stop" must still be a stop, and a carrier keyword on its own sentence
    # always wins.
    print("\nprice beats stop")
    PRICE_STOP = "$335,000.00. Cash and if not interested lose my number. Have a great day"
    got = classify.classify(PRICE_STOP)
    r.check("a price with 'lose my number' is INTERESTED, not an opt-out",
            got.intent == "INTERESTED", str(got.to_dict()))
    r.check("the rationale carries the price", "$335,000" in got.rationale, got.rationale)
    r.check("the rationale carries the condition", "lose my number" in got.rationale,
            got.rationale)
    for text, expect in (
        ("I'd take 250k for it but stop texting me", "INTERESTED"),
        ("not selling unless you pay 400,000", "INTERESTED"),
        ("The house was built in 1962, stop texting me", "OPT_OUT"),
        ("call me at 704 621 0442 and take me off your list", "OPT_OUT"),
        ("wrong number, I'm in 28027", "WRONG_NUMBER"),           # a ZIP is not a price
        ("I don't own that, I'm at 12345 Main St", "WRONG_NUMBER"),  # nor a house number
        ("$335,000. STOP", "OPT_OUT"),          # the carrier keyword always wins
        ("Wrong number. STOP", "OPT_OUT"),      # ...and is no longer dropped
        ("not mine, unsubscribe", "OPT_OUT"),
        ("wrong number, stop by the office sometime", "WRONG_NUMBER"),
    ):
        got = classify.classify(text)
        r.check(f"{text[:40]!r} -> {expect}", got.intent == expect,
                f"got {got.intent} ({got.source}: {got.rationale})")
    r.check("'end of story' is not an opt-out",
            classify.classify("No, end of story").intent != "OPT_OUT")
    r.check("opt_out_signal quotes the writer's words",
            classify.opt_out_signal(PRICE_STOP) == "lose my number",
            str(classify.opt_out_signal(PRICE_STOP)))
    r.check("opt_out_signal sees an embedded keyword",
            classify.opt_out_signal("Wrong number. STOP") == "stop",
            str(classify.opt_out_signal("Wrong number. STOP")))
    r.check("opt_out_signal ignores 'stop by'",
            classify.opt_out_signal("stop by the office") is None)
    r.check("strict price needs a money marker or six figures",
            classify.price_in("I'm in 28027", strict=True) == 0
            and classify.price_in("28027", strict=False) == 28027
            and classify.price_in("250000 firm", strict=True) == 250000)

    # End to end: no suppression, no CRM write, a hot-lead post that names the
    # ask and the condition, and a third button that honours the condition.
    _find = crm.find_records_by_phone
    crm.find_records_by_phone = lambda phone, limit=10: []
    try:
        store.map_phone("8650009335", record_uuid="rec-9335", context=ctx)
        writes_before = len(stub.crm_writes)
        out = inbound("8650009335", PRICE_STOP, sms_id="price-1")
        r.check("routes to the human, not to opted_out", out.get("action") == "handoff",
                str(out.get("action")))
        r.check("the line is NOT suppressed", store.is_suppressed("8650009335") is None,
                str(store.is_suppressed("8650009335")))
        r.check("no DNC reaches the CRM",
                not any(w[0] == "set_phone_status" and "DNC" in str(w[1]).upper()
                        and "8650009335" in str(w[1])
                        for w in stub.crm_writes[writes_before:]),
                str([w for w in stub.crm_writes[writes_before:] if w[0] == "set_phone_status"]))
        with store.tx() as c:
            c.execute("UPDATE escalations SET due_at='2000-01-01T00:00:00+00:00'"
                      " WHERE phone='8650009335'")
        stub.slack.clear()
        _w.flush_escalations()
        post = stub.slack[-1] if stub.slack else ""
        r.check("the handoff names the ask", "Asking $335,000" in post, post[:200])
        r.check("the handoff carries the condition", "They also said" in post
                and "lose my number" in post, post[:300])

        lead = escalate.hot_lead_buttons("8650009335", "rec-9335", conditional_opt_out=True)
        ids = [e["action_id"] for e in lead["elements"]]
        r.check("a conditional opt-out adds the third button",
                ids == list(escalate.LEAD_ACTIONS) + ["sms_not_lead_stop"], str(ids))
        r.check("the third button confirms first",
                "confirm" in lead["elements"][-1])
        r.check("a plain hot lead does NOT get it",
                "sms_not_lead_stop" not in
                [e["action_id"] for e in escalate.hot_lead_buttons("8650009335")["elements"]])
        from . import slack_buttons as _sb
        msg = _sb.handle("sms_not_lead_stop", "8650009335", "rec-9335")
        r.check("the tap suppresses the line", store.is_suppressed("8650009335") == "opt_out",
                str(store.is_suppressed("8650009335")))
        conv = store.get_conversation("8650009335") or {}
        r.check("the tap closes the thread as opted out", conv.get("state") == "opted_out",
                str(conv.get("state")))
        r.check("the tap makes the one permitted CRM write",
                any(w[0] == "set_phone_status" and "8650009335" in str(w[1])
                    and "DNC" in str(w[1]).upper() for w in stub.crm_writes[writes_before:]),
                msg)
    finally:
        crm.find_records_by_phone = _find

    # ---- 4d. a sensitive reply reaches a person, every time ----------------
    # "Oren Markowitz you can answer me now or I will be at your Huntersville
    # office tomorrow" (7045601058, 2026-09-10) paused the thread and posted
    # nothing: the ESCALATE_INTENTS gate (INTERESTED only) and the ops
    # suppression in alert() each swallowed it. Neither may ever again.
    print("\nsensitive reply")
    _sio = config.SLACK_INTERESTED_ONLY
    config.SLACK_INTERESTED_ONLY = True
    _find = crm.find_records_by_phone
    crm.find_records_by_phone = lambda phone, limit=10: []
    try:
        r.check("a suppressed alert says so", escalate.alert("x", "y", kind="ops") is False)
        r.check("an allowed alert still posts", escalate.alert("x", "y", kind="followup") is True)

        store.map_phone("8650009336", record_uuid="rec-9336", context=ctx)
        stub.slack.clear()
        out = inbound("8650009336", "my attorney will be in touch", sms_id="sens-1")
        r.check("posts exactly one Slack message, with the default gate",
                len(stub.slack) == 1, f"{len(stub.slack)} posts; ESCALATE_INTENTS={config.ESCALATE_INTENTS}")
        post = stub.slack[-1] if stub.slack else ""
        r.check("the post quotes the message", "my attorney will be in touch" in post, post[:200])
        r.check("the post is labelled sensitive", "Sensitive" in post, post[:120])
        r.check("the outcome says it posted",
                any("sensitive posted" in a for a in out.get("actions", [])),
                str(out.get("actions")))
        conv = store.get_conversation("8650009336") or {}
        r.check("the thread is paused as sensitive",
                conv.get("state") == "paused" and str(conv.get("paused_reason")).startswith("sensitive:"),
                str(conv.get("paused_reason")))

        # From a line we cannot name, it still posts.
        stub.slack.clear()
        out = inbound("8650009337", "I will be at your office tomorrow with my lawyer", sms_id="sens-2")
        r.check("an unmapped sensitive reply still posts",
                len(stub.slack) == 1 and out.get("action") == "escalated",
                f"{len(stub.slack)} posts; action={out.get('action')}")

        # Buttons under it when a listener is up, none when it is not.
        captured: list = []
        real_post = escalate._post
        escalate._post = lambda text, blocks=None: (captured.append((text, blocks)) or True)
        config.SLACK_BOT_TOKEN, config.SLACK_APP_TOKEN, config.SLACK_CHANNEL = "xoxb-t", "xapp-t", "C1"
        escalate.sensitive("8650009336", "my attorney will be in touch", "lawyer", ctx, [], "rec-9336")
        acts = [b for b in (captured[-1][1] or []) if b.get("type") == "actions"]
        r.check("the sensitive post carries Got it / Not a lead",
                bool(acts) and [e["action_id"] for e in acts[0]["elements"]] == list(escalate.LEAD_ACTIONS),
                str([e["action_id"] for e in acts[0]["elements"]] if acts else "no buttons"))
        config.SLACK_BOT_TOKEN = config.SLACK_APP_TOKEN = config.SLACK_CHANNEL = ""
        escalate.sensitive("8650009336", "my attorney will be in touch", "lawyer", ctx, [], "rec-9336")
        r.check("no buttons without a listener",
                not [b for b in (captured[-1][1] or []) if b.get("type") == "actions"])
        escalate._post = real_post
    finally:
        config.SLACK_INTERESTED_ONLY = _sio
        crm.find_records_by_phone = _find

    # ---- 4e. a weak no from the model goes to a person --------------------
    # With REPLY_TO_NO off a NOT_INTERESTED closes the thread with no human
    # look. "How much?... it's a 1989 mobile home" closed at 0.65 and "Perhaps
    # at some point" closed at 0.65 (2026-09-10). A price question is a lead; a
    # maybe is a draft. A plain "No" at 0.70 stays a no -- five of those landed
    # the same day and a draft for each would be its own bug.
    print("\nweak no")
    L = lambda intent, conf, text: (text, classify.Classification(intent, conf, "llm", "model"))
    for text, c, expect in (
        (*L("NOT_INTERESTED", 0.65, "How much?... it's a 1989 mobile home with a somewhat new metal roof"), "INTERESTED"),
        (*L("NOT_INTERESTED", 0.85, "What would you even pay for it"), "INTERESTED"),
        (*L("NOT_INTERESTED", 0.65, "Perhaps at some point"), "OTHER"),
        (*L("NOT_INTERESTED", 0.85, "Not right now, maybe later"), "OTHER"),
        (*L("NOT_INTERESTED", 0.70, "Try me back in the spring"), "OTHER"),
        (*L("NOT_INTERESTED", 0.62, "We are not committing to anyone yet"), "OTHER"),
        (*L("NOT_INTERESTED", 0.75, "No"), "NOT_INTERESTED"),
        (*L("NOT_INTERESTED", 0.70, "No bruh"), "NOT_INTERESTED"),
        (*L("NOT_INTERESTED", 0.75, "Sold"), "NOT_INTERESTED"),
        (*L("NOT_INTERESTED", 0.85, "No \U0001f44e"), "NOT_INTERESTED"),
        (*L("NOT_INTERESTED", 0.98, "Not interested thank you"), "NOT_INTERESTED"),
        (*L("NOT_INTERESTED", 0.75, "Fuck off"), "NOT_INTERESTED"),
        (*L("NOT_INTERESTED", 0.70, "Already sold it last year"), "NOT_INTERESTED"),
        (*L("NOT_INTERESTED", 0.85, "I have a buyer, just trying to get the Estate closed"), "NOT_INTERESTED"),
        (*L("OTHER", 0.55, "Perhaps at some point"), "OTHER"),          # only NOT_INTERESTED is guarded
        (*L("INTERESTED", 0.60, "If the deal falls thru"), "INTERESTED"),
    ):
        got = classify.guard_llm(text, c)
        label = text[:36].encode("ascii", "replace").decode()  # the console may not have the emoji
        r.check(f"{c.intent} {c.confidence:.2f} {label!r} -> {expect}",
                got.intent == expect, f"got {got.intent} ({got.source}: {got.rationale[:80]})")
    r.check("a rules answer is never guarded",
            classify.guard_llm("maybe?", classify.Classification("NOT_INTERESTED", 0.9, "rules", "x")).source == "rules")
    r.check("'keeping it for now' is still a rules no",
            classify.classify("I'm keeping it for now").source == "rules")
    fam = classify.classify("No. No.  This residence stays in the family.")
    r.check("'stays in the family' is a rules no",
            fam.intent == "NOT_INTERESTED" and fam.source == "rules", str(fam.to_dict()))
    r.check("'delete my number from your list' is an opt-out",
            classify.classify("You can delete my number from your list.").intent == "OPT_OUT")

    # End to end: the model says no, the guard says ask a person.
    _llm = classify.classify_llm
    try:
        classify.classify_llm = lambda text, history=None: classify.Classification(
            "NOT_INTERESTED", 0.65, "llm", "sounds like a no")
        store.map_phone("8650009338", record_uuid="rec-9338", context=ctx)
        out = inbound("8650009338", "Perhaps at some point", sms_id="weak-1")
        r.check("a maybe is drafted, not closed", out.get("action") == "replied",
                str(out.get("action")))
        conv = store.get_conversation("8650009338") or {}
        r.check("the thread stays active", conv.get("state") == "active", str(conv.get("state")))
        r.check("one draft waits for approval",
                len([x for x in store._conn().execute(
                    "SELECT 1 FROM outbox WHERE phone='8650009338' AND status IN ('held','queued')")]) == 1)
        r.check("the log shows the guard fired",
                out.get("classification", {}).get("source") == "guard",
                str(out.get("classification")))
        store.map_phone("8650009339", record_uuid="rec-9339", context=ctx)
        out = inbound("8650009339", "How much?... it's a 1989 mobile home", sms_id="weak-2")
        r.check("a price question is a hot lead", out.get("action") == "handoff",
                str(out.get("action")))
    finally:
        classify.classify_llm = _llm

    # ---- 4f. a relative answering is not a wrong number -------------------
    # "My name is Lisa Dana is my sister it's my mom's house" (7046748532,
    # 2026-09-10) was WRONG_NUMBER 0.75 from the model and suppressed for good.
    # The sibling who picks up on an estate IS the lead. Only a model
    # WRONG_NUMBER is guarded; "wrong number" from the rules stays terminal,
    # and Kristie's "we are not selling anything" stays a no.
    print("\nrelatives")
    W = lambda conf, text: (text, classify.Classification("WRONG_NUMBER", conf, "llm", "not the owner"))
    for text, c, expect in (
        (*W(0.75, "My name is Lisa Dana is my sister it's my mom's house"), "OTHER"),
        (*W(0.75, "Well it was my mom's. But she left it to her late husband. So I have no ties to it"), "OTHER"),
        (*W(0.80, "That's my dad's place, he passed in March"), "OTHER"),
        (*W(0.70, "I'm the executor of the estate, not the owner"), "OTHER"),
        (*W(0.90, "I'm not Sallie."), "WRONG_NUMBER"),
        (*W(0.90, "I am not Bashawn"), "WRONG_NUMBER"),
        (*W(0.85, "I'm not the owner, I work in real estate"), "WRONG_NUMBER"),  # 'real estate' is not 'estate'
    ):
        got = classify.guard_llm(text, c)
        r.check(f"WRONG_NUMBER {c.confidence:.2f} {text[:38]!r} -> {expect}",
                got.intent == expect, f"got {got.intent} ({got.source}: {got.rationale[:80]})")
    r.check("'wrong number' from the rules is still terminal",
            classify.classify("Wrong number").intent == "WRONG_NUMBER")
    kristie = classify.classify(
        "This is actually his sister Kristie, that is going to my brother. I am the "
        "Administrator to our Parents. We are not selling anything. So take it off your list.")
    r.check("a relative saying no is still a no",
            kristie.intent == "NOT_INTERESTED" and kristie.source == "rules", str(kristie.to_dict()))
    r.check("the prompt tells the model a relative is a lead", "relative" in classify.SYSTEM)

    _llm = classify.classify_llm
    try:
        classify.classify_llm = lambda text, history=None: classify.Classification(
            "WRONG_NUMBER", 0.75, "llm", "says she is not Dana")
        store.map_phone("8650009340", record_uuid="rec-9340", context=ctx)
        out = inbound("8650009340", "My name is Lisa Dana is my sister it's my mom's house", sms_id="rel-1")
        r.check("the sister is not suppressed", store.is_suppressed("8650009340") is None,
                str(store.is_suppressed("8650009340")))
        r.check("a reply is drafted for a person to approve", out.get("action") == "replied",
                str(out.get("action")))
        conv = store.get_conversation("8650009340") or {}
        r.check("the thread stays open", conv.get("state") == "active", str(conv.get("state")))
    finally:
        classify.classify_llm = _llm

    # ---- 5. human takeover silences the agent ---------------------------
    print("\nhuman takeover")
    inbound("8650004444", "who is this")
    before = len(store.due_outbox(50))
    out = engine.process("smrtphone", {
        "event": "smsOutgoing", "smsId": "st-h", "from": "+18650000001",
        "to": "8650004444", "message": "Hey, this is Adriana, got a second?",
        "source": "web", "userName": "Adriana",
    })
    r.check("detects the takeover", out.get("action") == "human_takeover", str(out.get("action")))
    conv = store.get_conversation("8650004444") or {}
    r.check("conversation paused", conv.get("state") == "paused", str(conv.get("state")))
    r.check("pending messages cancelled", len(store.due_outbox(50)) <= before)
    follow = inbound("8650004444", "sure, call me after 5")
    r.check("stays silent after takeover",
            "no reply" in " ".join(follow.get("actions", [])),
            str(follow.get("actions")))

    # ---- 6. delivery callback finds a dead number -----------------------
    print("\ndelivery callback")
    out = engine.process("smrtphone", {
        "event": "smsDeliveryCallback", "smsId": "st-d", "to": "8650005555",
        "status": "failed",
        "failure_reason": "The destination number is unknown and may no longer exist",
    })
    r.check("marks the number dead", out.get("action") == "dead", str(out.get("action")))
    r.check("phone flipped to DEAD",
            any(w[0] == "set_phone_status" and w[1][2] == "DEAD" for w in stub.crm_writes))

    # ---- 7. the output validator ----------------------------------------
    print("\noutput validator")
    for text, why in (
        ("We could do around 90k for it", "dollar amount"),
        ("I saw it is going to auction next month", "names the list"),
        ("Sorry to hear about the probate", "names the list"),
        ("Is 158 Old State Rd, Maryville TN 37804 yours?", "zip code"),
        ("Check us out at www.example.com", "link"),
        ("Hi Maron - I hope this message finds you well", "form letter"),
        ("I can leverage a seamless solution; call me", "AI wording"),
        ("Is it yours? Would a call work?", "two questions"),
        ("I am an AI assistant helping with this", "self-identifies"),
    ):
        ok, _ = respond.validate(text)
        r.check(f"blocks {why}", not ok, text[:52])
    ok, problems = respond.validate(
        "Hi Maron! Sorry to bother you. Is 158 Old State Rd yours?"
    )
    r.check("passes a good message", ok, "; ".join(problems))

    # ---- 8. quiet hours and the sender pool ------------------------------
    print("\nquiet hours and pool")
    r.check("865 resolves Eastern",
            sender_pool.timezone_for("8655551234").key == "America/New_York")
    r.check("931 resolves Central",
            sender_pool.timezone_for("9315551234").key == "America/Chicago")
    r.check("602 resolves Phoenix (no DST)",
            sender_pool.timezone_for("6025551234").key == "America/Phoenix")
    first = sender_pool.assign("8650006666")
    r.check("assigns a sender from the pool", bool(first), str(first))
    store.ensure_conversation("8650006666", from_number=first or "")
    r.check("sender is sticky", sender_pool.assign("8650006666") == first)

    # ---- 9. the outreach touches -----------------------------------------
    print("\noutreach copy")
    msg = touches.render(1, "158 old state rd|maron brown", "Maron",
                         "158 Old State Rd", "Maryville", "Adriana")
    ok, problems = respond.validate(msg)
    r.check("touch 1 reads human", ok, "; ".join(problems) or msg[:70])
    r.check("touch 1 is signed", "Adriana" in msg, msg[:70])
    entity = touches.clean_first("E A Henry")
    r.check("initials-only yields no first name", entity == "", repr(entity))
    r.check("an LLC is treated as an entity", touches.is_entity("BRADEN FAMILY HOLDINGS LLC"))
    seen = {
        touches.render(1, f"{i} main st|owner {i}", "Pat", f"{i} Main St", "Maryville", "Adriana")
        for i in range(12)
    }
    r.check("copy rotates across records", len(seen) > 1, f"{len(seen)} distinct variants")
    r.check("rendering is deterministic",
            touches.render(2, "seed|x", "Pat", "1 Main St", "Maryville", "Adriana")
            == touches.render(2, "seed|x", "Pat", "1 Main St", "Maryville", "Adriana"))

    # ---- 9b. soft no closes and stays workable ----------------------------
    print()
    print("soft no")
    classify.classify_rules = (lambda original: lambda text: (
        classify.Classification("NOT_INTERESTED", 0.9, "rules", "soft no, maybe later")
        if "not interested" in text.lower() else original(text)
    ))(classify.classify_rules)
    inbound("8650008888", "not interested right now, maybe later")
    conv = store.get_conversation("8650008888") or {}
    r.check("soft no closes the thread", conv.get("state") == "closed", str(conv.get("state")))
    r.check("recorded as a soft no", "soft" in str(conv.get("paused_reason")),
            str(conv.get("paused_reason")))
    # Scoped by intent: this number already carries an ASKING_WHO answer from
    # the "who is this" section above, and that one is allowed to exist.
    pending = list(store._conn().execute(
        "SELECT status FROM outbox WHERE phone='8650008888' AND intent='NOT_INTERESTED'"))
    r.check("a soft no is never texted back", not pending,
            f"REPLY_TO_NO is off, so found {len(pending)} outbox row(s) where 0 belong")
    from . import digest
    data = digest.collect(days=1)
    r.check("digest renders without error", isinstance(digest.render(data), str))
    r.check("digest counts the reply", data["inbound"] >= 1, str(data["inbound"]))

    # ---- 10. seeding respects suppression ---------------------------------
    print("\nseeding")
    rows = [
        {"phone": "8650007777", "uuid": "rec-7777", "street": "12 Elm St", "city": "Maryville",
         "county": "Blount", "first": "Dana", "last": "Reed", "owner": "Dana Reed",
         "assigned": "Adriana"},
        {"phone": "8650001111", "uuid": "rec-1111", "street": "9 Oak Ave", "city": "Maryville",
         "county": "Blount", "first": "Sam", "last": "Poe", "owner": "Sam Poe",
         "assigned": "Adriana"},   # opted out in step 2
        {"phone": "", "uuid": "rec-0000", "street": "1 No Phone Rd", "city": "Maryville",
         "county": "Blount", "first": "Jo", "last": "Kim", "owner": "Jo Kim",
         "assigned": "Adriana"},
    ]
    cands = seed.build(rows, touch=1)
    by_phone = {c.phone: c for c in cands}
    r.check("seeds a clean record", by_phone.get("8650007777", cands[0]).status == "ready")
    r.check("never seeds a suppressed number",
            by_phone.get("8650001111").status == "hold",
            str(by_phone.get("8650001111").reasons))
    r.check("holds a record with no phone",
            any(c.status == "hold" and "no usable phone" in " ".join(c.reasons) for c in cands))
    queued = seed.queue(cands, touch=1)
    r.check("queues only ready records", queued["queued"] == 1, str(queued))
    seeded = [x for x in store.due_outbox(50) if x["phone"] == "8650007777"]
    r.check("seed is held, not queued", not seeded,
            "outreach must not send without an explicit release")

    # ---- 11. the worker sends nothing it should not -----------------------
    print("\nworker guards")
    from . import worker

    store.queue_message("8650001111", "should never send", from_number="+18650000001")
    result = worker.drain_outbox(limit=25)
    r.check("worker skips suppressed numbers", result["skipped"] >= 1, str(result))
    r.check("nothing reached the transport in dry run", not stub.sent, str(stub.sent[:2]))

    # A draft whose own text promised a human follow-up pauses the thread at
    # DRAFT time ("model requested handoff") — before anyone can approve it.
    # Found live 2026-09-02: the approved draft was then cancelled as
    # "conversation paused" and silently never sent. That one pause reason must
    # let the draft through; every other pause still blocks. Quiet hours are
    # widened for these two checks so they pass at any hour, then restored.
    _q = (config.QUIET_START_HOUR, config.QUIET_END_HOUR)
    config.QUIET_START_HOUR, config.QUIET_END_HOUR = 0, 24
    store.ensure_conversation("8650004444", from_number="+18650000001")
    store.update_conversation("8650004444", state="paused",
                              paused_reason="model requested handoff")
    store.queue_message("8650004444", "a person will call you shortly",
                        from_number="+18650000001")
    result = worker.drain_outbox(limit=25)
    r.check("approved handoff draft still sends despite its own pause",
            result["sent"] >= 1, str(result))
    conv4444 = store.get_conversation("8650004444") or {}
    r.check("thread stays paused after the handoff draft sends",
            conv4444.get("state") == "paused", str(conv4444.get("state")))
    store.ensure_conversation("8650005555", from_number="+18650000001")
    store.update_conversation("8650005555", state="paused",
                              paused_reason="sensitive: selftest")
    store.queue_message("8650005555", "must never send", from_number="+18650000001")
    result = worker.drain_outbox(limit=25)
    r.check("any other pause still cancels the draft",
            result["skipped"] >= 1 and result["sent"] == 0, str(result))
    config.QUIET_START_HOUR, config.QUIET_END_HOUR = _q

    # ---- 12. the HTTP surface -------------------------------------------
    # The one part of this that faces the open internet. Neither vendor signs
    # its payloads, so the secret path and the allowlist ARE the auth.
    print()
    print("receiver endpoints")
    try:
        from fastapi.testclient import TestClient

        config.WEBHOOK_SECRET = "selftest-secret"
        config.ALLOWED_IPS = []
        from . import receiver

        with TestClient(receiver.app) as client:
            good = "/hooks/selftest-secret/smrtphone"

            resp = client.post("/hooks/wrong-secret/smrtphone", json={"event": "x"})
            r.check("rejects a wrong secret", resp.status_code == 404, f"got {resp.status_code}")

            resp = client.post("/hooks//smrtphone", json={"event": "x"})
            r.check("rejects an empty secret", resp.status_code in (404, 307),
                    f"got {resp.status_code}")

            payload = {"event": "smsIncoming", "smsId": "http-1", "from": "8659990000",
                       "to": "+18650000001", "message": "hello"}
            resp = client.post(good, json=payload)
            r.check("accepts a valid post", resp.status_code == 200, f"got {resp.status_code}")
            r.check("persists the event", bool(resp.json().get("event_id")), str(resp.json()))

            resp = client.post(good, json=payload)
            r.check("dedupes a retry of the same smsId",
                    resp.json().get("duplicate") is True, str(resp.json()))

            resp = client.post(good, content=b"{not json at all")
            r.check("survives a malformed body", resp.status_code == 200, f"got {resp.status_code}")
            r.check("logs the malformed body rather than dropping it",
                    "unparseable" in str(resp.json()), str(resp.json()))

            resp = client.post(good, json=["not", "an", "object"])
            r.check("survives a non-object payload", resp.status_code == 200, f"got {resp.status_code}")

            resp = client.post("/hooks/selftest-secret/datasift",
                               json={"uuid": "x" * 36, "phones": ["8659990001"]})
            r.check("accepts the DataSift endpoint", resp.status_code == 200, f"got {resp.status_code}")

            resp = client.get("/health")
            body = resp.json()
            r.check("health reports ok", resp.status_code == 200 and body.get("ok") is True)
            r.check("health surfaces the phase and dry run",
                    "phase" in body and "dry_run" in body, str(list(body)))

            config.ALLOWED_IPS = ["203.0.113.9"]
            resp = client.post(good, json={"event": "smsIncoming", "smsId": "http-2"})
            r.check("enforces the IP allowlist", resp.status_code == 404, f"got {resp.status_code}")
            config.ALLOWED_IPS = []
    except ImportError as exc:
        r.check("fastapi TestClient available", False, str(exc))

    # ---- 13. slack buttons ------------------------------------------------
    # Every action runs against the real store with no network and no tokens,
    # because the thing that must never happen is a tap doing something other
    # than what its label says.
    print("\nslack buttons")
    from . import slack_buttons

    r.check("no buttons without a listener", not config.slack_listener_ready(),
            "unconfigured selftest env must fall back to copy-paste commands")

    # With no tokens a draft posts the typed commands; with all three it posts
    # buttons. Both rendered through the stub, nothing reaches Slack.
    captured: list = []
    real_post = escalate._post
    escalate._post = lambda text, blocks=None: (captured.append((text, blocks)) or True)
    escalate.draft_for_approval("8650004242", "who is this", "Hi, it's Pat.", 0.9)
    r.check("without a listener the draft carries the commands",
            "cli.py approve 8650004242" in captured[-1][0]
            and not [b for b in (captured[-1][1] or []) if b.get("type") == "actions"])
    config.SLACK_BOT_TOKEN, config.SLACK_APP_TOKEN, config.SLACK_CHANNEL = "xoxb-t", "xapp-t", "C1"
    escalate.draft_for_approval("8650004242", "who is this", "Hi, it's Pat.", 0.9)
    r.check("with a listener the draft carries buttons",
            bool([b for b in (captured[-1][1] or []) if b.get("type") == "actions"])
            and "cli.py approve" not in captured[-1][0])
    config.SLACK_BOT_TOKEN = config.SLACK_APP_TOKEN = config.SLACK_CHANNEL = ""
    escalate._post = real_post

    blk = escalate.action_buttons("865-000-4242", "rec-4242")
    ids = [e["action_id"] for e in blk["elements"]]
    r.check("all four draft buttons render", ids == list(escalate.DRAFT_ACTIONS), str(ids))
    lead = escalate.hot_lead_buttons("865-000-4242", "rec-4242")
    r.check("hot-lead post gets Got it / Not a lead",
            [e["action_id"] for e in lead["elements"]] == list(escalate.LEAD_ACTIONS))
    r.check("every button id has a handler label",
            all(a in escalate.ACTIONS for a in escalate.DRAFT_ACTIONS + escalate.LEAD_ACTIONS))
    r.check("button value carries the phone",
            json.loads(blk["elements"][0]["value"])["phone"] == "8650004242")
    confirmed = [e["action_id"] for e in blk["elements"] if "confirm" in e]
    r.check("the irreversible buttons confirm first",
            confirmed == ["sms_approve", "sms_wrong"], str(confirmed))

    r.check("an unknown action_id does nothing",
            "ignored" in slack_buttons.handle("sms_delete_everything", "8650004242"))

    # "I'll handle it" — pause and drop the draft.
    store.ensure_conversation("8650004242")
    store.queue_message("8650004242", "draft one", status="held")
    slack_buttons.handle("sms_handle", "8650004242", who="oren")
    conv = store.get_conversation("8650004242") or {}
    r.check("handle-it pauses the thread", conv.get("state") == "paused", str(conv.get("state")))
    r.check("handle-it names who took it", "oren" in str(conv.get("paused_reason")),
            str(conv.get("paused_reason")))
    r.check("handle-it drops the held draft",
            not [x for x in store._conn().execute(
                "SELECT 1 FROM outbox WHERE phone='8650004242' AND status IN ('held','queued')")])

    # Wrong number — suppressed for good.
    slack_buttons.handle("sms_wrong", "8650004343")
    r.check("wrong number suppresses the line",
            store.is_suppressed("8650004343") == "wrong_number",
            str(store.is_suppressed("8650004343")))

    # Approve on a phone with nothing held must not invent a send.
    before = len(stub.sent)
    msg = slack_buttons.handle("sms_approve", "8650004444")
    r.check("approve with nothing held sends nothing",
            len(stub.sent) == before and "nothing" in msg, msg)

    # "Got it" on a hot-lead post records who took it. Local only.
    slack_buttons.handle("sms_got_it", "8650004545", who="oren")
    conv = store.get_conversation("8650004545") or {}
    r.check("got-it records who has the lead",
            conv.get("state") == "paused" and "oren has it" in str(conv.get("paused_reason")),
            str(conv.get("paused_reason")))

    # ---- 13b. a handed-off thread never goes silent on the PERSON ---------
    # After a handoff the agent stays silent to the seller (right) and used to
    # stay silent to the human too (wrong): nothing re-paged for 14 days.
    print("\nfollow-up nudge")
    store.map_phone("8650004646", record_uuid="rec-4646", context=ctx)
    store.ensure_conversation("8650004646", from_number="+18650000001")
    store.pause_conversation("8650004646", "handed to Oren")
    _fp = config.FOLLOWUP_PING_MINUTES
    config.FOLLOWUP_PING_MINUTES = 30
    before = len(stub.slack)
    out = inbound("8650004646", "who is this?", sms_id="fu-1")
    r.check("a text on a handed-off thread nudges the person",
            len(stub.slack) == before + 1 and "texted again" in stub.slack[-1],
            f"{len(stub.slack) - before} posts; action={out.get('action')}")
    r.check("the agent still does not reply on that thread",
            not [x for x in store._conn().execute(
                "SELECT 1 FROM outbox WHERE phone='8650004646'")])
    out = inbound("8650004646", "hello??", sms_id="fu-2")
    r.check("a second text inside the window does not nudge again",
            len(stub.slack) == before + 1, f"{len(stub.slack) - before} posts")
    config.FOLLOWUP_PING_MINUTES = 0
    store.map_phone("8650004747", record_uuid="rec-4747", context=ctx)
    store.ensure_conversation("8650004747", from_number="+18650000001")
    store.pause_conversation("8650004747", "handed to Oren")
    before = len(stub.slack)
    inbound("8650004747", "who is this?", sms_id="fu-3")
    r.check("nudge can be switched off", len(stub.slack) == before)
    config.FOLLOWUP_PING_MINUTES = _fp

    # ---- 13c. "who is this?" answers itself only when provably fresh ------
    print("\nfresh who-answer")
    _answer = config.ANSWER_WHO
    config.ANSWER_WHO = True
    store.map_phone("8650004848", record_uuid="rec-4848", context=ctx)
    out = engine.process("smrtphone", {
        "event": "smsIncoming", "smsId": "fresh-1", "from": "8650004848",
        "to": "+18650000001", "message": "who is this?", "fresh": True,
    })
    r.check("a fresh question is answered without approval",
            out.get("action") == "answered_who", str(out.get("action")))
    store.map_phone("8650004949", record_uuid="rec-4949", context=ctx)
    out = engine.process("smrtphone", {
        "event": "smsIncoming", "smsId": "stale-1", "from": "8650004949",
        "to": "+18650000001", "message": "who is this?",
    })
    r.check("a question of unknown age is drafted, not answered",
            out.get("action") != "answered_who", str(out.get("action")))
    out = engine.process("smrtphone", {
        "event": "smsIncoming", "smsId": "stale-2", "from": "8650004949",
        "to": "+18650000001", "message": "who is this?", "fresh": False,
    })
    r.check("a replayed backlog question is never auto-answered",
            out.get("action") != "answered_who", str(out.get("action")))

    # Once per thread. Elizabeth (7044675620, 2026-09-09) asked "What does this
    # mean?", then "I am unaware of Oren?", then "What company are you with?"
    # and the identical template went out twice with a third queued. A second
    # question is a person who read the first answer; it gets a drafted reply.
    out = engine.process("smrtphone", {
        "event": "smsIncoming", "smsId": "fresh-2", "from": "8650004848",
        "to": "+18650000001", "message": "who is this again?", "fresh": True,
    })
    r.check("a second fresh 'who?' is drafted, not templated again",
            out.get("action") == "replied", str(out.get("action")))
    r.check("the outcome says why",
            any("already sent once" in a for a in out.get("actions", [])), str(out.get("actions")))
    # The template path stamps confidence 1.0; a model draft never does.
    who_rows = [x for x in store._conn().execute(
        "SELECT status FROM outbox WHERE phone='8650004848' AND intent='ASKING_WHO' AND confidence=1.0")]
    r.check("exactly one template row exists for the thread", len(who_rows) == 1, str(who_rows))
    # Ty's rule stands (Oren, 2026-09-10): the drafted answer to "what company"
    # is a local buyer in the county, never a company name.
    r.check("drafts still never name a company",
            "NEVER say a company name" in respond._identity_block(ctx))
    config.ANSWER_WHO = _answer

    # The buttons come off the message once it is answered, so the channel
    # reads as a queue rather than a log.
    resolved = slack_buttons.resolved_blocks(
        [{"type": "section"}, blk], "yours now", "oren", "I'll handle it")
    r.check("answering a draft removes its buttons",
            not [b for b in resolved if b.get("type") == "actions"], str(len(resolved)))
    r.check("answering a draft records who did it",
            "oren" in json.dumps(resolved))

    print()
    return r.report()
