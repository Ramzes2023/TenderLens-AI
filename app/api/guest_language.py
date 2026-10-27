"""Strictly bound the public assistant's output to the question's language.

Most models obey natural-language instructions, but an English policy prompt
may make Russian questions return English. Enforce the writing system for
unambiguous non-Latin input without pretending Latin-script language ID is
reliable for a 3-character question. Never translate locally or fabricate
a successful model reply.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class OutputLanguage:
    name: str
    script: str | None
    reminder: str


_SCRIPT_PATTERNS = {
    "cyrillic": re.compile(r"[\u0400-\u052f]"),
    "georgian": re.compile(r"[\u10a0-\u10ff\u1c90-\u1cbf]"),
    "greek": re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]"),
    "arabic": re.compile(r"[\u0600-\u06ff\u0750-\u077f]"),
    "hebrew": re.compile(r"[\u0590-\u05ff]"),
    "devanagari": re.compile(r"[\u0900-\u097f]"),
    "hangul": re.compile(r"[\uac00-\ud7af\u1100-\u11ff]"),
    "han": re.compile(r"[\u3400-\u9fff]"),
    "japanese": re.compile(r"[\u3040-\u30ff]"),
    "thai": re.compile(r"[\u0e00-\u0e7f]"),
}

_SCRIPT_LANGUAGES = {
    "cyrillic": "Russian",
    "georgian": "Georgian",
    "greek": "Greek",
    "arabic": "the Arabic-script language of the question",
    "hebrew": "Hebrew",
    "devanagari": "the Devanagari-script language of the question",
    "hangul": "Korean",
    "han": "Chinese",
    "japanese": "Japanese",
    "thai": "Thai",
}


def output_language_for(question: str) -> OutputLanguage:
    """Determine an explicit script from sufficiently many relevant glyphs.

    A user may include VALYQON, API and other Latin product terms in a
    Russian question: a count of three or more non-Latin glyphs wins.
    For indistinguishable same-script languages, instruct the model to
    preserve the *language* of the question rather than assume all
    Cyrillic/Arabic/Devanagari input uses one specific language.
    """
    counts = {script: len(pattern.findall(question))
              for script, pattern in _SCRIPT_PATTERNS.items()}
    # Hiragana/Katakana disambiguate Japanese from Han-only Chinese.
    if counts["japanese"] >= 2:
        chosen = "japanese"
    else:
        chosen = max(counts, key=counts.get)
    if counts[chosen] < 3:
        return OutputLanguage(
            "the same language as the user's question", None,
            "Use only the language the user wrote in; do NOT default to English "
            "just because product facts and instructions are written in English.",
        )
    name = _SCRIPT_LANGUAGES[chosen]
    if chosen == "cyrillic":
        # Standard short Russian prompts are common; do not treat Ukrainian,
        # Belarusian or Kazakh as Russian when distinctive letters are present.
        if re.search(r"[іїєґ]", question, re.IGNORECASE):
            name = "Ukrainian"
        elif re.search(r"[ў]", question, re.IGNORECASE):
            name = "Belarusian"
        elif re.search(r"[әғқңөұүһі]", question, re.IGNORECASE):
            name = "the Cyrillic-script language of the question"
    reminder = (
        "Answer entirely in the SAME LANGUAGE as the user's question "
        f"({name}), using the {chosen} writing system. "
        "Product names like VALYQON AI or API may remain in Latin letters; "
        "all explanatory sentences must use the user's language."
    )
    if name == "Russian":
        reminder += " ОБЯЗАТЕЛЬНО ОТВЕЧАЙ ПО-РУССКИ. Не отвечай по-английски."
    return OutputLanguage(name, chosen, reminder)


def answer_uses_question_script(answer: str, lang: OutputLanguage) -> bool:
    """Reject unmistakably English-only completions for non-Latin questions.

    This tests script, not full linguistic correctness. Shared-script
    languages and Latin-script languages still depend on model adherence.
    """
    if not answer.strip():
        return False
    if lang.script is None:
        return True
    pattern = _SCRIPT_PATTERNS[lang.script]
    script_letters = len(pattern.findall(answer))
    # No need to penalize English proper nouns in otherwise non-Latin text.
    latin_letters = len(re.findall(r"[A-Za-z]", answer))
    return script_letters >= 3 and script_letters * 4 >= latin_letters
