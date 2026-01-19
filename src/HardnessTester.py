import cv2

# Try to import Picamera2 for Raspberry Pi
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    print("⚠️  Picamera2 not available. Will use cv2.VideoCapture instead.")

"""
SEGMENT-BASED LCD READING FOR 7-SEGMENT DISPLAYS

INSTALLATION:
Required:
    pip install opencv-python
    
Optional (Raspberry Pi):
    pip install picamera2  # For Raspberry Pi camera with better control

METHODOLOGY:
This approach reads 7-segment LCD displays by detecting which segments are active,
rather than using traditional OCR. This is much more reliable for LCD displays.

PIPELINE:
Phase 1: Image Acquisition & Advanced Preprocessing
    - Direct camera control with locked exposure and gain
    - LAB color space conversion (b-channel for best LCD contrast)
    - CLAHE (Contrast Limited Adaptive Histogram Equalization)
    
Phase 2: Segment Analysis Logic
    - Extract individual digit ROIs
    - Map 7 segments per digit (top, top-left, top-right, middle, bottom-left, bottom-right, bottom)
    - Count active pixels in each segment
    
Phase 3: Recognition via Lookup Table
    - Map segment patterns to digits using predefined lookup table
    
ADVANTAGES OVER OCR:
- More reliable for low-contrast LCD displays
- Not affected by font variations
- Works with partial/damaged displays
- No training data required
"""

