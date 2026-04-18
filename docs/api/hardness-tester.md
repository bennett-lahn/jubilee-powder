# HardnessTester API Reference

The `HardnessTester` class provides segment-based reading of 7-segment LCD displays. Instead of using traditional OCR, it detects which segments are active in each digit and matches the pattern against a lookup table.

## Overview

`HardnessTester` is designed for:

- Reading 7-segment LCD displays with low contrast
- Detecting active segments using image processing
- Recognizing digits via pattern matching
- Calibrating digit positions for accurate reading
- Working without OCR dependencies

This approach is more reliable than OCR for LCD displays because it's not affected by font variations, requires no training data, and works with low-contrast displays.

## Class Reference

### Constructor

```python
HardnessTester(num_digits=4, cam_id=0, exposure_time=None, gain=None)
```

Initialize the LCD reader.

**Parameters:**

- `num_digits` (int, optional): Number of digits in the display. Default: 4
- `cam_id` (int, optional): Camera device ID. Default: 0
- `exposure_time` (int, optional): Fixed exposure time in microseconds (Picamera2 only). None = auto. Default: None
- `gain` (float, optional): Fixed gain value (Picamera2 only). None = auto. Default: None

**Returns:** HardnessTester instance

**Example:**

```python
# Basic initialization
reader = HardnessTester(num_digits=4)

# With locked camera settings (Raspberry Pi)
reader = HardnessTester(
    num_digits=4,
    exposure_time=10000,
    gain=1.0
)
```

### Class Attributes

#### DIGITS_LOOKUP

```python
DIGITS_LOOKUP: Dict[Tuple[int, ...], str]
```

Lookup table mapping 7-bit segment patterns to digit strings.

Pattern order: `(top, top_left, top_right, middle, bottom_left, bottom_right, bottom)`

**Example:**

```python
# Pattern for digit '0': all segments except middle
(1, 1, 1, 0, 1, 1, 1): '0'

# Pattern for digit '1': only right segments
(0, 0, 1, 0, 0, 1, 0): '1'
```

## Core Methods

### capture_image

```python
capture_image(save=False, output_path='lcd_capture.jpg') -> np.ndarray
```

Capture an image from the camera.

**Parameters:**

- `save` (bool, optional): Whether to save the captured image. Default: False
- `output_path` (str, optional): Path to save the image. Default: 'lcd_capture.jpg'

**Returns:** BGR numpy array or None if capture failed

**Example:**

```python
frame = reader.capture_image(save=True, output_path='test.jpg')
if frame is not None:
    print("Image captured successfully")
```

### preprocess_frame

```python
preprocess_frame(frame, debug=False, debug_prefix="debug") -> np.ndarray
```

Phase 1: Image Acquisition & Advanced Preprocessing

Converts frame to LAB color space, extracts b-channel, and applies CLAHE to enhance LCD segment contrast.

**Parameters:**

- `frame` (np.ndarray): Input BGR frame from camera
- `debug` (bool, optional): Whether to save debug images. Default: False
- `debug_prefix` (str, optional): Prefix for debug image filenames. Default: "debug"

**Returns:** Binary image with enhanced LCD segments

**Raises:** ValueError if input frame is None

**Example:**

```python
frame = reader.capture_image()
binary = reader.preprocess_frame(frame, debug=True, debug_prefix="test")
```

**Debug Output:**

When `debug=True`, saves:
- `{prefix}_step1_original.png` - Original BGR frame
- `{prefix}_step2_lab.png` - LAB color space conversion
- `{prefix}_step3_b_channel.png` - Extracted b-channel
- `{prefix}_step4_clahe.png` - After CLAHE enhancement
- `{prefix}_step5_binary.png` - Binary thresholded image
- `{prefix}_step6_cleaned.png` - After morphological cleaning

### read_display

```python
read_display(frame=None, debug=False, debug_prefix="debug") -> Optional[str]
```

Complete pipeline: Read all digits from LCD display.

**Parameters:**

- `frame` (np.ndarray, optional): Input BGR frame. If None, captures from camera. Default: None
- `debug` (bool, optional): Whether to save debug images. Default: False
- `debug_prefix` (str, optional): Prefix for debug image filenames. Default: "debug"

**Returns:** String with recognized digits (e.g., "1234") or None if reading failed

