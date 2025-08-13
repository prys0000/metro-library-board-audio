#!/usr/bin/env python3
"""
Convert images in each folder to combined OCR'd PDFs
Creates searchable PDFs from meeting minute images
"""
# Use this format python pdf_converter.py E:\1974downloaded_pages\output#

import os
import sys
from pathlib import Path
import argparse
from PIL import Image
import pytesseract
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.utils import ImageReader
import tempfile
import shutil
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ImageToPDFConverter:
    def __init__(self, base_folder, page_size='letter', dpi=300):
        self.base_folder = Path(base_folder)
        self.page_size = letter if page_size.lower() == 'letter' else A4
        self.dpi = dpi
        
        # Supported image formats
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}
        
        # OCR configuration for better results
        self.ocr_config = r'--oem 3 --psm 6 -c tessedit_create_searchable_pdf=1'
        
    def get_meeting_folders(self):
        """Get all folders that contain meeting images"""
        meeting_folders = []
        
        for item in self.base_folder.iterdir():
            if item.is_dir() and item.name != "unassigned":
                # Check if folder contains images
                image_files = self.get_image_files(item)
                if image_files:
                    meeting_folders.append(item)
        
        # Sort folders by name (which should be date-based)
        meeting_folders.sort()
        return meeting_folders
    
    def get_image_files(self, folder):
        """Get all image files in a folder, sorted by name"""
        image_files = []
        
        for ext in self.image_extensions:
            image_files.extend(list(folder.glob(f'*{ext}')))
            image_files.extend(list(folder.glob(f'*{ext.upper()}')))
        
        # Sort by filename to maintain page order
        image_files.sort(key=lambda x: x.name.lower())
        return image_files
    
    def create_searchable_pdf_with_ocrmypdf(self, images, output_path):
        """Create searchable PDF using ocrmypdf (preferred method)"""
        try:
            import ocrmypdf
            
            # First create a simple PDF from images
            temp_pdf = output_path.parent / f"temp_{output_path.name}"
            
            # Create PDF from images
            self.create_simple_pdf(images, temp_pdf)
            
            # Apply OCR to make it searchable
            ocrmypdf.ocr(
                temp_pdf, 
                output_path,
                deskew=True,
                auto_rotate_pages=True,
                remove_background=False,
                optimize=1,
                jpeg_quality=85,
                png_quality=85,
                language='eng',
                force_ocr=True
            )
            
            # Clean up temp file
            if temp_pdf.exists():
                temp_pdf.unlink()
                
            return True
            
        except ImportError:
            logger.warning("ocrmypdf not available, falling back to basic method")
            return False
        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            return False
    
    def create_simple_pdf(self, images, output_path):
        """Create a simple PDF from images"""
        c = canvas.Canvas(str(output_path), pagesize=self.page_size)
        page_width, page_height = self.page_size
        
        for i, image_path in enumerate(images):
            logger.info(f"  Processing image {i+1}/{len(images)}: {image_path.name}")
            
            try:
                # Open and process image
                with Image.open(image_path) as img:
                    # Convert to RGB if necessary
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Calculate scaling to fit page while maintaining aspect ratio
                    img_width, img_height = img.size
                    
                    # Calculate scale factor
                    width_scale = (page_width - 40) / img_width  # 20pt margin on each side
                    height_scale = (page_height - 40) / img_height  # 20pt margin on each side
                    scale = min(width_scale, height_scale)
                    
                    # Calculate final dimensions
                    final_width = img_width * scale
                    final_height = img_height * scale
                    
                    # Center on page
                    x = (page_width - final_width) / 2
                    y = (page_height - final_height) / 2
                    
                    # Add image to PDF
                    c.drawImage(ImageReader(img), x, y, final_width, final_height)
                    
                    # Add page break (except for last image)
                    if i < len(images) - 1:
                        c.showPage()
                        
            except Exception as e:
                logger.error(f"Error processing image {image_path}: {e}")
                continue
        
        c.save()
    
    def create_ocr_pdf_with_tesseract(self, images, output_path):
        """Create OCR'd PDF using tesseract directly"""
        try:
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_dir_path = Path(temp_dir)
                
                # Process each image and extract text
                pdf_pages = []
                
                for i, image_path in enumerate(images):
                    logger.info(f"  OCR processing image {i+1}/{len(images)}: {image_path.name}")
                    
                    # Use tesseract to create searchable PDF for this image
                    temp_pdf = temp_dir_path / f"page_{i:03d}"
                    
                    try:
                        # Run tesseract OCR to create PDF
                        pytesseract.run_tesseract(
                            str(image_path),
                            str(temp_pdf),
                            extension='pdf',
                            lang='eng',
                            config=self.ocr_config
                        )
                        
                        pdf_file = temp_pdf.with_suffix('.pdf')
                        if pdf_file.exists():
                            pdf_pages.append(pdf_file)
                            
                    except Exception as e:
                        logger.error(f"OCR failed for {image_path}: {e}")
                        continue
                
                # Combine all PDF pages
                if pdf_pages:
                    self.combine_pdfs(pdf_pages, output_path)
                    return True
                else:
                    logger.error("No OCR pages were created successfully")
                    return False
                    
        except Exception as e:
            logger.error(f"Tesseract OCR processing failed: {e}")
            return False
    
    def combine_pdfs(self, pdf_files, output_path):
        """Combine multiple PDF files into one"""
        try:
            from PyPDF2 import PdfMerger
            
            merger = PdfMerger()
            
            for pdf_file in pdf_files:
                merger.append(str(pdf_file))
            
            with open(output_path, 'wb') as output_file:
                merger.write(output_file)
            
            merger.close()
            
        except ImportError:
            logger.error("PyPDF2 not available for PDF merging")
            # Fallback: just copy the first PDF if there's only one
            if len(pdf_files) == 1:
                shutil.copy2(pdf_files[0], output_path)
            else:
                raise Exception("Cannot combine PDFs without PyPDF2")
    
    def process_folder(self, folder_path, ocr_method='auto'):
        """Process a single folder to create OCR'd PDF"""
        folder_name = folder_path.name
        logger.info(f"Processing folder: {folder_name}")
        
        # Get all image files
        images = self.get_image_files(folder_path)
        
        if not images:
            logger.warning(f"No images found in {folder_name}")
            return False
        
        logger.info(f"Found {len(images)} images")
        
        # Create output PDF path
        pdf_filename = f"{folder_name}_meeting_minutes.pdf"
        output_path = folder_path / pdf_filename
        
        # Check if PDF already exists
        if output_path.exists():
            response = input(f"PDF already exists: {pdf_filename}. Overwrite? (y/n): ")
            if response.lower() != 'y':
                logger.info(f"Skipping {folder_name}")
                return False
        
        # Try different OCR methods
        success = False
        
        if ocr_method in ['auto', 'ocrmypdf']:
            logger.info("Attempting OCR with ocrmypdf...")
            success = self.create_searchable_pdf_with_ocrmypdf(images, output_path)
        
        if not success and ocr_method in ['auto', 'tesseract']:
            logger.info("Attempting OCR with tesseract...")
            success = self.create_ocr_pdf_with_tesseract(images, output_path)
        
        if not success and ocr_method in ['auto', 'simple']:
            logger.info("Creating simple PDF without OCR...")
            self.create_simple_pdf(images, output_path)
            success = True
        
        if success:
            logger.info(f"✅ Created: {pdf_filename}")
            
            # Create a text summary file
            self.create_summary_file(folder_path, images, output_path)
            return True
        else:
            logger.error(f"❌ Failed to create PDF for {folder_name}")
            return False
    
    def create_summary_file(self, folder_path, images, pdf_path):
        """Create a summary text file with basic info"""
        summary_path = folder_path / f"{folder_path.name}_summary.txt"
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(f"Meeting Minutes Summary\n")
            f.write(f"{'=' * 30}\n\n")
            f.write(f"Meeting Date: {folder_path.name}\n")
            f.write(f"PDF Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Pages: {len(images)}\n")
            f.write(f"PDF File: {pdf_path.name}\n\n")
            
            f.write("Source Images:\n")
            for i, img in enumerate(images, 1):
                f.write(f"  {i:2d}. {img.name}\n")
    
    def process_all_folders(self, ocr_method='auto'):
        """Process all meeting folders"""
        meeting_folders = self.get_meeting_folders()
        
        if not meeting_folders:
            logger.warning("No meeting folders found")
            return
        
        logger.info(f"Found {len(meeting_folders)} meeting folders to process")
        
        successful = 0
        failed = 0
        
        for folder in meeting_folders:
            try:
                if self.process_folder(folder, ocr_method):
                    successful += 1
                else:
                    failed += 1
            except KeyboardInterrupt:
                logger.info("Process interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error processing {folder.name}: {e}")
                failed += 1
        
        logger.info(f"\nProcessing complete!")
        logger.info(f"✅ Successful: {successful}")
        logger.info(f"❌ Failed: {failed}")

