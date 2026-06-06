"""Segment-based LCD reading for 7-segment displays.

INSTALLATION:
Required:
    pip install opencv-python
    pip install imageio  # For bundling debug images into animated GIFs

Optional (Raspberry Pi):
    pip install opencv-python  # For camera capture

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

import glob
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from science_jubilee.tools.Tool import Tool

if TYPE_CHECKING:
    from src.ConfigLoader import HardnessTesterConfig

# Optional package for creating animated debug GIFs
try:
    import imageio.v2 as imageio

    IMAGEIO_AVAILABLE = True
except ImportError:
    IMAGEIO_AVAILABLE = False
    print("WARNING: imageio not available. Debug GIF generation is disabled.")


class HardnessTester(Tool):
    """
    LCD 7-Segment Display Reader using segment detection instead of OCR.
    """

    # Segment order: (top, top-left, top-right, middle, bottom-left, bottom-right, bottom)
    DIGITS_LOOKUP = {
        (0, 0, 0, 0, 0, 0, 0): "OFF",
        (1, 1, 1, 0, 1, 1, 1): "0",
        (0, 0, 1, 0, 0, 1, 0): "1",
        (1, 0, 1, 1, 1, 0, 1): "2",
        (1, 0, 1, 1, 0, 1, 1): "3",
        (0, 1, 1, 1, 0, 1, 0): "4",
        (1, 1, 0, 1, 0, 1, 1): "5",
        (1, 1, 0, 1, 1, 1, 1): "6",
        (1, 0, 1, 0, 0, 1, 0): "7",
        (1, 1, 1, 1, 1, 1, 1): "8",
        (1, 1, 1, 1, 0, 1, 1): "9",
    }
    SEGMENT_ORDER = (
        "top",
        "top_left",
        "top_right",
        "middle",
        "bottom_left",
        "bottom_right",
        "bottom",
    )

    def __init__(
        self,
        calibration_path: str,
        num_digits: int = 4,
        cam_usb_path: str | None = None,
        use_camera: bool = True,
        index: int = 1,
        name: str = "HardnessTester",
        tester_mode: str = "shore_a",
        tip_length_mm: float | None = None,
        servo: str | None = None,
        power_press_angle: int | None = None,
        power_release_angle: int | None = None,
        zero_press_angle: int | None = None,
        zero_release_angle: int | None = None,
        state_machine=None,
        threshold_bias: int = 15,
        sharpen_strength: float = 31,
        sharpen_blur_radius: int = 90,
        morph_kernel_size: int = 5,
        morph_iterations: int = 3,
        morph_open: bool = False,
    ):
        """
        Initialize the LCD reader.

        Args:
            num_digits: Number of digits in the display (default: 4)
            cam_usb_path: Filesystem path to the camera USB device
                (e.g. /dev/v4l/by-path/...-video-index0). This is the only
                supported camera config source. When None, the camera cannot
                be opened until camera discrimination runs and sets the
                resolved index via identify_hardness_camera().
            use_camera: Whether to initialize and use a camera device
            index: Jubilee tool index for this tester
            name: Jubilee tool name for this tester
            tester_mode: Shore tester mode ("shore_a" or "shore_d")
            calibration_path: Path to the LCD calibration json for this tester
            tip_length_mm: Physical tip length for this tester
            servo: Servo identifier for the shared button servo (e.g. "S1" = servo
                channel 1). The same physical servo actuates both the power and zero
                buttons; the button is selected by angle range.
            power_press_angle: Servo angle in degrees when pressing the power button
            power_release_angle: Servo angle in degrees when releasing the power button
            zero_press_angle: Servo angle in degrees when pressing the zero button
            zero_release_angle: Servo angle in degrees when releasing the zero button
            state_machine: Optional MotionPlatformStateMachine reference. When set,
                turn_on(), turn_off(), and zero() use it directly without requiring
                a per-call argument (same pattern as Manipulator).
            threshold_bias: Amount to subtract from Otsu's computed threshold
                before applying binarization. Increase this value to make
                binarization less sensitive (fewer pixels classified as black),
                which helps when reflections or lens artifacts create spurious
                dark regions. Default is 0 (pure Otsu behavior).
            sharpen_strength: Unsharp masking strength applied to the grayscale
                image before CLAHE. 0.0 disables sharpening. Values in the range
                1.0-2.0 work well for mildly blurry images; go higher (e.g. 3.0)
                for strongly blurred captures. Higher values risk amplifying
                noise, so pair with a larger sharpen_blur_radius if needed.
            sharpen_blur_radius: Gaussian blur radius (odd integer) used when
                computing the unsharp mask. Larger values recover lower-frequency
                blur (wider blurred edges); smaller values target fine detail.
                Default is 5.
            morph_kernel_size: Side length of the rectangular structuring element
                used in morphological closing (and optional opening). Larger values
                bridge bigger gaps within segments and remove larger noise regions.
                Default is 2.
            morph_iterations: Number of times to apply each morphological operation.
                More iterations push the effect further without needing a huge kernel.
                Default is 1.
            morph_open: If True, runs a morphological opening (erode then dilate)
                before the closing pass. This scrubs isolated noise blobs first so
                they are not accidentally merged into segments by the close.
                Default is False.
        """
        super().__init__(index, name)
        self.num_digits = num_digits
        self.cam_usb_path = cam_usb_path
        self.use_camera = use_camera
        self.tester_mode = tester_mode
        self.calibration_path = calibration_path
        self.tip_length_mm = tip_length_mm
        self.servo = servo
        self.power_press_angle = power_press_angle
        self.power_release_angle = power_release_angle
        self.zero_press_angle = zero_press_angle
        self.zero_release_angle = zero_release_angle
        self.state_machine = state_machine
        self.threshold_bias = threshold_bias
        self.sharpen_strength = sharpen_strength
        self.sharpen_blur_radius = sharpen_blur_radius
        self.morph_kernel_size = morph_kernel_size
        self.morph_iterations = morph_iterations
        self.morph_open = morph_open

        # Integer cv2 camera index resolved from cam_usb_path at open time.
        self._resolved_cam_index: int | None = None

        # Digit ROI boundaries (will be set via calibration or manually)
        # Format: [(x1, y1, x2, y2), ...] for each digit
        self.digit_rois = None

        # Segment polygons (absolute pixel coordinates)
        # Format: [{segment_name: [(x, y), ...], ...}, ...] for each digit
        self.segment_points = None

        # Threshold for segment detection (proportion of pixels that must be active)
        self.segment_threshold = 0.5

        # cv2.VideoCapture handle (opened on demand)
        self.cap = None

        # Initialize camera only when requested
        if self.use_camera:
            self._init_camera()

    @classmethod
    def from_system_config(
        cls,
        tester_mode: str,
        cfg: "HardnessTesterConfig",
        num_digits: int = 4,
        state_machine=None,
    ) -> "HardnessTester":
        """Build a configured Shore tester from validated ``HardnessTesterConfig``."""
        calibration_path = cfg.lcd_calibration_path
        if calibration_path and not os.path.isabs(calibration_path):
            project_root = Path(__file__).resolve().parent.parent
            calibration_path = str(project_root / calibration_path)

        servos = cfg.button_servos
        return cls(
            num_digits=num_digits,
            cam_usb_path=cfg.cam_usb_path or None,
            use_camera=cfg.use_camera,
            index=cfg.tool.index,
            name=cfg.tool.name,
            tester_mode=tester_mode,
            calibration_path=calibration_path,
            tip_length_mm=cfg.tip_length_mm,
            servo=servos.servo,
            power_press_angle=servos.power_press_angle,
            power_release_angle=servos.power_release_angle,
            zero_press_angle=servos.zero_press_angle,
            zero_release_angle=servos.zero_release_angle,
            state_machine=state_machine,
        )

    def load_assigned_calibration(self) -> bool:
        """Load the calibration configured for this Shore tester."""
        return self.load_calibration(self.calibration_path)

    def turn_on(self) -> bool:
        """
        Actuate the tester power button via the stored state machine.
        """
        if self.state_machine is None:
            raise ValueError(f"state_machine is not set on {self.tester_mode} tester")
        result = self.state_machine.validated_hardness_turn_on(
            mode=self.tester_mode, hardness_tester=self
        )
        if not result.valid:
            raise RuntimeError(result.reason or "Hardness turn-on action failed")
        return True

    def turn_off(self) -> bool:
        """
        Actuate the tester power button for shutdown via the stored state machine.
        """
        if self.state_machine is None:
            raise ValueError(f"state_machine is not set on {self.tester_mode} tester")
        result = self.state_machine.validated_hardness_turn_off(
            mode=self.tester_mode, hardness_tester=self
        )
        if not result.valid:
            raise RuntimeError(result.reason or "Hardness turn-off action failed")
        return True

    def zero(self) -> bool:
        """
        Actuate the tester zero button via the stored state machine.
        """
        if self.state_machine is None:
            raise ValueError(f"state_machine is not set on {self.tester_mode} tester")
        result = self.state_machine.validated_hardness_zero(
            mode=self.tester_mode, hardness_tester=self
        )
        if not result.valid:
            raise RuntimeError(result.reason or "Hardness zero action failed")
        return True

    def is_display_zero(self, debug=False, debug_prefix="display_zero") -> bool:
        """
        Run a consensus display capture and check whether value is 0000-0005.
        """
        reading = self.read_display(debug=debug, debug_prefix=debug_prefix)
        if reading is None:
            return False
        if reading == "OFF":
            return False
        if not reading.isdigit():
            return False

        value = int(reading)
        return 0 <= value <= 5

    def is_display_on(self, debug=False, debug_prefix="display_on") -> bool:
        """
        Run a consensus display capture and classify display power state.

        Returns:
            False when all segments are off ("OFF")
            True when a valid reading is displayed

        Raises:
            RuntimeError when capture succeeds but the reading is indeterminate
        """
        reading = self.read_display(debug=debug, debug_prefix=debug_prefix)
        if reading is None:
            raise RuntimeError(
                "Display state is indeterminate: no consensus reading available"
            )
        if reading == "OFF":
            return False
        if reading.isdigit():
            return True
        raise RuntimeError(
            f"Display state is indeterminate: unexpected reading '{reading}'"
        )

    def _parse_hardness_reading(
        self, reading: str | None
    ) -> tuple[float | None, str | None]:
        """Convert a consensus LCD string to a hardness float."""
        if reading is None:
            return None, "No consensus OCR reading was captured."
        if reading == "OFF":
            return None, "Hardness tester display reported OFF."
        if not reading.isdigit():
            return None, f"OCR returned non-numeric reading '{reading}'."

        # The display does not include a decimal point, so we apply the
        # fixed one-decimal scaling used by existing hardness UI expectations.
        if len(reading) == 3:
            numeric_value = int(reading)
        else:
            numeric_value = int(reading) / 10.0
        return numeric_value

    def test_sample(
        self,
        tray_index: str | int,
        sample_id: str | int,
        state_machine,
        image_save_path=None,
    ) -> dict[str, float | str | None]:
        """
        Execute one hardness sample operation via the state machine move/action path.

        Mirrors the mold pick/place architecture: movement to the target position
        is a separate validated step from the measurement action itself. The state
        machine owns all coordinate resolution and position validation.
        """
        if state_machine is None:
            raise ValueError("state_machine is required for test_sample()")

        self.load_assigned_calibration()

        tray_result = state_machine.validated_move_to_sample_tray(tray_index)
        if not tray_result.valid:
            raise RuntimeError(tray_result.reason or "Move to sample tray failed")

        sample_result = state_machine.validated_move_to_hardness_sample(
            tray_index, sample_id
        )
        if not sample_result.valid:
            raise RuntimeError(sample_result.reason or "Move to hardness sample failed")

        result = state_machine.validated_test_sample(
            tray_index=tray_index,
            sample_id=sample_id,
            mode=self.tester_mode,
            hardness_tester=self,
            image_save_path=image_save_path,
        )
        if not result.valid:
            raise RuntimeError(result.reason or "Sample action failed")

        measured_value = getattr(state_machine._executor, "last_hardness_result", None)
        sample_error = getattr(state_machine._executor, "last_hardness_error", None)
        image_path = getattr(state_machine._executor, "last_hardness_image_path", None)
        return {
            "result": measured_value,
            "sample_error": sample_error,
            "image_path": image_path,
        }

    def _default_segment_templates(self):
        """
        Define default segment polygons as proportions of a digit ROI.
        Each segment is represented as a polygon.

        Returns:
            Dictionary mapping segment names to point lists [(x, y), ...]
        """
        return {
            # Horizontal segments: trapezoids with outer face larger.
            "top": [
                (0.06, 0.02),
                (0.94, 0.02),
                (0.82, 0.12),
                (0.18, 0.12),
            ],
            # Vertical segments: trapezoids with outer face larger.
            "top_left": [
                (0.03, 0.06),
                (0.22, 0.12),
                (0.18, 0.44),
                (0.00, 0.49),
            ],
            "top_right": [
                (0.97, 0.06),
                (1.00, 0.49),
                (0.82, 0.44),
                (0.78, 0.12),
            ],
            # Middle segment: two trapezoids merged (long faces inward).
            "middle": [
                (0.10, 0.50),
                (0.26, 0.43),
                (0.74, 0.43),
                (0.90, 0.50),
                (0.74, 0.57),
                (0.26, 0.57),
            ],
            "bottom_left": [
                (0.00, 0.51),
                (0.18, 0.56),
                (0.22, 0.88),
                (0.03, 0.95),
            ],
            "bottom_right": [
                (1.00, 0.51),
                (0.97, 0.95),
                (0.78, 0.88),
                (0.82, 0.56),
            ],
            "bottom": [
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
                    points.append(
                        (x1 + int(round(px * width)), y1 + int(round(py * height)))
                    )
                digit_segments[segment_name] = points
            segment_points.append(digit_segments)
        return segment_points

    def _init_camera(self):
        """Initialize cv2.VideoCapture by resolving cam_usb_path to a device index.

        Raises RuntimeError if cam_usb_path is not configured or cannot be
        resolved to a valid /dev/videoN index, or if the VideoCapture cannot
        be opened.
        """
        if not self.cam_usb_path:
            raise RuntimeError(
                f"Cannot open camera for {self.tester_mode}: cam_usb_path is not configured"
            )
        resolved = self.resolve_cam_index_from_usb_path(self.cam_usb_path)
        if resolved is None:
            raise RuntimeError(
                f"Cannot open camera for {self.tester_mode}: "
                f"cam_usb_path '{self.cam_usb_path}' could not be resolved to a device index"
            )
        self._resolved_cam_index = resolved
        print(f"Initializing camera (device {resolved})...")
        self.cap = cv2.VideoCapture(resolved)
        if not self.cap.isOpened():
            self.cap = None
            raise RuntimeError(f"Failed to open camera device {resolved}")
        print("Camera initialized successfully")

    def open_camera(self) -> None:
        """Open (or re-open) the camera for this tester.

        Resolves cam_usb_path to a device index. Safe to call when the camera
        is already open - closes the existing handle first.
        """
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            self.cap = None
        self._init_camera()

    def close_camera(self) -> None:
        """Release the camera handle for this tester."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            print(f"Camera closed for {self.tester_mode}")

    def reset_camera(self) -> None:
        """Close then reopen the camera, re-deriving the index from cam_usb_path."""
        self.close_camera()
        self._init_camera()

    @staticmethod
    def resolve_cam_index_from_usb_path(usb_path: str) -> int | None:
        """Resolve a USB/v4l by-path string to an integer OpenCV camera index.

        Handles:
        - /dev/v4l/by-path/ and /dev/v4l/by-id/ symlinks (Linux)
        - Direct /dev/videoN paths
        - Plain integer strings ("2")

        The by-path convention for multi-function USB cameras exposes a
        ``-video-index0`` variant for the actual image stream and
        ``-video-index1`` (or higher) for metadata; this method always
        follows the symlink target, so callers should pass the
        ``-video-index0`` path explicitly to get the data stream.

        Returns the integer index, or None if the path cannot be resolved.
        """
        if not usb_path:
            return None
        if str(usb_path).strip().lstrip("-").isdigit():
            return int(str(usb_path).strip())
        try:
            real_path = os.path.realpath(usb_path)
            m = re.search(r"/dev/video(\d+)$", real_path)
            if m:
                return int(m.group(1))
        except (OSError, ValueError):
            pass
        return None

    @staticmethod
    def enumerate_available_cam_indices(max_id: int = 10) -> list:
        """Return all camera indices in [0, max_id) that OpenCV can open.

        Each index is tested by attempting to open a VideoCapture; only
        indices where the capture reports isOpened() are returned. Always
        picks index 0 of each USB device (actual image stream, not
        metadata) when using numeric indices.
        """
        available = []
        for idx in range(max_id):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                available.append(idx)
            cap.release()
        return available

    def capture_image(self, save=False, output_path="lcd_capture.jpg"):
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

        if self.cap is None or not self.cap.isOpened():
            print("WARNING: Camera is not initialized")
            return None

        ret, frame = self.cap.read()
        if not ret or frame is None:
            print("WARNING: Camera capture failed")
            return None

        if save:
            cv2.imwrite(output_path, frame)
            print(f"Image saved to {output_path}")

        return frame

    def _collect_timed_frames(self, frame_count=10, total_duration_s=1.0):
        """Capture frames over a fixed time window using capture_image()."""
        if frame_count <= 0:
            return []
        if self.cap is None or not self.cap.isOpened():
            return None

        sample_interval = total_duration_s / float(frame_count)
        next_capture_time = time.monotonic()
        frames = []

        for _ in range(frame_count):
            now = time.monotonic()
            if now < next_capture_time:
                time.sleep(next_capture_time - now)

            ret, frame = self.cap.read()
            if not ret or frame is None:
                print("WARNING: Direct camera capture failed")
                return None

            frames.append(frame)
            next_capture_time += sample_interval

        return frames

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

        # Step 2 (optional): Unsharp masking to recover blurred edges
        # sharpened = original + strength * (original - blurred)
        if self.sharpen_strength > 0.0:
            radius = self.sharpen_blur_radius | 1  # ensure odd
            blurred = cv2.GaussianBlur(gray, (radius, radius), 0)
            gray = cv2.addWeighted(
                gray, 1.0 + self.sharpen_strength, blurred, -self.sharpen_strength, 0
            )
            if debug:
                cv2.imwrite(f"{debug_prefix}_step3_sharpened.png", gray)

        # Step 3: Apply CLAHE to enhance local contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step4_clahe.png", enhanced)

        # Step 4: Threshold to create binary image
        # Compute Otsu's threshold, then apply a bias to reduce sensitivity to
        # localized dark artifacts (e.g. camera lens reflection in the center).
        otsu_thresh, _ = cv2.threshold(
            enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        adjusted_thresh = max(0, int(otsu_thresh) - self.threshold_bias)
        _, binary = cv2.threshold(enhanced, adjusted_thresh, 255, cv2.THRESH_BINARY)
        if debug:
            cv2.imwrite(f"{debug_prefix}_step5_binary.png", binary)

        # Step 5: Morphological operations to clean up noise
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (self.morph_kernel_size, self.morph_kernel_size),
        )
        if self.morph_open:
            cleaned = cv2.morphologyEx(
                binary, cv2.MORPH_OPEN, kernel, iterations=self.morph_iterations
            )
        else:
            cleaned = binary
        cleaned = cv2.morphologyEx(
            cleaned, cv2.MORPH_CLOSE, kernel, iterations=self.morph_iterations
        )
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
                cv2.polylines(
                    overlay, [polygon], isClosed=True, color=(0, 255, 0), thickness=1
                )

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
            return "?"

        # Analyze all 7 segments in order
        segments = (
            self.analyze_segment(binary_frame, digit_idx, "top"),
            self.analyze_segment(binary_frame, digit_idx, "top_left"),
            self.analyze_segment(binary_frame, digit_idx, "top_right"),
            self.analyze_segment(binary_frame, digit_idx, "middle"),
            self.analyze_segment(binary_frame, digit_idx, "bottom_left"),
            self.analyze_segment(binary_frame, digit_idx, "bottom_right"),
            self.analyze_segment(binary_frame, digit_idx, "bottom"),
        )

        if debug:
            print(f"  Segment pattern: {segments}")

        # Look up digit in lookup table
        return self.DIGITS_LOOKUP.get(segments, "?")

    def _read_display_from_frame(self, frame, debug=False, debug_prefix="debug"):
        """Decode the LCD value from a single BGR frame."""
        if frame is None:
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

        return "".join(result)

    def read_display(
        self, frame=None, debug=False, debug_prefix="debug", image_save_path=None
    ):
        """
        Complete pipeline: Read all digits from LCD display.

        Args:
            frame: Input BGR frame. If provided, decode once and return result.
                   If None, collect 10 readings and return strict majority.
            debug: Whether to save debug images
            debug_prefix: Prefix for debug image filenames
            image_save_path: Optional path (str or Path) to save a raw camera
                frame alongside the reading.  The first frame that produced the
                consensus result is saved; if consensus fails the last captured
                frame is used as a fallback.  Parent directories are created
                automatically.  Has no effect when ``frame`` is supplied.

        Returns:
            String with recognized digits or None if reading failed
        """
        if frame is not None:
            return self._read_display_from_frame(
                frame, debug=debug, debug_prefix=debug_prefix
            )

        frames = self._collect_timed_frames(frame_count=10, total_duration_s=1.0)
        if frames is None:
            print("Failed to capture 10 frames for consensus read")
            return None

        read_results = []
        for idx, sample_frame in enumerate(frames):
            sample_debug = debug and idx == 0
            sample_result = self._read_display_from_frame(
                sample_frame,
                debug=sample_debug,
                debug_prefix=debug_prefix,
            )
            if sample_result is None:
                return None
            read_results.append(sample_result)

        consensus_counts = Counter(read_results)
        consensus_result, consensus_count = consensus_counts.most_common(1)[0]
        if debug:
            print(f"Consensus candidates: {dict(consensus_counts)}")

        if consensus_count > len(read_results) // 2:
            if image_save_path is not None and frames:
                save_frame = next(
                    (f for f, r in zip(frames, read_results) if r == consensus_result),
                    frames[-1],
                )
                Path(image_save_path).parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(image_save_path), save_frame)
            return consensus_result
        return None

    def calibrate(
        self,
        frame=None,
        image_path=None,
        save_calibration=True,
        calibration_path: str | None = None,
    ):
        """
        Interactive GUI calibration using an OpenCV popup window.
        Uses ``self.calibration_path`` when ``calibration_path`` is omitted.

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

        if calibration_path is None:
            calibration_path = self.calibration_path
        if not calibration_path:
            raise ValueError("calibration_path is required for calibrate()")

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
            "top": (0, 255, 255),
            "top_left": (0, 165, 255),
            "top_right": (0, 255, 0),
            "middle": (255, 0, 255),
            "bottom_left": (255, 165, 0),
            "bottom_right": (0, 0, 255),
            "bottom": (255, 0, 0),
        }

        # --- 4. Mutable state dict ------------------------------------------
        s = {
            "phase": "roi",
            "digit_idx": 0,
            "segment_idx": 0,
            "rois": [],
            "pending_roi": None,  # (x1,y1,x2,y2) image-coords, not yet confirmed
            "drag_origin": None,  # display (x,y) of mouse-down
            "all_segs": [],  # [{seg_name: [(x,y),...]}] per digit
            "cur_pts": [],  # working vertices for the active segment
            "default_segs": None,  # populated after ROI phase
            "mouse": [0, 0],
            "done": False,
            "cancelled": False,
        }

        # --- 5. Mouse callback ----------------------------------------------
        def on_mouse(event, x, y, _flags, _param):
            s["mouse"] = [x, y]
            if s["phase"] == "roi":
                if event == cv2.EVENT_LBUTTONDOWN:
                    s["drag_origin"] = (x, y)
                    s["pending_roi"] = None
                elif event == cv2.EVENT_MOUSEMOVE and s["drag_origin"]:
                    ox, oy = s["drag_origin"]
                    ix1, iy1 = to_img(min(ox, x), min(oy, y))
                    ix2, iy2 = to_img(max(ox, x), max(oy, y))
                    s["pending_roi"] = (ix1, iy1, ix2, iy2)
                elif event == cv2.EVENT_LBUTTONUP and s["drag_origin"]:
                    ox, oy = s["drag_origin"]
                    s["drag_origin"] = None
                    if abs(x - ox) > 5 and abs(y - oy) > 5:
                        ix1, iy1 = to_img(min(ox, x), min(oy, y))
                        ix2, iy2 = to_img(max(ox, x), max(oy, y))
                        s["pending_roi"] = (ix1, iy1, ix2, iy2)
            elif s["phase"] == "segment":
                if event == cv2.EVENT_LBUTTONDOWN:
                    s["cur_pts"].append(to_img(x, y))

        # --- 6. Render function ---------------------------------------------
        def render():
            base = cv2.resize(frame, (disp_w, disp_h))
            canvas = np.zeros((disp_h + STATUS_H, disp_w, 3), dtype=np.uint8)
            canvas[:disp_h] = base

            # Confirmed ROIs (green)
            for i, (x1, y1, x2, y2) in enumerate(s["rois"]):
                dx1, dy1 = to_disp(x1, y1)
                dx2, dy2 = to_disp(x2, y2)
                cv2.rectangle(canvas, (dx1, dy1), (dx2, dy2), (0, 255, 0), 2)
                cv2.putText(
                    canvas,
                    f"D{i}",
                    (dx1 + 2, dy1 + 14),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

            if s["phase"] == "roi":
                # Pending ROI (cyan)
                if s["pending_roi"]:
                    x1, y1, x2, y2 = s["pending_roi"]
                    dx1, dy1 = to_disp(x1, y1)
                    dx2, dy2 = to_disp(x2, y2)
                    cv2.rectangle(canvas, (dx1, dy1), (dx2, dy2), (0, 255, 255), 2)
                    cv2.putText(
                        canvas,
                        f"D{s['digit_idx']}",
                        (dx1 + 2, dy1 + 14),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )
                # Live drag preview
                if s["drag_origin"]:
                    ox, oy = s["drag_origin"]
                    mx, my = s["mouse"]
                    cv2.rectangle(
                        canvas,
                        (min(ox, mx), min(oy, my)),
                        (max(ox, mx), max(oy, my)),
                        (0, 255, 255),
                        1,
                    )
                status = (
                    f"ROI  Digit {s['digit_idx'] + 1}/{self.num_digits} - "
                    "drag to draw box | Enter=confirm | q=quit"
                )

            else:  # segment phase
                seg_name = self.SEGMENT_ORDER[s["segment_idx"]]
                hi_color = SEG_COLORS[seg_name]
                d_idx = s["digit_idx"]
                def_segs = s["default_segs"]

                # Faint outlines for all other segments of this digit
                if def_segs and d_idx < len(def_segs):
                    for sn in self.SEGMENT_ORDER:
                        if sn == seg_name:
                            continue
                        pts = (
                            s["all_segs"][d_idx].get(sn)
                            if d_idx < len(s["all_segs"])
                            else None
                        )
                        src = pts or def_segs[d_idx].get(sn, [])
                        if len(src) >= 3:
                            poly = np.array(
                                [to_disp(x, y) for x, y in src], dtype=np.int32
                            )
                            cv2.polylines(canvas, [poly], True, (60, 60, 60), 1)

                # Confirmed preceding segments for this digit (their actual colors)
                if d_idx < len(s["all_segs"]):
                    for prev_idx in range(s["segment_idx"]):
                        pn = self.SEGMENT_ORDER[prev_idx]
                        pts = s["all_segs"][d_idx].get(pn, [])
                        if len(pts) >= 3:
                            poly = np.array(
                                [to_disp(x, y) for x, y in pts], dtype=np.int32
                            )
                            cv2.polylines(canvas, [poly], True, SEG_COLORS[pn], 1)

                # Active segment being placed
                cur = s["cur_pts"]
                if len(cur) >= 2:
                    poly = np.array([to_disp(x, y) for x, y in cur], dtype=np.int32)
                    cv2.polylines(canvas, [poly], len(cur) >= 3, hi_color, 2)
                for px, py in cur:
                    cv2.circle(canvas, to_disp(px, py), 5, hi_color, -1)
                if cur:
                    lx, ly = to_disp(*cur[-1])
                    mx, my = s["mouse"]
                    cv2.line(canvas, (lx, ly), (mx, min(my, disp_h - 1)), hi_color, 1)

                n_def = (
                    len(def_segs[d_idx][seg_name])
                    if def_segs and d_idx < len(def_segs)
                    else "?"
                )
                status = (
                    f"SEG  Digit {d_idx + 1}/{self.num_digits}  '{seg_name}'  "
                    f"{len(cur)}/{n_def} pts - "
                    "click=add | d=default | Bksp=undo | c=clear | Enter=confirm | q=quit"
                )

            # Status bar
            cv2.rectangle(
                canvas, (0, disp_h), (disp_w, disp_h + STATUS_H), (20, 20, 20), -1
            )
            cv2.putText(
                canvas,
                status,
                (6, disp_h + 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )
            return canvas

        # --- 7. Event loop --------------------------------------------------
        WIN = "Hardness Tester Calibration"
        cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN, disp_w, disp_h + STATUS_H)
        cv2.setMouseCallback(WIN, on_mouse)

        while not s["done"] and not s["cancelled"]:
            cv2.imshow(WIN, render())
            key = cv2.waitKey(20) & 0xFF

            if key == ord("q") or key == 27:  # q or Esc
                s["cancelled"] = True
                break

            # ROI phase keys
            if s["phase"] == "roi":
                if key in (13, 10):  # Enter
                    if s["pending_roi"]:
                        s["rois"].append(s["pending_roi"])
                        s["pending_roi"] = None
                        s["digit_idx"] += 1
                        if s["digit_idx"] >= self.num_digits:
                            self.set_digit_rois(s["rois"])
                            s["default_segs"] = self._build_default_segment_points(
                                s["rois"]
                            )
                            s["all_segs"] = [{} for _ in range(self.num_digits)]
                            s["phase"] = "segment"
                            s["digit_idx"] = 0
                            s["segment_idx"] = 0
                            s["cur_pts"] = list(
                                s["default_segs"][0][self.SEGMENT_ORDER[0]]
                            )

            # Segment phase keys
            elif s["phase"] == "segment":
                seg_name = self.SEGMENT_ORDER[s["segment_idx"]]
                d_idx = s["digit_idx"]

                if key == ord("d"):
                    s["cur_pts"] = list(s["default_segs"][d_idx][seg_name])

                elif key == ord("c"):
                    s["cur_pts"] = []

                elif key in (8, 127):  # Backspace / Delete
                    if s["cur_pts"]:
                        s["cur_pts"].pop()

                elif key in (13, 10):  # Enter
                    if s["cur_pts"]:
                        s["all_segs"][d_idx][seg_name] = list(s["cur_pts"])
                        s["segment_idx"] += 1
                        if s["segment_idx"] >= len(self.SEGMENT_ORDER):
                            s["segment_idx"] = 0
                            s["digit_idx"] += 1
                            if s["digit_idx"] >= self.num_digits:
                                s["done"] = True
                                break
                        next_seg = self.SEGMENT_ORDER[s["segment_idx"]]
                        s["cur_pts"] = list(s["default_segs"][s["digit_idx"]][next_seg])

        cv2.destroyWindow(WIN)

        if s["cancelled"] or not s["done"]:
            print("Calibration cancelled.")
            return False

        self.segment_points = s["all_segs"]

        if save_calibration:
            calibration_dir = os.path.dirname(calibration_path)
            if calibration_dir:
                os.makedirs(calibration_dir, exist_ok=True)
            with open(calibration_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "digit_rois": s["rois"],
                        "segment_points": self.segment_points,
                    },
                    f,
                    indent=2,
                )
            print(f"Calibration saved to {calibration_path}")

        print("Testing calibration...")
        result = self.read_display(frame, debug=True, debug_prefix="calibration_test")
        print(f"Calibration test read: {result}")

        return True

    def load_calibration(self, filepath: str | None = None):
        """
        Load calibration from file.

        Args:
            filepath: Path to calibration JSON file (defaults to self.calibration_path)

        Returns:
            True if loaded successfully
        """
        filepath = filepath or self.calibration_path
        if not filepath:
            print("WARNING: No calibration path configured")
            return False
        try:
            import json

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.digit_rois = [tuple(roi) for roi in data["digit_rois"]]
                loaded_segment_points = []
                for digit_segments in data["segment_points"]:
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
        if self.cap is not None:
            try:
                self.cap.release()
            except (RuntimeError, AttributeError):
                pass


_CLI_DEFAULT_CALIBRATION = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "jubilee_api_config",
        "lcd_calibration_shore_a.json",
    )
)


def main():
    """
    Test the segment-based LCD reader.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Segment-based LCD reader for hardness tester"
    )
    parser.add_argument(
        "--image",
        type=str,
        default=None,
        help="Path to an existing image file to read instead of capturing from camera",
    )
    parser.add_argument(
        "--calibration",
        type=str,
        default=_CLI_DEFAULT_CALIBRATION,
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
    parser.add_argument(
        "--sharpen-strength",
        type=float,
        default=0.0,
        help="Unsharp masking strength (0 = disabled, 1.0-2.0 for mild blur, higher for strong blur)",
    )
    parser.add_argument(
        "--sharpen-blur-radius",
        type=int,
        default=5,
        help="Gaussian blur radius for unsharp masking (odd integer, larger targets wider blur)",
    )
    parser.add_argument(
        "--threshold-bias",
        type=int,
        default=0,
        help="Amount to lower the Otsu threshold to reduce sensitivity to dark artifacts",
    )
    parser.add_argument(
        "--morph-kernel-size",
        type=int,
        default=2,
        help="Morphological kernel size; larger fills bigger gaps and removes larger noise",
    )
    parser.add_argument(
        "--morph-iterations",
        type=int,
        default=1,
        help="Number of morphological operation iterations",
    )
    parser.add_argument(
        "--morph-open",
        action="store_true",
        help="Run an opening pass before closing to scrub isolated noise blobs",
    )
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("SEGMENT-BASED LCD READER TEST")
    print("=" * 80)

    # Initialize reader (camera is optional in image mode)
    print("\nInitializing LCD reader...")
    reader = HardnessTester(
        num_digits=4,
        use_camera=(args.image is None),
        calibration_path=args.calibration,
        sharpen_strength=args.sharpen_strength,
        sharpen_blur_radius=args.sharpen_blur_radius,
        threshold_bias=args.threshold_bias,
        morph_kernel_size=args.morph_kernel_size,
        morph_iterations=args.morph_iterations,
        morph_open=args.morph_open,
    )

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
        frame = reader.capture_image(save=True, output_path="lcd_test_capture.jpg")
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
    result = reader.read_display(
        frame=frame, debug=args.debug, debug_prefix=args.debug_prefix
    )

    print("\n" + "=" * 80)
    print(f"RESULT: {result}")
    print("=" * 80)

    print("\n" + "=" * 80)
    print("Test complete")
    print("=" * 80)


def test_with_image(image_path, calibration_file=_CLI_DEFAULT_CALIBRATION):
    """
    Simple test function to read LCD from a single image.

    Args:
        image_path: Path to LCD image
        calibration_file: Path to calibration file (optional)
    """
    reader = HardnessTester(
        num_digits=4,
        use_camera=False,
        calibration_path=calibration_file,
    )

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
