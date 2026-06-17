"""QR code decoder for Cadux — reads QR codes from image files.

Uses pyzbar (libzbar wrapper) + Pillow for cross-platform decoding.
Works on Windows, Linux, macOS, and Android (Flet APK).
"""

from PIL import Image
from pyzbar.pyzbar import decode as _pyzbar_decode


def is_available() -> bool:
    """Check that pyzbar + Pillow are importable."""
    return True  # already checked at import


def decode_qr_from_file(image_path: str) -> str | None:
    """Decode the first QR code found in an image file.

    Returns the decoded text content, or None if no QR code found.
    """
    try:
        img = Image.open(image_path)
        results = _pyzbar_decode(img)
        for r in results:
            if r.type == "QRCODE":
                return r.data.decode("utf-8")
    except Exception:
        return None
    return None
