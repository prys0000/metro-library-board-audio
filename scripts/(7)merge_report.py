import pandas as pd
from pathlib import Path

# -------- USER CONFIGURATION --------
SUMMARIES_FILE = Path("/path/to/meeting_summaries.csv")   # e.g., "1973-2_meeting_summaries.csv"
ATTENDEES_FILE = Path("/path/to/attendees.csv")           # e.g., "1973_attendees.csv"
OUTPUT_FILE    = Path("/path/to/output/merged.csv")       # e.g., "1973_merge.csv"
# -------------------------------------

# 1. Read the two sources
summaries_df = pd.read_csv(SUMMARIES_FILE)
compiled_df  = pd.read_csv(ATTENDEES_FILE)

# 2. Ensure the Date columns are datetime
summaries_df["Date"] = pd.to_datetime(summaries_df["Date"])
compiled_df["Date"]  = pd.to_datetime(compiled_df["Date"], errors="coerce")

# 3. Collapse attendees for each meeting
attendees_grouped = (
    compiled_df
    .groupby("Date")
    .apply(lambda x: x[["Category_1", "Category_2", "Name_1", "Name_2", "Title/Role"]]
           .to_dict(orient="records"))
    .reset_index(name="Attendees")
)

# 4. Merge and save
merged_df = pd.merge(summaries_df, attendees_grouped, on="Date", how="left")
merged_df.to_csv(OUTPUT_FILE, index=False)

print(f"Merged file saved as '{OUTPUT_FILE}'")
