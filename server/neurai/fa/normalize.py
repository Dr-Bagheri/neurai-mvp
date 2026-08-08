"""Persian text normalization — the project-owned `fa_normalize()` interface (D5).

Implemented in pure Python so there is no hard dependency on hazm/parsivar;
if we later adopt one of them, it gets wrapped *behind* this function and no
task module changes. Applied to both ASR output and LLM output.
"""
from __future__ import annotations

import re

# Arabic → Persian character unification (ی/ک etc.)
_CHAR_MAP = str.maketrans({
    "ي": "ی",  # Arabic yeh
    "ك": "ک",  # Arabic kaf
    "ة": "ه",
    "ۀ": "هٔ",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "ٱ": "ا",
    "ٳ": "ا",
    "ﻻ": "لا",
})

# Arabic-Indic digits (٠١٢…) and Extended Arabic-Indic (۰۱۲…) → keep Persian forms
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_DIGIT_MAP = str.maketrans(dict(zip(_ARABIC_DIGITS, _PERSIAN_DIGITS)))

ZWNJ = "‌"

# Suffixes that should attach with ZWNJ (نیم‌فاصله) instead of a space.
_ZWNJ_SUFFIXES = ("ها", "های", "هایی", "تر", "ترین", "ام", "ات", "اش", "می", "نمی")

_DIACRITICS = re.compile(r"[ً-ٰٟ]")  # tanwin, tashdid, etc.


def _fix_zwnj(text: str) -> str:
    # «می خوایم» → «می‌خوایم», «کتاب ها» → «کتاب‌ها»
    text = re.sub(r"\b(ن?می) (?=\S)", r"\1" + ZWNJ, text)
    for suf in ("ها", "های", "هایی", "تر", "ترین"):
        text = re.sub(rf"(\S) {suf}\b", rf"\1{ZWNJ}{suf}", text)
    # collapse duplicate ZWNJ and ZWNJ adjacent to spaces
    text = re.sub(rf"{ZWNJ}+", ZWNJ, text)
    text = re.sub(rf" ?{ZWNJ} ?", ZWNJ, text)
    return text


def fa_normalize(text: str, *, persian_digits: bool = True, strip_diacritics: bool = True) -> str:
    """Normalize Persian text: char unification, digits, ZWNJ, whitespace."""
    if not text:
        return text
    text = text.translate(_CHAR_MAP)
    if persian_digits:
        text = text.translate(_DIGIT_MAP)
    if strip_diacritics:
        text = _DIACRITICS.sub("", text)
    text = _fix_zwnj(text)
    # Persian punctuation spacing: no space before «؟ ، ؛», one after
    text = re.sub(r"\s+([؟،؛!.:])", r"\1", text)
    text = re.sub(r"([؟،؛])(?=\S)", r"\1 ", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text
