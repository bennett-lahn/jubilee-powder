# Reading LCD Displays

This guide walks through using the HardnessTester to read 7-segment LCD displays using segment detection instead of traditional OCR.

## Overview

The HardnessTester provides automated reading of 7-segment LCD displays by:

- Detecting which segments are active in each digit
- Matching segment patterns to recognize numbers
- Providing reliable readings even with low-contrast displays
- Working without OCR or machine learning dependencies

This approach is much more reliable than traditional OCR for LCD displays.

## Prerequisites

!!! info "Before you start"
    - [ ] Camera positioned with a clear view of the LCD
    - [ ] `opencv-python` installed (`pip install opencv-python`)
    - [ ] One-time calibration completed (see [First-Time Setup](#first-time-setup))
    - [ ] Consistent, indirect lighting for camera to prevent glare 

## Quick Start

### Install Dependencies

```bash
pip install opencv-python
```

For Raspberry Pi (optional):
```bash
pip install picamera2
```

### Basic Usage

```python
from src.HardnessTester import HardnessTester
from src.ConfigLoader import config

reader = HardnessTester.from_system_config(
    tester_mode="shore_a",
    cfg=config.system.hardness_testers.shore_a,
)

if reader.load_assigned_calibration():
    result = reader.read_display()
    print(f"LCD shows: {result}")  # e.g., "1234"
```

## First-Time Setup

!!! warning "Calibration is required once per display setup"
    Accuracy depend on digit ROIs and segment polygons saved during calibration. Re-calibrate if the camera or display position changes.

### Step 1: Capture Test Image

Capture an image of your LCD display for calibration:

```python
from src.HardnessTester import HardnessTester

reader = HardnessTester(
    calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
    num_digits=4,
)
frame = reader.capture_image(save=True, output_path='lcd_calibration_test.jpg')
print("Image saved - review it before calibration")
```

Check the saved image to ensure:
- LCD digits are clearly visible
- Lighting is adequate
- Camera is focused

### Step 2: Run Calibration

The calibration process opens an interactive GUI to map the digit and segment positions:

```python
reader.calibrate(frame=frame, save_calibration=True)
```

The system will:
1. Save debug images showing preprocessing steps
2. Open an interactive GUI where you click and drag to draw a bounding box around each digit, then click to set the segment polygon vertices for each of the 7 segments per digit
3. Save calibration to the configured `calibration_path` (for Shore A: `jubilee_api_config/lcd_calibration_shore_a.json`)
4. Test the calibration immediately and print the result

!!! tip
    Open the debug image `calibration_step5_binary.png` in an image viewer before calibrating. In the binary image, active LCD segments appear as dark regions on a bright background, which helps you place segment polygons accurately.

## Production Usage

Once calibrated, reading displays is simple:

```python
from src.HardnessTester import HardnessTester

# Initialize with calibration
reader = HardnessTester(
    calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
    num_digits=4,
)
reader.load_calibration()

# Read display
result = reader.read_display()

if result and '?' not in result:
    print(f"Reading: {result}")
    # Convert to number if needed
    value = int(result)
else:
    print("Reading failed or unclear")
```

### Reading from Static Images

Test with saved images:

```python
from src.HardnessTester import test_with_image

result = test_with_image(
    "lcd_photo.jpg",
    "jubilee_api_config/lcd_calibration_shore_a.json",
)
print(f"Result: {result}")
```

### Continuous Monitoring

Read from camera in a loop:

```python
from src.HardnessTester import HardnessTester

reader = HardnessTester(
    calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
    num_digits=4,
)
reader.load_calibration()

while True:
    result = reader.read_display()
    print(f"Current reading: {result}")
    
    # Wait before next reading
    import time
    time.sleep(1)
```

## Advanced Features

### Debug Mode

Enable debug output to troubleshoot recognition issues:

```python
result = reader.read_display(debug=True, debug_prefix="debug")
```

This saves images at each preprocessing step:
- `debug_step1_original.png` - Raw camera capture
- `debug_step2_gray.png` - Grayscale conversion
- `debug_step3_sharpened.png` - Unsharp masking (sharpening; on by default)
- `debug_step4_clahe.png` - Enhanced contrast
- `debug_step5_binary.png` - Binary threshold
- `debug_step6_cleaned.png` - Final cleaned image

### Viewing Segment Patterns

See which segments are detected for debugging. Both `analyze_segment` and `recognize_digit` take the full binary frame and a digit index - they no longer accept a cropped ROI:

```python
result = reader.read_display(debug=True)

# Show detailed segment analysis
frame = reader.capture_image()
binary = reader.preprocess_frame(frame)

for i in range(reader.num_digits):
    segments = {
        name: reader.analyze_segment(binary, i, name)
        for name in reader.SEGMENT_ORDER
    }
    digit = reader.recognize_digit(binary, i, debug=True)
    print(f"Digit {i}: {segments} => {digit}")
```

### Adjusting Sensitivity

If segments aren't being detected reliably:

```python
from src.HardnessTester import HardnessTester

reader = HardnessTester(
    calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
    num_digits=4,
)
reader.load_calibration()

# More sensitive (detects dimmer segments)
reader.segment_threshold = 0.3

# Less sensitive (only bright segments)
reader.segment_threshold = 0.7

result = reader.read_display()
```

## Understanding How It Works

### Segment-Based Recognition

Instead of OCR, the system:

1. **Preprocesses** the image to enhance LCD contrast
2. **Extracts** each digit's region of interest (ROI)
3. **Analyzes** seven segments per digit (top, top-left, top-right, middle, bottom-left, bottom-right, bottom)
4. **Counts** active pixels in each segment
5. **Matches** the 7-bit pattern to a digit (0-9)

### Segment Layout

Each 7-segment digit has this structure:

```
     ┌────────────┐
     │    top     │
     └────────────┘
  ┌───┐       ┌───┐
  │ TL│       │ TR│
  └───┘       └───┘
     ┌────────────┐
     │   middle   │
     └────────────┘
  ┌───┐       ┌───┐
  │ BL│       │ BR│
  └───┘       └───┘
     ┌────────────┐
     │   bottom   │
     └────────────┘
```

For example, digit "5" has these segments active:

- Top (active)
- Top-left (active)
- Middle (active)
- Bottom-right (active)
- Bottom (active)

Pattern: `(1, 1, 0, 1, 0, 1, 1)` → Recognized as "5"

### Preprocessing Pipeline

1. **Grayscale**: Converts BGR to grayscale as the primary preprocessing path
2. **Sharpening**: Unsharp masking applied by default to recover blurred segment edges
3. **CLAHE**: Adaptive histogram equalization enhances local contrast
4. **Thresholding**: Otsu's method creates binary image
5. **Morphological Cleaning**: Removes noise

This pipeline (including sharpening) is specifically optimized for LCD displays.

## Troubleshooting

### All digits show '?'

The segments aren't being recognized. Check:

1. **Review debug images**: Run with `debug=True` and check preprocessing steps
2. **Verify calibration**: Ensure digit ROIs are accurate
3. **Adjust threshold**: Try `reader.segment_threshold = 0.3` for more sensitivity
4. **Check lighting**: Improve lighting or lock camera exposure

### Some digits correct, others wrong

Calibration might be slightly off for some digits:

1. Re-run calibration with more precise coordinates
2. Check that all digits are the same size
3. Ensure digit ROIs don't overlap

### Reading changes with lighting

Camera auto-exposure may be adjusting between captures. On Raspberry Pi with Picamera2, the camera settings are fixed after the first capture and the system waits for auto-exposure to settle before starting reads. On other platforms, use consistent external lighting to stabilize the scene.

### Unrecognized segment pattern

If you see `Digit 0: (1, 0, 0, 1, 1, 0, 1) → ?`:

This pattern isn't in the lookup table. Possible causes:
- Display uses non-standard segment layout
- Segment ROI positions don't match your display
- Damaged or partially lit segments

### Reading is slow

Optimize for your use case:

```python
# Capture once, read multiple times
frame = reader.capture_image()

# Read without debug output
result = reader.read_display(frame=frame, debug=False)
```

## Best Practices

### For Reliable Readings

1. Calibrate with high-quality test image
2. Use consistent lighting
3. Lock camera exposure if possible
4. Position camera perpendicular to display
5. Ensure camera is in focus

### During Operation

- Check for `'?'` in results (unrecognized digits)
- Monitor first few readings to verify accuracy
- Re-calibrate if display position changes
- Keep camera lens clean

### Error Handling

```python
from src.HardnessTester import HardnessTester

reader = HardnessTester(
    calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
    num_digits=4,
)

if not reader.load_calibration():
    print("Calibration failed - run calibration first")
    exit(1)

result = reader.read_display()

if result is None:
    print("Camera capture failed")
elif '?' in result:
    print(f"Unclear reading: {result}")
else:
    print(f"Valid reading: {result}")
    # Use result
```

## Tips for Success

### Get Good Calibration

- Use high contrast image for calibration
- Measure coordinates precisely
- Test calibration immediately
- Save calibration file for reuse

### Handle Different Displays

Different displays may need:
- Adjusted segment threshold (0.3-0.7)
- Re-calibration to map the new digit ROIs and segment polygons

### Monitor Accuracy

Track reading accuracy:

```python
# Test against known values
known_value = "1234"
result = reader.read_display()

if result == known_value:
    print("[PASS] Accurate reading")
else:
    print(f"[FAIL] Mismatch: expected {known_value}, got {result}")
```

## Working with Different Display Types

### 3-Digit Displays

```python
from src.HardnessTester import HardnessTester

reader = HardnessTester(
    calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
    num_digits=3,
)
# Calibrate for 3 digits
```

### 6-Digit Displays

```python
from src.HardnessTester import HardnessTester

reader = HardnessTester(
    calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
    num_digits=6,
)
# Calibrate for 6 digits
```

### Displays with Decimal Points

Current version doesn't detect decimal points. Work around by:
- Knowing decimal position (e.g., reading "1234" as "12.34")
- Post-processing the result

```python
result = reader.read_display()  # "1234"
value = int(result) / 100  # 12.34
```

## See Also

- [HardnessTester API Reference](../api/hardness-tester.md)
- [Glossary: LCD terms](../concepts/glossary.md#lcd-display-reading-terms)
- [Architecture](../concepts/architecture.md)

## Getting Help

If readings are not working:

1. Run with `debug=True` and review preprocessing images
2. Check segment patterns to see what is being misdetected
3. Adjust segment threshold or ROI positions
4. Re-calibrate with a better test image
5. Modify `system_config.json` CV parameters
6. Consult [API Reference](../api/hardness-tester.md) for advanced options