def check_dependencies():
    """Check if required packages are installed"""
    required = {
        'PIL': 'Pillow',
        'pytesseract': 'pytesseract',
        'reportlab': 'reportlab'
    }
    
    optional = {
        'ocrmypdf': 'ocrmypdf (recommended for best OCR)',
        'PyPDF2': 'PyPDF2 (for PDF merging)'
    }
    
    missing_required = []
    missing_optional = []
    
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing_required.append(package)
    
    for module, package in optional.items():
        try:
            __import__(module)
        except ImportError:
            missing_optional.append(package)
    
    if missing_required:
        print("❌ Missing required packages:")
        for package in missing_required:
            print(f"   - {package}")
        print(f"\nInstall with: pip install {' '.join(missing_required)}")
        return False
    
    if missing_optional:
        print("⚠️  Missing optional packages (recommended):")
        for package in missing_optional:
            print(f"   - {package}")
        print(f"\nInstall with: pip install {' '.join([p.split()[0] for p in missing_optional])}")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Convert meeting minute images to OCR\'d PDFs')
    parser.add_argument('folder_path', help='Path to folder containing meeting subfolders')
    parser.add_argument('--ocr-method', choices=['auto', 'ocrmypdf', 'tesseract', 'simple'], 
                        default='auto', help='OCR method to use (default: auto)')
    parser.add_argument('--page-size', choices=['letter', 'a4'], default='letter',
                        help='PDF page size (default: letter)')
    parser.add_argument('--dpi', type=int, default=300, help='DPI for image processing (default: 300)')
    parser.add_argument('--check-deps', action='store_true', help='Check dependencies and exit')
    
    args = parser.parse_args()
    
    if args.check_deps:
        if check_dependencies():
            print("✅ All dependencies are available")
        sys.exit(0)
    
    # Validate folder path
    if not os.path.exists(args.folder_path):
        print(f"Error: Folder '{args.folder_path}' does not exist")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        print("\nPlease install missing required packages before continuing.")
        sys.exit(1)
    
    print(f"Processing folder: {args.folder_path}")
    print(f"OCR method: {args.ocr_method}")
    print(f"Page size: {args.page_size}")
    print("-" * 50)
    
    # Create converter and process
    converter = ImageToPDFConverter(
        args.folder_path, 
        page_size=args.page_size,
        dpi=args.dpi
    )
    
    try:
        converter.process_all_folders(args.ocr_method)
    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
