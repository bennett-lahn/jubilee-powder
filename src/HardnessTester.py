import cv2
import tesserocr
from tesserocr import PyTessBaseAPI
from PIL import Image

# Try to import PARSeq/TrOCR dependencies
try:
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    TROCR_AVAILABLE = True
except ImportError:
    TROCR_AVAILABLE = False
    print("⚠️  TrOCR not available. Install with: pip install torch transformers")

# Try to import EasyOCR as alternative
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False
    print("⚠️  EasyOCR not available. Install with: pip install easyocr")

# TODO: Set up raspberry pi VNC to use raspberry pi easily
# Would be even awesome to add a camera looking at the jubilee so you could do remove dev

"""
OCR PREPROCESSING FOR 7-SEGMENT DISPLAYS (Black text on dark grey background)

INSTALLATION:
Required:
    pip install opencv-python tesserocr pillow numpy

Optional (for additional OCR engines):
    pip install torch transformers  # For TrOCR (transformer-based OCR)
    pip install easyocr            # For EasyOCR (deep learning OCR)

OCR ENGINES AVAILABLE:
1. Tesseract OCR - Traditional OCR engine (always available)
2. TrOCR - Microsoft's transformer-based OCR (PARSeq-style architecture)
3. EasyOCR - Deep learning-based OCR with pretrained models

PREPROCESSING PIPELINE:
1. Upscale 3x (INTER_CUBIC interpolation)
2. Aggressive global contrast stretching + gamma correction
3. CLAHE with clipLimit=8.0, tileGridSize=(2,2)
4. Very strong Gaussian blur (15x15)
5. Extremely sensitive Otsu threshold (50% of calculated threshold)
6. NO inversion (keeps original polarity)
7. Morphological closing
8. Median blur denoising

TESTING:
Run main() to test all available OCR engines in parallel and compare results.
"""

# You may need to point to the tessdata path if it cannot be detected automatically. This can be done by setting the TESSDATA_PREFIX environment variable or by passing the path to PyTessBaseAPI (e.g.: PyTessBaseAPI(path='/usr/share/tessdata')). The path should contain .traineddata files which can be found at https://github.com/tesseract-ocr/tessdata.
# Make sure you have the correct version of traineddata for your tesseract --version.
# You can list the current supported languages on your system using the get_languages function:

# from tesserocr import get_languages
# print(get_languages('/usr/share/tessdata'))  # or any other path that applies to your system

