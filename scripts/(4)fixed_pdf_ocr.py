#!/usr/bin/env python3
"""
Fixed Batch OCR processor for existing PDFs
Handles the common issues with PDF OCR on Windows
"""

import os
import sys
from pathlib import Path
import argparse
import logging
from datetime import datetime
import shutil
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure Tesseract path for Windows
def setup_tesseract_path():
    """Configure pytesseract to find Tesseract on Windows"""
    try:
        import pytesseract
        
        # Common Tesseract installation paths on Windows
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Users\%USERNAME%\AppData\Local\Tesseract-OCR\tesseract.exe",
            r"C:\tesseract\tesseract.exe"
        ]
        
        # Check if tesseract is already in PATH
        try:
            result = subprocess.run(['tesseract', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("✅ Tesseract found in system PATH")
                return True
        except FileNotFoundError:
            pass
        
        # Try to find tesseract in common locations
        for path in possible_paths:
            expanded_path = os.path.expandvars(path)
            if os.path.exists(expanded_path):
                pytesseract.pytesseract.tesseract_cmd = expanded_path
                logger.info(f"✅ Tesseract configured at: {expanded_path}")
                
                # Test if it works
                try:
                    version = pytesseract.get_tesseract_version()
                    logger.info(f"✅ Tesseract version: {version}")
                    return True
                except Exception as e:
                    logger.warning(f"Tesseract found but not working: {e}")
                    continue
        
        logger.error("❌ Tesseract not found in common locations")
        logger.error("Please ensure Tesseract is installed and add it to your PATH")
        logger.error("Or update the tesseract_cmd path in the script")
        return False
        
    except ImportError:
        logger.error("pytesseract not installed")
        return False

# Set up Tesseract when module is imported
setup_tesseract_path()

class FixedBatchPDFOCR:
    def __init__(self, base_folder, output_suffix="_ocr", backup_originals=True, max_workers=2):
        self.base_folder = Path(base_folder)
        self.output_suffix = output_suffix
        self.backup_originals = backup_originals
        self.max_workers = max_workers
        
        # Statistics
        self.stats = {
            'total_found': 0,
            'already_ocr': 0,
            'processed': 0,
            'failed': 0,
            'skipped': 0
        }
        
    def find_pdf_files(self):
        """Find all PDF files in the directory structure"""
        pdf_files = []
        
        for pdf_file in self.base_folder.rglob("*.pdf"):
            # Skip backup files and already OCR'd files
            if not (pdf_file.name.endswith('_backup.pdf') or 
                   pdf_file.name.endswith('_ocr.pdf') or
                   pdf_file.name.startswith('temp_') or
                   '.backup' in pdf_file.name):
                pdf_files.append(pdf_file)
        
        # Sort by name for consistent processing order
        pdf_files.sort()
        self.stats['total_found'] = len(pdf_files)
        
        return pdf_files
    
    def check_if_pdf_has_text(self, pdf_path):
        """Check if PDF already contains searchable text"""
        try:
            import PyPDF2
            
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                
                # Check first few pages for text
                pages_to_check = min(3, len(reader.pages))
                total_text = ""
                
                for i in range(pages_to_check):
                    page = reader.pages[i]
                    text = page.extract_text().strip()
                    total_text += text
                
                # If we found substantial text, assume it's already OCR'd
                # Meeting minutes should have plenty of text
                if len(total_text) > 100:  # At least 100 characters
                    return True
                    
        except Exception as e:
            logger.warning(f"Could not check text content of {pdf_path.name}: {e}")
        
        return False
    
    def ocr_pdf_with_ocrmypdf_fixed(self, input_path, output_path):
        """OCR PDF using ocrmypdf with version compatibility fixes"""
        try:
            import ocrmypdf
            
            # Simple configuration that works with most ocrmypdf versions
            try:
                ocrmypdf.ocr(
                    input_path,
                    output_path,
                    language='eng',
                    rotate_pages=True,
                    deskew=True,
                    auto_rotate_pages=True,
                    force_ocr=False,  # Skip if already has text
                    skip_text=False,
                    clean=True,
                    optimize=1
                )
                return True
            except Exception as e:
                # Try with minimal options if advanced options fail
                logger.info(f"  Advanced options failed, trying basic OCR: {e}")
                try:
                    ocrmypdf.ocr(
                        input_path,
                        output_path,
                        language='eng',
                        force_ocr=False
                    )
                    return True
                except Exception as e2:
                    logger.error(f"  Basic ocrmypdf also failed: {e2}")
                    return False
                    
        except ImportError:
            logger.error("ocrmypdf not installed")
            return False
        except Exception as e:
            if "PriorOcrFoundError" in str(e):
                logger.info(f"  PDF already contains OCR text")
                return "already_ocr"
            else:
                logger.error(f"  ocrmypdf failed: {e}")
                return False
    
    def pdf_to_images_and_ocr(self, input_path, output_path):
        """Convert PDF to images first, then OCR each image and recombine"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                images_dir = temp_path / "images"
                images_dir.mkdir()
                
                # Step 1: Convert PDF to images using pdf2image or pymupdf
                success = False
                
                # Try pdf2image first (requires poppler)
                if not success:
                    try:
                        from pdf2image import convert_from_path
                        logger.info("  Converting PDF to images using pdf2image...")
                        
                        images = convert_from_path(
                            input_path,
                            dpi=300,
                            output_folder=images_dir,
                            fmt='png',
                            thread_count=2
                        )
                        
                        # Save images with proper names
                        image_files = []
                        for i, image in enumerate(images):
                            img_path = images_dir / f"page_{i:03d}.png"
                            image.save(img_path, 'PNG')
                            image_files.append(img_path)
                        
                        success = True
                        logger.info(f"  Created {len(image_files)} images")
                        
                    except ImportError:
                        logger.info("  pdf2image not available")
                    except Exception as e:
                        logger.info(f"  pdf2image failed: {e}")
                
                # Try pymupdf (fitz) as backup
                if not success:
                    try:
                        import fitz  # PyMuPDF
                        logger.info("  Converting PDF to images using PyMuPDF...")
                        
                        doc = fitz.open(str(input_path))
                        image_files = []
                        
                        for page_num in range(len(doc)):
                            page = doc.load_page(page_num)
                            # Render page to an image
                            mat = fitz.Matrix(300/72, 300/72)  # 300 DPI
                            pix = page.get_pixmap(matrix=mat)
                            
                            img_path = images_dir / f"page_{page_num:03d}.png"
                            pix.save(str(img_path))
                            image_files.append(img_path)
                        
                        doc.close()
                        success = True
                        logger.info(f"  Created {len(image_files)} images")
                        
                    except ImportError:
                        logger.info("  PyMuPDF not available")
                    except Exception as e:
                        logger.info(f"  PyMuPDF failed: {e}")
                
                # Try PIL + pdf2image alternative
                if not success:
                    logger.info("  Trying alternative PDF conversion method...")
                    try:
                        # Use subprocess to call external tools if available
                        cmd = [
                            'magick', 'convert',
                            '-density', '300',
                            str(input_path),
                            str(images_dir / 'page_%03d.png')
                        ]
                        
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                        if result.returncode == 0:
                            image_files = sorted(list(images_dir.glob("page_*.png")))
                            if image_files:
                                success = True
                                logger.info(f"  Created {len(image_files)} images using ImageMagick")
                    except Exception as e:
                        logger.info(f"  ImageMagick failed: {e}")
                
                if not success:
                    logger.error("  Could not convert PDF to images")
                    return False
                
                # Step 2: OCR each image using tesseract
                logger.info("  Running OCR on images...")
                ocr_texts = []
                
                import pytesseract
                from PIL import Image
                
                for img_file in image_files:
                    try:
                        # Extract text from image
                        text = pytesseract.image_to_string(
                            Image.open(img_file),
                            lang='eng',
                            config=r'--oem 3 --psm 6'
                        )
                        ocr_texts.append(text)
                    except Exception as e:
                        logger.warning(f"  OCR failed for {img_file.name}: {e}")
                        ocr_texts.append("")  # Empty text for failed pages
                
                # Step 3: Create searchable PDF
                logger.info("  Creating searchable PDF...")
                self.create_searchable_pdf_from_images_and_text(
                    image_files, ocr_texts, output_path
                )
                
                return True
                
        except Exception as e:
            logger.error(f"  PDF to images OCR failed: {e}")
            return False
    
    def create_searchable_pdf_from_images_and_text(self, image_files, ocr_texts, output_path):
        """Create a searchable PDF from images and OCR text"""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from PIL import Image
            
            c = canvas.Canvas(str(output_path), pagesize=letter)
            page_width, page_height = letter
            
            for i, (img_file, text) in enumerate(zip(image_files, ocr_texts)):
                logger.info(f"    Processing page {i+1}/{len(image_files)}")
                
                try:
                    # Add image to page
                    with Image.open(img_file) as img:
                        # Convert to RGB if necessary
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # Calculate scaling to fit page
                        img_width, img_height = img.size
                        width_scale = (page_width - 40) / img_width
                        height_scale = (page_height - 40) / img_height
                        scale = min(width_scale, height_scale)
                        
                        final_width = img_width * scale
                        final_height = img_height * scale
                        
                        # Center on page
                        x = (page_width - final_width) / 2
                        y = (page_height - final_height) / 2
                        
                        # Draw image
                        c.drawImage(ImageReader(img), x, y, final_width, final_height)
                        
                        # Add invisible text layer for searchability
                        if text.strip():
                            # Make text transparent (invisible but searchable)
                            c.setFillAlpha(0.0)
                            c.setFont("Helvetica", 8)
                            
                            # Split text into lines and add at various positions
                            words = text.split()
                            words_per_line = 10
                            line_height = 12
                            
                            for line_num, i in enumerate(range(0, len(words), words_per_line)):
                                line_words = words[i:i+words_per_line]
                                line_text = ' '.join(line_words)
                                
                                text_y = page_height - 50 - (line_num * line_height)
                                if text_y > 50:  # Don't go below bottom margin
                                    c.drawString(50, text_y, line_text)
                            
                            # Reset alpha for next page
                            c.setFillAlpha(1.0)
                        
                        # Add page break except for last page
                        if i < len(image_files) - 1:
                            c.showPage()
                            
                except Exception as e:
                    logger.warning(f"    Error processing page {i+1}: {e}")
                    continue
            
            c.save()
            logger.info("  ✅ Searchable PDF created successfully")
            return True
            
        except Exception as e:
            logger.error(f"  Failed to create searchable PDF: {e}")
            return False
    
    def process_single_pdf(self, pdf_path, method='auto'):
        """Process a single PDF file"""
        logger.info(f"Processing: {pdf_path.name}")
        
        # Check if already has text
        if self.check_if_pdf_has_text(pdf_path):
            logger.info(f"  ✅ Already contains searchable text - skipping")
            self.stats['already_ocr'] += 1
            return True
        
        # Create backup if requested
        if self.backup_originals:
            backup_path = pdf_path.with_suffix('.pdf.backup')
            if not backup_path.exists():
                shutil.copy2(pdf_path, backup_path)
                logger.info(f"  📄 Created backup: {backup_path.name}")
        
        # Create output path
        if self.output_suffix:
            output_path = pdf_path.with_name(f"{pdf_path.stem}{self.output_suffix}.pdf")
        else:
            # Replace original
            output_path = pdf_path.with_name(f"temp_{pdf_path.name}")
        
        # Try different OCR methods
        success = False
        
        if method in ['auto', 'ocrmypdf']:
            logger.info("  🔍 Trying ocrmypdf...")
            result = self.ocr_pdf_with_ocrmypdf_fixed(pdf_path, output_path)
            if result == "already_ocr":
                self.stats['already_ocr'] += 1
                return True
            elif result:
                success = True
        
        if not success and method in ['auto', 'pdf2images']:
            logger.info("  🔍 Trying PDF to images + OCR...")
            success = self.pdf_to_images_and_ocr(pdf_path, output_path)
        
        if success:
            # If we're replacing the original, do the replacement
            if not self.output_suffix:
                original_temp = pdf_path.with_name(f"original_{pdf_path.name}")
                shutil.move(pdf_path, original_temp)
                shutil.move(output_path, pdf_path)
                original_temp.unlink()  # Remove temp file
            
            logger.info(f"  ✅ OCR completed: {output_path.name}")
            self.stats['processed'] += 1
            return True
        else:
            logger.error(f"  ❌ OCR failed for {pdf_path.name}")
            self.stats['failed'] += 1
            return False
    
    def process_all_pdfs(self, method='auto', parallel=False):
        """Process all PDFs in the directory"""
        pdf_files = self.find_pdf_files()
        
        if not pdf_files:
            logger.warning("No PDF files found to process")
            return
        
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        logger.info(f"OCR method: {method}")
        logger.info(f"Parallel processing: {parallel}")
        logger.info(f"Max workers: {self.max_workers if parallel else 1}")
        logger.info("-" * 60)
        
        start_time = time.time()
        
        if parallel and self.max_workers > 1:
            self.process_parallel(pdf_files, method)
        else:
            self.process_sequential(pdf_files, method)
        
        # Print summary
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info("\n" + "=" * 60)
        logger.info("PROCESSING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total files found: {self.stats['total_found']}")
        logger.info(f"Already had OCR: {self.stats['already_ocr']}")
        logger.info(f"Successfully processed: {self.stats['processed']}")
        logger.info(f"Failed: {self.stats['failed']}")
        logger.info(f"Processing time: {duration:.1f} seconds")
        
        if self.stats['processed'] > 0:
            avg_time = duration / (self.stats['processed'] + self.stats['already_ocr'])
            logger.info(f"Average time per file: {avg_time:.1f} seconds")
    
    def process_sequential(self, pdf_files, method):
        """Process PDFs one by one"""
        for i, pdf_path in enumerate(pdf_files, 1):
            logger.info(f"\n[{i}/{len(pdf_files)}] Processing: {pdf_path.relative_to(self.base_folder)}")
            try:
                self.process_single_pdf(pdf_path, method)
            except KeyboardInterrupt:
                logger.info("Process interrupted by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error processing {pdf_path.name}: {e}")
                self.stats['failed'] += 1
    
    def process_parallel(self, pdf_files, method):
        """Process PDFs in parallel"""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_pdf = {
                executor.submit(self.process_single_pdf, pdf_path, method): pdf_path 
                for pdf_path in pdf_files
            }
            
            # Process completed tasks
            for i, future in enumerate(as_completed(future_to_pdf), 1):
                pdf_path = future_to_pdf[future]
                try:
                    future.result()
                    logger.info(f"[{i}/{len(pdf_files)}] Completed: {pdf_path.name}")
                except Exception as e:
                    logger.error(f"Error processing {pdf_path.name}: {e}")
                    self.stats['failed'] += 1

def check_dependencies():
    """Check available OCR tools and PDF conversion libraries"""
    print("Checking dependencies...")
    print("-" * 40)
    
    available_methods = []
    missing_packages = []
    
    # Check core requirements
    try:
        import PyPDF2
        print("✅ PyPDF2 - Available")
    except ImportError:
        print("❌ PyPDF2 - Missing")
        missing_packages.append("PyPDF2")
    
    try:
        import pytesseract
        import PIL
        print("✅ pytesseract + PIL - Available")
        
        # Test Tesseract configuration
        try:
            version = pytesseract.get_tesseract_version()
            print(f"✅ Tesseract OCR - Version {version}")
        except Exception as e:
            print(f"❌ Tesseract OCR - Configuration issue: {e}")
            print("   Make sure Tesseract is installed at: C:\\Program Files\\Tesseract-OCR\\")
            
    except ImportError:
        print("❌ pytesseract/PIL - Missing")
        missing_packages.append("pytesseract Pillow")
    
    try:
        import reportlab
        print("✅ reportlab - Available")
    except ImportError:
        print("❌ reportlab - Missing")
        missing_packages.append("reportlab")
    
    # Check OCR engines
    try:
        import ocrmypdf
        print("✅ ocrmypdf - Available (preferred)")
        available_methods.append("ocrmypdf")
    except ImportError:
        print("⚠️  ocrmypdf - Missing (recommended)")
    
    # Check PDF conversion libraries
    try:
        from pdf2image import convert_from_path
        print("✅ pdf2image - Available")
        available_methods.append("pdf2image")
    except ImportError:
        print("⚠️  pdf2image - Missing (recommended)")
        print("   Install with: pip install pdf2image")
        print("   Also requires poppler: https://github.com/oschwartz10612/poppler-windows/releases/")
    
    try:
        import fitz  # PyMuPDF
        print("✅ PyMuPDF - Available")
        available_methods.append("pymupdf")
    except ImportError:
        print("⚠️  PyMuPDF - Missing (alternative)")
        print("   Install with: pip install PyMuPDF")
    
    print("-" * 40)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print(f"\nInstall with: pip install {' '.join(missing_packages)}")
        print("\nOptional but recommended:")
        print("   pip install ocrmypdf pdf2image PyMuPDF")
        return False
    
    if available_methods:
        print("✅ OCR methods available:")
        for method in available_methods:
            print(f"   - {method}")
    else:
        print("⚠️  Limited OCR capabilities - install additional packages for better results")
    
    print("\n💡 For best results, ensure you have:")
    print("   1. Tesseract installed at: C:\\Program Files\\Tesseract-OCR\\")
    print("   2. At least one PDF conversion library (pdf2image or PyMuPDF)")
    print("   3. ocrmypdf for highest quality OCR")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Fixed Batch OCR processing for PDFs')
    parser.add_argument('folder_path', help='Path to folder containing PDFs')
    parser.add_argument('--method', choices=['auto', 'ocrmypdf', 'pdf2images'], 
                        default='auto', help='OCR method to use')
    parser.add_argument('--output-suffix', default='_ocr', 
                        help='Suffix for OCR output files (use empty string to replace originals)')
    parser.add_argument('--no-backup', action='store_true', 
                        help='Do not create backup files')
    parser.add_argument('--parallel', action='store_true',
                        help='Process files in parallel')
    parser.add_argument('--max-workers', type=int, default=2,
                        help='Maximum parallel workers (default: 2)')
    parser.add_argument('--check-deps', action='store_true',
                        help='Check dependencies and exit')
    
    args = parser.parse_args()
    
    if args.check_deps:
        check_dependencies()
        sys.exit(0)
    
    # Validate folder
    if not os.path.exists(args.folder_path):
        print(f"Error: Folder '{args.folder_path}' does not exist")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        print("\nPlease install required packages before continuing.")
        sys.exit(1)
    
    print(f"\nFixed Batch PDF OCR Processing")
    print(f"Folder: {args.folder_path}")
    print(f"Method: {args.method}")
    print(f"Output suffix: '{args.output_suffix}'")
    print(f"Create backups: {not args.no_backup}")
    print(f"Parallel processing: {args.parallel}")
    if args.parallel:
        print(f"Max workers: {args.max_workers}")
    print("-" * 50)
    
    # Create processor
    processor = FixedBatchPDFOCR(
        args.folder_path,
        output_suffix=args.output_suffix if args.output_suffix else "",
        backup_originals=not args.no_backup,
        max_workers=args.max_workers
    )
    
    try:
        processor.process_all_pdfs(args.method, args.parallel)
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