**Example:**

```python
# Capture and read in one call
result = reader.read_display()
print(f"LCD shows: {result}")

# Use existing frame
frame = reader.capture_image()
result = reader.read_display(frame=frame, debug=True)

# Check for errors
if result is None:
    print("Reading failed")
elif '?' in result:
    print(f"Unclear reading: {result}")
else:
    print(f"Valid reading: {result}")
```

## Calibration Methods

### calibrate

```python
calibrate(frame=None, save_calibration=True) -> bool
```

Interactive calibration to manually set digit ROIs.

**Parameters:**

- `frame` (np.ndarray, optional): Input BGR frame. If None, captures from camera. Default: None
- `save_calibration` (bool, optional): Whether to save calibration to file. Default: True

**Returns:** True if calibration successful

**Example:**

```python
reader = HardnessTester(num_digits=4)
frame = reader.capture_image(save=True)
reader.calibrate(frame=frame)
```

**Calibration Process:**

1. Preprocesses frame and saves debug images
2. Prompts for pixel coordinates of each digit (x1, y1, x2, y2)
3. Saves calibration to `lcd_calibration.json`
4. Tests the calibration immediately

### load_calibration

```python
load_calibration(filepath='lcd_calibration.json') -> bool
```

Load calibration from file.

**Parameters:**

- `filepath` (str, optional): Path to calibration JSON file. Default: 'lcd_calibration.json'

**Returns:** True if loaded successfully

**Example:**

```python
if reader.load_calibration('lcd_calibration.json'):
    print("Calibration loaded")
else:
    print("Failed to load calibration")
```

**Calibration File Format:**

```json
{
  "digit_rois": [
    [x1, y1, x2, y2],
    [x1, y1, x2, y2],
    [x1, y1, x2, y2],
    [x1, y1, x2, y2]
  ]
}
```

### set_digit_rois

```python
set_digit_rois(rois: List[Tuple[int, int, int, int]]) -> None
```

Set the ROI boundaries for each digit.

**Parameters:**

- `rois` (List[Tuple[int, int, int, int]]): List of tuples `[(x1, y1, x2, y2), ...]` for each digit

**Raises:** ValueError if number of ROIs doesn't match `num_digits`

**Example:**

```python
# Manually set digit ROIs
rois = [
    (50, 100, 90, 180),   # Digit 0
    (100, 100, 140, 180), # Digit 1
    (150, 100, 190, 180), # Digit 2
    (200, 100, 240, 180)  # Digit 3
]
reader.set_digit_rois(rois)
```

### auto_detect_digit_rois

```python
auto_detect_digit_rois(binary_frame) -> Optional[List[Tuple[int, int, int, int]]]
```

Attempt to automatically detect digit ROIs using contour detection.

**Parameters:**

- `binary_frame` (np.ndarray): Preprocessed binary image

**Returns:** List of digit ROIs `[(x1, y1, x2, y2), ...]` or None if detection failed

**Example:**

```python
frame = reader.capture_image()
binary = reader.preprocess_frame(frame)
rois = reader.auto_detect_digit_rois(binary)

if rois:
    reader.set_digit_rois(rois)
    print(f"Detected {len(rois)} digit ROIs")
else:
    print("Auto-detection failed - use manual calibration")
```

**Note:** Auto-detection works best with clear digit separation and good contrast. Manual calibration is more reliable.

## Digit Analysis Methods

### extract_digit_roi

```python
extract_digit_roi(binary_frame, digit_idx: int) -> Optional[np.ndarray]
```

Extract a single digit ROI from the binary frame.

**Parameters:**

- `binary_frame` (np.ndarray): Preprocessed binary image
- `digit_idx` (int): Index of the digit to extract

**Returns:** Cropped digit image or None

**Example:**

```python
binary = reader.preprocess_frame(frame)
digit_0 = reader.extract_digit_roi(binary, 0)
```

### analyze_segment

```python
analyze_segment(digit_roi, segment_name: str) -> int
```

Phase 3: Segment Analysis Logic

Analyzes a single segment within a digit ROI to determine if it's active.

**Parameters:**

- `digit_roi` (np.ndarray): Binary image of a single digit
- `segment_name` (str): Name of the segment ('top', 'top_left', 'top_right', 'middle', 'bottom_left', 'bottom_right', 'bottom')

