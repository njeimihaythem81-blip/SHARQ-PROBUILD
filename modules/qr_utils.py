"""QR code generator for panel client-page links.
Colored to match the SHARQ brand (neon green on white) so a printed
QR sticker is recognizable and still scans reliably."""
import io
import qrcode
from PIL import Image

NEON_GREEN = "#1f9e0c"  # slightly darkened neon for reliable scanning contrast


def generate_qr(url: str) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color=NEON_GREEN, back_color="white").convert("RGB")


def image_to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
