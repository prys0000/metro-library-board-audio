import os
import csv
import fitz  # PyMuPDF
from datetime import datetime
from pathlib import Path
import openai
from dotenv import load_dotenv
import re
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load API key from .env file
load_dotenv()

# Set up OpenAI client (updated for newer versions)
try:
    # For newer openai library versions (1.0+)
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    USE_NEW_API = True
except ImportError:
    # For older openai library versions
    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    USE_NEW_API = False

class MeetingMinutesSummarizer:
    def __init__(self, root_dir, output_csv, max_chars=20000):
        self.root_dir = Path(root_dir)
        self.output_csv = Path(output_csv)
        self.max_chars = max_chars  # Limit for API calls (reduced for token limits)
        
        # Statistics
        self.stats = {
            'total_found': 0,
            'processed': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def find_pdf_files(self):
        """Find all PDF files, prioritizing OCR versions"""
        pdf_files = {}
        
        # Walk through all directories
        for pdf_file in self.root_dir.rglob("*.pdf"):
            # Skip backup files
            if pdf_file.name.endswith('.backup') or 'backup' in pdf_file.name.lower():
                continue
            
            # Extract date from filename or parent folder
            date_key = self.extract_date_key(pdf_file)
            if not date_key:
                continue
            
            # Prioritize OCR versions
            if date_key not in pdf_files:
                pdf_files[date_key] = pdf_file
            elif '_ocr' in pdf_file.name and '_ocr' not in pdf_files[date_key].name:
                # Replace with OCR version if available
                pdf_files[date_key] = pdf_file
                logger.info(f"Using OCR version: {pdf_file.name}")
        
        self.stats['total_found'] = len(pdf_files)
        return pdf_files
    
    def extract_date_key(self, pdf_file):
        """Extract date key from filename or folder name"""
        # Try filename first (e.g., "1970-01-05_meeting_minutes_ocr.pdf")
        filename_patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD format
            r'(\d{4}_\d{2}_\d{2})',  # YYYY_MM_DD format
        ]
        
        for pattern in filename_patterns:
            match = re.search(pattern, pdf_file.name)
            if match:
                date_str = match.group(1).replace('_', '-')
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                    return date_str
                except ValueError:
                    continue
        
        # Try parent folder name (e.g., "1970-01-05" folder)
        parent_patterns = [
            r'^(\d{4}-\d{2}-\d{2})$',  # Exact YYYY-MM-DD format
        ]
        
        for pattern in parent_patterns:
            match = re.match(pattern, pdf_file.parent.name)
            if match:
                date_str = match.group(1)
                try:
                    datetime.strptime(date_str, "%Y-%m-%d")
                    return date_str
                except ValueError:
                    continue
        
        return None
    
    def extract_text_from_pdf(self, pdf_path):
        """Extract text from PDF using PyMuPDF"""
        try:
            text = ""
            with fitz.open(pdf_path) as doc:
                for page_num, page in enumerate(doc):
                    page_text = page.get_text()
                    if page_text.strip():  # Only add non-empty pages
                        text += f"\n--- Page {page_num + 1} ---\n"
                        text += page_text
                        text += "\n"
            
            # Clean up the text
            text = self.clean_text(text)
            
            # Truncate if too long
            if len(text) > self.max_chars:
                logger.warning(f"Text truncated from {len(text)} to {self.max_chars} characters")
                text = text[:self.max_chars] + "\n\n[TEXT TRUNCATED DUE TO LENGTH]"
            
            return text
            
        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {e}")
            return ""
    
    def clean_text(self, text):
        """Clean and normalize extracted text"""
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Remove common OCR artifacts
        text = re.sub(r'[^\w\s\.,;:!?\-\(\)\[\]"\'/\$%&@#]', ' ', text)
        
        # Fix common OCR mistakes in meeting minutes
        replacements = {
            ' tho ': ' the ',
            ' ard ': ' and ',
            ' mado ': ' made ',
            ' soconded ': ' seconded ',
            ' moeting ': ' meeting ',
            ' minutos ': ' minutes ',
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text.strip()
    
    def generate_summary(self, text, date_str):
        """Generate structured summary using OpenAI"""
        if not text.strip():
            return {
                "synopsis": "No readable text found in PDF",
                "summary": "Unable to extract text content",
                "key_notes": "N/A"
            }
        
        # Additional truncation for very long texts to ensure we fit in token limits
        # GPT-4 has ~8192 tokens, and we need space for the prompt too
        max_text_chars = 15000  # Conservative limit to leave room for prompt
        if len(text) > max_text_chars:
            text = text[:max_text_chars] + "\n\n[TEXT TRUNCATED - DOCUMENT WAS LONGER]"
            logger.warning(f"Text further truncated to {max_text_chars} characters for API limits")
        
        prompt = (
            "You are a professional historian and archivist specializing in Oklahoma City Board of Education meetings. "
            f"This is a meeting from {date_str}. "
            "Using only the content provided below, generate a structured summary with the following sections:\n\n"
            "1. **Synopsis:** An overview (3-7 sentences) of meeting's main theme, issues, context.\n"
            "2. **Summary:** A detailed summary of discussions, decisions, actions taken, motions, legal and financial statements and reports, controversies, and notable processes.\n"
            "3. **Key Notes:** List specific motions, resolutions, votes, personnel actions, financial matters, and significant issues discussed.\n\n"
            "Important guidelines:\n"
            "- Use only information present in the text\n"
            "- Include specific names, amounts, and dates when mentioned\n"
            "- Note any votes and their outcomes\n"
            "- Highlight personnel changes, appointments, or resignations\n"
            "- Mention significant financial decisions or budget items\n"
            "- If text is unclear or incomplete, note this limitation\n\n"
            f"Meeting Minutes Text:\n{text}"
        )
        
        try:
            if USE_NEW_API:
                # Use new OpenAI client with gpt-3.5-turbo (larger context window and cheaper)
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo-16k",  # 16k context window model
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=2000
                )
                content = response.choices[0].message.content
            else:
                # Use legacy OpenAI API
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo-16k",  # 16k context window model
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=2000
                )
                content = response['choices'][0]['message']['content']
            
            # Parse the response into sections
            return self.parse_summary_response(content)
            
        except Exception as e:
            logger.error(f"Error generating summary for {date_str}: {e}")
            
            # If we still hit token limits, try with even shorter text
            if "context_length_exceeded" in str(e) or "maximum context length" in str(e):
                logger.info(f"  Retrying with shorter text...")
                return self.generate_summary_short(text[:8000], date_str)  # Much shorter
            
            return {
                "synopsis": f"Error generating summary: {str(e)}",
                "summary": "Unable to process due to API error",
                "key_notes": "N/A"
            }
    
    def generate_summary_short(self, text, date_str):
        """Generate summary with much shorter text for problematic documents"""
        prompt = (
            f"Summarize this Oklahoma City Board of Education meeting from {date_str}. "
            "Provide:\n"
            "1. **Synopsis:** Brief overview (1-2 sentences)\n"
            "2. **Summary:** Key discussions and decisions\n"
            "3. **Key Notes:** Important motions, votes, personnel changes, financial matters\n\n"
            f"Meeting text:\n{text}"
        )
        
        try:
            if USE_NEW_API:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",  # Standard model
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1500
                )
                content = response.choices[0].message.content
            else:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1500
                )
                content = response['choices'][0]['message']['content']
            
            return self.parse_summary_response(content)
            
        except Exception as e:
            logger.error(f"Even shorter summary failed for {date_str}: {e}")
            return {
                "synopsis": f"Could not process - text too long: {str(e)}",
                "summary": "Document too long for processing",
                "key_notes": "Unable to extract due to length"
            }
    
    def parse_summary_response(self, content):
        """Parse the AI response into structured sections"""
        synopsis = ""
        summary = ""
        key_notes = ""
        
        current_section = None
        lines = content.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Detect section headers
            if re.match(r'^\*?\*?synopsis\*?\*?:?', line, re.IGNORECASE):
                current_section = 'synopsis'
                # Extract content after the header if on same line
                synopsis_content = re.sub(r'^\*?\*?synopsis\*?\*?:?\s*', '', line, flags=re.IGNORECASE)
                if synopsis_content:
                    synopsis = synopsis_content
                continue
            elif re.match(r'^\*?\*?summary\*?\*?:?', line, re.IGNORECASE):
                current_section = 'summary'
                summary_content = re.sub(r'^\*?\*?summary\*?\*?:?\s*', '', line, flags=re.IGNORECASE)
                if summary_content:
                    summary = summary_content
                continue
            elif re.match(r'^\*?\*?key notes?\*?\*?:?', line, re.IGNORECASE):
                current_section = 'key_notes'
                notes_content = re.sub(r'^\*?\*?key notes?\*?\*?:?\s*', '', line, flags=re.IGNORECASE)
                if notes_content:
                    key_notes = notes_content
                continue
            
            # Add content to current section
            if line and current_section:
                if current_section == 'synopsis':
                    synopsis += (" " + line) if synopsis else line
                elif current_section == 'summary':
                    summary += (" " + line) if summary else line
                elif current_section == 'key_notes':
                    key_notes += (" " + line) if key_notes else line
        
        return {
            "synopsis": synopsis.strip() or "No synopsis provided",
            "summary": summary.strip() or "No summary provided", 
            "key_notes": key_notes.strip() or "No key notes provided"
        }
    
    def process_meeting_minutes(self):
        """Process all PDFs and generate summaries"""
        logger.info(f"Starting processing of PDFs in: {self.root_dir}")
        
        # Find all PDF files
        pdf_files = self.find_pdf_files()
        
        if not pdf_files:
            logger.warning("No PDF files found to process")
            return
        
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        # Sort by date
        sorted_dates = sorted(pdf_files.keys())
        
        rows = []
        start_time = time.time()
        
        for i, date_str in enumerate(sorted_dates, 1):
            pdf_path = pdf_files[date_str]
            logger.info(f"[{i}/{len(pdf_files)}] Processing {date_str}: {pdf_path.name}")
            
            try:
                # Extract text
                text = self.extract_text_from_pdf(pdf_path)
                
                if not text.strip():
                    logger.warning(f"No text extracted from {pdf_path.name}")
                    self.stats['failed'] += 1
                    continue
                
                logger.info(f"  Extracted {len(text)} characters of text")
                
                # Generate summary
                logger.info("  Generating AI summary...")
                summary = self.generate_summary(text, date_str)
                
                # Add to results
                rows.append({
                    "Date": date_str,
                    "PDF_File": pdf_path.name,
                    "Synopsis": summary["synopsis"],
                    "Summary": summary["summary"],
                    "Key Notes": summary["key_notes"]
                })
                
                self.stats['processed'] += 1
                logger.info(f"  ✅ Successfully processed {date_str}")
                
                # Rate limiting - be nice to the API
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"  ❌ Error processing {pdf_path.name}: {e}")
                self.stats['failed'] += 1
                continue
        
        # Write results to CSV
        self.write_to_csv(rows)
        
        # Print summary
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info("\n" + "=" * 60)
        logger.info("PROCESSING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total files found: {self.stats['total_found']}")
        logger.info(f"Successfully processed: {self.stats['processed']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Processing time: {duration:.1f} seconds")
        logger.info(f"Output file: {self.output_csv}")
    
    def write_to_csv(self, rows):
        """Write results to CSV file"""
        try:
            # Create output directory if it doesn't exist
            self.output_csv.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.output_csv, mode="w", newline="", encoding="utf-8") as csvfile:
                fieldnames = ["Date", "PDF_File", "Synopsis", "Summary", "Key Notes"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            logger.info(f"✅ Results written to: {self.output_csv}")
            logger.info(f"📊 Total summaries: {len(rows)}")
            
        except Exception as e:
            logger.error(f"Error writing CSV file: {e}")

def main():
    # Configuration
    input_folder = Path("/path/to/ocr_pdfs")
    output_file  = Path("/path/to/output/meeting_summaries.csv")
    
    # Check if API key is available
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY not found in environment variables")
        logger.error("Please create a .env file with your OpenAI API key")
        return
    
    # Check if input folder exists
    if not Path(input_folder).exists():
        logger.error(f"Input folder does not exist: {input_folder}")
        return
    
    logger.info("PDF Meeting Minutes Summarizer")
    logger.info(f"Input folder: {input_folder}")
    logger.info(f"Output file: {output_file}")
    logger.info("-" * 60)
    
    # Create and run summarizer
    summarizer = MeetingMinutesSummarizer(input_folder, output_file)
    
    try:
        summarizer.process_meeting_minutes()
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY not found in environment variables")

    summarizer = MeetingMinutesSummarizer(input_folder, output_file)
    summarizer.process_meeting_minutes()
