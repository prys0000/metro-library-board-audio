#!/usr/bin/env python
"""
transcribe_and_summarise_template.py
Whisper → GPT-4o *strict* pipeline for Board-of-Education meetings.

Outputs per meeting folder
-------------------------
* `[name]_transcript.(txt|md)` – verbatim transcript.
* `[name]_summary.(txt|md)`    – strict narrative summary (facts only).
* `[name]_outline.(txt|md)`    – bullet outline (facts only).
* `[name]_decisions.csv`       – structured motions/votes table.

Dependencies:
    pip install openai-whisper pandas openai torch tqdm tiktoken
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import List, Set

import pandas as pd
import tiktoken
import torch
import whisper
from openai import OpenAI
from tqdm import tqdm

# ─────────────────────────────────────────────────────────────────────────────
# USER CONFIGURATION (edit or pass via CLI)
# ─────────────────────────────────────────────────────────────────────────────
API_KEY: str = ""  # ← your OpenAI key or leave empty to pass via environment
AUDIO_ROOT: str = "/path/to/meeting_audio_root"
BOARD_CSV: str = "/path/to/board_members.csv"
DEFAULT_MODEL: str = "medium"  # whisper model size
# ─────────────────────────────────────────────────────────────────────────────

PART_RE = re.compile(r"_part_(\d+)", re.IGNORECASE)
ENC = tiktoken.encoding_for_model("gpt-4o-mini")

def natural_key(path: Path) -> int:
    m = PART_RE.search(path.stem)
    return int(m.group(1)) if m else 0

def load_whisper(name: str) -> whisper.Whisper:
    if torch.cuda.is_available():
        return whisper.load_model(name)
    return whisper.load_model(name, device="cpu", fp16=False)

def load_board_members(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        print(f"[WARN] Board CSV not found: {csv_path}")
        return pd.DataFrame()
    return pd.read_csv(csv_path)

def _transcribe_part(model: whisper.Whisper, wav: Path, word_ts: bool) -> str:
    res = model.transcribe(str(wav), word_timestamps=word_ts, verbose=False)
    return res["text"].strip()

def transcribe_parts(model: whisper.Whisper, wavs: List[Path], word_ts: bool) -> List[str]:
    return [_transcribe_part(model, wav, word_ts) for wav in tqdm(wavs, desc="Transcribing", unit="part")]

STRICT_SUMMARY_PROMPT = (
    "You are an impartial meeting scribe. Summarise the following board-of-education "
    "meeting transcript using concise paragraphs. Include ONLY information that is "
    "explicitly present in the transcript.Do NOT add background knowledge, opinions, "
    "interpretations or historical context beyond what is written. Emphasise key decisions, "
    "debates, motions, votes, budget discussions and controversies when they appear."
)
STRICT_OUTLINE_PROMPT = (
    "Create a chronological bullet‑point outline of the meeting. Use ONLY facts explicitly "
    "found in the transcript. No external information or assumptions."
)
STRICT_DECISIONS_PROMPT = (
    "Identify every motion, resolution or vote that is explicitly recorded in the transcript. "
    "Return them as a JSON array, each item formatted: {\"motion\": str, \"result\": str, "
    "\"yes\": int|null, \"no\": int|null}. If the transcript contains none, return an empty array []."
)
FUSE_PROMPT = (
    "Merge the following partial summaries into a single coherent summary, ensuring you keep "
    "ONLY the information that appears explicitly in the partials, with no additional detail."
)

def num_tokens(text: str) -> int:
    return len(ENC.encode(text))

def gpt_call(client: OpenAI, prompt: str, text: str, temp: float = 0.0) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        temperature=temp,
    )
    return response.choices[0].message.content.strip()

def _write(path: Path, txt: str):
    path.write_text(txt, encoding="utf-8")
    print(f"→ {path.name}")

def write_md(path: Path, heading: str, body: str):
    _write(path, f"# {heading}\n\n{body}")

def write_csv(path: Path, records: List[dict]):
    if not records:
        print("→ no decisions found")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    print(f"→ {path.name}")

def summarise_with_gpt(full_text: str, client: OpenAI):
    tokens = num_tokens(full_text)
    if tokens < 7300:
        narrative = gpt_call(client, STRICT_SUMMARY_PROMPT, full_text)
        outline = gpt_call(client, STRICT_OUTLINE_PROMPT, full_text)
        decisions_json = gpt_call(client, STRICT_DECISIONS_PROMPT, full_text)
    else:
        max_chunk = 6000
        paras = full_text.split("\n")
        chunks, buf, cnt = [], [], 0
        for p in paras:
            t = num_tokens(p) + 1
            if cnt + t > max_chunk and buf:
                chunks.append("\n".join(buf))
                buf, cnt = [], 0
            buf.append(p)
            cnt += t
        if buf:
            chunks.append("\n".join(buf))
        partials = [gpt_call(client, STRICT_SUMMARY_PROMPT, ch) for ch in chunks]
        narrative = gpt_call(client, FUSE_PROMPT, "\n\n".join(partials))
        outline = gpt_call(client, STRICT_OUTLINE_PROMPT, narrative)
        decisions_json = gpt_call(client, STRICT_DECISIONS_PROMPT, narrative)

    try:
        decisions = json.loads(decisions_json)
        if not isinstance(decisions, list):
            decisions = []
    except json.JSONDecodeError:
        decisions = []

    return narrative, outline, decisions

def process_meeting(folder: Path, args, board_df: pd.DataFrame, client: OpenAI):
    print(f"\n📂 {folder}")
    wavs = sorted(folder.glob("*_part_*.wav"), key=natural_key)
    if not wavs:
        print("   · no parts – skip")
        return
    model = load_whisper(args.model)
    parts = transcribe_parts(model, wavs, word_ts=args.word_ts)

    header = []
    try:
        _, _, date_str, _ = folder.name.split("_")
        year = date_str.split("-")[0]
        mask = board_df["year_range"].astype(str).str.contains(year, na=False)
        members = board_df.loc[mask, "name"].tolist()
        if members:
            header.append("Board Members: " + ", ".join(members))
    except Exception:
        pass

    full_text = "\n".join(header + parts)

    _write(folder / f"{folder.name}_transcript.txt", full_text)
    if not args.no_md:
        write_md(folder / f"{folder.name}_transcript.md", "Transcript", full_text)
    if args.heuristic_only:
        return

    narrative, outline, decisions = summarise_with_gpt(full_text, client)
    _write(folder / f"{folder.name}_summary.txt", narrative)
    _write(folder / f"{folder.name}_outline.txt", outline)
    if not args.no_md:
        write_md(folder / f"{folder.name}_summary.md", "Summary", narrative)
        write_md(folder / f"{folder.name}_outline.md", "Outline", outline)
    write_csv(folder / f"{folder.name}_decisions.csv", decisions)

def discover_meeting_folders(root: Path, recursive: bool) -> List[Path]:
    if not recursive:
        return [root]
    wav_dirs: Set[Path] = {p.parent for p in root.rglob("*_part_*.wav")}
    return sorted(wav_dirs, key=lambda p: p.as_posix())

def parse_cli(argv: List[str] | None = None):
    p = argparse.ArgumentParser("Whisper→GPT summariser for BOE meetings")
    p.add_argument("source", nargs="?", default=AUDIO_ROOT, help="Meeting folder or root")
    p.add_argument("--csv", default=BOARD_CSV, help="Board-member lookup CSV")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Whisper model size")
    p.add_argument("--word-ts", action="store_true", help="Include word timestamps")
    p.add_argument("--recursive", action="store_true", help="Recurse into sub-folders")
    p.add_argument("--no-md", action="store_true", help="Skip Markdown outputs")
    p.add_argument("--heuristic-only", action="store_true", help="Only write transcript (skip GPT)")
    return p.parse_args(argv)

def main(argv: List[str] | None = None):
    args = parse_cli(argv)
    root = Path(args.source).expanduser().resolve()
    board_df = load_board_members(Path(args.csv).expanduser().resolve())
    client = OpenAI(api_key=API_KEY or None)
    meetings = discover_meeting_folders(root, args.recursive)
    for m in meetings:
        process_meeting(m, args, board_df, client)
    print("✅ done")

if __name__ == "__main__":
    main()
