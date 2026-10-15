"""Read local HTML as data only; verify all CPV rows against packaged labels.

Usage: python scripts/verify_cpv_reference.py LOCAL_REFERENCE.html
No URL fetching, browser, script execution or external dependencies.
"""
from html.parser import HTMLParser
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analytics.cpv import CPV_LABELS, CPV_METADATA, verify_reference


class ReferenceRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.cells, self.parts = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.cells = []
        if tag == 'td' and self.cells is not None:
            self.parts = []

    def handle_data(self, data):
        if self.parts is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'td' and self.parts is not None:
            self.cells.append(' '.join(''.join(self.parts).split()))
            self.parts = None
        if tag == 'tr' and self.cells is not None:
            self.rows.append(self.cells)
            self.cells = None


def verify(raw):
    if not verify_reference(raw):
        raise ValueError('Reference SHA256 mismatch.')
    parser = ReferenceRows()
    parser.feed(raw.decode('utf-8'))
    if ['Version', '2008'] not in parser.rows or ['Structure', 'hierarchical'] not in parser.rows:
        raise ValueError('Reference metadata mismatch.')
    rows = [row for row in parser.rows if len(row) == 2 and len(row[0]) == 8
            and row[0].isascii() and row[0].isdigit()]
    if len(rows) != len(CPV_LABELS) or dict(rows) != dict(CPV_LABELS):
        raise ValueError('Reference labels or coverage mismatch.')
    return len(rows)


if __name__ == '__main__':
    print(f'CPV 2008: {verify(Path(sys.argv[1]).read_bytes())} verified labels; '
          f"SHA256 {CPV_METADATA['reference_sha256']}")
