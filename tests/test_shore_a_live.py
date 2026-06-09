#!/usr/bin/env python3
"""
Live Shore A hardness tester camera feed with real-time LCD translation.

Run standalone to verify camera framing and calibration without Jubilee.

Usage:
    python tests/test_shore_a_live.py [options]

    # Use a specific camera index
    python tests/test_shore_a_live.py --cam-id 1

    # Use a custom calibration file
    python tests/test_shore_a_live.py --calibration path/to/calibration.json

Keyboard controls:
    q / Esc     - quit
    c           - run calibration UI on the current frame
    r           - run a 10-frame consensus read and print to console
    s           - save snapshot of the current raw frame
    p           - save snapshot of the current processed frame
    +/-         - raise/lower threshold bias by 5 (helps with reflections)
    d           - toggle per-frame debug image dumps
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

# Allow running from project root or from inside tests/
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

# Stub science_jubilee.tools.Tool if the package is not installed so this
# script runs on a plain dev machine without the full Jubilee environment.
try:
    from science_jubilee.tools.Tool import Tool as _Tool  # noqa: F401
except ImportError:
    import types

    _stub_module = types.ModuleType("science_jubilee")
    _stub_tools = types.ModuleType("science_jubilee.tools")
    _stub_tool = types.ModuleType("science_jubilee.tools.Tool")

    class _StubTool:
        def __init__(self, index=0, name=""):
            self.index = index
            self.name = name

    _stub_tool.Tool = _StubTool
    _stub_tools.Tool = _stub_tool
    sys.modules["science_jubilee"] = _stub_module
    sys.modules["science_jubilee.tools"] = _stub_tools
    sys.modules["science_jubilee.tools.Tool"] = _stub_tool

from HardnessTester import HardnessTester  # noqa: E402

# Default calibration path: shore_a-specific, then fall back to the generic file
_SHORE_A_CAL = os.path.join(
    _PROJECT_ROOT, "api_config", "lcd_calibration_shore_a.json"
)
_GENERIC_CAL = os.path.join(_PROJECT_ROOT, "api_config", "lcd_calibration.json")
DEFAULT_CAL = _SHORE_A_CAL if os.path.exists(_SHORE_A_CAL) else _GENERIC_CAL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _draw_segment_overlay(bgr_frame: np.ndarray, reader: HardnessTester) -> np.ndarray:
    """Return a copy of bgr_frame with segment polygon outlines drawn."""
    out = bgr_frame.copy()
    if reader.segment_points is None:
        return out
    for digit_segs in reader.segment_points:
        for seg_name in reader.SEGMENT_ORDER:
            pts = digit_segs.get(seg_name)
            if pts and len(pts) >= 3:
                poly = reader._normalize_polygon_point_order(pts)
                if poly is not None:
                    cv2.polylines(
                        out, [poly], isClosed=True, color=(0, 255, 0), thickness=1
                    )
    return out


def _make_processed_view(frame: np.ndarray, reader: HardnessTester) -> np.ndarray:
    """Return the binary-processed image with segment overlays as a BGR image."""
    try:
        binary = reader.preprocess_frame(frame)
        bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        return _draw_segment_overlay(bgr, reader)
    except Exception:
        return np.zeros_like(frame)


def _annotate_live(frame: np.ndarray, reading: str, calibrated: bool) -> np.ndarray:
    """Return a copy of frame with the current Shore A reading overlaid."""
    out = frame.copy()
    h, w = out.shape[:2]

    if reading.replace("?", "").isdigit() and "?" not in reading:
        color = (0, 255, 0)  # green - good numeric read
    elif reading == "OFF":
        color = (0, 0, 255)  # red - display off
    elif reading == "---":
        color = (180, 180, 180)  # grey - no read yet
    else:
        color = (0, 165, 255)  # orange - partial/ambiguous

    font_scale = max(1.0, w / 700)
    thickness = max(2, int(font_scale * 2))
    text = f"Shore A: {reading}"
    (tw, th), baseline = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    cv2.rectangle(out, (10, 10), (20 + tw, 20 + th + baseline), (0, 0, 0), -1)
    cv2.putText(
        out,
        text,
        (15, 15 + th),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        color,
        thickness,
        cv2.LINE_AA,
    )

    if not calibrated:
        warn = "NO CALIBRATION - press 'c' to calibrate"
        cv2.putText(
            out,
            warn,
            (10, h - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    return out


def _camera_source_for_dev(cam_id: int, cam_usb_path: str | None) -> str:
    """Pick a value HardnessTester accepts as cam_usb_path (off-Pi uses numeric index)."""
    if cam_usb_path:
        return cam_usb_path
    return str(cam_id)


def run_live_feed(
    cam_id: int,
    cam_usb_path: str | None,
    calibration_path: str,
    debug: bool,
):
    """Continuous live camera loop with real-time LCD translation."""
    cam_source = _camera_source_for_dev(cam_id, cam_usb_path)
    if cam_usb_path:
        print(f"Initializing Shore A camera (USB path: {cam_source})...")
    else:
        print(f"Initializing Shore A camera (OpenCV device index: {cam_id})...")
    reader = HardnessTester(
        num_digits=4,
        cam_usb_path=cam_source,
        use_camera=True,
        tester_mode="shore_a",
        calibration_path=calibration_path,
    )

    if os.path.exists(calibration_path):
        print(f"Loading calibration: {calibration_path}")
        reader.load_calibration(calibration_path)
    else:
        print(f"No calibration found at {calibration_path}")

    WIN_LIVE = "Shore A - Live Feed  [q=quit | c=calibrate | r=read | s=snapshot | +/-=bias | d=debug]"
    WIN_PROC = "Shore A - Processed"
    cv2.namedWindow(WIN_LIVE, cv2.WINDOW_NORMAL)
    cv2.namedWindow(WIN_PROC, cv2.WINDOW_NORMAL)

    last_reading = "---"
    last_read_time = 0.0
    READ_INTERVAL = 0.4  # single-frame read every 400 ms
    snapshot_count = 0
    debug_active = debug

    print("\nLive feed running. Controls:")
    print("  q / Esc   - quit")
    print("  c         - run calibration UI on current frame")
    print("  r         - run 10-frame consensus read (printed to console)")
    print("  s         - save raw snapshot")
    print("  p         - save processed snapshot")
    print("  +/-       - raise/lower threshold bias by 5")
    print("  d         - toggle per-frame debug image dumps")

    while True:
        ret, frame = reader.cap.read()
        if not ret or frame is None:
            print("WARNING: Camera frame grab failed")
            time.sleep(0.05)
            continue

        now = time.monotonic()

        # Lightweight single-frame read at regular intervals
        if now - last_read_time >= READ_INTERVAL and reader.segment_points is not None:
            raw = reader._read_display_from_frame(frame)
            if raw is not None:
                last_reading = raw
                if debug_active:
                    reader._read_display_from_frame(
                        frame, debug=True, debug_prefix="shore_a_live"
                    )
            last_read_time = now

        live_view = _annotate_live(
            frame, last_reading, reader.segment_points is not None
        )
        proc_view = _make_processed_view(frame, reader)

        cv2.imshow(WIN_LIVE, live_view)
        cv2.imshow(WIN_PROC, proc_view)

        key = cv2.waitKey(30) & 0xFF

        if key in (ord("q"), 27):
            break

        elif key == ord("c"):
            print("\nOpening calibration UI on current frame...")
            ret2, cal_frame = reader.cap.read()
            target_frame = cal_frame if (ret2 and cal_frame is not None) else frame
            ok = reader.calibrate(
                frame=target_frame,
                save_calibration=True,
                calibration_path=calibration_path,
            )
            print("Calibration complete." if ok else "Calibration cancelled.")

        elif key == ord("r"):
            print("\nRunning 10-frame consensus read...")
            result = reader.read_display()
            last_reading = result if result is not None else "---"
            print(f"Consensus result: {last_reading}")

        elif key == ord("s"):
            path = f"shore_a_snapshot_{snapshot_count:03d}.jpg"
            cv2.imwrite(path, frame)
            print(f"Raw snapshot saved: {path}")
            snapshot_count += 1

        elif key == ord("p"):
            path = f"shore_a_processed_{snapshot_count:03d}.jpg"
            cv2.imwrite(path, proc_view)
            print(f"Processed snapshot saved: {path}")
            snapshot_count += 1

        elif key in (ord("+"), ord("=")):
            reader.threshold_bias = max(0, reader.threshold_bias - 5)
            print(f"Threshold bias: {reader.threshold_bias}")

        elif key == ord("-"):
            reader.threshold_bias += 5
            print(f"Threshold bias: {reader.threshold_bias}")

        elif key == ord("d"):
            debug_active = not debug_active
            print(f"Debug image dumps: {'ON' if debug_active else 'OFF'}")

    cv2.destroyAllWindows()
    print("Live feed stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Shore A hardness tester - live camera feed with LCD translation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--cam-id",
        type=int,
        default=0,
        metavar="N",
        help="OpenCV camera index for dev machines (default: 0). Ignored if --cam-usb-path is set.",
    )
    parser.add_argument(
        "--cam-usb-path",
        type=str,
        default=None,
        metavar="PATH",
        help="Linux USB device path (Pi deployment). Overrides --cam-id.",
    )
    parser.add_argument(
        "--calibration",
        type=str,
        default=DEFAULT_CAL,
        metavar="PATH",
        help=f"Calibration JSON file (default: {DEFAULT_CAL})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save preprocessing debug images on startup",
    )
    args = parser.parse_args()

    run_live_feed(args.cam_id, args.cam_usb_path, args.calibration, args.debug)


if __name__ == "__main__":
    main()
