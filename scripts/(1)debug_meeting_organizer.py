import os
import re
import shutil
from datetime import datetime
from pathlib import Path
import pytesseract
from PIL import Image
import argparse

# Configure Tesseract path for Windows
def setup_tesseract_path():
    """Configure pytesseract to find Tesseract on Windows"""
    try:
        import pytesseract
        
        # Set your specific Tesseract path
        tesseract_path = "/path/to/tesseract.exe"  # ← EDIT THIS OR ensure tesseract is in PATH
        
        if os.path.exists(tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            print(f"✅ Tesseract configured at: {tesseract_path}")
            
            # Test if it works
            try:
                version = pytesseract.get_tesseract_version()
                print(f"✅ Tesseract version: {version}")
                return True
            except Exception as e:
                print(f"❌ Tesseract found but not working: {e}")
                return False
        else:
            print(f"❌ Tesseract not found at: {tesseract_path}")
            
            # Fallback to other common locations
            possible_paths = [
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                r"C:\Users\%USERNAME%\AppData\Local\Tesseract-OCR\tesseract.exe",
                r"C:\tesseract\tesseract.exe"
            ]
            
            for path in possible_paths:
                expanded_path = os.path.expandvars(path)
                if os.path.exists(expanded_path):
                    pytesseract.pytesseract.tesseract_cmd = expanded_path
                    print(f"✅ Tesseract found at fallback location: {expanded_path}")
                    return True
            
            print("❌ Tesseract not found in any common locations")
            return False
        
    except ImportError:
        print("❌ pytesseract not installed")
        return False

# Set up Tesseract when module is imported
setup_tesseract_path()

class DebugMeetingMinutesOrganizer:
    def __init__(self, source_folder, output_folder, debug_mode=True):
        self.source_folder = Path(source_folder)
        self.output_folder = Path(output_folder)
        self.current_meeting_folder = None
        self.current_meeting_date = None
        self.debug_mode = debug_mode
        
        # Create output folder if it doesn't exist
        self.output_folder.mkdir(exist_ok=True)
        
        # Create debug folder
        if debug_mode:
            self.debug_folder = self.output_folder / "debug_ocr_output"
            self.debug_folder.mkdir(exist_ok=True)
        
        # Date patterns to match various formats in the documents
        self.date_patterns = [
            # "MEETING OF JANUARY 5, 1971"
            r'MEETING\s+OF\s+([A-Z]+)\s+(\d{1,2}),?\s+(\d{4})',
            # "January 5, 1971"
            r'([A-Z][a-z]+)\s+(\d{1,2}),?\s+(\d{4})',
            # "JANUARY 5, 1971"
            r'([A-Z]+)\s+(\d{1,2}),?\s+(\d{4})',
            # Additional patterns for other possible formats
            r'(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})',
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            # More flexible patterns for 1971
            r'MEETING.*?([A-Z]+)\s+(\d{1,2}),?\s+(19\d{2})',
            r'BOARD.*?EDUCATION.*?([A-Z]+)\s+(\d{1,2}),?\s+(19\d{2})',
        ]
        
        # Month name mapping
        self.month_names = {
            'JANUARY': 1, 'JAN': 1,
            'FEBRUARY': 2, 'FEB': 2,
            'MARCH': 3, 'MAR': 3,
            'APRIL': 4, 'APR': 4,
            'MAY': 5,
            'JUNE': 6, 'JUN': 6,
            'JULY': 7, 'JUL': 7,
            'AUGUST': 8, 'AUG': 8,
            'SEPTEMBER': 9, 'SEP': 9, 'SEPT': 9,
            'OCTOBER': 10, 'OCT': 10,
            'NOVEMBER': 11, 'NOV': 11,
            'DECEMBER': 12, 'DEC': 12
        }

    def extract_text_from_image(self, image_path):
        """Extract text from image using OCR"""
        try:
            # Open and preprocess image for better OCR
            image = Image.open(image_path)
            
            # Convert to grayscale for better OCR results
            if image.mode not in ['L', 'RGB']:
                image = image.convert('RGB')
            
            # Try different OCR configurations
            configs = [
                '--psm 6',  # Uniform block of text
                '--psm 4',  # Single column of text
                '--psm 3',  # Fully automatic page segmentation
                '--psm 1',  # Automatic page segmentation with OSD
            ]
            
            best_text = ""
            for config in configs:
                try:
                    text = pytesseract.image_to_string(image, config=config)
                    if len(text.strip()) > len(best_text.strip()):
                        best_text = text
                except:
                    continue
            
            return best_text.upper()  # Convert to uppercase for consistent matching
            
        except Exception as e:
            print(f"Error extracting text from {image_path}: {e}")
            return ""

    def save_debug_info(self, image_path, text, is_meeting_start, parsed_date):
        """Save debug information for troubleshooting"""
        if not self.debug_mode:
            return
            
        debug_file = self.debug_folder / f"{image_path.stem}_debug.txt"
        
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(f"Image: {image_path.name}\n")
            f.write(f"Is Meeting Start: {is_meeting_start}\n")
            f.write(f"Parsed Date: {parsed_date}\n")
            f.write("=" * 50 + "\n")
            f.write("OCR Text:\n")
            f.write(text)
            f.write("\n" + "=" * 50 + "\n")
            
            # Check for meeting indicators
            meeting_indicators = [
                "MEETING OF",
                "THE BOARD OF EDUCATION", 
                "OKLAHOMA CITY, OKLAHOMA",
                "MET IN REGULAR SESSION",
                "MET IN ADJOURNED SESSION",
                "BOARD OF EDUCATION",
                "OKLAHOMA CITY",
                "MEETING",
                "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
            ]
            
            f.write("Found Indicators:\n")
            for indicator in meeting_indicators:
                if indicator in text:
                    f.write(f"✅ {indicator}\n")
                else:
                    f.write(f"❌ {indicator}\n")

    def parse_date(self, text):
        """Extract date from text using regex patterns"""
        for i, pattern in enumerate(self.date_patterns):
            matches = re.search(pattern, text)
            if matches:
                groups = matches.groups()
                
                try:
                    # Handle different pattern formats
                    if len(groups) == 3:
                        if groups[0].isalpha():  # Month name first
                            month_str = groups[0]
                            day = int(groups[1])
                            year = int(groups[2])
                            
                            # Convert month name to number
                            month = self.month_names.get(month_str)
                            if month is None:
                                continue
                                
                        elif groups[1].isalpha():  # Day, month name, year
                            day = int(groups[0])
                            month_str = groups[1]
                            year = int(groups[2])
                            
                            month = self.month_names.get(month_str)
                            if month is None:
                                continue
                                
                        else:  # Numeric format
                            # Could be MM/DD/YYYY or DD/MM/YYYY - assume MM/DD/YYYY
                            month = int(groups[0])
                            day = int(groups[1])
                            year = int(groups[2])
                    
                    # Validate date
                    if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100:
                        if self.debug_mode:
                            print(f"    📅 Date found with pattern {i}: {year}-{month:02d}-{day:02d}")
                        return datetime(year, month, day)
                        
                except (ValueError, TypeError) as e:
                    if self.debug_mode:
                        print(f"    ❌ Date parse error with pattern {i}: {e}")
                    continue
                    
        return None

    def get_folder_name(self, date_obj):
        """Generate folder name in YYYY-MM-DD format"""
        return date_obj.strftime("%Y-%m-%d")

    def is_meeting_start_page(self, text):
        """Determine if this page starts a new meeting"""
        # Look for meeting header indicators - more flexible for 1971
        meeting_indicators = [
            "MEETING OF",
            "THE BOARD OF EDUCATION",
            "OKLAHOMA CITY, OKLAHOMA", 
            "MET IN REGULAR SESSION",
            "MET IN ADJOURNED SESSION",
            "BOARD OF EDUCATION",
            "OKLAHOMA CITY",
        ]
        
        # Count how many indicators are present
        indicator_count = sum(1 for indicator in meeting_indicators if indicator in text)
        
        # Also look for date patterns as additional evidence
        has_date = self.parse_date(text) is not None
        
        # More lenient criteria for 1971 - either multiple indicators OR date + some indicators
        is_meeting_start = indicator_count >= 2 or (has_date and indicator_count >= 1)
        
        return is_meeting_start

    def organize_files(self, max_files=None):
        """Main method to organize all meeting files"""
        # Get all image files
        image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(self.source_folder.glob(f'*{ext}'))
            image_files.extend(self.source_folder.glob(f'*{ext.upper()}'))
        
        # Sort files by name to maintain order
        image_files.sort()
        
        # Limit files for debugging
        if max_files:
            image_files = image_files[:max_files]
        
        print(f"Found {len(image_files)} image files to process")
        
        meeting_starts_found = 0
        
        for i, file_path in enumerate(image_files):
            print(f"Processing {i+1}/{len(image_files)}: {file_path.name}")
            
            try:
                # Extract text from image
                text = self.extract_text_from_image(file_path)
                
                if self.debug_mode and i < 10:  # Show OCR results for first 10 files
                    print(f"  📝 OCR extracted {len(text)} characters")
                    if text:
                        print(f"  📖 First 200 chars: {text[:200]}...")
                
                # Check if this is a meeting start page
                is_meeting_start = self.is_meeting_start_page(text)
                parsed_date = None
                
                if is_meeting_start:
                    # Try to extract date
                    parsed_date = self.parse_date(text)
                    
                    if parsed_date:
                        # Create new meeting folder
                        folder_name = self.get_folder_name(parsed_date)
                        self.current_meeting_folder = self.output_folder / folder_name
                        self.current_meeting_folder.mkdir(exist_ok=True)
                        self.current_meeting_date = parsed_date
                        
                        print(f"  🎉 New meeting detected: {parsed_date.strftime('%B %d, %Y')}")
                        print(f"  📁 Created folder: {folder_name}")
                        meeting_starts_found += 1
                    else:
                        print(f"  ⚠️ Meeting start detected but couldn't parse date")
                        # Continue with current folder if we have one
                
                # Save debug info for first 10 files
                if self.debug_mode and i < 10:
                    self.save_debug_info(file_path, text, is_meeting_start, parsed_date)
                
                # Copy file to current meeting folder
                if self.current_meeting_folder:
                    destination = self.current_meeting_folder / file_path.name
                    shutil.copy2(file_path, destination)
                    print(f"  ✅ Copied to: {self.current_meeting_folder.name}")
                else:
                    # Create "unassigned" folder for files without a meeting
                    unassigned_folder = self.output_folder / "unassigned"
                    unassigned_folder.mkdir(exist_ok=True)
                    destination = unassigned_folder / file_path.name
                    shutil.copy2(file_path, destination)
                    print(f"  📋 Copied to: unassigned (no meeting folder determined)")
                    
            except Exception as e:
                print(f"  ❌ Error processing {file_path.name}: {e}")
                continue
        
        print(f"\n📊 Summary: Found {meeting_starts_found} meeting starts out of {len(image_files)} files")

    def create_summary_report(self):
        """Create a summary report of organized meetings"""
        report_path = self.output_folder / "organization_report.txt"
        
        with open(report_path, 'w') as f:
            f.write("Meeting Minutes Organization Report\n")
            f.write("=" * 40 + "\n\n")
            
            # List all created folders
            meeting_folders = [d for d in self.output_folder.iterdir() 
                             if d.is_dir() and d.name not in ["unassigned", "debug_ocr_output"]]
            meeting_folders.sort()
            
            f.write(f"Total meetings organized: {len(meeting_folders)}\n\n")
            
            for folder in meeting_folders:
                files_count = len(list(folder.iterdir()))
                f.write(f"{folder.name}: {files_count} files\n")
            
            # Check unassigned folder
            unassigned_folder = self.output_folder / "unassigned"
            if unassigned_folder.exists():
                unassigned_count = len(list(unassigned_folder.iterdir()))
                if unassigned_count > 0:
                    f.write(f"\nUnassigned files: {unassigned_count}\n")
        
        print(f"\n📄 Summary report created: {report_path}")

def main():
    parser = argparse.ArgumentParser(description='Debug version: Organize meeting minutes into folders by date')
    parser.add_argument('source_folder', help='Path to folder containing meeting minute images')
    parser.add_argument('output_folder', help='Path to output folder for organized meetings')
    parser.add_argument('--debug', action='store_true', default=True, help='Enable debug mode (default: enabled)')
    parser.add_argument('--max-files', type=int, help='Limit number of files to process (for testing)')
    parser.add_argument('--no-debug', action='store_true', help='Disable debug mode')
    
    args = parser.parse_args()
    
    # Validate source folder
    if not os.path.exists(args.source_folder):
        print(f"Error: Source folder '{args.source_folder}' does not exist")
        return
    
    debug_mode = args.debug and not args.no_debug
    
    print(f"🔍 DEBUG MODE: {'ENABLED' if debug_mode else 'DISABLED'}")
    print(f"📁 Source folder: {args.source_folder}")
    print(f"📁 Output folder: {args.output_folder}")
    if args.max_files:
        print(f"📊 Max files to process: {args.max_files}")
    print("-" * 50)
    
    # Create organizer and run
    organizer = DebugMeetingMinutesOrganizer(args.source_folder, args.output_folder, debug_mode)
    
    try:
        organizer.organize_files(args.max_files)
        organizer.create_summary_report()
        
        if debug_mode:
            print(f"\n🔍 Debug OCR output saved to: {organizer.debug_folder}")
            print("Check the debug files to see what text is being extracted from your images!")
        
        print("\n✅ Organization complete!")
        
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        raise

if __name__ == "__main__":
    main()
