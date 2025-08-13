# Metro Library Audio Digitization Project

A collaborative digital preservation initiative between the **Carl Albert Congressional Research and Studies Center** and the **Metropolitan Library System** focused on digitizing and processing historical audio materials and meeting documentation.

## Project Overview

This repository contains tools and processes for preserving historical audio recordings and meeting minutes from the Oklahoma City Board of Education. The project combines audio digitization, transcription, and text processing to create searchable, accessible digital archives.

## Repository Structure

```
├── audio-processing/           # Audio digitization and transcription tools
├── text-processing/           # Meeting minutes processing scripts
├── original_wavs/            # Source audio files
├── transcripts/              # Generated transcripts
├── summaries/               # AI-generated summaries
├── quality-control/         # QC scripts and logs
└── documentation/           # Process workflows and guidelines
```

## Audio Processing Workflow

### First Run Process (`1_run_all_meetings.py`)
```
original_wavs → convert to mp3 → transcription → summaries
```

### Enhanced Audio Processing Workflow (`run_all_meetings.py`)

This comprehensive workflow ensures high-quality digitization and processing:

```
📁 original_wavs 
    ↓
🎛️ re-edit wav/enhance using podcast, Izotope, or Premiere Enhance 
    ↓
✂️ split audio files into <3000 token chunks 
    ↓
🔍 error check for drop-outs, speed variations, spectral anomalies, file structure 
    ↓
📝 transcribe 
    ↓
📋 summaries 
    ↓
✏️ check word structure, spelling, coherency, double words 
    ↓
✅ verify facts of new summaries with transcriptions 
    ↓
🔄 re-check for errors 
    ↓
🎵 convert to mp3 
    ↓
📊 create log/index
```

**Workflow Stages:**
1. **Audio Enhancement** - Professional audio editing and noise reduction
2. **Chunking** - Split into manageable segments for processing
3. **Quality Control** - Automated detection of audio anomalies
4. **Transcription** - AI-powered speech-to-text conversion
5. **Summarization** - Generate structured meeting summaries
6. **Text Validation** - Grammar, spelling, and coherency checks
7. **Fact Verification** - Cross-reference summaries with transcriptions
8. **Final QC** - Comprehensive error checking
9. **Format Conversion** - Create distribution-ready MP3s
10. **Documentation** - Generate processing logs and index files


### Audio Processing Components

#### Transcription Process
- ✅ Loads Whisper model (`whisper.load_model("medium")`)
- ✅ Processes all `.wav` files in `original_wavs` directory
- ✅ Transcribes using Whisper AI
- ✅ Saves transcripts as `.txt` files in `transcripts` folder

#### Text Processing & Chunking
- ✅ Splits transcripts into ≤3,000 token chunks
- ✅ Uses `tiktoken` for encoding/decoding
- ✅ Creates temporary summaries for each chunk
- ✅ Logs processing progress

#### Adaptive Model Assisted Summarization
- ✅ Sends transcript chunks for AI summarization
- ✅ Generates structured summaries with historical context
- ✅ Merges chunk summaries into final comprehensive recap
- ✅ Saves final summaries in `summaries` folder

## Quality Control System

### QC Level 1: Basic Validation
1. **File Integrity & Audio Length Checks**
   - ✅ Ensures every WAV has corresponding MP3, transcript, and summary
   - ✅ Confirms MP3 and WAV durations match
   - ✅ Detects corrupt or unreadable files

2. **Transcription Quality Checks**
   - ✅ Detects dropped sections or unnaturally short transcripts
   - ✅ Identifies repeated words and AI glitches
   - ✅ Flags missing key terms or discussions

3. **Summary Verification**
   - ✅ Ensures summaries faithfully represent key discussions and decisions
   - ✅ Flags missing or misrepresented information
   - ✅ Validates historical accuracy and context

4. **Grammar & Spelling Corrections**
   - ✅ Uses LanguageTool API for corrections
   - ✅ Ensures readability before archiving

5. **Historical Data Validation**
   - ✅ Extracts meeting dates from filenames (e.g., `board_1975-06-12.wav`)
   - ✅ Verifies expected participant names are mentioned
   - ✅ Flags missing or incorrect dates/names

6. **Issues Logging & Reporting**
   - ✅ Generates detailed QC report (`qc_issues_log.txt`)
   - ✅ Logs audio mismatches, missing names, validation errors
   - ✅ Provides pass/fail status for each file


---
## Text Minutes Processing Workflow

### Image Organization & PDF Creation
```bash
# 1. Organize images into meeting folders
python (1)debug_meeting_organizer.py "E:\1976-downloaded_pages" "E:\1976-downloaded_pages\output"

# 2. Create PDFs from images
python (2)pdf_ocr_converter.py "E:\1974downloaded_pages\output"
```

### OCR Processing
```powershell
# Clear environment variable and run OCR
Remove-Item Env:OPENAI_API_KEY
python (4)fixed_pdf_ocr.py "E:\1974downloaded_pages\output"

# Move non-OCR PDFs to separate folder
python (5)pdfocrmove.py

# Generate summaries from OCR'd documents
python (6)74summs.py

# Merge information into final CSV report
python (7)merge.py
```

### AI Summarization Prompt
The system uses specialized prompts for historical accuracy:

```
You are a professional historian and archivist specializing in Oklahoma City Board of Education meetings. 
This is a meeting from {date}. Using only the content provided below, generate a structured summary with:

1. **Synopsis:** Overview (3-7 sentences) of main theme, issues, context
2. **Summary:** Detailed summary of discussions, decisions, actions, motions, legal and financial statements
3. **Key Notes:** Specific motions, resolutions, votes, personnel actions, financial matters

Guidelines:
- Use only information present in the text
- Include specific names, amounts, and dates
- Note votes and outcomes
- Highlight personnel changes and financial decisions
- Flag unclear or incomplete text
```

## Key Scripts

| Script | Purpose |
|--------|---------|
| `1_run_all_meetings.py` | Initial audio processing pipeline |
| `Enhanced_1_run_all_meetings.py` | Enhanced audio processing with quality checks |
| `(1)debug_meeting_organizer.py` | Organize images by meeting date |
| `(2)pdf_ocr_converter.py` | Convert images to PDF |
| `(3)-clear API KEY.txt`  | Clear API Key-clean run |
| `(4)fixed_pdf_ocr.py` | Add OCR to existing PDFs |
| `(5)pdfocrmove.py` | Organize OCR'd vs non-OCR'd files |
| `(6)74summs.py` | Generate AI summaries from OCR'd text |
| `(7)merge.py` | Merge all data into final CSV report |

## Partnership

This project operates under formal agreement between:
- **Carl Albert Congressional Research and Studies Center** - Digitization expertise and audio services
- **Metropolitan Library System** - Archival materials and preservation requirements

## Goals

Preserve historical audio recordings and meeting documentation while making them accessible through modern digital formats, searchable text, and comprehensive summaries suitable for researchers and the public.

---

*Supporting long-term preservation of Oklahoma City Board of Education historical materials through collaborative digital humanities work.*
