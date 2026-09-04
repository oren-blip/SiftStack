"""Parse Facebook-group harvest files (output/fb_harvest/<term>.json, written by
fb_group_harvest.py) for BUYER-intent posts and emit a review CSV.

    python fb_buyer_harvest_parse_20260903.py            # buyer terms only
    python fb_buyer_harvest_parse_20260903.py --all      # every term file

Buyer-prospector context: the harvest has NO post dates (Facebook obfuscates
them) and NO permalinks, so recency must come from deed data, never from here.
Output: output/charlotte_fb_group_buyers_<date>.csv  (one row per author,
phones aggregated, sample post text, matched terms, intent class).
READ-ONLY: nothing is uploaded to DataSift.
"""
import json, re, sys, argparse
from datetime import date
from pathlib import Path
import pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
HARV = ROOT / "output" / "fb_harvest"
BUYER_TERMS = ["cash buyer","cash buyers","buyers list","looking for deals","send me deals","looking to buy",
               "buy and hold","fix and flip","we buy houses","off market","wholesale deal",
               "add me to your buyers list","flipper","rental portfolio"]
INTENT = {
 "BUYER": re.compile(r"(looking (to|for) (buy|purchase) (a |an |another |more )?(house|home|propert|deal|lot|land|duplex|multi)|looking for (deals|off[- ]market|distressed|fixer|flips?)|send me (your )?(deals|off[- ]market|dispo)|add me to (your )?(buyers?|dispo|cash)|cash buyer|we buy (houses|homes|propert|land)|i buy (houses|homes|propert|land|lots)|buying (houses|homes|propert|land|lots|in charlotte)|actively (buying|acquiring)|fix (and|&|n) flip|buy (and|&|n) hold|rental portfolio|looking to (add|acquire) (to )?(my |our )?(portfolio|rentals)|close \d+[-–]?\d* deals? a month|need(ing)? to close \d+)", re.I),
 "WHOLESALER_SELLING": re.compile(r"\b(off[- ]market (deal|property|properties)|wholesale (deal|property)|under contract|assignment|arv|need(s)? (a )?buyer|jv|daily deals|contract price)\b", re.I),
}
# lenders advertise the same vocabulary as buyers but are NOT dispo targets
LENDER = re.compile(r"\b(hard money|dscr|bridge loan|100% financing|no down payment|lending solution|loan officer|we lend|funding (made simple|for real estate)|apply today|rates? as low as|ltv|points? and|capital (alliance|group|partners)|mortgage)\b", re.I)
# a tradesperson advertising services in a comment is not a buyer, even with a phone
TRADE_PITCH = re.compile(r"\b(give (us|me) a call|call me|licensed and insured|free estimate|we (do|install|service|offer)|dumpster|roll ?off|electric(al)? (and|&) hvac|plumbing (and|&)|hauling|junk removal|handyman|landscap|painting service|our company (does|offers)|linktr\.ee)\b", re.I)
# guard: buying MATERIALS or SERVICES is not buying PROPERTY
NOT_BUYER = re.compile(r"\b(freon|refrigerant|material|lumber|supplies|tools?|equipment|dryer vent|water heater|appliance|permit|insurance polic|software|crm|leads? list|course|coaching|mentorship)\b", re.I)
PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})")
BUYERS = ROOT / "output" / "fb_buyers"      # siftstack-11 schema: <gid>/*.json + <gid>/threads/*.json
CHARLOTTE_GID = "285310938318371"


