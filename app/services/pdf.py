"""Bounded Telegram download and isolated PDF processing."""
import asyncio
import io
import json
import sys
from pathlib import Path
from app.parsers.pdf import MAX_BYTES, PdfSummary


class LimitedBuffer(io.BytesIO):
    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > MAX_BYTES:
            raise ValueError("Download size limit")
        return super().write(data)


async def summarize_pdf(data: bytes, timeout: float = 30) -> PdfSummary:
    if len(data) > MAX_BYTES:
        return PdfSummary("too_large")
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.parsers.pdf_worker",
        cwd=Path(__file__).resolve().parents[2],
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(data), timeout)
        if process.returncode != 0:
            return PdfSummary("invalid")
        return PdfSummary(**json.loads(stdout))
    except TimeoutError:
        return PdfSummary("timeout")
    except (ValueError, TypeError):
        return PdfSummary("invalid")
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
