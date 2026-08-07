"""Render deep-prospecting research packs (.md) to PDF.

WHY: the packs are written as Markdown, but a PDF is what uploads cleanly into a
DataSift record's Files tab and what a caller can actually read on a phone. The
deep-prospecting skill referenced this renderer; it had never been built.

Design notes:
  * Heir maps and dial sheets live in ``` fences and are ASCII art -- they are
    rendered in Courier with alignment preserved, never re-flowed.
  * Reportlab's base-14 fonts are Latin-1 only, so the marker glyphs used in the
    packs (dagger, check, arrow, ...) would render as black boxes. They are
    transliterated to single-width ASCII, which keeps the heir-map columns lined
    up AND keeps the legend self-consistent (the legend text is transliterated
    by the same table, so "+ = Verified DECEASED" still reads correctly).

Usage:
    python src/deep_prospect_pdf.py output/reports/DP_Week32_Baker_*.md
    python src/deep_prospect_pdf.py --all          # every .md in output/reports
"""
from __future__ import annotations

import argparse
import glob
import html
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

REPORT_DIR = os.path.join("output", "reports")

# Glyphs the packs use -> Latin-1 safe equivalents (single width where it
# matters, so ASCII heir-map columns stay aligned).
_GLYPHS = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...",
    "†": "+",    # dagger  = deceased
    "✓": "v",    # check   = verified living
    "▸": ">",    # triangle= recommended decision-maker
    "●": "o",    # circle  = current owner on title
    "→": "->", "←": "<-",
    "⚠": "!", "★": "*", "•": "-",
    " ": " ",
}


def _ascii(s: str) -> str:
    for k, v in _GLYPHS.items():
        s = s.replace(k, v)
    # anything still outside Latin-1 would render as a black box
    return s.encode("latin-1", "replace").decode("latin-1")


def _inline(s: str) -> str:
    """Markdown inline -> reportlab mini-HTML. Escapes first, so text is safe."""
    s = _ascii(s)
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", s)
    # [label](url) -> label (url shown small, since a printed link is dead text)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
               r'\1 <font size="7" color="#555555">\2</font>', s)
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)  # wiki-links from memory notes
    return s


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontSize=15, spaceAfter=8,
                             textColor=colors.HexColor("#14532d")),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=11,
                             spaceAfter=5, textColor=colors.HexColor("#166534")),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontSize=10.5, spaceBefore=8,
                             spaceAfter=3, textColor=colors.HexColor("#374151")),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontSize=9, leading=12.5,
                               alignment=TA_LEFT, spaceAfter=5),
        "bullet": ParagraphStyle("bullet", parent=ss["BodyText"], fontSize=9, leading=12.5,
                                 leftIndent=14, bulletIndent=4, spaceAfter=2),
        "code": ParagraphStyle("code", fontName="Courier", fontSize=7.6, leading=9.2,
                               backColor=colors.HexColor("#f5f5f4"),
                               borderPadding=5, leftIndent=2),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.6, leading=9.5),
        "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=7.6,
                                leading=9.5, textColor=colors.white),
    }


def _table(rows: list[list[str]], st) -> Table | None:
    if not rows:
        return None
    ncol = max(len(r) for r in rows)
    data = []
    for i, r in enumerate(rows):
        r = list(r) + [""] * (ncol - len(r))
        style = st["cellh"] if i == 0 else st["cell"]
        data.append([Paragraph(_inline(c), style) for c in r])
    avail = 7.0 * inch
    t = Table(data, colWidths=[avail / ncol] * ncol, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#166534")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d4d4d4")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#fafaf9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def md_to_flowables(md: str, st) -> list:
    out: list = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        # fenced code -> monospace block, alignment preserved
        if ln.lstrip().startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                buf.append(_ascii(lines[i]))
                i += 1
            i += 1
            body = html.escape("\n".join(buf), quote=False).replace("\n", "<br/>")
            body = body.replace(" ", "&nbsp;")
            out.append(Spacer(1, 4))
            out.append(Paragraph(body, st["code"]))
            out.append(Spacer(1, 6))
            continue
        # markdown table
        if ln.strip().startswith("|") and ln.strip().endswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
                    rows.append(cells)
                i += 1
            t = _table(rows, st)
            if t is not None:
                out.append(Spacer(1, 3))
                out.append(t)
                out.append(Spacer(1, 7))
            continue
        s = ln.strip()
        if not s:
            i += 1
            continue
        if s.startswith("### "):
            out.append(Paragraph(_inline(s[4:]), st["h3"]))
        elif s.startswith("## "):
            out.append(Paragraph(_inline(s[3:]), st["h2"]))
        elif s.startswith("# "):
            out.append(Paragraph(_inline(s[2:]), st["h1"]))
        elif re.match(r"^[-*]\s+", s):
            out.append(Paragraph(_inline(re.sub(r"^[-*]\s+", "", s)),
                                 st["bullet"], bulletText="-"))
        elif re.match(r"^\d+[.)]\s+", s):
            m = re.match(r"^(\d+)[.)]\s+(.*)$", s)
            out.append(Paragraph(_inline(m.group(2)), st["bullet"],
                                 bulletText=f"{m.group(1)}."))
        elif set(s) <= {"-", "="} and len(s) >= 3:
            out.append(Spacer(1, 5))
        else:
            out.append(Paragraph(_inline(s), st["body"]))
        i += 1
    return out


def render(md_path: str, pdf_path: str | None = None) -> str:
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    pdf_path = pdf_path or os.path.splitext(md_path)[0] + ".pdf"
    st = _styles()
    doc = SimpleDocTemplate(
        pdf_path, pagesize=LETTER,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title=os.path.splitext(os.path.basename(md_path))[0],
        author="SiftStack deep prospecting",
    )
    doc.build(md_to_flowables(md, st))
    return pdf_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help=".md research packs")
    ap.add_argument("--all", action="store_true",
                    help=f"render every .md in {REPORT_DIR}")
    args = ap.parse_args()
    paths: list[str] = []
    for p in args.paths:
        paths.extend(glob.glob(p))
    if args.all or not paths:
        paths.extend(sorted(glob.glob(os.path.join(REPORT_DIR, "*.md"))))
    paths = sorted(set(paths))
    if not paths:
        raise SystemExit("no .md packs found")
    for p in paths:
        try:
            out = render(p)
            print(f"  {os.path.basename(p)} -> {os.path.basename(out)} "
                  f"({os.path.getsize(out) / 1024:.0f} KB)")
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED {p}: {type(e).__name__} {e}")
    print(f"\n{len(paths)} pack(s) processed -> {REPORT_DIR}")


if __name__ == "__main__":
    main()
