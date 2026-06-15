"""QR code scanning for Cadux — live camera + static image decode.

Live scanning uses OpenCV + built-in QRCodeDetector for webcam feed.
Static image decoding uses pyzbar + Pillow as fallback.
"""

import base64
import io
import logging
import threading
import time

logger = logging.getLogger(__name__)

# ── Static image decoding (pyzbar + Pillow) ──────────────────────────

try:
    from pyzbar.pyzbar import decode as _zbar_decode
    from PIL import Image

    _HAVE_PYZBAR = True
except ImportError:
    _HAVE_PYZBAR = False
    logger.info("pyzbar/Pillow not available — static QR decoding disabled")


# ── Live camera scanning (OpenCV) ────────────────────────────────────

try:
    import cv2

    _HAVE_CV2 = True
except ImportError:
    _HAVE_CV2 = False
    logger.info("opencv-python-headless not available — live camera scanning disabled")


def is_available() -> bool:
    """Return True if any QR decoding method is available."""
    return _HAVE_PYZBAR or _HAVE_CV2


def is_camera_available() -> bool:
    """Return True if live camera scanning is available."""
    return _HAVE_CV2


# ── Static image decode ──────────────────────────────────────────────

def decode_qr_from_file(path: str) -> str | None:
    """Decode a QR code from an image file path using pyzbar."""
    if not _HAVE_PYZBAR:
        return None
    try:
        img = Image.open(path)
        results = _zbar_decode(img)
        if results:
            return results[0].data.decode("utf-8")
        return None
    except Exception as exc:
        logger.warning("QR decode from file failed: %s", exc)
        return None


def decode_qr_from_bytes(data: bytes) -> str | None:
    """Decode a QR code from raw image bytes using pyzbar."""
    if not _HAVE_PYZBAR:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        results = _zbar_decode(img)
        if results:
            return results[0].data.decode("utf-8")
        return None
    except Exception as exc:
        logger.warning("QR decode from bytes failed: %s", exc)
        return None


# ── Live Camera QR Scanner ───────────────────────────────────────────

def list_cameras(max_index: int = 4) -> list[dict]:
    """Enumerate available cameras, skipping dead/broken devices.

    Returns a list of dicts: {"index": int, "backend": str, "width": int, "height": int}
    Only includes cameras that actually produce non-empty frames.
    """
    import numpy as np

    cameras: list[dict] = []
    for idx in range(max_index + 1):
        for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
            cap = cv2.VideoCapture(idx, backend)
            opened = cap.isOpened()
            if not opened:
                cap.release()
                continue

            # Try to read a frame with timeout — some virtual devices hang on read()
            good = False
            w = h = 0
            for _ in range(5):
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    # Skip near-black frames (privacy shutter / dark room still gives > 0)
                    if frame.max() > 5:
                        h, w = frame.shape[:2]
                        good = True
                    break
                time.sleep(0.05)

            cap.release()
            if good:
                cameras.append({"index": idx, "backend": "DSHOW" if backend == cv2.CAP_DSHOW else "AUTO", "width": w, "height": h})
                break  # don't try CAP_ANY if DSHOW already found this index
    return cameras


class CameraQRScanner:
    """Live webcam QR scanner using OpenCV's built-in QRCodeDetector.

    Runs a capture loop in a background thread. Callers poll
    ``get_frame_jpeg()`` for the latest frame and check
    ``detected_text`` for QR results.

    Usage::

        cameras = list_cameras()
        scanner = CameraQRScanner(camera_index=cameras[0]["index"])
        scanner.start()
        while scanner.running:
            jpeg = scanner.get_frame_jpeg()
            if scanner.detected_text:
                print("QR:", scanner.detected_text)
                break
            await asyncio.sleep(0.05)
        scanner.stop()
    """

    def __init__(self, camera_index: int = 0):
        self._camera_index = camera_index
        self._cap: cv2.VideoCapture | None = None
        self._detector = cv2.QRCodeDetector() if _HAVE_CV2 else None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_bytes: bytes | None = None
        self.detected_text: str | None = None

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Open the camera, warm it up, and start capture. Returns True on success."""
        if not _HAVE_CV2:
            logger.warning("Cannot start camera — OpenCV not installed")
            return False

        # Open camera
        for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
            self._cap = cv2.VideoCapture(self._camera_index, backend)
            if self._cap.isOpened():
                logger.info("Camera %d opened with backend %s", self._camera_index, backend)
                break
            self._cap.release()
            self._cap = None

        if self._cap is None or not self._cap.isOpened():
            logger.warning("Failed to open camera index %d", self._camera_index)
            return False

        # Warm up: discard first several frames (some cameras produce dark frames initially)
        for _ in range(15):
            self._cap.read()

        self._running = True
        self.detected_text = None
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """Stop the capture thread and release the camera."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with self._lock:
            self._frame_bytes = None

    def get_frame_base64(self) -> str | None:
        """Return the latest frame as a base64-encoded JPEG data URI, or None."""
        with self._lock:
            if self._frame_bytes is None:
                return None
            b64 = base64.b64encode(self._frame_bytes).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"

    def get_frame_jpeg(self) -> bytes | None:
        """Return the latest frame as raw JPEG bytes, or None."""
        with self._lock:
            return self._frame_bytes

    def _capture_loop(self):
        """Background thread: read frames, detect QR, store latest JPEG."""
        logger.info("Camera capture loop started")
        frame_count = 0
        while self._running:
            if self._cap is None:
                break

            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            frame_count += 1
            if frame_count == 1:
                logger.info("Camera first frame received (shape %s)", frame.shape)

            # QR detection (every frame — QRCodeDetector is fast)
            if self.detected_text is None and self._detector is not None:
                try:
                    data, bbox, _ = self._detector.detectAndDecode(frame)
                    if data:
                        self.detected_text = data
                        logger.info("QR code detected: %s...", data[:40])
                except cv2.error:
                    pass  # OpenCV 4.x internal assertion on some frames, skip

            # Draw detection overlay if QR found
            if self.detected_text is not None:
                h, w = frame.shape[:2]
                cv2.putText(
                    frame, "QR DETECTED",
                    (w // 2 - 80, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3,
                )

            # Encode frame as JPEG for UI
            ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ok:
                with self._lock:
                    self._frame_bytes = jpeg.tobytes()

            time.sleep(0.03)  # ~30 fps cap
