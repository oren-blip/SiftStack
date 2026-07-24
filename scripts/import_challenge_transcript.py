"""Convert a 5 Day Deal Flow Challenge webinar transcript into the knowledge library.

Accepts .vtt, .docx, .md, or .txt exports and writes clean markdown into
knowledge/5-day-deal-flow/transcripts/ so the transcripts stay greppable.

Source quality, best first:
    1. Zoom ``*.transcript.vtt``  -- real speaker names ("Ty Garrett:")
    2. AssemblyAI ``*.docx``      -- diarized, but speakers are "Student 1/2/3"
    3. Zoom ``*.cc.vtt``          -- closed captions, NO speaker labels at all

Usage:
    python scripts/import_challenge_transcript.py "C:/Users/omark/Downloads/GMT20260715-165954_Recording.transcript.vtt"
    python scripts/import_challenge_transcript.py ~/Downloads/*.vtt

Day number and recording date are inferred from the filename when possible --
either ``DAY 2 ... 2026-07-14`` or Zoom's ``GMT20260715-165954`` naming. Pass
--day / --date to override.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPT_DIR = REPO_ROOT / "knowledge" / "5-day-deal-flow" / "transcripts"

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Zoom names recordings by date, not by challenge day, so map them.
CHALLENGE_DATES = {
    "2026-07-13": 1,
    "2026-07-14": 2,
    "2026-07-15": 3,
    "2026-07-16": 4,
    "2026-07-17": 5,
}

# Merge consecutive cues from the same speaker until this many seconds of
# spoken time have accumulated, so paragraphs stay readable instead of one
# line per caption.
VTT_PARAGRAPH_SECONDS = 45


def docx_to_text(path: Path) -> str:
    """Extract paragraph text from a .docx without external dependencies."""
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")

    root = ElementTree.fromstring(xml)
    lines: list[str] = []

    for para in root.iter(f"{W_NS}p"):
        parts: list[str] = []
        for node in para.iter():
            if node.tag == f"{W_NS}t":
                parts.append(node.text or "")
            elif node.tag == f"{W_NS}tab":
                parts.append("\t")
            elif node.tag == f"{W_NS}br":
                parts.append("\n")
        lines.append("".join(parts).strip())

    return "\n".join(lines)


CUE_TIME = re.compile(
    r"^(?:(\d{2}):)?(\d{2}):(\d{2})[.,]\d{3}\s*-->\s*(?:\d{2}:)?\d{2}:\d{2}[.,]\d{3}"
)


def vtt_to_text(path: Path) -> str:
    """Flatten a WebVTT file into ``[HH:MM:SS] Speaker: text`` paragraphs.

    Handles both Zoom flavors: ``*.transcript.vtt`` prefixes each cue with a
    speaker name, ``*.cc.vtt`` has none. Consecutive cues from the same speaker
    are merged so the result reads like prose rather than captions.
    """
    raw = path.read_text(encoding="utf-8-sig", errors="replace")

    cues: list[tuple[int, str | None, str]] = []
    start: int | None = None
    buffered: list[str] = []

    def flush() -> None:
        if start is None or not buffered:
            return
        text = " ".join(buffered).strip()
        speaker: str | None = None
        # "Ty Garrett: What's going on" -- a name, not a mid-sentence colon.
        match = re.match(r"^([A-Z][\w.'-]*(?: [\w.'-]+){0,3}):\s+(.*)$", text)
        if match and len(match.group(1)) <= 40:
            speaker, text = match.group(1), match.group(2)
        if text:
            cues.append((start, speaker, text))

    for line in raw.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or line.isdigit():
            continue
        match = CUE_TIME.match(line)
        if match:
            flush()
            hours, minutes, seconds = match.group(1) or "0", match.group(2), match.group(3)
            start = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            buffered = []
        elif start is not None:
            buffered.append(line)
    flush()

    paragraphs: list[str] = []
    para_start: int | None = None
    para_speaker: str | None = None
    para_parts: list[str] = []

    def emit() -> None:
        if para_start is None or not para_parts:
            return
        stamp = f"[{para_start // 3600:02d}:{para_start % 3600 // 60:02d}:{para_start % 60:02d}]"
        body = " ".join(para_parts)
        paragraphs.append(f"{stamp} {para_speaker}: {body}" if para_speaker else f"{stamp} {body}")

    for at, speaker, text in cues:
        rolled_over = para_start is not None and at - para_start >= VTT_PARAGRAPH_SECONDS
        if para_start is None or speaker != para_speaker or (speaker is None and rolled_over):
            emit()
            para_start, para_speaker, para_parts = at, speaker, [text]
        else:
            para_parts.append(text)
    emit()

    return "\n\n".join(paragraphs)


def read_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return docx_to_text(path)
    if suffix == ".vtt":
        return vtt_to_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def infer_date(name: str) -> str | None:
    match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", name)
    return "-".join(match.groups()) if match else None


def infer_day(name: str) -> int | None:
    """Day number from an explicit "DAY 3" label, else from the recording date."""
    match = re.search(r"day[\s_-]*(\d)", name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    date = infer_date(name)
    return CHALLENGE_DATES.get(date) if date else None


def source_quality(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".transcript.vtt"):
        return "Zoom transcript (named speakers)"
    if name.endswith(".cc.vtt"):
        return "Zoom closed captions (NO speaker labels)"
    if path.suffix.lower() == ".docx":
        return "AssemblyAI diarization (speakers numbered, not named)"
    return "plain text"


def normalize(text: str) -> str:
    """Collapse runaway blank lines and normalize smart punctuation."""
    replacements = {
        "\u2014": "--",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u00a0": " ",
        "\u00b7": "-",
        "\u2026": "...",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="+", help="transcript file(s): .vtt, .docx, .md, or .txt")
    parser.add_argument("--day", type=int, help="challenge day number (1-5)")
    parser.add_argument("--date", help="recording date, YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="overwrite an existing transcript")
    args = parser.parse_args()

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    for raw in args.source:
        src = Path(raw).expanduser()
        if not src.exists():
            print(f"[skip] not found: {src}")
            continue

        day = args.day or infer_day(src.name)
        date = args.date or infer_date(src.name)
        if day is None:
            print(f"[skip] could not infer day number from {src.name} -- pass --day N")
            continue

        body = normalize(read_source(src))
        turns = len(re.findall(r"^\[\d{2}:\d{2}:\d{2}\]", body, re.MULTILINE))
        quality = source_quality(src)
        speakers = sorted(set(re.findall(r"^\[\d{2}:\d{2}:\d{2}\] ([^:]{1,40}):", body, re.MULTILINE)))

        header = [
            f"# 5 Day Deal Flow Challenge -- Day {day}",
            "",
            f"- Recorded: {date or 'unknown'}",
            f"- Source file: `{src.name}`",
            f"- Source quality: {quality}",
            f"- Timestamped turns: {turns}",
            f"- Speakers: {', '.join(speakers) if speakers else 'NOT LABELED -- captions only'}",
            "",
            "---",
            "",
        ]

        out = TRANSCRIPT_DIR / f"day-{day}{'-' + date if date else ''}.md"
        if out.exists() and not args.force:
            print(f"[skip] exists (use --force): {out.name}")
            continue

        out.write_text("\n".join(header) + body + "\n", encoding="utf-8")
        print(f"[ok] {src.name} -> {out.relative_to(REPO_ROOT)}")
        print(f"     {quality}; {len(body):,} chars, {turns} turns, {len(speakers)} named speakers")

    return 0


if __name__ == "__main__":
    sys.exit(main())