**Returns:** 1 if segment is active (ON), 0 if inactive (OFF)

**Example:**

```python
digit_roi = reader.extract_digit_roi(binary, 0)
top_active = reader.analyze_segment(digit_roi, 'top')
middle_active = reader.analyze_segment(digit_roi, 'middle')
```

### recognize_digit

```python
recognize_digit(digit_roi, debug=False) -> str
```

Phase 4: Recognition via Lookup Table

Recognizes a single digit by analyzing all 7 segments.

**Parameters:**

- `digit_roi` (np.ndarray): Binary image of a single digit
- `debug` (bool, optional): Whether to print debug information. Default: False

**Returns:** Recognized digit as string or '?' if not recognized

**Example:**

```python
digit_roi = reader.extract_digit_roi(binary, 0)
digit = reader.recognize_digit(digit_roi, debug=True)
print(f"Recognized: {digit}")
```

**Debug Output:**

When `debug=True`, prints:
```
Segment pattern: (1, 1, 1, 0, 1, 1, 1)
```

## Instance Attributes

### num_digits

```python
num_digits: int
```

Number of digits in the display.

### digit_rois

```python
digit_rois: Optional[List[Tuple[int, int, int, int]]]
```

ROI boundaries for each digit. Format: `[(x1, y1, x2, y2), ...]`

Set via calibration, `load_calibration()`, or `set_digit_rois()`.

### segment_rois

```python
segment_rois: Dict[str, Tuple[float, float, float, float]]
```

Segment ROI boundaries relative to digit ROI. Proportions (0.0 to 1.0).

Default values:
```python
{
    'top':          (0.2, 0.0, 0.8, 0.2),
    'top_left':     (0.0, 0.0, 0.3, 0.5),
    'top_right':    (0.7, 0.0, 1.0, 0.5),
    'middle':       (0.2, 0.4, 0.8, 0.6),
    'bottom_left':  (0.0, 0.5, 0.3, 1.0),
    'bottom_right': (0.7, 0.5, 1.0, 1.0),
    'bottom':       (0.2, 0.8, 0.8, 1.0),
}
```

Can be customized for different display layouts.

### segment_threshold

```python
segment_threshold: float
```

Threshold for segment detection (proportion of pixels that must be active). Default: 0.5

Adjust for sensitivity:
- Lower (0.3): More sensitive, detects dimmer segments
- Higher (0.7): Less sensitive, only bright segments

**Example:**

```python
reader.segment_threshold = 0.3  # More sensitive
```

### picamera / cv2_camera

```python
picamera: Optional[Picamera2]
cv2_camera: Optional[cv2.VideoCapture]
```

Camera objects (internal use). One will be initialized based on availability.

## Usage Examples

### Basic Reading with Calibration

```python
from src.HardnessTester import HardnessTester

# Initialize and load calibration
reader = HardnessTester(num_digits=4)
reader.load_calibration('lcd_calibration.json')

# Read display
result = reader.read_display()
print(f"LCD reading: {result}")
```

### First-Time Setup

```python
from src.HardnessTester import HardnessTester

# Initialize
reader = HardnessTester(num_digits=4)

# Capture test image
frame = reader.capture_image(save=True, output_path='calibration.jpg')

# Run calibration
reader.calibrate(frame=frame, save_calibration=True)

# Now ready for production use
result = reader.read_display()
```

### Reading from Static Image

```python
from src.HardnessTester import test_with_image
import cv2

# Using helper function
result = test_with_image('lcd_photo.jpg', 'lcd_calibration.json')

# Or manually
reader = HardnessTester(num_digits=4)
reader.load_calibration('lcd_calibration.json')
frame = cv2.imread('lcd_photo.jpg')
result = reader.read_display(frame=frame)
```

### Advanced Debugging

