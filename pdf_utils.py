"""Extract raw text from the pre-uploaded panel diagram PDF, for AI grounding only.
The app never generates or edits diagrams -- it only reads the text layer of an
already-designed PDF supplied by the design engineer."""
import io
from pypdf import PdfReader


def extract_text(raw_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        pages_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(f"[Page {i+1}]\n{text.strip()}")
        return "\n\n".join(pages_text) if pages_text else "(No extractable text layer in this PDF.)"
    except Exception as e:
        return f"(Could not extract text from PDF: {e})"
