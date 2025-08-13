---

# Scripts – Meeting Minutes OCR & Summarization Pipeline

This folder contains a collection of Python scripts designed to process historical meeting minutes from scanned PDFs, run OCR if needed, generate structured summaries using OpenAI’s API, and merge those summaries with attendance records for archival research and publication.

---

## **Scripts Overview**

### 1. **`pdf_ocr_converter.py`**

Automates OCR conversion for scanned PDF meeting minutes.

* Detects non-searchable PDFs and converts them to OCR-enabled versions.
* Uses Tesseract OCR to produce text layers for downstream processing.
* Preserves original files in a configurable directory.
* **Use case**: Ensure all meeting minutes PDFs are text-searchable before summarization.

### 2. **`fixed_pdf_ocr.py`**

Refined version of the OCR script with:

* Better file handling and error reporting.
* Automatic skip for already searchable PDFs.
* Improved folder structure handling for large archival collections.

### 3. **`pdfocrmove.py`**

Organizes and moves processed OCR PDFs.

* Moves completed OCR files from a working directory to an archival folder.
* Handles duplicate detection and naming conflicts.

### 4. **`74summs.py`**

AI-assisted summarization tool for OCR PDFs.

* Extracts text from PDFs using **PyMuPDF**.
* Cleans and normalizes text, removing OCR artifacts.
* Uses OpenAI’s GPT models to create:

  * **Synopsis** – 3–7 sentence overview.
  * **Detailed Summary** – key decisions, motions, discussions.
  * **Key Notes** – bulleted list of votes, appointments, finances, and other specifics.
* Handles truncation for very large documents.
* Outputs results to a CSV with one row per meeting.

### 5. **`meeting_minutes_summarizer.py`**

A more advanced summarization script with:

* Logging for processing progress.
* Automatic OCR-version prioritization if both OCR and non-OCR versions exist.
* More robust date extraction from filenames or folder structures.
* Fallback “short summary” mode for extremely long PDFs that hit API limits.
* Clean CSV export with `Date`, `PDF_File`, `Synopsis`, `Summary`, and `Key Notes`.

### 6. **`merge_meeting_data.py`**

Combines summaries with compiled attendee lists.

* Reads **meeting\_summaries.csv** and **attendees.csv**.
* Groups attendees by meeting date into a JSON-like list.
* Merges with summaries on the `Date` field.
* Outputs a merged CSV with both the summaries and attendance data.

---


## **Example Folder Structure**

### **Before Processing**

```
meeting_minutes_raw/
├── 1973_01_15.pdf      # Scanned, non-searchable PDF
├── 1973_02_12.pdf
├── 1973_03_19.pdf
└── attendees/
    ├── 1973_attendees.csv
    ├── 1974_attendees.csv
```

---

### **After OCR Conversion** (`pdf_ocr_converter.py` or `fixed_pdf_ocr.py`)

```
meeting_minutes_ocr/
├── 1973_01_15_OCR.pdf  # Searchable PDF
├── 1973_02_12_OCR.pdf
├── 1973_03_19_OCR.pdf
```

---

### **After Summarization** (`74summs.py` or `meeting_minutes_summarizer.py`)

```
output_summaries/
├── 1973_meeting_summaries.csv
└── logs/
    ├── processing_log.txt
```

**`1973_meeting_summaries.csv` Example:**

| Date       | PDF\_File             | Synopsis                    | Summary         | Key\_Notes             |
| ---------- | --------------------- | --------------------------- | --------------- | ---------------------- |
| 1973-01-15 | 1973\_01\_15\_OCR.pdf | The board met to discuss... | Full summary... | Bulleted key points... |

---

### **After Merging with Attendance Data** (`merge_meeting_data.py`)

```
merged_output/
└── 1973_merge.csv
```

**`1973_merge.csv` Example:**

| Date       | PDF\_File             | Synopsis | Summary | Key\_Notes | Attendees                             |
| ---------- | --------------------- | -------- | ------- | ---------- | ------------------------------------- |
| 1973-01-15 | 1973\_01\_15\_OCR.pdf | ...      | ...     | ...        | \[{"Category\_1":"Board",...}, {...}] |

---

## **Requirements**

* **Python** 3.8+

* **Libraries**:

  ```bash
  pip install pandas python-dotenv PyMuPDF openai pytesseract
  ```

* **OCR Tools**:

  * [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
  * (Optional, Recommended) [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) for better OCR accuracy and page handling.

* **OpenAI API key** stored in a `.env` file:

  ```
  OPENAI_API_KEY=your_api_key_here
  ```

---

## **Use Case**

These scripts were built for an **archival digitization and research project** involving decades of Oklahoma City Board of Education meeting minutes. The tools automate the tedious steps of OCR conversion, text cleaning, structured AI summarization, and attendee data integration, producing clean datasets for public access and scholarly research.

---

