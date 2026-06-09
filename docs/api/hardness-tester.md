# HardnessTester

The `HardnessTester` class serves two related roles:

1. **Shore hardness testing toolhead** - picks up the tester tool, presses it into a sample, and reads the result as part of a validated state-machine workflow.
2. **LCD display reader** - reads 7-segment LCD displays by detecting which segments are active rather than using traditional OCR. This is more reliable for low-contrast displays and requires no training data.

Both roles are combined in one class because the tester's LCD display is its primary output channel.

---

=== "Operator Guide"

    ## Calibration Walkthrough

    Before the system can read hardness values, the camera must be calibrated to the position of each digit on the display. Calibration is a one-time setup per physical mounting.

    ### Step 1: Capture a reference image

    ```python
    from src.HardnessTester import HardnessTester

    tester = HardnessTester(
        calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
        num_digits=4,
        use_camera=True,
    )
    frame = tester.capture_image(save=True, output_path='calibration_reference.jpg')
    print("Image saved - open it to identify digit pixel coordinates.")
    ```

    Check the saved image for:

    - Digits are clearly visible and lit
    - Lighting is adequate and not overexposed
    - Camera is in focus

    ### Step 2: Run the interactive calibration

    ```python
    tester.calibrate(frame=frame, save_calibration=True)
    ```

    The calibration process:

    1. Saves debug images of each preprocessing step (`calibration_step*.png`)
    2. Opens an interactive GUI: click-and-drag to draw a bounding box for each digit, then click to place segment polygon vertices for each of the 7 segments per digit
    3. Saves the calibration to the configured `calibration_path`
    4. Immediately tests the calibration and prints a result (saves `calibration_test_step*.png`)

    !!! tip
        Open `calibration_step5_binary.png` in an image viewer. In the binary image, active LCD segments appear as dark regions on a bright background. Use this to verify that the preprocessing is enhancing the segments correctly before confirming calibration.

    ### Step 3: Verify

    After calibration, run a standalone read to confirm the result:

    ```python
    if tester.load_assigned_calibration():
        result = tester.read_display()
        print(f"Display reads: {result}")
    else:
        print("Calibration file not found - re-run calibration.")
    ```

    ---

    ## Reading Displays

    ### Recommended: via JubileeManager

    When running a full hardness testing session through `JubileeManager`, you do not call `read_display()` directly. Instead call:

    ```python
    # Turn on the tester, zero it, then test a sample
    manager.hardness_turn_on(mode="shore_a")  # actuate power button
    manager.hardness_zero(mode="shore_a")     # actuate zero button

    success = manager.test_sample(
        tray_index=0,
        sample_index=3,
        mode="shore_a",
    )
    if success:
        print(f"Result: {manager.last_hardness_result}")  # e.g. 42.5
        print(f"Error: {manager.last_hardness_error}")    # None if clean read
    ```

    The `test_sample` method handles moving to the sample position, pressing the tester into the sample, reading the display, and logging the result.

    ### Standalone use (no JubileeManager)

    Use `from_system_config` to build a configured instance from `system_config.json`:

    ```python
    from src.HardnessTester import HardnessTester
    from src.ConfigLoader import config

    tester = HardnessTester.from_system_config(
        tester_mode="shore_a",
        hardware_cfg=config.system.hardness_testers.shore_a,
        profile_cfg=config.get_active_hardness_profile(),
    )

    if tester.load_assigned_calibration():
        result = tester.read_display()
        print(f"Display: {result}")
    ```

    Or construct directly for testing purposes:

    ```python
    tester = HardnessTester(
        calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
        num_digits=4,
        use_camera=True,
    )
    tester.load_calibration("jubilee_api_config/lcd_calibration_shore_a.json")
    result = tester.read_display()
    ```

    ### Reading from a static image

    Useful for debugging calibration without a live camera:

    ```python
    from src.HardnessTester import test_with_image

    result = test_with_image(
        "lcd_photo.jpg",
        "jubilee_api_config/lcd_calibration_shore_a.json",
    )
    print(f"Result: {result}")
    ```

    ---

    ## Checking Display State

    Two helper methods let you confirm the display is on and zeroed before testing:

    ```python
    # Returns True if the display reads a valid number, False if OFF
    # Raises RuntimeError if indeterminate
    is_on = tester.is_display_on()

    # Returns True if the display reads 0-5 (effectively zeroed)
    is_zeroed = tester.is_display_zero()
    ```

    ---

    ## Adjusting Sensitivity

    The `segment_threshold` attribute controls how many pixels in a segment region must be active before the segment is counted as ON. The default is `0.5` (50%).

    ```python
    tester.segment_threshold = 0.3  # more sensitive - detects dimmer segments
    tester.segment_threshold = 0.7  # less sensitive - only bright segments
    ```

    Lowering the threshold helps when lighting is dim or the display contrast is low. Raising it reduces false positives from stray light.

    ---

    ## Troubleshooting

    ### All digits show `?`

    The segments are not being recognized. Check:

    1. **Run with debug=True**: `tester.read_display(debug=True, debug_prefix="debug")` saves `debug_step*.png` images.
    2. **Review the binary image** (`debug_step5_binary.png`): active segments should be dark on a bright background.
    3. **Re-run calibration** if the camera has been moved.
    4. **Adjust threshold**: try `tester.segment_threshold = 0.3`.

    ### Display reads `OFF`

    The tester is powered off or the segments are not lit. Power on the tester and wait for it to settle before reading.

    ### Reading is inconsistent between calls

    `read_display()` with no arguments runs a 10-sample consensus read (captures 10 frames over ~1 second and returns the strict majority). If no majority is reached, it returns `None`. This is intentional: a `None` result means the display value is genuinely changing or the camera cannot achieve a consistent view.

    - Check that the tester has finished settling after a sample press.
    - Check for external vibration or changing lighting.

    ### Reading changes with lighting

    Camera auto-exposure may be adjusting between captures. On Raspberry Pi with Picamera2, the camera settings are fixed after the first capture. Ensure the camera is fully initialized and stabilized before the first read.

    ---

    ## Limitations

    - Only digits 0-9 are recognized. No decimal point, negative sign, or unit symbols.
    - Decimal position must be known in advance. The display on Shore testers has one implied decimal place: a raw display read of `"0425"` corresponds to 42.5 Shore units. The `test_sample()` method applies this scaling automatically.
    - `read_display()` does not detect partially lit segments. If a segment is damaged or dimly lit, it will be counted based on the threshold.

    ---

    ## Performance

    Typical performance on Raspberry Pi 4:

    - Calibration: 5-10 seconds (one-time setup)
    - Single frame read: 100-200 ms
    - Consensus read (10 frames, default): ~1 second
    - With debug images enabled: add 300-500 ms

    On a desktop PC: single frame read 20-50 ms.

