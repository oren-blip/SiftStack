"""Render the merged private-lender list as a phone-readable call sheet (HTML).

    python build_lender_sheet.py                       # newest master CSV
    python build_lender_sheet.py --csv <path> --out <path.html>

The page is a working call sheet, not a report: tap a number to dial, mark each
lender Called / Interested / Pass, and the marks persist per viewer via the
artifact `db` capability so the phone and the desktop agree.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"


def norm_phone(v: str) -> str:
    d = re.sub(r"\D", "", v or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d if len(d) == 10 else ""


def pretty_phone(d: str) -> str:
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" if len(d) == 10 else ""


def load(csv_path: Path) -> list[dict]:
    out = []
    for i, r in enumerate(csv.DictReader(csv_path.open(encoding="utf-8-sig"))):
        cls = (r.get("Class") or "").strip()
        if "JUNK" in cls.upper():
            continue
        phones = [p for p in (norm_phone(x) for x in (r.get("Phones") or "").split(",")) if p]
        emails = [e.strip() for e in (r.get("Emails") or "").split(",") if e.strip()]
        src = (r.get("Source") or "").strip()
        check = (r.get("Check size") or "").strip()
        if src.startswith("subto"):
            lane, kind = "warm", "pace"
        elif "INDIVIDUAL" in cls.upper() or "LIKELY LENDER" in cls.upper():
            lane, kind = "cold", "individual"
        elif "BORROWER" in cls.upper():
            lane, kind = "cold", "borrower"
        else:
            lane, kind = "cold", "company"
        ev = " ".join((r.get("Evidence") or "").split())
        out.append({
            "i": i,
            "n": (r.get("Name") or "").strip()[:60],
            "p": phones[:2],
            "e": emails[:1],
            "c": check,
            "cv": int(re.sub(r"\D", "", check) or 0),
            "k": kind,
            "l": lane,
            "s": int(r.get("Score") or 0),
            "w": (r.get("Where") or "").strip()[:70],
            "q": ev[:180],
            "u": (r.get("Post") or r.get("Profile") or "").strip(),
        })
    return out


HTML = """<title>Private Money Call Sheet</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --ground:#e9edf0; --surface:#fff; --surface-2:#f4f6f8; --line:#d3dae0;
  --ink:#0f1720; --muted:#5b6a78;
  --brass:#8a5d16; --brass-soft:#f0e2c8; --cold:#2f6183; --cold-soft:#dfe9f1;
  --good:#1c6b50; --stop:#8a3324;
  --shadow:0 1px 2px rgba(15,23,32,.06),0 4px 14px rgba(15,23,32,.05);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#0d1319; --surface:#151d25; --surface-2:#1b242d; --line:#28343f;
  --ink:#e7edf2; --muted:#93a2b0;
  --brass:#d7a244; --brass-soft:#3a2e18; --cold:#7cb2d4; --cold-soft:#1b2c39;
  --good:#5cc79b; --stop:#e08a76;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 18px rgba(0,0,0,.3);
}}
:root[data-theme="dark"]{
  --ground:#0d1319; --surface:#151d25; --surface-2:#1b242d; --line:#28343f;
  --ink:#e7edf2; --muted:#93a2b0;
  --brass:#d7a244; --brass-soft:#3a2e18; --cold:#7cb2d4; --cold-soft:#1b2c39;
  --good:#5cc79b; --stop:#e08a76;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 6px 18px rgba(0,0,0,.3);
}
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);
  font-family:"IBM Plex Sans",ui-sans-serif,system-ui,sans-serif;line-height:1.45;
  padding:0 0 4rem;-webkit-text-size-adjust:100%}
.wrap{max-width:1180px;margin:0 auto;padding:0 clamp(.75rem,3vw,1.75rem)}

header{padding:clamp(1.25rem,4vw,2.25rem) 0 1rem}
h1{font-family:"Bricolage Grotesque","IBM Plex Sans",sans-serif;font-weight:800;
  font-size:clamp(1.5rem,4.5vw,2.35rem);letter-spacing:-.02em;margin:0;text-wrap:balance}
