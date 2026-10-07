"""Safe canonical normalization for procurement currency labels."""

from __future__ import annotations

import re
import unicodedata


_ALIASES = {
    "\u20ac": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "\u0435\u0432\u0440\u043e": "EUR",

    "\u00a3": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
    "pound sterling": "GBP",
    "sterling": "GBP",

    "\u20bd": "RUB",
    "rur": "RUB",
    "ruble": "RUB",
    "rubles": "RUB",
    "rouble": "RUB",
    "roubles": "RUB",
    "\u0440\u0443\u0431": "RUB",
    "\u0440\u0443\u0431.": "RUB",
    "\u0440\u0443\u0431\u043b\u044c": "RUB",
    "\u0440\u0443\u0431\u043b\u044f": "RUB",
    "\u0440\u0443\u0431\u043b\u0435\u0439": "RUB",

    "\u20b8": "KZT",
    "tenge": "KZT",
    "\u0442\u0435\u043d\u0433\u0435": "KZT",

    "\u20b9": "INR",
    "rupee": "INR",
    "rupees": "INR",
    "indian rupee": "INR",

    "\u20ba": "TRY",
    "tl": "TRY",
    "turkish lira": "TRY",

    "\u20be": "GEL",
    "lari": "GEL",
    "georgian lari": "GEL",

    "\u20bc": "AZN",
    "manat": "AZN",
    "azerbaijani manat": "AZN",

    "us$": "USD",
    "usd$": "USD",
    "us dollar": "USD",
    "us dollars": "USD",
    "u.s. dollar": "USD",
    "u.s. dollars": "USD",

    "a$": "AUD",
    "au$": "AUD",
    "australian dollar": "AUD",
    "australian dollars": "AUD",

    "c$": "CAD",
    "ca$": "CAD",
    "canadian dollar": "CAD",
    "canadian dollars": "CAD",

    "nz$": "NZD",
    "new zealand dollar": "NZD",
    "new zealand dollars": "NZD",

    "yuan": "CNY",
    "renminbi": "CNY",
    "chinese yuan": "CNY",

    "yen": "JPY",
    "japanese yen": "JPY",

    "rand": "ZAR",
    "south african rand": "ZAR",
}


_EXACT_CODE = re.compile(
    r"^[A-Za-z]{3}$"
)

_PAREN_CODE = re.compile(
    r"\(([A-Za-z]{3})\)"
)

_UPPER_CODE_TOKEN = re.compile(
    r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])"
)


def _clean(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKC",
        value,
    )

    return " ".join(
        normalized.strip().split()
    )


def normalize_currency_code(
    value: str | None,
) -> str | None:
    """
    Return a stable currency representation.

    Confident ISO-style values and known aliases become
    three-letter canonical codes.

    Ambiguous standalone symbols such as "$" and "?"
    are intentionally not guessed without source context.
    Unknown non-empty labels are preserved rather than
    silently discarded.
    """

    if value is None:
        return None

    if not isinstance(value, str):
        return value

    cleaned = _clean(value)

    if not cleaned:
        return None

    alias = _ALIASES.get(
        cleaned.casefold()
    )

    if alias is not None:
        return alias

    if _EXACT_CODE.fullmatch(
        cleaned
    ):
        return cleaned.upper()

    parenthetical = _PAREN_CODE.search(
        cleaned
    )

    if parenthetical is not None:
        return (
            parenthetical
            .group(1)
            .upper()
        )

    explicit_code = (
        _UPPER_CODE_TOKEN.search(
            cleaned
        )
    )

    if explicit_code is not None:
        return (
            explicit_code
            .group(1)
            .upper()
        )

    return cleaned