=== "API Reference"

    ## Class Reference

    ::: src.HardnessTester.HardnessTester
        options:
          members:
            - __init__
            - from_system_config
            - load_assigned_calibration
            - load_calibration
            - calibrate
            - capture_image
            - preprocess_frame
            - read_display
            - analyze_segment
            - recognize_digit
            - set_digit_rois
            - turn_on
            - turn_off
            - zero
            - is_display_on
            - is_display_zero
            - test_sample
          show_root_heading: true
          show_source: false

    ## Helper Function

    ::: src.HardnessTester.test_with_image
        options:
          show_root_heading: true
          show_source: false

    ## Configuration Model

    `HardnessTester.from_system_config()` resolves tool and calibration settings from `system_config.json`.

    ```json
    {
      "hardness_testers": {
        "shore_a": {
          "use_camera": true,
          "tool": {
            "index": 1,
            "name": "shore_a_hardness_tester"
          },
          "lcd_calibration_path": "jubilee_api_config/lcd_calibration_shore_a.json",
          "button_servos": {
            "servo": "S1",
            "power_press_angle": 90,
            "power_release_angle": 0,
            "zero_press_angle": 90,
            "zero_release_angle": 0
          },
          "cam_usb_path": "/dev/shore_a_cam"
        }
      }
    }
    ```

    ## Calibration File Format

    The calibration JSON produced by `calibrate()` and consumed by `load_calibration()`:

    ```json
    {
      "digit_rois": [
        [x1, y1, x2, y2],
        [x1, y1, x2, y2],
        [x1, y1, x2, y2],
        [x1, y1, x2, y2]
      ],
      "segment_points": [
        {
          "top":          [[x, y], [x, y], [x, y], [x, y]],
          "top_left":     [[x, y], [x, y], [x, y], [x, y]],
          "top_right":    [[x, y], [x, y], [x, y], [x, y]],
          "middle":       [[x, y], [x, y], [x, y], [x, y], [x, y], [x, y]],
          "bottom_left":  [[x, y], [x, y], [x, y], [x, y]],
          "bottom_right": [[x, y], [x, y], [x, y], [x, y]],
          "bottom":       [[x, y], [x, y], [x, y], [x, y]]
        }
      ]
    }
    ```

    `digit_rois` holds the bounding box `[x1, y1, x2, y2]` for each digit in the camera frame (absolute pixel coordinates). `segment_points` holds the absolute pixel polygon vertices for each of the 7 segments per digit. These are populated by the calibration process and used by `analyze_segment()`.

    ## Segment Lookup Table

    Segment order is `(top, top_left, top_right, middle, bottom_left, bottom_right, bottom)`.

    | Pattern               | Digit |
    |-----------------------|-------|
    | `(1, 1, 1, 0, 1, 1, 1)` | `0` |
    | `(0, 0, 1, 0, 0, 1, 0)` | `1` |
    | `(1, 0, 1, 1, 1, 0, 1)` | `2` |
    | `(1, 0, 1, 1, 0, 1, 1)` | `3` |
    | `(0, 1, 1, 1, 0, 1, 0)` | `4` |
    | `(1, 1, 0, 1, 0, 1, 1)` | `5` |
    | `(1, 1, 0, 1, 1, 1, 1)` | `6` |
    | `(1, 0, 1, 0, 0, 1, 0)` | `7` |
    | `(1, 1, 1, 1, 1, 1, 1)` | `8` |
    | `(1, 1, 1, 1, 0, 1, 1)` | `9` |
    | `(0, 0, 0, 0, 0, 0, 0)` | `OFF` |

    ## Advanced Debugging Example

    After calibration, inspect segment detection per digit using the updated API:

    ```python
    tester = HardnessTester(
        calibration_path="jubilee_api_config/lcd_calibration_shore_a.json",
        num_digits=4,
        use_camera=True,
    )
    tester.load_assigned_calibration()

    frame = tester.capture_image()
    binary = tester.preprocess_frame(frame, debug=True, debug_prefix="debug")

    for i in range(tester.num_digits):
        segments = {
            name: tester.analyze_segment(binary, i, name)
            for name in tester.SEGMENT_ORDER
        }
        digit = tester.recognize_digit(binary, i, debug=True)
        print(f"Digit {i}: {segments} => {digit}")
    ```

    Note that `analyze_segment` and `recognize_digit` both take the full binary frame and a `digit_idx` argument. They no longer accept a cropped digit ROI.

