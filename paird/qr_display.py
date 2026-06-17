"""QR code display for Cadux pairing.

Generates QR codes as ASCII art (for terminal) and PNG (for sharing).
Supports both plain-text config and encrypted-blob+code modes.
"""

import argparse
import base64
import hashlib
import json
import os
import sys

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import SquareModuleDrawer


def _load_config() -> dict:
    """Load Hermes config from env (with dotenv .env fallback)."""
    from dotenv import load_dotenv
    load_dotenv()

    api_url = os.environ.get(
        "CADUX_API_URL", os.environ.get("HERMES_API_URL", "")
    )
    secret_key = os.environ.get("CADUX_SECRET_KEY", "")
    return {"api_url": api_url.rstrip("/"), "secret_key": secret_key}


def _encrypt(data: bytes, password: str) -> str:
    """XOR-encrypt data with sha256(password), return 'encrypted:md5'.

    Matches paird/server.py _encrypt and cadux/src/pairing.py decrypt_blob.
    """
    key = hashlib.sha256(password.encode()).digest()
    enc = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    md5_sig = hashlib.md5(data).hexdigest()
    return base64.b64encode(enc).decode() + ":" + md5_sig


def _generate_code(length: int = 4) -> str:
    """Generate a random code from unambiguous characters."""
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    import random
    return "".join(random.choice(chars) for _ in range(length))


def generate(config: dict, pin: str | None = None) -> tuple[str, str | None]:
    """Return (qr_text, code) where qr_text is the string to encode in QR.

    If pin is provided, encrypts config with that pin.
    If pin is None, returns plain JSON config.
    """
    if pin:
        config_json = json.dumps(config).encode()
        return _encrypt(config_json, pin), pin

    # No PIN: plain JSON
    return json.dumps(config, indent=2), None


def ascii_qr(text: str) -> str:
    """Generate ASCII art QR code for terminal display."""
    qr = qrcode.QRCode(border=1, box_size=1)
    qr.add_data(text)
    qr.make(fit=True)
    return "\n".join(
        "".join("██" if module else "  " for module in row)
        for row in qr.modules
    )


def png_qr(text: str, output_path: str) -> str:
    """Generate a PNG QR code image. Returns output_path."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=SquareModuleDrawer(),
        fill_color="black",
        back_color="white",
    )
    img.save(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Cadux QR code display")
    parser.add_argument(
        "--pin", type=str, default=None,
        help="Encryption PIN (4-char). If omitted, uses plain JSON (no PIN)."
    )
    parser.add_argument(
        "--png", type=str, default=None,
        help="Save PNG QR code to this path."
    )
    parser.add_argument(
        "--plain", action="store_true",
        help="Force plain JSON (no encryption) even if PIN would otherwise apply."
    )
    args = parser.parse_args()

    config = _load_config()
    if not config.get("secret_key"):
        print("ERROR: CADUX_SECRET_KEY not set in env or .env", file=sys.stderr)
        sys.exit(1)

    pin = args.pin
    if args.plain:
        pin = None
    elif pin is None:
        # Default: auto-generate a PIN for encryption
        pin = _generate_code(4)

    qr_text, code = generate(config, pin)

    # Terminal output
    print("═" * 60)
    print("  Cadux Pairing QR Code")
    print("═" * 60)
    print()
    print(ascii_qr(qr_text))
    print()
    print("─" * 60)
    print(f"  API:  {config['api_url']}")
    if code:
        print(f"  CODE: {code}")
        print(f"  (scan QR, then enter this code to decrypt)")
    else:
        print("  (no encryption — scan QR to connect directly)")
    print("─" * 60)

    # PNG output
    if args.png:
        png_qr(qr_text, args.png)
        print(f"\n  PNG saved → {args.png}")


if __name__ == "__main__":
    main()
