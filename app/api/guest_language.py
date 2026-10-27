"""Conservative script checks for public AI responses matching guest questions.

Script checks catch conspicuously wrong responses (e.g. Chinese text in
response to an English question). They do not constitute a general-purpose
language classifier, especially for languages sharing the Latin alphabet.
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

_LATIN_LETTERS = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-žƀ-ɏ]")
_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)

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

# Hints are intentionally conservative: a single ordinary product word
# must not force the wrong language. These are not language-model outputs,
# and the fallback remains "same language as question".
_LATIN_HINTS = {
    "English": frozenset({"how", "what", "where", "why", "does", "which",
                          "would", "could", "guest", "search", "works"}),
    "Italian": frozenset({"funziona", "ricerca", "ospite", "posso",
                          "dove", "perché", "quali"}),
    "Turkish": frozenset({"nasıl", "çalışır", "arama", "nerede",
                          "nedir", "misafir"}),
    "Azerbaijani": frozenset({"necə", "işləyir", "axtarış", "harada",
                              "nədir", "qonaq"}),
    "French": frozenset({"comment", "fonctionne", "recherche",
                         "pourquoi", "puis-je"}),
    "Spanish": frozenset({"cómo", "funciona", "búsqueda",
                          "dónde", "puedo", "cuáles"}),
    "German": frozenset({"wie", "funktioniert", "suche", "warum",
                         "welche", "kann"}),
}
_LATIN_REMINDERS = {
    "English": "REPLY ONLY IN ENGLISH. Do not switch to Chinese or another language.",
    "Italian": "RISPONDI SOLO IN ITALIANO. Non usare un'altra lingua.",
    "Turkish": "SADECE TÜRKÇE YANIT VER.",
    "Azerbaijani": "YALNIZ AZƏRBAYCAN DİLİNDƏ CAVAB VER.",
    "French": "RÉPONDEZ UNIQUEMENT EN FRANÇAIS.",
    "Spanish": "RESPONDE ÚNICAMENTE EN ESPAÑOL.",
    "German": "ANTWORTE NUR AUF DEUTSCH.",
}


def _latin_language(question: str) -> str:
    words = set(word.casefold() for word in _WORDS.findall(question))
    scores = {name: len(words & hints)
              for name, hints in _LATIN_HINTS.items()}
    top = max(scores.values(), default=0)
    winners = [name for name, score in scores.items() if score == top]
    if top >= 2 and len(winners) == 1:
        return winners[0]
    return "the same language as the user's question"


def output_language_for(question: str) -> OutputLanguage:
    """Prefer a sufficiently represented non-Latin script over product names.

    Latin-script questions get a Latin script expectation too. An English
    question must not accept a Chinese completion as a successful reply.
    When language identity is ambiguous, the model must follow the input;
    we never pretend writing-system checks distinguish English from Italian.
    """
    counts = {script: len(pattern.findall(question))
              for script, pattern in _SCRIPT_PATTERNS.items()}
    if counts["japanese"] >= 2:
        chosen = "japanese"
    else:
        chosen = max(counts, key=counts.get)
    if counts[chosen] < 3:
        if len(_LATIN_LETTERS.findall(question)) < 3:
            return OutputLanguage(
                "the same language as the user's question", None,
                "Use only the language the user wrote in. Do not choose an "
                "unrelated language because the product instructions are English.",
            )
        name = _latin_language(question)
        reminder = (
            "Write the full answer in the EXACT LANGUAGE of the user's question "
            f"({name}). The user's question uses LATIN letters. "
            "Do not reply using Chinese, Japanese, Korean, Cyrillic or any "
            "different writing system. Product brand names may be retained. "
            "Do not translate the user question into another language."
        )
        if name in _LATIN_REMINDERS:
            reminder += " " + _LATIN_REMINDERS[name]
        return OutputLanguage(name, "latin", reminder)

    name = _SCRIPT_LANGUAGES[chosen]
    if chosen == "cyrillic":
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
    """Reject an unambiguous different writing system; no semantic claim."""
    if not answer.strip():
        return False
    if lang.script is None:
        return True

    if lang.script == "latin":
        latin_letters = len(_LATIN_LETTERS.findall(answer))
        foreign_letters = sum(len(pattern.findall(answer))
                              for pattern in _SCRIPT_PATTERNS.values())
        # A few stray non-Latin symbols may appear in product names, but a
        # Chinese/Cyrillic/etc explanation is never acceptable for English.
        return latin_letters >= 3 and foreign_letters <= 2

    pattern = _SCRIPT_PATTERNS[lang.script]
    script_letters = len(pattern.findall(answer))
    latin_letters = len(_LATIN_LETTERS.findall(answer))
    return script_letters >= 3 and script_letters * 4 >= latin_letters