class HardnessTester:

    def __init__(self):
        # Initialize Tesseract
        self.api = PyTessBaseAPI(path='./tessdata')
        self.api.SetVariable("tessedit_char_whitelist", ".0123456789") # Set OCR to only look for digits, period
        self.api.SetVariable("load_system_dawg", "0")
        self.api.SetVariable("load_freq_dawg", "0")
        self.api.SetVariable("tessedit_write_images", "1")
        self.api.SetPageSegMode(tesserocr.PSM.SINGLE_LINE) # Set OCR segmentation to single line instead of page by default
        
        # Additional settings for better digit recognition
        self.api.SetVariable("classify_bln_numeric_mode", "1")  # Assume numeric content
        self.api.SetVariable("tessedit_pageseg_mode", "7")  # Treat image as single line of text
        
        # Initialize TrOCR (PARSeq-style transformer model)
        self.trocr_processor = None
        self.trocr_model = None
        self.trocr_available = False
        if TROCR_AVAILABLE:
            try:
                print("🤖 Loading TrOCR model (Microsoft's transformer-based OCR)...")
                # Using printed text model - better for displays
                self.trocr_processor = TrOCRProcessor.from_pretrained('microsoft/trocr-base-printed')
                self.trocr_model = VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-base-printed')
                self.trocr_model.eval()
                if torch.cuda.is_available():
                    self.trocr_model = self.trocr_model.cuda()
                    print("✓ TrOCR model loaded successfully (GPU)")
                else:
                    print("✓ TrOCR model loaded successfully (CPU)")
                self.trocr_available = True
            except Exception as e:
                print(f"⚠️  Failed to load TrOCR: {e}")
        
        # Initialize EasyOCR
        self.easyocr_reader = None
        self.easyocr_available = False
        if EASYOCR_AVAILABLE:
            try:
                print("🤖 Loading EasyOCR model...")
                gpu_enabled = torch.cuda.is_available() if TROCR_AVAILABLE else False
                self.easyocr_reader = easyocr.Reader(['en'], gpu=gpu_enabled)
                print(f"✓ EasyOCR model loaded successfully ({'GPU' if gpu_enabled else 'CPU'})")
                self.easyocr_available = True
            except Exception as e:
                print(f"⚠️  Failed to load EasyOCR: {e}")

    def capture_image(self, save=False, cam_id=0):
        pil_img = None
        ret, frame = cv2.VideoCapture(0).read()
        if ret:
            # Convert cv2 image to pil_img
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            if save:
                cv2.imwrite('ocr.jpg', frame)
        return pil_img

    def process_image(self, image_path="test.png"):
        """
        Process image with black text on dark grey background (7-segment display)
        Uses extremely sensitive Otsu thresholding with no inversion
        
        Args:
            image_path: Path to the image file
            
        Returns:
            PIL Image ready for Tesseract OCR
        """
        # Generate output filename based on input
        import os
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        output_name = f"bw_{base_name}_otsu.png"
        
        return self._process_image_advanced_otsu(image_path, output_name)
    
    def _process_image_advanced_otsu(self, image_path, output_name="bw.png"):
        """
        Advanced preprocessing with EXTREMELY SENSITIVE Otsu (50% threshold)
        NO INVERSION - keeps original polarity
        Should eliminate hollow text issue
        """
        import os
        import numpy as np
        # Generate debug filename prefix
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        debug_prefix = f"debug_{base_name}_otsu"
        
        # Read image in grayscale
        g = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        cv2.imwrite(f"{debug_prefix}_step1_original_grayscale.png", g)
        
        # Step 1: Upscale image
        scale_factor = 3
        height, width = g.shape
        g_upscaled = cv2.resize(g, (width * scale_factor, height * scale_factor), 
                                interpolation=cv2.INTER_CUBIC)
        cv2.imwrite(f"{debug_prefix}_step2_upscaled.png", g_upscaled)
        
        # Step 2a: AGGRESSIVE Global contrast stretching with gamma correction
        stretched = cv2.normalize(g_upscaled, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
        stretched = cv2.convertScaleAbs(stretched, alpha=1.3, beta=10)
        cv2.imwrite(f"{debug_prefix}_step3a_contrast_stretched.png", stretched)
        
        # Step 2b: EXTREMELY AGGRESSIVE CLAHE
        # Increased clipLimit to 8.0 (was 5.0) for maximum contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(2, 2))
        enhanced = clahe.apply(stretched)
        cv2.imwrite(f"{debug_prefix}_step3b_clahe_enhanced.png", enhanced)
        
        # Step 3: Apply EXTREMELY STRONG Gaussian blur
        # Increased to 15x15 (was 11x11) for much stronger smoothing
        blurred = cv2.GaussianBlur(enhanced, (15, 15), 0)
        cv2.imwrite(f"{debug_prefix}_step4_gaussian_blurred.png", blurred)
        
        # Step 4: Use EXTREMELY SENSITIVE Otsu threshold
        # First get Otsu threshold value, then reduce it significantly to capture darker text
        otsu_thresh, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Make threshold EXTREMELY sensitive by reducing it to 50% (was 65%)
        sensitive_thresh = int(otsu_thresh * 0.50)
        _, binary = cv2.threshold(blurred, sensitive_thresh, 255, cv2.THRESH_BINARY)
        cv2.imwrite(f"{debug_prefix}_step5_otsu_threshold_sensitive.png", binary)
        print(f"  Otsu: {otsu_thresh:.1f} → Extremely Sensitive: {sensitive_thresh} (50%)")
        
        # Step 5: DO NOT INVERT - keep as is (dark text on light background after processing)
        # Skip inversion step
        cv2.imwrite(f"{debug_prefix}_step6_no_inversion.png", binary)
        
        # Step 6: Morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morphed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        cv2.imwrite(f"{debug_prefix}_step7_morphological_close.png", morphed)
        
        # Step 7: Denoising
        denoised = cv2.medianBlur(morphed, 3)
        cv2.imwrite(f"{debug_prefix}_step8_median_blur.png", denoised)
        
        # Save final result
        cv2.imwrite(output_name, denoised)
        
        return Image.fromarray(denoised)

    def process_image_custom(self, image_path, scale=3, clahe_clip=3.0, 
                             clahe_tile=(4, 4), invert=True, morph_size=(2, 2),
                             output_name=None):
        """
        Custom preprocessing with adjustable parameters
        Use this to fine-tune for your specific display
        
        Args:
            image_path: Path to image
            scale: Upscale factor (2-4 recommended)
            clahe_clip: CLAHE clip limit (1.0-5.0)
            clahe_tile: CLAHE tile grid size
            invert: Whether to invert the image
            morph_size: Morphological kernel size
            output_name: Output filename (auto-generated if None)
        """
        g = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        
        # Upscale
        height, width = g.shape
        g_upscaled = cv2.resize(g, (width * scale, height * scale), 
                                interpolation=cv2.INTER_CUBIC)
        
        # Optional inversion (do this FIRST for dark text on dark background)
        if invert:
            g_upscaled = cv2.bitwise_not(g_upscaled)
        
        # CLAHE
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=clahe_tile)
        enhanced = clahe.apply(g_upscaled)
        
        # Threshold
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Morphology
        if morph_size[0] > 0:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, morph_size)
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # Generate output filename if not provided
        if output_name is None:
            import os
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            output_name = f"bw_{base_name}_custom.png"
        
        cv2.imwrite(output_name, binary)
        return Image.fromarray(binary)

    def convert_image_tesseract(self, image, output_name="thresholded.png"):
        """Run Tesseract OCR"""
        self.api.SetImage(image)
        self.api.Recognize()
        thresholded = self.api.GetThresholdedImage()
        thresholded.save(output_name)
        text = self.api.GetUTF8Text().strip()
        confidence = self.api.AllWordConfidences()
        return text, confidence
    
    def convert_image_trocr(self, image):
        """Run TrOCR (transformer-based OCR)"""
        if not self.trocr_available or self.trocr_model is None:
            return "N/A (TrOCR not available)", []
        
        try:
            # Convert PIL image to RGB if needed
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Process image
            pixel_values = self.trocr_processor(images=image, return_tensors="pt").pixel_values
            if torch.cuda.is_available():
                pixel_values = pixel_values.cuda()
            
            # Generate text
            with torch.no_grad():
                generated_ids = self.trocr_model.generate(pixel_values)
            text = self.trocr_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            
            # Filter to only digits and period (like Tesseract whitelist)
            filtered_text = ''.join(c for c in text if c in '.0123456789')
            
            return filtered_text, []  # TrOCR doesn't provide confidence scores easily
        except Exception as e:
            return f"Error: {e}", []
    
    def convert_image_easyocr(self, image):
        """Run EasyOCR"""
        if not self.easyocr_available or self.easyocr_reader is None:
            return "N/A (EasyOCR not available)", []
        
        try:
            # Convert PIL to numpy array
            import numpy as np
            img_array = np.array(image)
            
            # Run EasyOCR with allowlist for digits
            results = self.easyocr_reader.readtext(img_array, allowlist='0123456789.', detail=1)
            
            if results:
                # Combine all detected text and confidences
                text = ' '.join([result[1] for result in results])
                confidences = [int(result[2] * 100) for result in results]
                return text, confidences
            else:
                return "", []
        except Exception as e:
            return f"Error: {e}", []
    
    def convert_image(self, image, output_name="thresholded.png"):
        """Legacy method for compatibility - uses Tesseract"""
        text, conf = self.convert_image_tesseract(image, output_name)
        print(text)
        print(conf)


