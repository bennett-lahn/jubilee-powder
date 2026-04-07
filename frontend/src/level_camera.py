"""
Level camera streamers for the Jubilee Automation server.

Streams MJPEG frames from a camera pointed at the scale bubble level.

Three-stage pipeline
--------------------
  1. Capture thread  - grabs frames at 30 fps (OpenCV or synthetic).
  2. Encode pool     - 3-worker ThreadPoolExecutor, TurboJPEG encoding.
  3. Frame queue     - ordered futures consumed by the async generator.

MockLevelCameraStreamer draws a synthetic bubble level for UI development
using only numpy (no physical camera required).  It falls back to cv2 or
Pillow for JPEG encoding if TurboJPEG is not installed.

LevelCameraStreamer reads from a real USB camera via OpenCV and encodes
with TurboJPEG.
"""

import asyncio
import math
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import cv2
from turbojpeg import TurboJPEG


# =============================================================================
# Base streamer
# =============================================================================

class _BaseLevelCameraStreamer:
    """Shared capture-encode-queue pipeline for both mock and real cameras."""

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=3)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=5)
        self._capture_thread: threading.Thread | None = None
        self._running = False
        self._jpeg = None

    @property
    def active(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._on_start()
        self._running = True
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True,
        )
        self._capture_thread.start()

    def stop(self) -> None:
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
        self._on_stop()
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

    def _on_start(self) -> None:
        """Hook for subclass init (open camera, resolve encoder, etc.)."""

    def _on_stop(self) -> None:
        """Hook for subclass cleanup (release camera, etc.)."""

    def _capture_loop(self) -> None:
        """Hook for subclass capture loop (read frames, enqueue futures)."""
        raise NotImplementedError

    def _encode_frame(self, frame):
        return self._jpeg.encode(frame, quality=80)

    def _enqueue_frame(self, frame) -> None:
        """Submit frame to the encoding pool and add the future to the queue."""
        future = self._pool.submit(self._encode_frame, frame)
        try:
            self._frame_queue.put(future, timeout=0.1)
        except queue.Full:
            # Drop the oldest frame to make room.
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frame_queue.put(future, timeout=0.1)
            except queue.Full:
                pass

    async def frame_generator(self):
        """Async generator yielding MJPEG boundary-delimited frames."""
        while self._running:
            try:
                future = self._frame_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
            try:
                jpeg_bytes = await asyncio.to_thread(future.result, 1.0)
            except Exception:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg_bytes
                + b"\r\n"
            )


# =============================================================================
# Mock streamer
# =============================================================================

def _mock_jpeg_encoder():
    """Return a JPEG encoding callable."""
    tj = TurboJPEG()
    return lambda frame: tj.encode(frame, quality=80)


class MockLevelCameraStreamer(_BaseLevelCameraStreamer):
    """
    Synthetic bubble-level feed for UI development.

    Draws a 320x240 dark frame with a circular vial ring, crosshairs, and a
    green bubble that drifts slowly using sin/cos — no physical camera needed.
    """

    def _on_start(self) -> None:
        import numpy as np
        self._np = np
        self._do_encode = _mock_jpeg_encoder()

    def _encode_frame(self, frame):
        return self._do_encode(frame)

    def _capture_loop(self) -> None:
        np = self._np
        interval = 1.0 / 30.0
        h, w = 240, 320
        cx, cy = w // 2, h // 2
        yy, xx = np.ogrid[:h, :w]
        dist_center = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2).astype(np.float32)
        ring_mask = (dist_center > 58) & (dist_center <= 62)
        cross_h = np.zeros((h, w), dtype=bool)
        cross_v = np.zeros((h, w), dtype=bool)
        cross_h[cy, cx - 40 : cx + 41] = True
        cross_v[cy - 40 : cy + 41, cx] = True

        while self._running:
            t0 = time.monotonic()
            frame = np.full((h, w, 3), 30, dtype=np.uint8)
            frame[ring_mask] = [80, 80, 80]
            frame[cross_h] = [50, 50, 50]
            frame[cross_v] = [50, 50, 50]

            bx = cx + 12 * math.sin(t0 * 0.3)
            by = cy + 8 * math.cos(t0 * 0.2)
            dist_bubble = np.sqrt((xx - bx) ** 2 + (yy - by) ** 2).astype(np.float32)
            frame[dist_bubble <= 18] = [0, 180, 0]
            frame[(dist_bubble > 16) & (dist_bubble <= 20)] = [0, 120, 0]

            self._enqueue_frame(frame)

            elapsed = time.monotonic() - t0
            if elapsed < interval:
                time.sleep(interval - elapsed)


# =============================================================================
# Real camera streamer
# =============================================================================

class LevelCameraStreamer(_BaseLevelCameraStreamer):
    """Real USB camera streamer using OpenCV + TurboJPEG."""

    def __init__(self, camera_index: int = 0) -> None:
        super().__init__()
        self._camera_index = camera_index
        self._cap = None

    def _on_start(self) -> None:
        self._jpeg = TurboJPEG()
        self._cap = cv2.VideoCapture(self._camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera index {self._camera_index}")

    def _on_stop(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _capture_loop(self) -> None:
        interval = 1.0 / 30.0
        while self._running:
            t0 = time.monotonic()
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(interval)
                continue
            self._enqueue_frame(frame)
            elapsed = time.monotonic() - t0
            if elapsed < interval:
                time.sleep(interval - elapsed)