class HardnessTester:
    """
    LCD 7-Segment Display Reader using segment detection instead of OCR.
    """
    
    # Segment order: (top, top-left, top-right, middle, bottom-left, bottom-right, bottom)
    DIGITS_LOOKUP = {
        (1, 1, 1, 0, 1, 1, 1): '0',
        (0, 0, 1, 0, 0, 1, 0): '1',
        (1, 0, 1, 1, 1, 0, 1): '2',
        (1, 0, 1, 1, 0, 1, 1): '3',
        (0, 1, 1, 1, 0, 1, 0): '4',
        (1, 1, 0, 1, 0, 1, 1): '5',
        (1, 1, 0, 1, 1, 1, 1): '6',
        (1, 0, 1, 0, 0, 1, 0): '7',
        (1, 1, 1, 1, 1, 1, 1): '8',
        (1, 1, 1, 1, 0, 1, 1): '9',
    }

    def __init__(self, num_digits=4, cam_id=0, exposure_time=None, gain=None):
        """
        Initialize the LCD reader.
        
        Args:
            num_digits: Number of digits in the display (default: 4)
            cam_id: Camera device ID (default: 0)
            exposure_time: Fixed exposure time in microseconds (None = auto)
            gain: Fixed gain value (None = auto)
        """
        self.num_digits = num_digits
        self.cam_id = cam_id
        self.exposure_time = exposure_time
        self.gain = gain
        
        # Camera objects
        self.picamera = None
        self.cv2_camera = None
        
        # Digit ROI boundaries (will be set via calibration or manually)
        # Format: [(x1, y1, x2, y2), ...] for each digit
        self.digit_rois = None
        
        # Segment ROI boundaries relative to digit ROI
        # Format: {segment_name: (x1, y1, x2, y2), ...}
        # These are proportions (0.0 to 1.0) of the digit ROI
        self.segment_rois = self._default_segment_rois()
        
        # Threshold for segment detection (proportion of pixels that must be active)
        self.segment_threshold = 0.5
        
        # Initialize camera
        self._init_camera()

    def _default_segment_rois(self):
        """
        Define default segment ROI positions as proportions of digit ROI.
        These are typical for 7-segment displays but may need calibration.
        
        Returns:
            Dictionary mapping segment names to (x1, y1, x2, y2) proportions
        """
        return {
            'top':          (0.2, 0.0, 0.8, 0.2),
            'top_left':     (0.0, 0.0, 0.3, 0.5),
            'top_right':    (0.7, 0.0, 1.0, 0.5),
            'middle':       (0.2, 0.4, 0.8, 0.6),
            'bottom_left':  (0.0, 0.5, 0.3, 1.0),
            'bottom_right': (0.7, 0.5, 1.0, 1.0),
            'bottom':       (0.2, 0.8, 0.8, 1.0),
        }
    
    def _init_camera(self):
        """Initialize camera with locked exposure and gain if available."""
        if PICAMERA2_AVAILABLE:
            try:
                print("🎥 Initializing Picamera2...")
                self.picamera = Picamera2()
                config = self.picamera.create_still_configuration()
                self.picamera.configure(config)
                
                # Lock exposure and gain if specified
                if self.exposure_time is not None:
                    self.picamera.set_controls({"ExposureTime": self.exposure_time})
                if self.gain is not None:
                    self.picamera.set_controls({"AnalogueGain": self.gain})
                
                self.picamera.start()
                print("✓ Picamera2 initialized successfully")
            except (RuntimeError, ValueError) as e:
                print(f"⚠️  Failed to initialize Picamera2: {e}")
                print("   Falling back to cv2.VideoCapture...")
                self.picamera = None
                self._init_cv2_camera()
        else:
            self._init_cv2_camera()
    
    def _init_cv2_camera(self):
        """Initialize OpenCV camera with manual settings."""
        print(f"🎥 Initializing cv2.VideoCapture (camera {self.cam_id})...")
        self.cv2_camera = cv2.VideoCapture(self.cam_id)
        
        if not self.cv2_camera.isOpened():
            raise RuntimeError(f"Failed to open camera {self.cam_id}")
        
        # Try to disable auto-exposure and set manual values
        # Note: These settings may not work on all cameras
        if self.exposure_time is not None:
            self.cv2_camera.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)  # Manual mode
            self.cv2_camera.set(cv2.CAP_PROP_EXPOSURE, self.exposure_time)
        
        if self.gain is not None:
            self.cv2_camera.set(cv2.CAP_PROP_GAIN, self.gain)
        
        print("✓ cv2.VideoCapture initialized successfully")
    
    def capture_image(self, save=False, output_path='lcd_capture.jpg'):
        """
        Capture an image from the camera.
        
        Args:
            save: Whether to save the captured image
            output_path: Path to save the image
            
        Returns:
            numpy array (BGR format) or None if capture failed
        """
        frame = None
        
        if self.picamera is not None:
            try:
                frame = self.picamera.capture_array()
                # Convert RGB to BGR for OpenCV compatibility
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            except (RuntimeError, ValueError) as e:
                print(f"⚠️Picamera2 capture failed: {e}")
        elif self.cv2_camera is not None:
            ret, frame = self.cv2_camera.read()
            if not ret:
                print("⚠️  cv2.VideoCapture read failed")
                frame = None
        
        if frame is not None and save:
            cv2.imwrite(output_path, frame)
            print(f"✓ Image saved to {output_path}")
        
        return frame

    def preprocess_frame(self, frame, debug=False, debug_prefix="debug"):
        """
        Phase 1: Image Acquisition & Advanced Preprocessing
        
        Converts frame to LAB color space, extracts b-channel, and applies CLAHE
        to enhance LCD segment contrast.
        
        Args:
            frame: Input BGR frame from camera
            debug: Whether to save debug images
            debug_prefix: Prefix for debug image filenames
            
        Returns:
            Binary image with enhanced LCD segments
        """
        if frame is None:
            raise ValueError("Input frame is None")
        
        if debug:
            cv2.imwrite(f"{debug_prefix}_step1_original.png", frame)
        
        # Step 1: Convert BGR to LAB color space
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step2_lab.png", lab)
        
        # Step 2: Extract b-channel (blue-yellow axis)
        # This provides best contrast for LCD segments
        _l_channel, _a_channel, b_channel = cv2.split(lab)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step3_b_channel.png", b_channel)
        
        # Step 3: Apply CLAHE to enhance local contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(b_channel)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step4_clahe.png", enhanced)
        
        # Step 4: Threshold to create binary image
        # Use Otsu's method to automatically determine threshold
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step5_binary.png", binary)
        
        # Step 5: Morphological operations to clean up noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step6_cleaned.png", cleaned)
        
        return cleaned

    def set_digit_rois(self, rois):
        """
        Set the ROI boundaries for each digit.
        
        Args:
            rois: List of tuples [(x1, y1, x2, y2), ...] for each digit
        """
        if len(rois) != self.num_digits:
            raise ValueError(f"Expected {self.num_digits} ROIs, got {len(rois)}")
        self.digit_rois = rois
    
    def auto_detect_digit_rois(self, binary_frame):
        """
        Attempt to automatically detect digit ROIs using contour detection.
        
        Args:
            binary_frame: Preprocessed binary image
            
        Returns:
            List of digit ROIs [(x1, y1, x2, y2), ...]
        """
        # Find contours
        contours, _ = cv2.findContours(binary_frame, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter contours by size and aspect ratio
        digit_contours = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = h / w if w > 0 else 0
            area = w * h
            
            # Typical 7-segment digit has aspect ratio between 1.5 and 2.5
            if 1.2 < aspect_ratio < 3.0 and area > 100:
                digit_contours.append((x, y, x + w, y + h))
        
        # Sort by x-coordinate (left to right)
        digit_contours.sort(key=lambda roi: roi[0])
        
        # Take the first num_digits contours
        if len(digit_contours) >= self.num_digits:
            return digit_contours[:self.num_digits]
        else:
            print(f"⚠️  Found {len(digit_contours)} digit contours, expected {self.num_digits}")
            return digit_contours if digit_contours else None
    
    def extract_digit_roi(self, binary_frame, digit_idx):
        """
        Extract a single digit ROI from the binary frame.
        
        Args:
            binary_frame: Preprocessed binary image
            digit_idx: Index of the digit to extract
            digit
        Returns:
            Cropped digit image or None
        """
        if self.digit_rois is None or digit_idx >= len(self.digit_rois):
            return None
        
        x1, y1, x2, y2 = self.digit_rois[digit_idx]
        return binary_frame[y1:y2, x1:x2]
    
    def analyze_segment(self, digit_roi, segment_name):
        """
        Phase 3: Segment Analysis Logic
        
        Analyzes a single segment within a digit ROI to determine if it's active.
        
        Args:
            digit_roi: Binary image of a single digit
            segment_name: Name of the segment ('top', 'middle', etc.)
            
        Returns:
            1 if segment is active (ON), 0 if inactive (OFF)
        """
        if digit_roi is None or segment_name not in self.segment_rois:
            return 0
        
        h, w = digit_roi.shape[:2]
        x1_prop, y1_prop, x2_prop, y2_prop = self.segment_rois[segment_name]
        
        # Convert proportions to pixel coordinates
        x1 = int(x1_prop * w)
        y1 = int(y1_prop * h)
        x2 = int(x2_prop * w)
        y2 = int(y2_prop * h)
        
        # Extract segment ROI
        segment = digit_roi[y1:y2, x1:x2]
        
        if segment.size == 0:
            return 0
        
        # Count active (white) pixels
        active_pixels = cv2.countNonZero(segment)
        total_pixels = segment.size
        
        # Return 1 if more than threshold percentage are active
        return 1 if (active_pixels / total_pixels) > self.segment_threshold else 0
    
    def recognize_digit(self, digit_roi, debug=False):
        """
        Phase 4: Recognition via Lookup Table
        
        Recognizes a single digit by analyzing all 7 segments.
        
        Args:
            digit_roi: Binary image of a single digit
            debug: Whether to print debug information
            
        Returns:
            Recognized digit as string or '?' if not recognized
        """
        if digit_roi is None:
            return '?'
        
        # Analyze all 7 segments in order
        segments = (
            self.analyze_segment(digit_roi, 'top'),
            self.analyze_segment(digit_roi, 'top_left'),
            self.analyze_segment(digit_roi, 'top_right'),
            self.analyze_segment(digit_roi, 'middle'),
            self.analyze_segment(digit_roi, 'bottom_left'),
            self.analyze_segment(digit_roi, 'bottom_right'),
            self.analyze_segment(digit_roi, 'bottom'),
        )
        
        if debug:
            print(f"  Segment pattern: {segments}")
        
        # Look up digit in lookup table
        return self.DIGITS_LOOKUP.get(segments, '?')
    
    def read_display(self, frame=None, debug=False, debug_prefix="debug"):
        """
        Complete pipeline: Read all digits from LCD display.
        
        Args:
            frame: Input BGR frame (if None, captures from camera)
            debug: Whether to save debug images
            debug_prefix: Prefix for debug image filenames
            
        Returns:
            String with recognized digits or None if reading failed
        """
        # Capture frame if not provided
        if frame is None:
            frame = self.capture_image()
            if frame is None:
                print("❌ Failed to capture image")
                return None
        
        # Preprocess frame
        binary = self.preprocess_frame(frame, debug=debug, debug_prefix=debug_prefix)
        
        # Auto-detect digit ROIs if not set
        if self.digit_rois is None:
            print("📍 Auto-detecting digit ROIs...")
            self.digit_rois = self.auto_detect_digit_rois(binary)
            if self.digit_rois is None:
                print("❌ Failed to detect digit ROIs")
                return None
            print(f"✓ Detected {len(self.digit_rois)} digit ROIs")
        
        # Read each digit
        result = []
        for i in range(self.num_digits):
            digit_roi = self.extract_digit_roi(binary, i)
            digit = self.recognize_digit(digit_roi, debug=debug)
            result.append(digit)
            if debug:
                print(f"  Digit {i}: {digit}")
        
        return ''.join(result)
    
    def calibrate(self, frame=None, save_calibration=True):
        """
        Interactive calibration to manually set digit ROIs.
        
        Args:
            frame: Input BGR frame (if None, captures from camera)
            save_calibration: Whether to save calibration to file
            
        Returns:
            True if calibration successful
        """
        if frame is None:
            frame = self.capture_image()
            if frame is None:
                print("❌ Failed to capture image for calibration")
                return False
        
        # Preprocess
        binary = self.preprocess_frame(frame, debug=True, debug_prefix="calibration")
        
        print("\n" + "=" * 60)
        print("CALIBRATION MODE")
        print("=" * 60)
        print("Please check the debug images:")
        print("  - calibration_step6_cleaned.png (final binary image)")
        print("\nYou need to manually determine digit ROI boundaries.")
        print("Use an image viewer to find pixel coordinates.\n")
        
        rois = []
        for i in range(self.num_digits):
            print(f"Digit {i}:")
            x1 = int(input("  x1 (left): "))
            y1 = int(input("  y1 (top): "))
            x2 = int(input("  x2 (right): "))
            y2 = int(input("  y2 (bottom): "))
            rois.append((x1, y1, x2, y2))
        
        self.set_digit_rois(rois)
        
        if save_calibration:
            import json
            with open('lcd_calibration.json', 'w', encoding='utf-8') as f:
                json.dump({'digit_rois': rois}, f, indent=2)
            print("\n✓ Calibration saved to lcd_calibration.json")
        
        # Test the calibration
        print("\n" + "=" * 60)
        print("TESTING CALIBRATION")
        print("=" * 60)
        result = self.read_display(frame, debug=True, debug_prefix="test")
        print(f"\nRead: {result}")
        
        return True
    
    def load_calibration(self, filepath='lcd_calibration.json'):
        """
        Load calibration from file.
        
        Args:
            filepath: Path to calibration JSON file
            
        Returns:
            True if loaded successfully
        """
        try:
            import json
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.digit_rois = [tuple(roi) for roi in data['digit_rois']]
            print(f"✓ Calibration loaded from {filepath}")
            return True
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            print(f"⚠️  Failed to load calibration: {e}")
            return False
    
    def __del__(self):
        """Clean up camera resources."""
        if self.picamera is not None:
            try:
                self.picamera.stop()
            except (RuntimeError, AttributeError):
                pass
        if self.cv2_camera is not None:
            try:
                self.cv2_camera.release()
            except (RuntimeError, AttributeError):
                pass


def main():
    """
    Test the segment-based LCD reader.
    """
    import os
    
    print("\n" + "=" * 80)
    print("📺 SEGMENT-BASED LCD READER TEST")
    print("=" * 80)
    
    # Initialize reader
    print("\n🔧 Initializing LCD reader...")
    reader = HardnessTester(num_digits=4, cam_id=0)
    
    # Try to load existing calibration
    if os.path.exists('lcd_calibration.json'):
        print("\n📁 Loading existing calibration...")
        reader.load_calibration()
    
    # Option 1: Test with captured image
    print("\n📷 Capturing image from camera...")
    frame = reader.capture_image(save=True, output_path='lcd_test_capture.jpg')
    
    if frame is not None:
        print("✓ Image captured successfully")
        
        # If no calibration exists, run calibration
        if reader.digit_rois is None:
            print("\n⚠️  No calibration found. Starting calibration process...")
            reader.calibrate(frame=frame)
        else:
            # Read display
            print("\n🔍 Reading LCD display...")
            result = reader.read_display(frame=frame, debug=True, debug_prefix="lcd_read")
            
            print("\n" + "=" * 80)
            print(f"📊 RESULT: {result}")
            print("=" * 80)
            
            # Show segment patterns for debugging
            print("\nSegment patterns detected:")
            binary = reader.preprocess_frame(frame)
            for i in range(reader.num_digits):
                digit_roi = reader.extract_digit_roi(binary, i)
                if digit_roi is not None:
                    segments = (
                        reader.analyze_segment(digit_roi, 'top'),
                        reader.analyze_segment(digit_roi, 'top_left'),
                        reader.analyze_segment(digit_roi, 'top_right'),
                        reader.analyze_segment(digit_roi, 'middle'),
                        reader.analyze_segment(digit_roi, 'bottom_left'),
                        reader.analyze_segment(digit_roi, 'bottom_right'),
                        reader.analyze_segment(digit_roi, 'bottom'),
                    )
                    print(f"  Digit {i}: {segments} → {result[i] if i < len(result) else '?'}")
    else:
        print("❌ Failed to capture image")
    
    # Option 2: Test with static image file
    print("\n" + "=" * 80)
    print("📁 Testing with static image file...")
    print("=" * 80)
    
    test_image = "test.png"
    if os.path.exists(test_image):
        print(f"\n📸 Loading {test_image}...")
        static_frame = cv2.imread(test_image)
        
        if static_frame is not None:
            # Try auto-detection
            print("\n🔍 Attempting auto-detection of digit ROIs...")
            binary = reader.preprocess_frame(static_frame, debug=True, debug_prefix="static")
            detected_rois = reader.auto_detect_digit_rois(binary)
            
            if detected_rois:
                print(f"✓ Detected {len(detected_rois)} digit ROIs:")
                for i, roi in enumerate(detected_rois):
                    print(f"  Digit {i}: {roi}")
                
                reader.set_digit_rois(detected_rois)
                result = reader.read_display(frame=static_frame, debug=True, debug_prefix="static_read")
                print(f"\n📊 RESULT: {result}")
            else:
                print("⚠️  Auto-detection failed. Manual calibration required.")
    else:
        print(f"⚠️  Test image '{test_image}' not found")
    
    print("\n" + "=" * 80)
    print("✓ Test complete")
    print("=" * 80)


def test_with_image(image_path, calibration_file='lcd_calibration.json'):
    """
    Simple test function to read LCD from a single image.
    
    Args:
        image_path: Path to LCD image
        calibration_file: Path to calibration file (optional)
    """
    import os
    
    reader = HardnessTester(num_digits=4)
    
    # Load calibration if available
    if os.path.exists(calibration_file):
        reader.load_calibration(calibration_file)
    
    # Read image
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"❌ Failed to load image: {image_path}")
        return None
    
    # Read display
    result = reader.read_display(frame=frame, debug=True, debug_prefix="test")
    print(f"\n📊 Result: {result}")
    return result


if __name__ == "__main__":
    main()