---

## Design Notes

???+ note "Why not OCR?"
    Traditional OCR (Tesseract, EasyOCR) struggles with 7-segment LCD displays because:

    - Low contrast between segments and background
    - Font variations across display manufacturers
    - Hollow or partially lit segments
    - Sensitivity to lighting changes
    - Sensitivity to camera distortion

    Segment-based detection avoids these problems:

    - Specifically designed for 7-segment geometry
    - Reliable with low-contrast or dim displays
    - No training data required
    - Fast and lightweight
    - Easy to debug: each segment decision is independently inspectable

???+ info "Preprocessing pipeline"
    The preprocessing and sharpening pipeline is optimized for LCD displays:

    1. **Grayscale conversion** - converts the BGR camera frame to grayscale as the primary preprocessing path.
    2. **Unsharp masking (sharpening)** - applied by default after grayscale to recover blurred segment edges before CLAHE. Default ``sharpen_strength`` is 31; set to ``0.0`` to disable.
    3. **CLAHE** (Contrast Limited Adaptive Histogram Equalization) - enhances contrast in local 8x8 tiles rather than globally, handling shadows and glare that would fool global thresholding.
    4. **Otsu thresholding** - automatically finds the optimal binary threshold value for the local image content.
    5. **Morphological cleaning** - removes small noise pixels that survive thresholding.

???+ info "Segment detection"
    Each segment is detected by:

    1. Applying the calibrated polygon mask for that segment to the binary image
    2. Counting dark (active) pixels inside the mask with `cv2.countNonZero`
    3. Comparing the ratio against `segment_threshold` (default 0.5)

    Segment polygons are stored as absolute pixel coordinates in `segment_points`, populated from the calibration file. The polygon approach handles trapezoidal LCD segment shapes more accurately than rectangular ROI proportions.

---

## See Also

- [JubileeManager](jubilee-manager.md) - orchestrates Shore test workflows via `test_sample`, `hardness_turn_on`, `hardness_turn_off`, `hardness_zero`
- [MotionPlatformStateMachine](motion-platform.md) - validates movements and executes hardware actions
- [Reading LCD Displays](../how-to/reading-lcd-displays.md) - operator how-to guide
- [Architecture Overview](../concepts/architecture.md) - system design context