def main():
    import os
    test = HardnessTester()
    
    # Test images
    test_images = ["test.png", "test2.png", "test3.png", "test4.png"]
    
    print("\n" + "=" * 80)
    print("🔍 EXTREMELY SENSITIVE OTSU (50% threshold, CLAHE 8.0, 15x15 blur, NO INVERT)")
    print("=" * 80)
    
    for img_path in test_images:
        print(f"\n📸 Processing {img_path}...")
        try:
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            image = test.process_image(image_path=img_path)
            print(f"✓ Debug images: debug_{base_name}_otsu_step*.png")
            
            # Test all three OCR engines
            print("\n" + "-" * 80)
            print("OCR RESULTS:")
            print("-" * 80)
            
            # Tesseract
            print("🔤 Tesseract OCR:")
            text_tess, conf_tess = test.convert_image_tesseract(
                image, output_name=f"thresholded_{base_name}_otsu.png"
            )
            print(f"   Text: '{text_tess}'")
            print(f"   Confidence: {conf_tess}")
            
            # TrOCR (PARSeq-style transformer)
            if test.trocr_available:
                print("\n🤖 TrOCR (Transformer OCR - PARSeq-style):")
                text_trocr, conf_trocr = test.convert_image_trocr(image)
                print(f"   Text: '{text_trocr}'")
                if conf_trocr:
                    print(f"   Confidence: {conf_trocr}")
            
            # EasyOCR
            if test.easyocr_available:
                print("\n🔍 EasyOCR:")
                text_easy, conf_easy = test.convert_image_easyocr(image)
                print(f"   Text: '{text_easy}'")
                print(f"   Confidence: {conf_easy}")
            
            print("-" * 80)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
