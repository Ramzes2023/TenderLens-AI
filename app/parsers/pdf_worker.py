"""Isolated parser process: PDF bytes in, small JSON summary out."""
import json
import sys
from dataclasses import asdict
from .pdf import MAX_BYTES, parse_pdf

if __name__ == "__main__":
    result = parse_pdf(sys.stdin.buffer.read(MAX_BYTES + 1))
    print(json.dumps(asdict(result)))
