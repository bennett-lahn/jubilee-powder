import cv2
import glob
import os
import re
import threading
import time
import numpy as np

# Try to import Picamera2 for Raspberry Pi
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    print("WARNING: Picamera2 not available. Camera capture is disabled.")

# Optional package for creating animated debug GIFs
try:
    import imageio.v2 as imageio
    IMAGEIO_AVAILABLE = True
except ImportError:
    IMAGEIO_AVAILABLE = False
    print("WARNING: imageio not available. Debug GIF generation is disabled.")


DEFAULT_CALIBRATION_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "jubilee_api_config", "lcd_calibration.json")
)

"""
SEGMENT-BASED LCD READING FOR 7-SEGMENT DISPLAYS

INSTALLATION:
Required:
    pip install opencv-python
    pip install imageio  # For bundling debug images into animated GIFs
    
Optional (Raspberry Pi):
    pip install picamera2  # For Raspberry Pi camera with better control

METHODOLOGY:
This approach reads 7-segment LCD displays by detecting which segments are active,
rather than using traditional OCR. This is much more reliable for LCD displays.

PIPELINE:
Phase 1: Image Acquisition & Advanced Preprocessing
    - Direct camera capture with automatic camera settings
    - Grayscale conversion for primary preprocessing
    - CLAHE (Contrast Limited Adaptive Histogram Equalization)
    
Phase 2: Segment Analysis Logic
    - Extract individual digit ROIs
    - Map 7 segments per digit (top, top-left, top-right, middle, bottom-left, bottom-right, bottom)
    - Count active pixels in each segment
    
Phase 3: Recognition via Lookup Table
    - Map segment patterns to digits using predefined lookup table
"""

