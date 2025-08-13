# run_all_meetings_template.py
# One-shot pipeline: convert every WAV → MP3, transcribe, summarize.
# Use python run_all_meetings_template.py --base "/my/folder" --ffmpeg "/usr/bin/ffmpeg"

import os
import time
import subprocess
import openai
import whisper
import csv
from pathlib import Path
from datetime import datetime
from pydub import AudioSegment
from dotenv import load_dotenv
import tiktoken

# ---------- USER CONFIGURATION ------------------------------------------------
# Edit these paths for your environment
BASE            = Path(r"/path/to/project/folder")          # Base working directory
WAV_DIR         = BASE / "original_wavs"                    # Folder containing WAV files
MP3_DIR         = BASE / "converted_mp3s"                   # Folder to store converted MP3s
TXT_DIR         = BASE / "transcripts"                      # Folder to store transcriptions
SUM_DIR         = BASE / "summaries"                        # Folder to store summaries
LOGFILE         = BASE / "batch_log.txt"                    # Log file location
FFMPEG_EXE      = r"/path/to/ffmpeg"                        # Full path to ffmpeg executable
ENV_FILE        = BASE / ".env"                             # Path to .env file with OPENAI_API_KEY
# ------------------------------------------------------------------------------

# Ensure output folders exist
for d in (MP3_DIR, TXT_DIR, SUM_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Make sure Whisper can find ffmpeg
os.environ["PATH"] = os.path.dirname(FFMPEG_EXE) + os.pathsep + os.environ["PATH"]

# Load OpenAI API key from .env file
load_dotenv(ENV_FILE, override=True)
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise RuntimeError("OPENAI_API_KEY not found. Check your .env file.")

# ---------- Helper Functions ---------------------------------------------------
def log(msg):
    now = time.strftime("%H:%M:%S")
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(f"{now} - {msg}\n")
    print(f"{now} - {msg}")

def mp3_from_wav(wav: Path) -> Path:
    mp3 = MP3_DIR / (wav.stem + ".mp3")
    if mp3.exists():
        return mp3
    log(f"Converting {wav.name} → {mp3.name}")
    subprocess.run([FFMPEG_EXE, "-y", "-i", str(wav), str(mp3)], check=True)
    return mp3

def extract_date(name: str) -> str:
    parts = name.split("_")
    for p in parts:
        if len(p) == 10 and p[4] == "-" and p[7] == "-":
            try:
                return datetime.strptime(p, "%Y-%m-%d").strftime("%B %d, %Y")
            except ValueError:
                pass
    return "an unknown date"

# ---------- Load Whisper -------------------------------------------------------
log("Loading Whisper model… (first call is slow)")
whisper_model = whisper.load_model("medium")

enc = tiktoken.encoding_for_model("gpt-4")
MAX_TOK = 3000  # chunk-size safety margin

# ---------- Main Processing Loop -----------------------------------------------
log("\n=== Batch run started ===")
for wav in WAV_DIR.glob("*.wav"):
    name = wav.stem
    mp3  = mp3_from_wav(wav)
    txt  = TXT_DIR / f"{name}.txt"
    summ = SUM_DIR / f"{name}.summary.txt"

    # Transcription
    log(f"Transcribing {wav.name}")
    result = whisper_model.transcribe(str(wav))
    transcript = result["text"]
    txt.write_text(transcript, encoding="utf-8")

    # Summarization
    log(f"Summarizing {wav.name}")

    def pieces(text):
        tok = enc.encode(text)
        for i in range(0, len(tok), MAX_TOK):
            yield enc.decode(tok[i:i+MAX_TOK])

    chunk_summaries = []
    for n, piece in enumerate(pieces(transcript), 1):
        log(f"  ↳ chunk {n}")
        rsp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{
                "role": "user",
                "content": (
                    "Provide a concise summary of the following transcript "
                    "chunk so it can later be merged with other chunks.\n\n" + piece)
            }],
            temperature=0.3,
        )
        chunk_summaries.append(rsp.choices[0].message.content.strip())

    # Merge chunk summaries into a final summary
    merge_prompt = (
        "You are an expert historian and analyst specializing in educational policy.\n"
        "Your task is to create a detailed yet concise summary of the following board of education meeting transcript.\n"
        "Capture the key decisions, debates, and discussions, emphasizing any policy changes, budget concerns, societal influences, "
        "or controversies mentioned in the meeting.\n"
        "Provide historical context where applicable, indicating how these discussions may reflect broader educational trends of the time.\n"
        "Structure the summary in a way that would be useful to researchers, historians, professors, and educators.\n\n"
        + "\n\n---\n\n".join(chunk_summaries)
    )
    final_summary = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": merge_prompt}],
        temperature=0.2,
    ).choices[0].message.content.strip()

    summ.write_text(final_summary, encoding="utf-8")
    log(f"Finished {wav.name}")

    # Update index.csv
    index_path = BASE / "index.csv"
    header = ["file", "meeting_date", "duration_min", "word_count"]
    row = [
        wav.name,
        extract_date(name),
        round(AudioSegment.from_wav(wav).duration_seconds / 60, 2),
        len(transcript.split())
    ]

    new_file = not index_path.exists()
    with index_path.open("a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if new_file:
            writer.writerow(header)
        writer.writerow(row)

log("=== Batch run complete ===\n")
