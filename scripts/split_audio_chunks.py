# split_audio_chunks.py
import os
import subprocess
from pathlib import Path

# -------- USER CONFIGURATION --------
SOURCE_FOLDER = Path("/path/to/source_wavs")      # Folder containing input WAV files
OUTPUT_FOLDER = Path("/path/to/output_chunks")    # Folder to save split WAVs
CHUNK_SECONDS = 30 * 60  # Duration per chunk in seconds (30 minutes default)
# -------------------------------------

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

def split_audio_ffmpeg(input_path, output_dir, base_name, chunk_seconds):
    """Split WAV file into chunks using ffmpeg."""
    command = [
        "ffmpeg",
        "-i", str(input_path),
        "-f", "segment",
        "-segment_time", str(chunk_seconds),
        "-c", "copy",
        str(output_dir / f"{base_name}_part_%03d.wav")
    ]
    subprocess.run(command, check=True)

# Process all .wav files
for wav_file in SOURCE_FOLDER.glob("*.wav"):
    print(f"Splitting {wav_file.name}...")
    split_audio_ffmpeg(
        wav_file,
        OUTPUT_FOLDER,
        wav_file.stem,
        CHUNK_SECONDS
    )
    print(f"✔ Done splitting {wav_file.name}")

print("All files processed.")