```python
reader = HardnessTester(num_digits=4)
reader.load_calibration('lcd_calibration.json')

# Capture and preprocess
frame = reader.capture_image()
binary = reader.preprocess_frame(frame, debug=True, debug_prefix="debug")

# Analyze each digit
for i in range(reader.num_digits):
    digit_roi = reader.extract_digit_roi(binary, i)
    
    # Check each segment
    segments = {
        'top': reader.analyze_segment(digit_roi, 'top'),
        'top_left': reader.analyze_segment(digit_roi, 'top_left'),
        'top_right': reader.analyze_segment(digit_roi, 'top_right'),
        'middle': reader.analyze_segment(digit_roi, 'middle'),
        'bottom_left': reader.analyze_segment(digit_roi, 'bottom_left'),
        'bottom_right': reader.analyze_segment(digit_roi, 'bottom_right'),
        'bottom': reader.analyze_segment(digit_roi, 'bottom'),
    }
    
    # Recognize
    digit = reader.recognize_digit(digit_roi)
    print(f"Digit {i}: {segments} → {digit}")
```

### Adjusting for Different Displays

```python
reader = HardnessTester(num_digits=4)

# Custom segment positions (if default doesn't work)
reader.segment_rois = {
    'top':          (0.15, 0.0, 0.85, 0.15),
    'top_left':     (0.0, 0.0, 0.25, 0.45),
    'top_right':    (0.75, 0.0, 1.0, 0.45),
    'middle':       (0.15, 0.45, 0.85, 0.55),
    'bottom_left':  (0.0, 0.55, 0.25, 1.0),
    'bottom_right': (0.75, 0.55, 1.0, 1.0),
    'bottom':       (0.15, 0.85, 0.85, 1.0),
}

# Adjust sensitivity
reader.segment_threshold = 0.4

# Load calibration
reader.load_calibration('lcd_calibration.json')
```

## Helper Functions

### test_with_image

```python
test_with_image(image_path: str, calibration_file='lcd_calibration.json') -> Optional[str]
```

Simple test function to read LCD from a single image.

**Parameters:**

- `image_path` (str): Path to LCD image
- `calibration_file` (str, optional): Path to calibration file. Default: 'lcd_calibration.json'

**Returns:** String with recognized digits or None

**Example:**

```python
from src.HardnessTester import test_with_image

result = test_with_image('lcd_image.jpg')
print(f"Result: {result}")
```

## Design Notes

### Why Not OCR?

Traditional OCR (Tesseract, TrOCR, EasyOCR) struggles with:
- Low-contrast LCD displays
- Varying lighting conditions
- Font variations in 7-segment displays
- Hollow or outlined digits

Segment-based detection advantages:

- Specifically designed for 7-segment displays
- More reliable with low contrast
- No training data required
- Fast and lightweight (no ML models)
- Easy to debug (visual segment patterns)

### Preprocessing Strategy

The preprocessing pipeline is optimized for LCD displays:

1. **LAB Color Space**: The b-channel (blue-yellow axis) provides best contrast for LCD segments with greenish or gray backgrounds
2. **CLAHE**: Enhances contrast in local 8×8 tiles rather than globally, handling shadows and glare
3. **Adaptive Thresholding**: Otsu's method automatically finds the best threshold value

### Segment Detection

Each segment is detected by:
1. Extracting segment ROI (proportional to digit size)
2. Counting white pixels with `cv2.countNonZero()`
3. Comparing ratio to threshold (default 50%)

This is more robust than edge detection or contour analysis.

### Calibration Trade-offs

**Manual Calibration:**

- More accurate
- Works with any display layout
- Requires user input
- One-time setup per display

**Auto-Detection:**

- No user input
- Quick setup
- May fail with complex layouts
- Less accurate

Recommendation: Use auto-detection for testing, manual calibration for production.

## Limitations

Current implementation supports:

- Recognizes digits 0-9

Current implementation does not support:

- Decimal point detection
- Negative sign detection
- Unit symbols
- 14-segment or dot matrix displays

Workarounds:
- Decimal points: Know position and post-process (e.g., "1234" → 12.34)
- Negative signs: Check separate ROI or use additional processing
- Units: Read separately or ignore

## Performance

Typical performance on Raspberry Pi 4:
- Initialization: < 1 second
- Calibration: 5-10 seconds (one-time)
- Single reading: 100-200ms
- With debug output: 300-500ms

On desktop PC:
- Single reading: 20-50ms

## See Also

- [Reading LCD Displays Guide](../how-to/reading-lcd-displays.md) - User-facing tutorial
<!-- - [Segment Layout Guide](../../SEGMENT_LAYOUT_GUIDE.md) - Technical segment details -->
- [Architecture Overview](../concepts/architecture.md) - System design
