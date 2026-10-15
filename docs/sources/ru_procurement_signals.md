# Russian procurement metadata signals

`app.sources.ru_procurement_signals.extract_ru_procurement_signals` is a
standalone, standard-library extractor. It performs no HTTP requests, database
access, AI calls, or integration with adapters, ingestion, or shared models.

```python
from app.sources.ru_procurement_signals import extract_ru_procurement_signals

result = extract_ru_procurement_signals({
    "description": "44-ФЗ; ОКПД2: 62.01.11.000",
})
assert result.law == "44-FZ"
assert result.okpd2_codes == ("62.01.11.000",)
```

The input is a mapping of field names to values, or `None`. Only `title`,
`description`, `summary`, `procurement_law`, `law_text`, and
`classification_text` are scanned, in that fixed order. URLs, platform names,
source names, buyers, customer names, IDs, and all other keys are ignored.
Callers must supply actual content in the appropriate fields; moving a source
name or URL into a content field defeats that semantic separation.

Frozen dataclasses expose the aggregate law (`44-FZ`, `223-FZ`, `ambiguous`,
or `unknown`), sorted unique `okpd2_codes` and `ktru_codes`, every occurrence
in `signals`, and input diagnostics in `issues`. Each signal has `kind`,
normalized `value`, exact `evidence`, `source_field`, and half-open `start` / `end`
Python string offsets. Evidence includes the code label. Offsets count Unicode
code points, not bytes or grapheme clusters. Original text is never normalized.
Signals are ordered by field order, then text position. Duplicate occurrences
remain as evidence; both laws produce `ambiguous`, with no precedence rule.

Law patterns recognize case-insensitive Cyrillic ФЗ and Latin FZ, optional
spacing and common Unicode dashes, plus Russian federal-law wording and
English `Federal Law`, with optional number markers. Bare 44 and 223 do not
qualify. Word boundaries reject attached identifiers and serial suffixes.
Codes require an immediately preceding ОКПД2 / OKPD2 or КТРУ / KTRU label,
optionally followed by `код` / `code` and `:`, `=`, or `№`. OKPD2 accepts dotted
ASCII digit structures `NN`, `NN.NN`, `NN.NN.N`, `NN.NN.NN`, or
`NN.NN.NN.NNN`. KTRU accepts `NN.NN.NN.NNN-NNNNNNNN`; Unicode dashes are
normalized to ASCII in its value. Only the first code after a label is extracted;
each additional code needs its own label. Partial malformed codes are rejected.

Missing and `None` fields are ignored. Other non-string values are skipped with
`invalid_type`; non-mapping input raises `TypeError`. Fields longer than
`MAX_FIELD_CHARS` (100,000 code points) are skipped entirely with `too_long`.
There is no truncation that could create a partial signal. At most six bounded
fields are scanned. Separator whitespace is bounded to 16 characters and does
not bridge lines; full-law wording uses whitespace between words.

Detection records explicit textual mentions; **it does not determine legal
applicability**. Negated, quoted, historical, and comparative mentions still
count. Structurally valid codes are not checked against a classification
registry, and no missing codes, descriptions, or classifications are invented.
Unsupported wording, transliterations, markup, or distant labels may be missed.
This is conservative metadata extraction, not a legal decision or a catalog
validator. It is Russia-first; it does not classify CIS or international laws.

Offline validation (use an available Python interpreter):

```text
python -B -m pytest -p no:cacheprovider tests/test_ru_procurement_signals.py
```

Syntax can be checked without bytecode by calling `compile()` on both Python
files. No broad test run or runtime integration is required for this phase.
