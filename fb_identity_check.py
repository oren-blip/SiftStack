"""Identity pass over the harvested threads, keyed on Facebook's numeric user id.

Display names are NOT identity. B2L Construction's two "independent" recommendations
turned out to be the company's licence qualifier commenting as "Jld Dixon" and
"JD Wes" - two real, different-looking strings, one human. Neither phone matching
nor name matching can see that. The group user id can.

    python fb_identity_check.py                 # whole-corpus report
    python fb_identity_check.py 980-297-3841    # audit specific phones

Reads only fields Facebook produced (author, uid, phones). It never reads a field
this pipeline wrote, so it cannot confirm our own conclusions back to us.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

THREADS = Path(__file__).resolve().parent / "output" / "fb_harvest" / "threads"


def main(argv: list[str]) -> int:
    files = sorted(THREADS.glob("*.json"))
    if not files:
        print("no thread files at", THREADS)
        return 1

    uid_names: dict[str, set] = defaultdict(set)   # uid -> display names used
    name_uids: dict[str, set] = defaultdict(set)   # display name -> uids
    phone_uids: dict[str, set] = defaultdict(set)  # phone -> uids that named it
    phone_rows: dict[str, list] = defaultdict(list)
    have_uid = no_uid = 0

    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        for c in d.get("comments", []):
            uid, name = c.get("uid", ""), (c.get("author") or "").strip()
            if uid:
                have_uid += 1
                uid_names[uid].add(name)
                name_uids[name].add(uid)
            else:
                no_uid += 1
            for p in c.get("phones", []):
                if uid:
                    phone_uids[p].add(uid)
                phone_rows[p].append((f.name, name, uid,
                                      "reply" if c.get("is_reply") else "top"))

    print(f"{len(files)} thread files | {have_uid} comments with a uid, "
          f"{no_uid} without\n")

    # THE test: one account posting under more than one display name.
    aliases = {u: n for u, n in uid_names.items() if len(n) > 1}
    print(f"ACCOUNTS USING MULTIPLE DISPLAY NAMES: {len(aliases)}")
    for uid, names in sorted(aliases.items(), key=lambda kv: -len(kv[1]))[:20]:
        print(f"  uid {uid}: {sorted(names)}")

    # The reverse: one display name across several accounts (impersonation, or two
    # real people who share a common name - do not treat this as proof of anything).
    shared = {n: u for n, u in name_uids.items() if len(u) > 1 and n}
    print(f"\nDISPLAY NAMES SEEN ON MULTIPLE ACCOUNTS: {len(shared)}")
    for name, uids in sorted(shared.items(), key=lambda kv: -len(kv[1]))[:10]:
        print(f"  {name!r}: {sorted(uids)}")

    targets = argv or []
    if targets:
        print("\n=== PHONE AUDIT ===")
        for p in targets:
            rows = phone_rows.get(p, [])
            uids = phone_uids.get(p, set())
            print(f"\n{p}: named in {len({r[0] for r in rows})} thread(s) by "
                  f"{len({r[1] for r in rows})} display name(s), "
                  f"{len(uids)} distinct account(s)")
            for fn, name, uid, kind in rows:
                print(f"    {fn:<34} {name[:24]:<24} uid={uid or '-':<18} {kind}")
            if len(uids) == 1 and len({r[1] for r in rows}) > 1:
                print("    ^ ONE ACCOUNT, MULTIPLE DISPLAY NAMES - not independent")
            elif len(uids) >= 2:
                print(f"    ^ {len(uids)} distinct accounts - independent on identity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
