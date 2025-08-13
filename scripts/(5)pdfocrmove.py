import os
import shutil
from pathlib import Path

def move_non_ocr_pdfs(root_path, destination_folder):
    os.makedirs(destination_folder, exist_ok=True)
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            if filename.lower().endswith(".pdf") and "_ocr" not in filename.lower():
                source_path = Path(dirpath) / filename
                destination_path = Path(destination_folder) / filename
                shutil.move(source_path, destination_path)
                print(f"Moved: {source_path} -> {destination_path}")

# -------- USER CONFIGURATION --------
root_directory = Path("/path/to/search/root")
destination_directory = Path("/path/to/destination")
# -------------------------------------

move_non_ocr_pdfs(root_directory, destination_directory)
