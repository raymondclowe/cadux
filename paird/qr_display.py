"""
Cadux QR helper — generate a QR code for the ``cadux://`` deep link.

Usage:
    uv run paird/qr_display.py <api_url> <secret_key>

Generates a QR code PNG at ``temp/cadux_qr.png`` and opens it with
the default image viewer.

Dependencies:
    - ``qrcode`` (included via flet/flet-cli deps)
    - ``Pillow`` (for PNG output — optional, ``qrcode`` can make
      terminal output without it)
"""

import sys
import os
import urllib.parse
import tempfile
import subprocess


def build_deeplink(api_url: str, secret_key: str) -> str:
    """Build a ``cadux://`` deep link URL from Hermes config."""
    encoded_url = urllib.parse.quote(api_url, safe="")
    encoded_key = urllib.parse.quote(secret_key, safe="")
    return f"cadux://connect?url={encoded_url}&key={encoded_key}"


def generate_qr_png(deeplink: str, output_path: str):
    """Generate a QR code PNG image."""
    import qrcode

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(deeplink)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(output_path)


def print_qr_terminal(deeplink: str):
    """Print a QR code to the terminal using block characters."""
    import qrcode
    from qrcode.image.styledpil import StyledPilImage

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=2,
        border=1,
    )
    qr.add_data(deeplink)
    qr.make(fit=True)

    # Simple ASCII output
    matrix = qr.get_matrix()
    for row in matrix:
        line = ""
        for cell in row:
            line += "██" if cell else "  "
        print(line)


def main():
    if len(sys.argv) < 3:
        print("Usage: uv run paird/qr_display.py <api_url> <secret_key>", file=sys.stderr)
        sys.exit(1)

    api_url = sys.argv[1]
    secret_key = sys.argv[2]

    deeplink = build_deeplink(api_url, secret_key)
    print(f"Deep link: {deeplink}")
    print()

    # Generate PNG
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    output_dir = os.path.join(project_root, "temp")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "cadux_qr.png")

    try:
        generate_qr_png(deeplink, output_path)
        print(f"QR code saved to: {output_path}")
        print()

        # Open with default viewer
        if sys.platform == "win32":
            os.startfile(output_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", output_path], check=False)
        else:
            subprocess.run(["xdg-open", output_path], check=False)

    except Exception as e:
        print(f"Could not generate PNG QR code: {e}")
        print()
        # Fallback: print to terminal
        print_terminal = False
        if not print_terminal:
            # Try with Pillow
            try:
                from qrcode.image.pil import PilImage
                print_qr = False
            except ImportError:
                print_qr_terminal(deeplink)

    print()
    print("Scan this QR code with your phone camera to connect Cadux.")


if __name__ == "__main__":
    main()
