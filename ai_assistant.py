"""
FREE local "grounded assistant" — no external AI API, no internet call, no cost.

This module never calls any language model. It only searches, verbatim, inside:
  1) the panel's approved Excel parts list (Part Number / Description / Quantity), and
  2) the extracted text of the panel's PDF diagram.

Because it only returns data that literally exists in these two sources, it cannot
hallucinate, guess, or use outside knowledge by construction -- there is no generative
step at all. If nothing matches, it returns the fixed refusal message.
"""
import re
from difflib import SequenceMatcher

REFUSAL_MESSAGE = (
    "Sorry, this information is not listed in the approved technical data "
    "for this panel. Please contact the technical department."
)

_QUANTITY_WORDS = ["how many", "quantity", "qty", "count", "number of", "عدد", "كم"]
_DESCRIPTION_WORDS = ["what is", "description", "desc", "وصف", "ما هو", "ايش", "شنو"]
_WORD_RE = re.compile(r"[a-zA-Z0-9\-_/]+")


def _tokens(text: str) -> set:
    return set(_WORD_RE.findall((text or "").lower()))


def _match_row(question_lower: str, question_tokens: set, rows: list):
    """Find the best-matching parts-list row for the question.
    Exact/partial Part Number match always wins; otherwise fall back to
    keyword overlap + fuzzy similarity against the Description column."""
    best_row, best_score = None, 0.0

    for row in rows:
        part = str(row.get("Part Number", "")).strip()
        desc = str(row.get("Description", "")).strip()
        part_lower = part.lower()
        desc_lower = desc.lower()

        score = 0.0
        if part_lower and part_lower in question_lower:
            score = 100 + len(part_lower)  # strong signal: the exact part number was typed
        else:
            desc_tokens = _tokens(desc)
            overlap = question_tokens & desc_tokens
            if overlap:
                similarity = SequenceMatcher(None, question_lower, desc_lower).ratio()
                score = len(overlap) * 10 + similarity * 5

        if score > best_score:
            best_score, best_row = score, row

    return best_row, best_score


def _search_pdf_text(question_tokens: set, pdf_text: str):
    """Verbatim snippet lookup inside the diagram's extracted text -- never generated,
    only copied from the source, so it stays 100% faithful to the approved PDF."""
    if not pdf_text:
        return None
    lower_text = pdf_text.lower()
    for token in sorted(question_tokens, key=len, reverse=True):
        if len(token) < 3:
            continue
        idx = lower_text.find(token)
        if idx != -1:
            start, end = max(0, idx - 80), min(len(pdf_text), idx + 80)
            snippet = pdf_text[start:end].strip().replace("\n", " ")
            return f'Found in the panel diagram text: "...{snippet}..."'
    return None


def ask_local(question: str, excel_rows: list, pdf_text: str) -> str:
    q_lower = (question or "").strip().lower()
    q_tokens = _tokens(q_lower)

    row, score = _match_row(q_lower, q_tokens, excel_rows or [])
    if row and score >= 8:
        part = row.get("Part Number", "")
        desc = row.get("Description", "")
        qty = row.get("Quantity", "")
        wants_qty = any(w in q_lower for w in _QUANTITY_WORDS)
        wants_desc = any(w in q_lower for w in _DESCRIPTION_WORDS)
        if wants_qty and not wants_desc:
            return f"{part} — {desc}: Quantity = {qty}."
        if wants_desc and not wants_qty:
            return f"{part}: {desc}."
        return f"{part} — {desc} — Quantity: {qty}."

    pdf_hit = _search_pdf_text(q_tokens, pdf_text)
    if pdf_hit:
        return pdf_hit

    return REFUSAL_MESSAGE