class HardnessTester:
    """
    LCD 7-Segment Display Reader using segment detection instead of OCR.
    """
    
    # Segment order: (top, top-left, top-right, middle, bottom-left, bottom-right, bottom)
    DIGITS_LOOKUP = {
        (0, 0, 0, 0, 0, 0, 0): 'OFF',
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
    SEGMENT_ORDER = ('top', 'top_left', 'top_right', 'middle', 'bottom_left', 'bottom_right', 'bottom')

    def __init__(self, num_digits=4, cam_id=0, use_camera=True):
        """
        Initialize the LCD reader.
        
        Args:
            num_digits: Number of digits in the display (default: 4)
            cam_id: Camera device ID (default: 0)
            use_camera: Whether to initialize and use a camera device
        """
        self.num_digits = num_digits
        self.cam_id = cam_id
        self.use_camera = use_camera
        
        # Camera objects
        self.picamera = None
        self._capture_thread = None
        self._stop_capture_event = threading.Event()
        self._frame_ready_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        
        # Digit ROI boundaries (will be set via calibration or manually)
        # Format: [(x1, y1, x2, y2), ...] for each digit
        self.digit_rois = None
        
        # Segment polygons (absolute pixel coordinates)
        # Format: [{segment_name: [(x, y), ...], ...}, ...] for each digit
        self.segment_points = None
        
        # Threshold for segment detection (proportion of pixels that must be active)
        self.segment_threshold = 0.5
        
        # Initialize camera only when requested
        if self.use_camera:
            self._init_camera()

    def _default_segment_templates(self):
        """
        Define default segment polygons as proportions of a digit ROI.
        Each segment is represented as a polygon.
        
        Returns:
            Dictionary mapping segment names to point lists [(x, y), ...]
        """
        return {
            # Horizontal segments: trapezoids with outer face larger.
            'top': [
                (0.06, 0.02),
                (0.94, 0.02),
                (0.82, 0.12),
                (0.18, 0.12),
            ],
            # Vertical segments: trapezoids with outer face larger.
            'top_left': [
                (0.03, 0.06),
                (0.22, 0.12),
                (0.18, 0.44),
                (0.00, 0.49),
            ],
            'top_right': [
                (0.97, 0.06),
                (1.00, 0.49),
                (0.82, 0.44),
                (0.78, 0.12),
            ],
            # Middle segment: two trapezoids merged (long faces inward).
            'middle': [
                (0.10, 0.50),
                (0.26, 0.43),
                (0.74, 0.43),
                (0.90, 0.50),
                (0.74, 0.57),
                (0.26, 0.57),
            ],
            'bottom_left': [
                (0.00, 0.51),
                (0.18, 0.56),
                (0.22, 0.88),
                (0.03, 0.95),
            ],
            'bottom_right': [
                (1.00, 0.51),
                (0.97, 0.95),
                (0.78, 0.88),
                (0.82, 0.56),
            ],
            'bottom': [
                (0.18, 0.88),
                (0.82, 0.88),
                (0.94, 0.98),
                (0.06, 0.98),
            ],
        }

    def _build_default_segment_points(self, digit_rois):
        """
        Build absolute segment polygons for each digit from template proportions.

        Args:
            digit_rois: List of digit ROIs [(x1, y1, x2, y2), ...]

        Returns:
            List of per-digit segment polygon dictionaries.
        """
        templates = self._default_segment_templates()
        segment_points = []
        for x1, y1, x2, y2 in digit_rois:
            width = x2 - x1
            height = y2 - y1
            digit_segments = {}
            for segment_name in self.SEGMENT_ORDER:
                points = []
                for px, py in templates[segment_name]:
                    points.append((x1 + int(round(px * width)), y1 + int(round(py * height))))
                digit_segments[segment_name] = points
            segment_points.append(digit_segments)
        return segment_points
    
    def _init_camera(self):
        """Initialize Picamera2 camera."""
        if not PICAMERA2_AVAILABLE:
            raise RuntimeError("Picamera2 is required for camera mode but is not available.")
        try:
            print("Initializing Picamera2...")
            self.picamera = Picamera2()
            config = self.picamera.create_still_configuration()
            self.picamera.configure(config)
            self.picamera.start()
            self._start_capture_thread()
            print("Picamera2 initialized successfully")
        except (RuntimeError, ValueError) as e:
            self.picamera = None
            raise RuntimeError(f"Failed to initialize Picamera2: {e}") from e

    def _start_capture_thread(self):
        """Start background thread that continuously captures latest frame."""
        self._stop_capture_event.clear()
        self._frame_ready_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self._capture_thread.start()

    def _capture_worker(self):
        """Continuously capture frames and publish the newest frame."""
        while not self._stop_capture_event.is_set():
            if self.picamera is None:
                time.sleep(0.1)
                continue
            try:
                frame = self.picamera.capture_array()
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                with self._frame_lock:
                    self._latest_frame = frame
                self._frame_ready_event.set()
            except (RuntimeError, ValueError) as e:
                print(f"WARNING: Picamera2 background capture failed: {e}")
                time.sleep(0.02)

    def _stop_capture_thread(self):
        """Stop background frame capture thread safely."""
        self._stop_capture_event.set()
        if self._capture_thread is not None and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        self._capture_thread = None
    
    def capture_image(self, save=False, output_path='lcd_capture.jpg'):
        """
        Capture an image from the camera.
        
        Args:
            save: Whether to save the captured image
            output_path: Path to save the image
            
        Returns:
            numpy array (BGR format) or None if capture failed
        """
        if not self.use_camera:
            print("WARNING: Camera capture requested but camera mode is disabled")
            return None

        if self.picamera is None:
            print("WARNING: Picamera2 camera is not initialized")
            return None

        if not self._frame_ready_event.wait(timeout=1.0):
            print("WARNING: Timed out waiting for camera frame")
            return None

        with self._frame_lock:
            frame = None if self._latest_frame is None else self._latest_frame.copy()
        
        if frame is not None and save:
            cv2.imwrite(output_path, frame)
            print(f"Image saved to {output_path}")
        
        return frame

    def preprocess_frame(self, frame, debug=False, debug_prefix="debug"):
        """
        Phase 1: Image Acquisition & Advanced Preprocessing
        
        Converts frame to grayscale and applies CLAHE to enhance LCD segment
        contrast.
        
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
        
        # Step 1: Convert BGR to grayscale (primary path)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step2_gray.png", gray)
        
        # Step 2: Apply CLAHE to enhance local contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step4_clahe.png", enhanced)
        
        # Step 3: Threshold to create binary image
        # Use Otsu's method to automatically determine threshold
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step5_binary.png", binary)
        
        # Step 4: Morphological operations to clean up noise
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
    
    def _save_segment_roi_debug_overlay(self, binary_frame, debug_prefix):
        """
        Save an overlay image showing all segment ROIs on the final binary frame.

        Args:
            binary_frame: Final preprocessed binary image
            debug_prefix: Prefix for debug image filenames
        """
        if binary_frame is None or self.segment_points is None:
            return

        overlay = cv2.cvtColor(binary_frame, cv2.COLOR_GRAY2BGR)

        for digit_segments in self.segment_points:
            for segment_name in self.SEGMENT_ORDER:
                points = digit_segments.get(segment_name)
                if not points or len(points) < 3:
                    continue
                polygon = self._normalize_polygon_point_order(points)
                if polygon is None:
                    continue
                cv2.polylines(overlay, [polygon], isClosed=True, color=(0, 255, 0), thickness=1)

        cv2.imwrite(f"{debug_prefix}_step7_segment_rois.png", overlay)

    def _normalize_polygon_point_order(self, points):
        """
        Order polygon points around centroid to avoid self-crossing edges.

        Args:
            points: Iterable of (x, y) points

        Returns:
            np.int32 polygon array or None
        """
        if points is None or len(points) < 3:
            return None

        polygon = np.array(points, dtype=np.float32)
        center = np.mean(polygon, axis=0)
        angles = np.arctan2(polygon[:, 1] - center[1], polygon[:, 0] - center[0])
        order = np.argsort(angles)
        return polygon[order].astype(np.int32)

    def _save_debug_gif(self, debug_prefix):
        """
        Bundle debug PNG images into an animated GIF.

        Uses all files matching "<debug_prefix>_step*.png", sorted by step number.
        Each frame shows for 1 second, and the last frame is held for 2 seconds.
        """
        if not IMAGEIO_AVAILABLE:
            return

        debug_images = glob.glob(f"{debug_prefix}_step*.png")
        if not debug_images:
            return

        def _sort_key(path):
            filename = os.path.basename(path)
            match = re.search(r"_step(\d+)_", filename)
            step_num = int(match.group(1)) if match else 9999
            return (step_num, filename)

        debug_images.sort(key=_sort_key)

        frames = []
        base_size = None
        for image_path in debug_images:
            image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
            if image is None:
                continue

            if len(image.shape) == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            elif image.shape[2] == 4:
                image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

            if base_size is None:
                base_size = (image.shape[1], image.shape[0])
            elif (image.shape[1], image.shape[0]) != base_size:
                image = cv2.resize(image, base_size, interpolation=cv2.INTER_NEAREST)

            frames.append(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

        if not frames:
            return

        durations = [1.0] * len(frames)
        durations[-1] = 2.0
        gif_path = f"{debug_prefix}_debug.gif"
        imageio.mimsave(gif_path, frames, duration=durations, loop=0)
        print(f"Debug GIF saved to {gif_path}")
    
    def analyze_segment(self, binary_frame, digit_idx, segment_name):
        """
        Phase 3: Segment Analysis Logic
        
        Analyzes a single segment within a digit ROI to determine if it's active.
        
        Args:
            binary_frame: Full preprocessed binary image
            digit_idx: Index of digit in display
            segment_name: Name of the segment ('top', 'middle', etc.)
            
        Returns:
            1 if segment is active (ON), 0 if inactive (OFF)
        """
        if (
            binary_frame is None
            or self.segment_points is None
            or digit_idx >= len(self.segment_points)
            or segment_name not in self.segment_points[digit_idx]
        ):
            return 0

        points = self.segment_points[digit_idx][segment_name]
        polygon = self._normalize_polygon_point_order(points)
        if polygon is None:
            return 0

        h, w = binary_frame.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask, [polygon], 255)
        total_pixels = cv2.countNonZero(mask)
        if total_pixels == 0:
            return 0

        segment_masked = cv2.bitwise_and(binary_frame, binary_frame, mask=mask)
        # Otsu typically yields dark digit segments on a bright background.
        # Count dark (zero) pixels as active segment pixels.
        non_zero_pixels = cv2.countNonZero(segment_masked)
        active_pixels = total_pixels - non_zero_pixels
        
        # Return 1 if more than threshold percentage are active
        return 1 if (active_pixels / total_pixels) > self.segment_threshold else 0
    
    def recognize_digit(self, binary_frame, digit_idx, debug=False):
        """
        Phase 4: Recognition via Lookup Table
        
        Recognizes a single digit by analyzing all 7 segments.
        
        Args:
            binary_frame: Full preprocessed binary image
            digit_idx: Index of digit in display
            debug: Whether to print debug information
            
        Returns:
            Recognized digit as string or '?' if not recognized
        """
        if binary_frame is None:
            return '?'
        
        # Analyze all 7 segments in order
        segments = (
            self.analyze_segment(binary_frame, digit_idx, 'top'),
            self.analyze_segment(binary_frame, digit_idx, 'top_left'),
            self.analyze_segment(binary_frame, digit_idx, 'top_right'),
            self.analyze_segment(binary_frame, digit_idx, 'middle'),
            self.analyze_segment(binary_frame, digit_idx, 'bottom_left'),
            self.analyze_segment(binary_frame, digit_idx, 'bottom_right'),
            self.analyze_segment(binary_frame, digit_idx, 'bottom'),
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
                print("Failed to capture image")
                return None
        
        # Preprocess frame
        binary = self.preprocess_frame(frame, debug=debug, debug_prefix=debug_prefix)
        
        # Calibration ROIs are required (auto-detection disabled)
        if self.segment_points is None:
            print("No calibrated segment points loaded. Please calibrate first.")
            return None

        if debug:
            self._save_segment_roi_debug_overlay(binary, debug_prefix)
        
        # Read each digit
        result = []
        for i in range(self.num_digits):
            digit = self.recognize_digit(binary, i, debug=debug)
            result.append(digit)
            if debug:
                print(f"  Digit {i}: {digit}")

        if debug:
            self._save_debug_gif(debug_prefix)

        return ''.join(result)
    
    def calibrate(self, frame=None, image_path=None, save_calibration=True, calibration_path=DEFAULT_CALIBRATION_PATH):
        """
        Interactive calibration to manually set digit ROIs.
        
        Args:
            frame: Input BGR frame (if None, uses image_path or captures from camera)
            image_path: Path to an existing image for calibration (optional)
            save_calibration: Whether to save calibration to file
            calibration_path: Path where calibration JSON should be saved
            
        Returns:
            True if calibration successful
        """
        if frame is None:
            if image_path is not None:
                frame = cv2.imread(image_path)
                if frame is None:
                    print(f"Failed to load calibration image: {image_path}")
                    return False
            else:
                frame = self.capture_image()
                if frame is None:
                    print("Failed to capture image for calibration")
                    return False
        
        # Preprocess
        binary = self.preprocess_frame(frame, debug=True, debug_prefix="calibration")
        self._save_debug_gif("calibration")
        
        print("\n" + "=" * 60)
        print("CALIBRATION MODE")
        print("=" * 60)
        print("Please check the debug images:")
        print("  - calibration_step6_cleaned.png (final binary image)")
        print("\nCalibration requires:")
        print("  1) Digit ROI boundaries")
        print("  2) Every polygon point for every segment of every digit")
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
        default_segment_points = self._build_default_segment_points(rois)

        segment_points = []
        print("\nNow enter segment polygon points.")
        print("For each point, type: x,y")
        print("Press Enter to accept the shown default.\n")
        for digit_idx in range(self.num_digits):
            print(f"Digit {digit_idx} segment points:")
            digit_segments = {}
            for segment_name in self.SEGMENT_ORDER:
                default_points = default_segment_points[digit_idx][segment_name]
                print(f"  Segment '{segment_name}' ({len(default_points)} points):")
                points = []
                for point_idx, (dx, dy) in enumerate(default_points):
                    raw = input(f"    p{point_idx} [{dx},{dy}]: ").strip()
                    if raw == "":
                        points.append((dx, dy))
                        continue
                    try:
                        sx, sy = raw.split(",")
                        points.append((int(sx.strip()), int(sy.strip())))
                    except ValueError:
                        print("      Invalid input, using default.")
                        points.append((dx, dy))
                digit_segments[segment_name] = points
            segment_points.append(digit_segments)
        self.segment_points = segment_points
        
        if save_calibration:
            import json
            calibration_dir = os.path.dirname(calibration_path)
            if calibration_dir:
                os.makedirs(calibration_dir, exist_ok=True)
            with open(calibration_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {
                        'digit_rois': rois,
                        'segment_points': self.segment_points,
                    },
                    f,
                    indent=2,
                )
            print(f"\nCalibration saved to {calibration_path}")
        
        # Test the calibration
        print("\n" + "=" * 60)
        print("TESTING CALIBRATION")
        print("=" * 60)
        result = self.read_display(frame, debug=True, debug_prefix="test")
        print(f"\nRead: {result}")
        
        return True
    
    def load_calibration(self, filepath=DEFAULT_CALIBRATION_PATH):
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
                loaded_segment_points = []
                for digit_segments in data['segment_points']:
                    normalized = {}
                    for segment_name in self.SEGMENT_ORDER:
                        points = digit_segments.get(segment_name, [])
                        normalized[segment_name] = [tuple(point) for point in points]
                    loaded_segment_points.append(normalized)
                self.segment_points = loaded_segment_points
            print(f"Calibration loaded from {filepath}")
            return True
        except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
            print(f"WARNING: Failed to load calibration: {e}")
            return False
    
    def __del__(self):
        """Clean up camera resources."""
        self._stop_capture_thread()
        if self.picamera is not None:
            try:
                self.picamera.stop()
            except (RuntimeError, AttributeError):
                pass
        


def main():
    """
    Test the segment-based LCD reader.
    """
    import argparse
    parser = argparse.ArgumentParser(description="Segment-based LCD reader for hardness tester")
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Path to an existing image file to read instead of capturing from camera",
    )
    parser.add_argument(
        "--calibration",
        type=str,
        default=DEFAULT_CALIBRATION_PATH,
        help="Path to calibration JSON file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug image output",
    )
    parser.add_argument(
        "--debug-prefix",
        type=str,
        default="lcd_read",
        help="Prefix for debug images",
    )
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("SEGMENT-BASED LCD READER TEST")
    print("=" * 80)
    
    # Initialize reader (camera is optional in image mode)
    print("\nInitializing LCD reader...")
    reader = HardnessTester(num_digits=4, cam_id=0, use_camera=(args.image is None))
    
    # Try to load existing calibration
    if os.path.exists(args.calibration):
        print("\nLoading existing calibration...")
        reader.load_calibration(args.calibration)
    
    if args.image:
        print(f"\nLoading image from CLI: {args.image}")
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"Failed to load image: {args.image}")
            return
    else:
        print("\nCapturing image from camera...")
        frame = reader.capture_image(save=True, output_path='lcd_test_capture.jpg')
        if frame is None:
            print("Failed to capture image")
            return
        print("Image captured successfully")

    if reader.segment_points is None:
        print("\nNo calibration found. Starting calibration process...")
        ok = reader.calibrate(
            frame=frame,
            save_calibration=True,
            calibration_path=args.calibration,
        )
        if not ok:
            return

    # Read display
    print("\nReading LCD display...")
    result = reader.read_display(frame=frame, debug=args.debug, debug_prefix=args.debug_prefix)

    print("\n" + "=" * 80)
    print(f"RESULT: {result}")
    print("=" * 80)
    
    print("\n" + "=" * 80)
    print("Test complete")
    print("=" * 80)


def test_with_image(image_path, calibration_file=DEFAULT_CALIBRATION_PATH):
    """
    Simple test function to read LCD from a single image.
    
    Args:
        image_path: Path to LCD image
        calibration_file: Path to calibration file (optional)
    """
    reader = HardnessTester(num_digits=4, use_camera=False)
    
    # Load calibration if available
    if os.path.exists(calibration_file):
        reader.load_calibration(calibration_file)
    
    # Read image
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"Failed to load image: {image_path}")
        return None
    
    # Read display
    result = reader.read_display(frame=frame, debug=True, debug_prefix="test")
    print(f"\nResult: {result}")
    return result


if __name__ == "__main__":
    main()
