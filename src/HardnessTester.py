import cv2
import glob
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional
import numpy as np
from science_jubilee.tools.Tool import Tool

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

class HardnessTester(Tool):
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

    def __init__(
        self,
        num_digits=4,
        cam_id=0,
        use_camera=True,
        index: int = 1,
        name: Optional[str] = None,
        tester_mode: str = "shore_a",
        calibration_path: str = DEFAULT_CALIBRATION_PATH,
        tip_length_mm: Optional[float] = None,
        power_servo: Optional[str] = None,
        zero_servo: Optional[str] = None,
    ):
        """
        Initialize the LCD reader.
        
        Args:
            num_digits: Number of digits in the display (default: 4)
            cam_id: Camera device ID (default: 0)
            use_camera: Whether to initialize and use a camera device
            index: Jubilee tool index for this tester
            name: Jubilee tool name for this tester
            tester_mode: Shore tester mode ("shore_a" or "shore_d")
            calibration_path: Path to the LCD calibration json for this tester
            tip_length_mm: Physical tip length for this tester
            power_servo: Servo identifier used for power button actuation
            zero_servo: Servo identifier used for zero button actuation
        """
        super().__init__(index, name)
        self.num_digits = num_digits
        self.cam_id = cam_id
        self.use_camera = use_camera
        self.tester_mode = tester_mode
        self.calibration_path = calibration_path
        self.tip_length_mm = tip_length_mm
        self.power_servo = power_servo
        self.zero_servo = zero_servo
        
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

    @classmethod
    def from_system_config(
        cls,
        tester_mode: str,
        config_payload: dict,
        num_digits: int = 4,
        cam_id: int = 0,
        use_camera: bool = True,
    ) -> "HardnessTester":
        """Build a configured Shore tester instance from system config."""
        testers_cfg = config_payload.get("hardness_testers", {})
        if tester_mode not in testers_cfg:
            raise KeyError(f"Unknown hardness tester mode '{tester_mode}' in system config")

        tester_cfg = testers_cfg[tester_mode]
        calibration_path = tester_cfg.get("lcd_calibration_path", DEFAULT_CALIBRATION_PATH)
        if calibration_path and not os.path.isabs(calibration_path):
            project_root = Path(__file__).resolve().parent.parent
            calibration_path = str(project_root / calibration_path)

        button_servos = tester_cfg.get("button_servos", {})
        tool_cfg = tester_cfg.get("tool", {})
        return cls(
            num_digits=num_digits,
            cam_id=cam_id,
            use_camera=use_camera,
            index=tool_cfg.get("index", 1),
            name=tool_cfg.get("name", f"{tester_mode}_hardness_tester"),
            tester_mode=tester_mode,
            calibration_path=calibration_path,
            tip_length_mm=tester_cfg.get("tip_length_mm"),
            power_servo=button_servos.get("power"),
            zero_servo=button_servos.get("zero"),
        )

    def load_assigned_calibration(self) -> bool:
        """Load the calibration configured for this Shore tester."""
        return self.load_calibration(self.calibration_path)

    def turn_on(self, state_machine) -> bool:
        """
        Actuate the tester power button via the state machine action framework.
        """
        if state_machine is None:
            raise ValueError("state_machine is required for turn_on()")
        result = state_machine.validated_hardness_turn_on(mode=self.tester_mode)
        if not result.valid:
            raise RuntimeError(result.reason or "Hardness turn-on action failed")
        return True

    def turn_off(self, state_machine) -> bool:
        """
        Actuate the tester power button for shutdown via the state machine action framework.
        """
        if state_machine is None:
            raise ValueError("state_machine is required for turn_off()")
        result = state_machine.validated_hardness_turn_off(mode=self.tester_mode)
        if not result.valid:
            raise RuntimeError(result.reason or "Hardness turn-off action failed")
        return True

    def zero(self, state_machine) -> bool:
        """
        Actuate the tester zero button via the state machine action framework.
        """
        if state_machine is None:
            raise ValueError("state_machine is required for zero()")
        result = state_machine.validated_hardness_zero(mode=self.tester_mode)
        if not result.valid:
            raise RuntimeError(result.reason or "Hardness zero action failed")
        return True

    def _resolve_sample_target(
        self,
        state_machine,
        tray_index: str | int,
        sample_id: str | int,
    ):
        """
        Resolve tray-local sample id to target coordinates using tray metadata.
        """
        try:
            tray_index_int = int(str(tray_index))
        except (TypeError, ValueError):
            raise ValueError(f"Tray index '{tray_index}' must be a non-negative integer")

        if tray_index_int < 0:
            raise ValueError("Tray index must be non-negative")

        try:
            sample_index = int(str(sample_id))
        except (TypeError, ValueError):
            raise ValueError(f"Sample id '{sample_id}' must be a zero-based integer")

        if sample_index < 0:
            raise ValueError("Sample id must be non-negative")

        tray_position = next(
            (
                position
                for position in state_machine._registry._positions.values()
                if position.type.name == "HARDNESS_SAMPLE_READY"
                and position.metadata.get("tray_index") == tray_index_int
            ),
            None,
        )
        if tray_position is None:
            raise ValueError(f"Sample tray with tray_index={tray_index_int} is not configured")

        metadata = tray_position.metadata
        rows = metadata.get("rows")
        columns = metadata.get("columns")
        if not isinstance(rows, int) or not isinstance(columns, int) or rows <= 0 or columns <= 0:
            raise ValueError(
                f"Sample tray '{tray_position.identifier}' has invalid rows/columns metadata"
            )

        tray_capacity = rows * columns
        if sample_index >= tray_capacity:
            raise ValueError(
                f"Sample id '{sample_id}' is outside tray {tray_index_int} capacity ({tray_capacity})"
            )

        sample_start_x = metadata.get("sample_start_x")
        sample_start_y = metadata.get("sample_start_y")
        x_offset = metadata.get("sample_spacing_x")
        y_offset = metadata.get("sample_spacing_y")
        if not isinstance(sample_start_x, (int, float)) or not isinstance(sample_start_y, (int, float)):
            raise ValueError(
                f"Sample tray '{tray_position.identifier}' missing numeric metadata: sample_start_x, sample_start_y"
            )
        if not isinstance(x_offset, (int, float)) or not isinstance(y_offset, (int, float)):
            raise ValueError(
                f"Sample tray '{tray_position.identifier}' missing numeric metadata: sample_spacing_x/sample_spacing_y"
            )

        tray_result = state_machine._resolve_ready_position_coords(
            tray_position.identifier,
            require_v=False,
        )
        if tray_result.error:
            raise ValueError(tray_result.error.reason)
        tray_xyz = tray_result.coords
        if tray_xyz is None:
            raise ValueError(f"Sample tray '{tray_position.identifier}' coordinates could not be resolved")

        row = sample_index // columns
        column = sample_index % columns
        target_x = sample_start_x + column * x_offset
        target_y = sample_start_y + row * y_offset
        target_z = metadata.get("test_z", tray_xyz[2])
        if target_z == "USE_Z_HEIGHT_POLICY":
            target_z = tray_xyz[2]

        if not isinstance(target_z, (int, float)):
            raise ValueError(
                f"Sample tray '{tray_position.identifier}' has non-numeric target Z for testing"
            )

        return target_x, target_y, target_z

    def test_sample(self, tray_index: str | int, sample_id: str | int, state_machine) -> bool:
        """
        Execute one hardness sample operation via the state machine action path.
        """
        if state_machine is None:
            raise ValueError("state_machine is required for test_sample()")

        self.load_assigned_calibration()
        tray_result = state_machine.validated_move_to_sample_tray(tray_index)
        if not tray_result.valid:
            raise RuntimeError(tray_result.reason or "Move to sample tray failed")

        target_x, target_y, target_z = self._resolve_sample_target(
            state_machine,
            tray_index,
            sample_id,
        )
        result = state_machine.validated_test_sample(
            tray_index=tray_index,
            sample_id=sample_id,
            mode=self.tester_mode,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
        )
        if not result.valid:
            raise RuntimeError(result.reason or "Sample action failed")
        return True


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
        Interactive GUI calibration using an OpenCV popup window.

        ROI phase
        ---------
        Click and drag on the image to draw a bounding rectangle around each
        digit.  Release the mouse button to set the pending ROI (shown in cyan).
        Press Enter to confirm that digit's ROI and advance to the next digit.
        You can re-drag before pressing Enter to redo the current digit.

        Segment phase
        -------------
        For each segment of each digit the default polygon vertices are
        pre-loaded.  Click anywhere on the image to append a point; the polygon
        preview updates live.  Controls:
            d       - reset to default vertices
            c       - clear all vertices
            Backspace / Delete - remove last vertex
            Enter   - confirm vertices and advance to next segment
            q / Esc - cancel and discard all changes

        Args:
            frame: Input BGR frame (if None, uses image_path or captures from camera)
            image_path: Path to an existing image for calibration (optional)
            save_calibration: Whether to save calibration to file
            calibration_path: Path where calibration JSON should be saved

        Returns:
            True if calibration was completed and saved successfully
        """
        import json

        # --- 1. Acquire frame -----------------------------------------------
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

        self.preprocess_frame(frame, debug=True, debug_prefix="calibration")
        self._save_debug_gif("calibration")

        # --- 2. Display scaling ---------------------------------------------
        MAX_DIM = 1200
        img_h, img_w = frame.shape[:2]
        scale = min(MAX_DIM / img_w, MAX_DIM / img_h, 1.0)
        disp_w = max(int(img_w * scale), 1)
        disp_h = max(int(img_h * scale), 1)
        STATUS_H = 44  # pixels reserved for the status bar

        def to_img(dx, dy):
            return int(round(dx / scale)), int(round(dy / scale))

        def to_disp(ix, iy):
            return int(round(ix * scale)), int(round(iy * scale))

        # --- 3. Segment colours ---------------------------------------------
        SEG_COLORS = {
            'top':          (0,   255, 255),
            'top_left':     (0,   165, 255),
            'top_right':    (0,   255,   0),
            'middle':       (255,   0, 255),
            'bottom_left':  (255, 165,   0),
            'bottom_right': (0,     0, 255),
            'bottom':       (255,   0,   0),
        }

        # --- 4. Mutable state dict ------------------------------------------
        s = {
            'phase':       'roi',
            'digit_idx':   0,
            'segment_idx': 0,
            'rois':        [],
            'pending_roi': None,   # (x1,y1,x2,y2) image-coords, not yet confirmed
            'drag_origin': None,   # display (x,y) of mouse-down
            'all_segs':    [],     # [{seg_name: [(x,y),...]}] per digit
            'cur_pts':     [],     # working vertices for the active segment
            'default_segs': None, # populated after ROI phase
            'mouse':       [0, 0],
            'done':        False,
            'cancelled':   False,
        }

        # --- 5. Mouse callback ----------------------------------------------
        def on_mouse(event, x, y, flags, _param):
            s['mouse'] = [x, y]
            if s['phase'] == 'roi':
                if event == cv2.EVENT_LBUTTONDOWN:
                    s['drag_origin'] = (x, y)
                    s['pending_roi'] = None
                elif event == cv2.EVENT_MOUSEMOVE and s['drag_origin']:
                    ox, oy = s['drag_origin']
                    ix1, iy1 = to_img(min(ox, x), min(oy, y))
                    ix2, iy2 = to_img(max(ox, x), max(oy, y))
                    s['pending_roi'] = (ix1, iy1, ix2, iy2)
                elif event == cv2.EVENT_LBUTTONUP and s['drag_origin']:
                    ox, oy = s['drag_origin']
                    s['drag_origin'] = None
                    if abs(x - ox) > 5 and abs(y - oy) > 5:
                        ix1, iy1 = to_img(min(ox, x), min(oy, y))
                        ix2, iy2 = to_img(max(ox, x), max(oy, y))
                        s['pending_roi'] = (ix1, iy1, ix2, iy2)
            elif s['phase'] == 'segment':
                if event == cv2.EVENT_LBUTTONDOWN:
                    s['cur_pts'].append(to_img(x, y))

        # --- 6. Render function ---------------------------------------------
        def render():
            base = cv2.resize(frame, (disp_w, disp_h))
            canvas = np.zeros((disp_h + STATUS_H, disp_w, 3), dtype=np.uint8)
            canvas[:disp_h] = base

            # Confirmed ROIs (green)
            for i, (x1, y1, x2, y2) in enumerate(s['rois']):
                dx1, dy1 = to_disp(x1, y1)
                dx2, dy2 = to_disp(x2, y2)
                cv2.rectangle(canvas, (dx1, dy1), (dx2, dy2), (0, 255, 0), 2)
                cv2.putText(canvas, f"D{i}", (dx1 + 2, dy1 + 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

            if s['phase'] == 'roi':
                # Pending ROI (cyan)
                if s['pending_roi']:
                    x1, y1, x2, y2 = s['pending_roi']
                    dx1, dy1 = to_disp(x1, y1)
                    dx2, dy2 = to_disp(x2, y2)
                    cv2.rectangle(canvas, (dx1, dy1), (dx2, dy2), (0, 255, 255), 2)
                    cv2.putText(canvas, f"D{s['digit_idx']}", (dx1 + 2, dy1 + 14),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
                # Live drag preview
                if s['drag_origin']:
                    ox, oy = s['drag_origin']
                    mx, my = s['mouse']
                    cv2.rectangle(canvas,
                                  (min(ox, mx), min(oy, my)),
                                  (max(ox, mx), max(oy, my)),
                                  (0, 255, 255), 1)
                status = (
                    f"ROI  Digit {s['digit_idx'] + 1}/{self.num_digits} - "
                    "drag to draw box | Enter=confirm | q=quit"
                )

            else:  # segment phase
                seg_name = self.SEGMENT_ORDER[s['segment_idx']]
                hi_color = SEG_COLORS[seg_name]
                d_idx = s['digit_idx']
                def_segs = s['default_segs']

                # Faint outlines for all other segments of this digit
                if def_segs and d_idx < len(def_segs):
                    for sn in self.SEGMENT_ORDER:
                        if sn == seg_name:
                            continue
                        pts = (s['all_segs'][d_idx].get(sn)
                               if d_idx < len(s['all_segs']) else None)
                        src = pts or def_segs[d_idx].get(sn, [])
                        if len(src) >= 3:
                            poly = np.array([to_disp(x, y) for x, y in src], dtype=np.int32)
                            cv2.polylines(canvas, [poly], True, (60, 60, 60), 1)

                # Confirmed preceding segments for this digit (their actual colors)
                if d_idx < len(s['all_segs']):
                    for prev_idx in range(s['segment_idx']):
                        pn = self.SEGMENT_ORDER[prev_idx]
                        pts = s['all_segs'][d_idx].get(pn, [])
                        if len(pts) >= 3:
                            poly = np.array([to_disp(x, y) for x, y in pts], dtype=np.int32)
                            cv2.polylines(canvas, [poly], True, SEG_COLORS[pn], 1)

                # Active segment being placed
                cur = s['cur_pts']
                if len(cur) >= 2:
                    poly = np.array([to_disp(x, y) for x, y in cur], dtype=np.int32)
                    cv2.polylines(canvas, [poly], len(cur) >= 3, hi_color, 2)
                for px, py in cur:
                    cv2.circle(canvas, to_disp(px, py), 5, hi_color, -1)
                if cur:
                    lx, ly = to_disp(*cur[-1])
                    mx, my = s['mouse']
                    cv2.line(canvas, (lx, ly), (mx, min(my, disp_h - 1)), hi_color, 1)

                n_def = (len(def_segs[d_idx][seg_name])
                         if def_segs and d_idx < len(def_segs) else '?')
                status = (
                    f"SEG  Digit {d_idx + 1}/{self.num_digits}  '{seg_name}'  "
                    f"{len(cur)}/{n_def} pts - "
                    "click=add | d=default | Bksp=undo | c=clear | Enter=confirm | q=quit"
                )

            # Status bar
            cv2.rectangle(canvas, (0, disp_h), (disp_w, disp_h + STATUS_H), (20, 20, 20), -1)
            cv2.putText(canvas, status, (6, disp_h + 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
            return canvas

        # --- 7. Event loop --------------------------------------------------
        WIN = "Hardness Tester Calibration"
        cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN, disp_w, disp_h + STATUS_H)
        cv2.setMouseCallback(WIN, on_mouse)

        while not s['done'] and not s['cancelled']:
            cv2.imshow(WIN, render())
            key = cv2.waitKey(20) & 0xFF

            if key == ord('q') or key == 27:  # q or Esc
                s['cancelled'] = True
                break

            # ROI phase keys
            if s['phase'] == 'roi':
                if key in (13, 10):  # Enter
                    if s['pending_roi']:
                        s['rois'].append(s['pending_roi'])
                        s['pending_roi'] = None
                        s['digit_idx'] += 1
                        if s['digit_idx'] >= self.num_digits:
                            self.set_digit_rois(s['rois'])
                            s['default_segs'] = self._build_default_segment_points(s['rois'])
                            s['all_segs'] = [{} for _ in range(self.num_digits)]
                            s['phase'] = 'segment'
                            s['digit_idx'] = 0
                            s['segment_idx'] = 0
                            s['cur_pts'] = list(s['default_segs'][0][self.SEGMENT_ORDER[0]])

            # Segment phase keys
            elif s['phase'] == 'segment':
                seg_name = self.SEGMENT_ORDER[s['segment_idx']]
                d_idx = s['digit_idx']

                if key == ord('d'):
                    s['cur_pts'] = list(s['default_segs'][d_idx][seg_name])

                elif key == ord('c'):
                    s['cur_pts'] = []

                elif key in (8, 127):  # Backspace / Delete
                    if s['cur_pts']:
                        s['cur_pts'].pop()

                elif key in (13, 10):  # Enter
                    if s['cur_pts']:
                        s['all_segs'][d_idx][seg_name] = list(s['cur_pts'])
                        s['segment_idx'] += 1
                        if s['segment_idx'] >= len(self.SEGMENT_ORDER):
                            s['segment_idx'] = 0
                            s['digit_idx'] += 1
                            if s['digit_idx'] >= self.num_digits:
                                s['done'] = True
                                break
                        next_seg = self.SEGMENT_ORDER[s['segment_idx']]
                        s['cur_pts'] = list(s['default_segs'][s['digit_idx']][next_seg])

        cv2.destroyWindow(WIN)

        if s['cancelled'] or not s['done']:
            print("Calibration cancelled.")
            return False

        self.segment_points = s['all_segs']

        if save_calibration:
            calibration_dir = os.path.dirname(calibration_path)
            if calibration_dir:
                os.makedirs(calibration_dir, exist_ok=True)
            with open(calibration_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {
                        'digit_rois': s['rois'],
                        'segment_points': self.segment_points,
                    },
                    f,
                    indent=2,
                )
            print(f"Calibration saved to {calibration_path}")

        print("Testing calibration...")
        result = self.read_display(frame, debug=True, debug_prefix="calibration_test")
        print(f"Calibration test read: {result}")

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
        print("\nNo calibration found. Opening calibration UI...")
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