.sub{color:var(--muted);font-size:.95rem;margin:.4rem 0 0;max-width:62ch}
.tally{display:flex;flex-wrap:wrap;gap:.4rem .5rem;margin-top:1rem}
.tally b{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.tag{display:inline-flex;align-items:baseline;gap:.4rem;padding:.3rem .6rem;border-radius:2px;
  background:var(--surface);border:1px solid var(--line);font-size:.8rem;color:var(--muted)}

.bar{position:sticky;top:0;z-index:5;background:var(--ground);
  padding:.65rem 0 .6rem;border-bottom:1px solid var(--line);margin-bottom:1rem}
.bar .row{display:flex;flex-wrap:wrap;gap:.45rem}
input[type=search]{flex:1 1 14rem;min-width:0;padding:.5rem .7rem;border:1px solid var(--line);
  border-radius:2px;background:var(--surface);color:var(--ink);font:inherit;font-size:.9rem}
input[type=search]:focus-visible,button:focus-visible{outline:2px solid var(--brass);outline-offset:1px}
button{font:inherit;font-size:.82rem;padding:.45rem .7rem;border:1px solid var(--line);
  border-radius:2px;background:var(--surface);color:var(--muted);cursor:pointer}
button[aria-pressed="true"]{background:var(--ink);color:var(--ground);border-color:var(--ink)}
button .n{font-family:"IBM Plex Mono",monospace;opacity:.65;margin-left:.35rem}

.list{display:grid;gap:.5rem}
@media(min-width:900px){.list{grid-template-columns:1fr 1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--cold);
  border-radius:2px;padding:.7rem .8rem;box-shadow:var(--shadow);display:flex;flex-direction:column;gap:.4rem}
.card.warm{border-left-color:var(--brass)}
.card.done{opacity:.5}
.top{display:flex;gap:.5rem;align-items:flex-start;justify-content:space-between}
.nm{font-weight:600;font-size:.98rem;line-height:1.25}
.chip{font-family:"IBM Plex Mono",monospace;font-size:.72rem;font-weight:600;white-space:nowrap;
  padding:.15rem .4rem;border-radius:2px;background:var(--cold-soft);color:var(--cold)}
.chip.money{background:var(--brass-soft);color:var(--brass)}
.meta{font-size:.75rem;color:var(--muted);letter-spacing:.02em;text-transform:uppercase}
.q{font-size:.83rem;color:var(--muted);border-left:2px solid var(--line);padding-left:.55rem;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.contact{display:flex;flex-wrap:wrap;gap:.35rem .7rem;align-items:center}
.contact a{font-family:"IBM Plex Mono",monospace;font-size:.85rem;color:var(--ink);
  text-decoration:none;border-bottom:1px solid var(--brass);padding-bottom:1px}
.contact a.em{font-size:.78rem;border-bottom-color:var(--line);color:var(--muted);
  max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nonum{font-size:.78rem;color:var(--muted);font-style:italic}
.marks{display:flex;gap:.3rem;margin-left:auto}
.marks button{padding:.22rem .5rem;font-size:.72rem;border-radius:2px}
.marks button[aria-pressed="true"][data-v="called"]{background:var(--ink);color:var(--ground);border-color:var(--ink)}
.marks button[aria-pressed="true"][data-v="yes"]{background:var(--good);color:#fff;border-color:var(--good)}
.marks button[aria-pressed="true"][data-v="no"]{background:var(--stop);color:#fff;border-color:var(--stop)}
.empty{padding:2rem 0;color:var(--muted)}
.more{margin:1rem auto 0;display:block}
footer{color:var(--muted);font-size:.78rem;margin-top:2rem;border-top:1px solid var(--line);padding-top:.8rem}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>

<div class="wrap">
<header>
  <h1>Private Money Call Sheet</h1>
  <p class="sub">Every private lender we could find, in one list. <strong>Warm</strong> came off Pace Morby&rsquo;s PML lists and carries the check size they&rsquo;ll write. <strong>Cold</strong> came out of three Facebook lender groups &mdash; the quote is what they posted. Facebook strips post dates, so none of the cold rows carry one.</p>
  <div class="tally" id="tally"></div>
</header>

<div class="bar">
  <div class="row">
    <input type="search" id="q" placeholder="Search name, quote, or number" aria-label="Search lenders">
    <button data-f="lane" data-v="all" aria-pressed="true">All</button>
    <button data-f="lane" data-v="warm">Warm</button>
    <button data-f="lane" data-v="cold">Cold</button>
  </div>
  <div class="row" style="margin-top:.45rem">
    <button data-f="kind" data-v="all" aria-pressed="true">Everyone</button>
    <button data-f="kind" data-v="pace">Pace&rsquo;s list<span class="n" data-c="pace"></span></button>
    <button data-f="kind" data-v="individual">Individuals<span class="n" data-c="individual"></span></button>
    <button data-f="kind" data-v="company">Companies<span class="n" data-c="company"></span></button>
    <button data-f="kind" data-v="borrower">Borrowers<span class="n" data-c="borrower"></span></button>
    <button data-f="phone" data-v="1">Has a phone</button>
    <button data-f="open" data-v="1">Not yet called</button>
  </div>
</div>

<div class="list" id="list"></div>
<button class="more" id="more" hidden>Show more</button>
<footer id="foot"></footer>
</div>

<script>
const DATA = __DATA__;
const BUILT = "__BUILT__";
const KIND_LABEL = {pace:"Pace's list", individual:"Individual", company:"Company", borrower:"Borrower"};
const state = {lane:"all", kind:"all", phone:false, open:false, q:"", shown:60};
let marks = {};      // id -> "called" | "yes" | "no"
let db = null;

const list = document.getElementById("list");
const moreBtn = document.getElementById("more");

function money(v){ return v >= 1000 ? "$" + (v>=1000000 ? (v/1000000)+"M" : Math.round(v/1000)+"K") : ""; }

function matches(r){
  if (state.lane !== "all" && r.l !== state.lane) return false;
  if (state.kind !== "all" && r.k !== state.kind) return false;
  if (state.phone && !r.p.length) return false;
  if (state.open && marks[r.i]) return false;
  if (state.q){
    const hay = (r.n + " " + r.q + " " + r.w + " " + r.p.join(" ") + " " + r.e.join(" ")).toLowerCase();
    if (!hay.includes(state.q)) return false;
  }
  return true;
}

function card(r){
  const el = document.createElement("article");
  el.className = "card" + (r.l === "warm" ? " warm" : "") + (marks[r.i] ? " done" : "");
  const chip = r.cv ? `<span class="chip money">${money(r.cv)}</span>`
                    : `<span class="chip">${KIND_LABEL[r.k] || ""}</span>`;
  const phones = r.p.map(p => `<a href="tel:+1${p}">${p.slice(0,3)}-${p.slice(3,6)}-${p.slice(6)}</a>`).join("");
  const emails = r.e.map(e => `<a class="em" href="mailto:${e}">${e}</a>`).join("");
  const contact = (phones || emails)
      ? phones + emails
      : (r.u ? `<a class="em" href="${r.u}" target="_blank" rel="noopener">open their post</a>`
             : `<span class="nonum">no number yet</span>`);
  el.innerHTML =
    `<div class="top"><div><div class="nm"></div>
       <div class="meta">${r.l === "warm" ? "Warm &middot; " : ""}${r.w ? r.w.replace(/</g,"&lt;") : KIND_LABEL[r.k]}</div>
     </div>${chip}</div>` +
    (r.q ? `<p class="q"></p>` : "") +
    `<div class="contact">${contact}
       <span class="marks">
         <button data-v="called" aria-pressed="${marks[r.i]==="called"}">Called</button>
         <button data-v="yes" aria-pressed="${marks[r.i]==="yes"}">Interested</button>
         <button data-v="no" aria-pressed="${marks[r.i]==="no"}">Pass</button>
       </span>
     </div>`;
  el.querySelector(".nm").textContent = r.n;
  if (r.q) el.querySelector(".q").textContent = "\\u201c" + r.q + "\\u201d";
  el.querySelectorAll(".marks button").forEach(b => {
    b.addEventListener("click", () => setMark(r.i, b.dataset.v));
  });
  return el;
}

function render(){
  const rows = DATA.filter(matches);
  list.textContent = "";
  if (!rows.length){
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "Nobody matches those filters.";
    list.appendChild(p);
  }
  const frag = document.createDocumentFragment();
  rows.slice(0, state.shown).forEach(r => frag.appendChild(card(r)));
  list.appendChild(frag);
  moreBtn.hidden = rows.length <= state.shown;
  moreBtn.textContent = `Show more (${rows.length - state.shown} left)`;
  const done = Object.keys(marks).length;
  document.getElementById("foot").textContent =
    `${rows.length} of ${DATA.length} shown \\u00b7 ${done} marked \\u00b7 built ${BUILT}`
    + (db ? "" : " \\u00b7 marks are not saving in this view");
}

function setMark(id, v){
  if (marks[id] === v) delete marks[id]; else marks[id] = v;
  render();
  if (!db) return;
  const doc = db.doc("data/users/me/calls/" + id);
  (marks[id] ? doc.set({status: marks[id], at: Date.now()}) : doc.delete())
    .catch(() => {});
}

document.querySelectorAll("button[data-f]").forEach(b => {
  b.addEventListener("click", () => {
    const f = b.dataset.f, v = b.dataset.v;
    if (f === "lane" || f === "kind"){
      state[f] = v;
      document.querySelectorAll(`button[data-f="${f}"]`).forEach(o =>
        o.setAttribute("aria-pressed", String(o.dataset.v === v)));
    } else {
      state[f] = !state[f];
      b.setAttribute("aria-pressed", String(state[f]));
    }
    state.shown = 60;
    render();
  });
});
document.getElementById("q").addEventListener("input", e => {
  state.q = e.target.value.trim().toLowerCase(); state.shown = 60; render();
});
moreBtn.addEventListener("click", () => { state.shown += 60; render(); });

const counts = {};
DATA.forEach(r => counts[r.k] = (counts[r.k] || 0) + 1);
document.querySelectorAll("[data-c]").forEach(s => s.textContent = counts[s.dataset.c] || 0);
const withPhone = DATA.filter(r => r.p.length).length;
document.getElementById("tally").innerHTML =
  `<span class="tag">lenders <b>${DATA.length}</b></span>` +
  `<span class="tag">warm, with a check size <b>${DATA.filter(r=>r.l==="warm").length}</b></span>` +
  `<span class="tag">individuals in the groups <b>${DATA.filter(r=>r.l==="cold"&&r.k==="individual").length}</b></span>` +
  `<span class="tag">reachable by phone <b>${withPhone}</b></span>`;

render();

// Marks persist per viewer; the page works read-only if db never resolves.
(async () => {
  try {
    db = await claude.use("db");
    if (!db) return;
    const snap = await db.collection("data/users/me/calls").limit(1000).get();
    (snap.docs || snap || []).forEach(d => {
      const id = (d.id || "").split("/").pop();
      const v = (d.data ? d.data() : d).status;
      if (id && v) marks[id] = v;
    });
    render();
  } catch (e) { db = null; }
})();
</script>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    path = Path(args.csv) if args.csv else Path(sorted(glob.glob(str(OUT / "private_lenders_master_*.csv")))[-1])
    rows = load(path)
    html = (HTML.replace("__DATA__", json.dumps(rows, separators=(",", ":")))
                .replace("__BUILT__", datetime.now().strftime("%b %d").replace(" 0", " ")))
    dest = Path(args.out) if args.out else OUT / "private_lender_call_sheet.html"
    dest.write_text(html, encoding="utf-8")
    print(f"{len(rows)} lenders from {path.name} -> {dest}  ({dest.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
