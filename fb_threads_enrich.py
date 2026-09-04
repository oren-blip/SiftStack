"""Back-fill is_reply / reply_to onto thread files already on disk.

The distinction is recoverable from the stored aria-label, so threads harvested
before the harvester emitted these fields do not need re-opening (~2 min each).

Why it matters: two DIFFERENT people naming the same vendor is cross-validation,
the strongest signal in the sourcing playbook. A vendor replying to their own
thread under a second account is one self-promo wearing two names. Counting the
second as an independent vouch promotes a self-promoter to "call this one first".

    python fb_threads_enrich.py            # enrich in place, then report
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

THREADS = Path(__file__).resolve().parent / "output" / "fb_harvest" / "threads"


def clean_name(name: str) -> str:
    """Strip the trailing relative timestamp off a comment author.

    Must cover the wordy forms too: the digit-only pattern left "CharLit Paintings
    a year ago" intact, so it read as a second, different person naming the same
    number and the phone showed as cross-validated by one account talking to itself.
    """
    name = re.sub(r"\s+(\d+|an?)\s*(y|m|d|w|h|yr|mo|sec|min)s?\b.*$", "", name, flags=re.I)
    name = re.sub(r"\s+(\d+|an?)\s+(year|month|week|day|hour|minute|second)s?\s+ago.*$",
                  "", name, flags=re.I)
    return name.strip()


def strip_author_prefix(text: str, author: str) -> str:
    """Drop the leading "<author> 3y" that Facebook's innerText prepends.

    Without this, every comment literally contains its own author's name, so any
    "did the commenter name themselves?" test matches everything.
    """
    if not author:
        return text
    t = text.lstrip()
    if t.lower().startswith(author.lower()):
        t = t[len(author):].lstrip()
        t = re.sub(r"^(\d+|an?)\s*(y|m|d|w|h|yr|mo|sec|min)s?\b\s*", "", t, flags=re.I)
        t = re.sub(r"^(\d+|an?)\s+(year|month|week|day|hour|minute)s?\s+ago\s*", "", t, flags=re.I)
        t = re.sub(r"^(Follow|Edited)\s+", "", t, flags=re.I)
    return t.strip()


def enrich(c: dict) -> dict:
    c["author"] = clean_name(c.get("author", ""))
    c["body"] = strip_author_prefix(c.get("text", ""), c["author"])
    lab = c.get("label", "")
    c["is_reply"] = lab.startswith("Reply by")
    m = re.search(r" to (.+?)(?:'s comment|’s comment|$)", lab)
    c["reply_to"] = m.group(1).strip() if (c["is_reply"] and m) else ""
    return c


def main() -> int:
    files = sorted(THREADS.glob("*.json"))
    if not files:
        print("no thread files yet at", THREADS)
        return 1

    # A cross-validation must be two CUSTOMERS, not two staff. "At Ease Pest Solutions
    # would love to help you! We are local" and "At Ease Pest Solutions LLC, local,
    # veteran-owned" are both written in company voice - two employees advertising, not
    # two people vouching. Counting those promotes a self-promoter to top pick.
    SELF = re.compile(r"\b(i am|i'?m your|we are|we'?re|my company|our (team|company|shop)|"
                      r"call or text me|give me a call|dm me|would love to help|we offer|"
                      r"we do|i do|book (me|us)|free quote)\b", re.I)
    VOUCH = re.compile(r"\b(i recommend|highly recommend|recommend|used (him|her|them)|"
                       r"he (did|does)|she (did|does)|they (did|do)|did (a )?great|"
                       r"reach out to|call\b|great (job|work|guy)|been using|we use)\b", re.I)

    phone_sources: dict[str, set] = defaultdict(set)
    phone_toplevel: dict[str, set] = defaultdict(set)
    phone_vouchers: dict[str, set] = defaultdict(set)
    total = replies = 0

    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        for c in d.get("comments", []):
            enrich(c)
            total += 1
            replies += c["is_reply"]
            txt = c.get("body") or c.get("text", "")
            # These threads ARE referral requests, so a top-level answer naming a
            # vendor is a recommendation even without the words "I recommend" - the
            # commonest form is a bare "Jeff Parslow 704..." . Requiring explicit
            # vouch language scored every one of those as unclear and collapsed
            # cross-validation to zero. So: a vouch is anything that is NOT the vendor
            # talking about themselves.
            own = [w for w in clean_name(c.get("author", "")).split() if len(w) > 3]
            names_self = any(re.search(rf"\b{re.escape(w)}", txt, re.I) for w in own)
            c["voice"] = "self-promo" if (SELF.search(txt) or names_self) else "vouch"
            for p in c.get("phones", []):
                phone_sources[p].add(c.get("author", ""))
                if not c["is_reply"]:
                    phone_toplevel[p].add(c.get("author", ""))
                    if c["voice"] == "vouch":
                        phone_vouchers[p].add(c.get("author", ""))
        f.write_text(json.dumps(d, indent=1), encoding="utf-8")

    print(f"enriched {len(files)} thread files, {total} comments ({replies} replies)\n")

    # A phone named by 2+ people is only cross-validated if at least two of them said
    # so at top level - otherwise it is one voice using the reply box twice.
    real, suspect = [], []
    for phone, names in phone_sources.items():
        if len(names) < 2:
            continue
        # Genuine only when 2+ distinct people vouched AS CUSTOMERS at top level.
        (real if len(phone_vouchers.get(phone, set())) >= 2 else suspect).append(
            (phone, sorted(names), sorted(phone_vouchers.get(phone, set()))))

    print(f"phones named by 2+ commenters : {len(real) + len(suspect)}")
    print(f"  genuinely cross-validated   : {len(real)}")
    print(f"  only via replies (suspect)  : {len(suspect)}")
    for phone, names, top in suspect:
        print(f"    {phone}  named by {names} but only {len(top)} at top level")
    for phone, names, top in real:
        print(f"    CROSS-VALIDATED {phone}  {names}")

    # One row per comment that names a phone - the vendor leads the posts never had.
    import csv
    crossed = {p for p, _, _ in real}
    suspects = {p for p, _, _ in suspect}
    out = THREADS.parent / "fb_thread_leads.csv"
    rows = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        ask = " ".join(d.get("post_text", "").split())[:180]
        for c in d.get("comments", []):
            if not c.get("phones"):
                continue
            for p in c["phones"]:
                rows.append({
                    "phone": p,
                    "named_by": c.get("author", ""),
                    "is_reply": "reply" if c.get("is_reply") else "top-level",
                    "signal": "CROSS-VALIDATED" if p in crossed else
                              ("same-voice twice - treat as self-promo" if p in suspects else
                               "single mention"),
                    "comment": " ".join((c.get("body") or c.get("text", "")).split())[:400],
                    "thread_asked": ask,
                    "permalink": d.get("permalink", ""),
                    "source_file": f.name,
                })
    rows.sort(key=lambda r: (r["signal"] != "CROSS-VALIDATED", r["phone"]))
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(rows)} phone-bearing comments -> {out}")
    print(f"  distinct phones from comments: {len({r['phone'] for r in rows})}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
