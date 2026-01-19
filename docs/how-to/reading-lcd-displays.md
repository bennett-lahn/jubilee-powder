# Reading LCD Displays

This guide walks through using the HardnessTester to read 7-segment LCD displays using segment detection instead of traditional OCR.

## Overview

The HardnessTester provides automated reading of 7-segment LCD displays by:

- Detecting which segments are active in each digit
- Matching segment patterns to recognize numbers
- Providing reliable readings even with low-contrast displays
- Working without OCR or machine learning dependencies

This approach is much more reliable than traditional OCR for LCD displays.

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

# Initialize reader for 4-digit display
reader = HardnessTester(num_digits=4)

# Load calibration
reader.load_calibration('lcd_calibration.json')

# Read the display
result = reader.read_display()
print(f"LCD shows: {result}")  # e.g., "1234"
```

## First-Time Setup

### Step 1: Capture Test Image

Capture an image of your LCD display for calibration:

```python
from src.HardnessTester import HardnessTester

reader = HardnessTester(num_digits=4)
frame = reader.capture_image(save=True, output_path='lcd_calibration_test.jpg')
print("Image saved - review it before calibration")
```

Check the saved image to ensure:
- LCD digits are clearly visible
- Lighting is adequate
- Camera is focused

### Step 2: Run Calibration

The calibration process will ask you to identify the boundaries of each digit:

```python
reader.calibrate(frame=frame, save_calibration=True)
```

The system will:
1. Save debug images showing preprocessing steps
2. Ask for pixel coordinates of each digit (x1, y1, x2, y2)
3. Save calibration to `lcd_calibration.json`
4. Test the calibration immediately

!!! tip
    Open the debug image `calibration_step6_cleaned.png` in an image viewer to find the exact pixel coordinates of each digit.

### Step 3: Note the Coordinates

For each digit, you'll enter four values:
- **x1**: Left edge of the digit (pixels from left)
- **y1**: Top edge of the digit (pixels from top)
- **x2**: Right edge of the digit
- **y2**: Bottom edge of the digit

Example calibration session:
```
Digit 0:
  x1 (left): 50
  y1 (top): 100
  x2 (right): 90
  y2 (bottom): 180

Digit 1:
  x1 (left): 100
  y1 (top): 100
  x2 (right): 140
  y2 (bottom): 180
...
```

## Production Usage

Once calibrated, reading displays is simple:

```python
from src.HardnessTester import HardnessTester

# Initialize with calibration
reader = HardnessTester(num_digits=4)
reader.load_calibration('lcd_calibration.json')

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

result = test_with_image('lcd_photo.jpg', 'lcd_calibration.json')
print(f"Result: {result}")
```

### Continuous Monitoring

Read from camera in a loop:

```python
reader = HardnessTester(num_digits=4)
reader.load_calibration('lcd_calibration.json')

while True:
    result = reader.read_display()
    print(f"Current reading: {result}")
    
    # Wait before next reading
    import time
    time.sleep(1)
```

## Advanced Features

### Locking Camera Settings

Prevent auto-exposure from washing out LCD segments:

```python
reader = HardnessTester(
    num_digits=4,
    exposure_time=10000,  # microseconds (Picamera2 only)
    gain=1.0              # Analog gain (Picamera2 only)
)
```

!!! note
    Camera locking works best with Picamera2 on Raspberry Pi. With cv2.VideoCapture, the system will attempt to set exposure but results vary by camera.

### Debug Mode

Enable debug output to troubleshoot recognition issues:

```python
result = reader.read_display(debug=True, debug_prefix="debug")
```

This saves images at each preprocessing step:
- `debug_step1_original.png` - Raw camera capture
- `debug_step2_lab.png` - LAB color space
- `debug_step3_b_channel.png` - Extracted b-channel
- `debug_step4_clahe.png` - Enhanced contrast
- `debug_step5_binary.png` - Binary threshold
- `debug_step6_cleaned.png` - Final cleaned image

### Viewing Segment Patterns

See which segments are detected for debugging:

```python
result = reader.read_display(debug=True)

# Show detailed segment analysis
frame = reader.capture_image()
binary = reader.preprocess_frame(frame)

for i in range(reader.num_digits):
    digit_roi = reader.extract_digit_roi(binary, i)
    segments = (
        reader.analyze_segment(digit_roi, 'top'),
        reader.analyze_segment(digit_roi, 'top_left'),
        reader.analyze_segment(digit_roi, 'top_right'),
        reader.analyze_segment(digit_roi, 'middle'),
        reader.analyze_segment(digit_roi, 'bottom_left'),
        reader.analyze_segment(digit_roi, 'bottom_right'),
        reader.analyze_segment(digit_roi, 'bottom'),
    )
    digit = reader.recognize_digit(digit_roi)
    print(f"Digit {i}: {segments} → {digit}")
```

### Adjusting Sensitivity

If segments aren't being detected reliably:

```python
reader = HardnessTester(num_digits=4)
reader.load_calibration('lcd_calibration.json')

# More sensitive (detects dimmer segments)
reader.segment_threshold = 0.3

# Less sensitive (only bright segments)
reader.segment_threshold = 0.7

result = reader.read_display()
```

### Automatic ROI Detection

Try automatic detection (may not work for all displays):

```python
reader = HardnessTester(num_digits=4)
frame = reader.capture_image()
binary = reader.preprocess_frame(frame)

# Attempt auto-detection
detected_rois = reader.auto_detect_digit_rois(binary)

if detected_rois:
    print(f"Detected {len(detected_rois)} digit ROIs:")
    for i, roi in enumerate(detected_rois):
        print(f"  Digit {i}: {roi}")
    
    reader.set_digit_rois(detected_rois)
    result = reader.read_display()
else:
    print("Auto-detection failed - use manual calibration")
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

1. **LAB Color Space**: Converts BGR → LAB and extracts the b-channel, which provides best contrast for LCD segments
2. **CLAHE**: Adaptive histogram equalization enhances local contrast
3. **Thresholding**: Otsu's method creates binary image
4. **Morphological Cleaning**: Removes noise

This pipeline is specifically optimized for LCD displays.

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

Camera auto-exposure is adjusting:

```python
# Lock exposure (Raspberry Pi with Picamera2)
reader = HardnessTester(
    num_digits=4,
    exposure_time=10000,
    gain=1.0
)
```

Or use consistent external lighting.

### Auto-detection fails

Manual calibration is more reliable:

1. Capture test image
2. Open in image viewer
3. Note pixel coordinates
4. Run `calibrate()` and enter coordinates
5. Save calibration file

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
reader = HardnessTester(num_digits=4)

if not reader.load_calibration('lcd_calibration.json'):
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
- Custom segment ROI positions
- Different camera settings

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
reader = HardnessTester(num_digits=3)
# Calibrate for 3 digits
```

### 6-Digit Displays

```python
reader = HardnessTester(num_digits=6)
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

## Next Steps

- Read [HardnessTester API Reference](../api/hardness-tester.md) for detailed documentation
- Explore [Segment Layout Guide](../../SEGMENT_LAYOUT_GUIDE.md) for technical details
- Review [Architecture](../concepts/architecture.md) to understand system integration

## Getting Help

If readings aren't working:

1. Run with `debug=True` and review preprocessing images
2. Check segment patterns to see what's being detected
3. Adjust segment threshold or ROI positions
4. Re-calibrate with better test image
5. Consult [API Reference](../api/hardness-tester.md) for advanced options
