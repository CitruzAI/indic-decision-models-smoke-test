"""Drop items that mention a product wake word or assistant name.

The list covers Latin spellings and common Hindi and Tamil spellings.
An item is dropped if any of the three language texts matches.
Tokenization treats letters and combining marks as part of a token, so
Tamil and Devanagari vowel signs stay attached to the word.
"""

from __future__ import annotations

import unicodedata
from typing import Iterable

# Latin names, compared case-insensitively after tokenizing.
LATIN_NAMES = frozenset(
    {
        "siri",
        "alexa",
        "olly",
        "google",
        "googles",
        "cortana",
    }
)
LATIN_PREFIXES = frozenset({"hey", "hi", "ok", "okay"})
LATIN_PREFIX_ONLY_NAMES = frozenset({"assistant"})

# Hindi spellings of the same product names and of hey/ok.
HINDI_NAMES = frozenset(
    {
        "सिरी",
        "सेरी",
        "एलेक्सा",
        "एलेकसा",
        "आलेक्सा",
        "एलेक्सी",
        "ओली",
        "ऑली",
        "ओल्ली",
        "ऑल्ली",
        "गूगल",
        "गुगल",
        "गोगल",
        "कॉर्टाना",
        "कोर्टाना",
        "करटाना",
    }
)
HINDI_PREFIXES = frozenset({"हे", "हेय", "हाय", "अरे", "ओके", "ओकेय"})

# Tamil spellings. Short tokens such as சிரி are matched only as whole tokens,
# so words like சிரிப்பை are not treated as a hit.
TAMIL_NAMES = frozenset(
    {
        "சிரி",
        "சிரீ",
        "அலெக்சா",
        "அலெக்ஸா",
        "ஆலி",
        "ஒல்லி",
        "ஓலி",
        "ஆல்லி",
        "ஓல்லி",
        "கூகுள்",
        "கூகல்",
        "கூகுல்",
        "கூகில்",
        "கார்ட்டானா",
        "கார்டானா",
    }
)
TAMIL_PREFIXES = frozenset({"ஹே", "ஹேய்", "ஹாய்", "ஏய்", "ஓகே", "ஓகேய்"})

NAMES = LATIN_NAMES | HINDI_NAMES | TAMIL_NAMES
PREFIXES = LATIN_PREFIXES | HINDI_PREFIXES | TAMIL_PREFIXES
PREFIX_ONLY_NAMES = LATIN_PREFIX_ONLY_NAMES


def _is_token_char(ch: str) -> bool:
    if ch.isalpha():
        return True
    return unicodedata.category(ch) in {"Mn", "Mc"}


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text or "")
    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        if _is_token_char(ch):
            buf.append(ch)
        elif buf:
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    return out


def text_has_wake_word(text: str) -> bool:
    toks = tokens(text)
    folded = [t.casefold() for t in toks]
    for i, tok in enumerate(folded):
        if tok in NAMES or tok in {n.casefold() for n in HINDI_NAMES | TAMIL_NAMES}:
            return True
        if tok in PREFIX_ONLY_NAMES or tok == "assistant":
            prev = folded[i - 1] if i else ""
            if prev in PREFIXES or prev in {p.casefold() for p in PREFIXES}:
                return True
    return False


def item_has_wake_word(texts: Iterable[str]) -> bool:
    return any(text_has_wake_word(t) for t in texts)
