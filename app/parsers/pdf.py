"""Bounded PDF text and statistics. No OCR, persistence, or LLM calls."""
from dataclasses import dataclass, field
import pymupdf

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 200
MAX_CHARACTERS = 2_000_000


@dataclass(frozen=True)
class PdfSummary:
    status: str
    pages: int | None = None
    characters: int = 0
    empty_pages: int = 0
    text: str = field(default="", repr=False)
    page_texts: tuple[str, ...] = field(default_factory=tuple, repr=False)


def parse_pdf(data: bytes) -> PdfSummary:
    if len(data) > MAX_BYTES:
        return PdfSummary("too_large")
    if not data or b"%PDF-" not in data[:1024]:
        return PdfSummary("invalid")
    # Suppress native diagnostics containing document-controlled strings.
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                return PdfSummary("encrypted")
            pages = document.page_count
            if pages > MAX_PAGES:
                return PdfSummary("too_many_pages", pages)
            if pages == 0:
                return PdfSummary("invalid", 0)
            count = empty = 0
            texts = []
            for page in document:
                text = page.get_text("text")
                texts.append(text)
                count += len(text)
                empty += not bool(text.strip())
                if count > MAX_CHARACTERS:
                    return PdfSummary("too_much_text", pages)
            return PdfSummary("no_text" if empty == pages else "ok", pages, count, empty, "\n".join(texts), tuple(texts))
    except Exception:
        return PdfSummary("invalid")