def _thread_rows(gid_filter=None):
    """Commenter rows from fb_buyer_harvest.py thread files. The contact info in a
    recommendation / buyer-rollcall thread lives in the COMMENTS, not the post."""
    rows = []
    for tdir in sorted(BUYERS.glob("*/threads")):
        gid = tdir.parent.name
        if gid_filter and gid != gid_filter:
            continue
        for f in sorted(tdir.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for c in d.get("comments", []):
                rows.append({"author": (c.get("author") or "").strip(), "text": c.get("text", "") or "",
                             "phones": set(c.get("phones") or []), "term": f"thread:{d.get('post_kind','')}",
                             "comments": 0, "hrefs": [c.get("profile") or c.get("href") or ""],
                             "source": "comment",
                             # fb_buyer_harvest.py sets these; prefer them over our own regex
                             "lender_signal": bool(c.get("lender_signal")),
                             "buyer_signal": bool(c.get("buyer_signal"))})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every term file, not just buyer terms")
    ap.add_argument("--group", default=None, help="only this fb_buyers group id (e.g. the Charlotte gid)")
    a = ap.parse_args()
    files = sorted(HARV.glob("*.json"))
    if not a.all:
        want = {re.sub(r"[^a-z0-9]+","_",t).strip("_") for t in BUYER_TERMS}
        files = [f for f in files if f.stem in want]
    files += [f for f in sorted(BUYERS.glob("*/*.json")) if not a.group or f.parent.name == a.group]
    threads = _thread_rows(a.group)
    if not files and not threads: print("no harvest files yet in", HARV, "or", BUYERS); return 1
    by_author = {}
    for c in threads:
        rec = by_author.setdefault(c["author"] or "(unknown)", {"Author": c["author"], "Intent": set(), "Phones": set(),
                                   "Terms": set(), "Posts": 0, "Comments (max)": 0, "Sample Post": "", "Author Links": set(),
                                   "Source": set()})
        t = c["text"]
        # NOTE: fb_buyer_harvest.py's buyer_signal over-fires on short replies ("I'll DM you"),
        # so it is a tiebreaker, never sufficient on its own. Our own pattern must agree.
        if c.get("lender_signal") or LENDER.search(t):
            ci = "LENDER"
        elif INTENT["BUYER"].search(t) and not NOT_BUYER.search(t):
            ci = "BUYER"
        elif INTENT["WHOLESALER_SELLING"].search(t):
            ci = "WHOLESALER_SELLING"
        else:
            ci = "OTHER"
        rec["Intent"].add(ci)
        rec["Phones"] |= c["phones"]; rec["Terms"].add(c["term"]); rec["Posts"] += 1; rec["Source"].add("comment")
        # keep the text that TRIGGERED the class, not merely the first text seen
        if ci == "BUYER" and not rec.get("Evidence"):
            rec["Evidence"] = re.sub(r"\s+", " ", t)[:400]; rec["Evidence From"] = "comment"
        if not rec["Sample Post"]: rec["Sample Post"] = re.sub(r"\s+", " ", t)[:400]
        for h in c["hrefs"]:
            if h and "/user/" in h: rec["Author Links"].add("https://www.facebook.com" + h.split("?")[0] if h.startswith("/") else h.split("?")[0])
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        for post in d.get("posts", []):
            text = post.get("text","") or ""; author = (post.get("author") or "").strip()
            if not author:
                author = text.split("\n",1)[0].strip()[:60]
            if not author or len(text) < 30: continue
            phones = set(post.get("phones") or []) | {f"{m[0]}-{m[1]}-{m[2]}" for m in PHONE.findall(text)}
            neg = NOT_BUYER.search(text)
            kind = str(post.get("kind") or "")      # fb_buyer_harvest.py post_kind; may be "lender"
            if kind == "lender" or LENDER.search(text):
                intent = "LENDER"
            elif INTENT["BUYER"].search(text) and not neg:
                intent = "BUYER"
            elif INTENT["WHOLESALER_SELLING"].search(text):
                intent = "WHOLESALER_SELLING"
            else:
                intent = "OTHER"
            rec = by_author.setdefault(author, {"Author":author,"Intent":set(),"Phones":set(),"Terms":set(),"Posts":0,"Comments (max)":0,"Sample Post":"","Author Links":set(),"Source":set()})
            rec["Intent"].add(intent); rec["Phones"] |= phones; rec["Terms"].add(d.get("term", f.stem)); rec["Posts"] += 1; rec["Source"].add("post")
            try: cm = int(float(post.get("comments") or 0))
            except (TypeError, ValueError): cm = 0
            rec["Comments (max)"] = max(rec["Comments (max)"], cm)
            if intent == "BUYER" and not rec.get("Evidence"):
                rec["Evidence"] = re.sub(r"\s+"," ",text)[:400]; rec["Evidence From"] = "post"
            if intent == "BUYER" or not rec["Sample Post"]: rec["Sample Post"] = re.sub(r"\s+"," ",text)[:400]
            for h in (post.get("hrefs") or []):
                if "/user/" in h: rec["Author Links"].add("https://www.facebook.com" + h.split("?")[0])
    rows = []
    for r in by_author.values():
        pri = next((k for k in ("BUYER", "WHOLESALER_SELLING", "LENDER") if k in r["Intent"]), "OTHER")
        rows.append({"Author":r["Author"],"Intent":pri,"Phones":", ".join(sorted(r["Phones"])),"Terms":", ".join(sorted(r["Terms"])),
                     "Found in":", ".join(sorted(r.get("Source") or {"post"})),
                     "Trade/vendor pitch":"Yes" if TRADE_PITCH.search(r.get("Evidence") or r["Sample Post"]) else "",
                     "Posts":r["Posts"],"Comments (max)":r["Comments (max)"],"Author Links":", ".join(sorted(r["Author Links"]))[:300],
                     "Evidence (why classed)":r.get("Evidence",""),"Evidence From":r.get("Evidence From",""),"Sample Post":r["Sample Post"]})
    df = pd.DataFrame(rows).sort_values(["Intent","Posts","Comments (max)"], ascending=[True,False,False])
    out = ROOT / "output" / f"charlotte_fb_group_buyers_{date.today().isoformat()}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    ncom = int((df["Found in"].str.contains("comment")).sum())
    print(f"files: {len(files)} | comment rows: {len(threads)} | authors: {len(df)} ({ncom} from comments) | "
          f"BUYER: {(df.Intent=='BUYER').sum()} | wholesalers: {(df.Intent=='WHOLESALER_SELLING').sum()} | "
          f"lenders: {(df.Intent=='LENDER').sum()} | with phone: {(df.Phones!='').sum()}")
    print("->", out); return 0
if __name__ == "__main__": sys.exit(main())
