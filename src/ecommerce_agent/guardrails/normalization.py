from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageDetection:
    detected_language: str
    confidence: float
    supported: bool
    support_level: str


@dataclass(frozen=True)
class NormalizedInput:
    canonical: str
    original_hash: str
    language: LanguageDetection
    signals: tuple[str, ...]


_SCRIPT_PATTERNS = {
    "han": re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]"),
    "hiragana_katakana": re.compile(r"[\u3040-\u30ff]"),
    "hangul": re.compile(r"[\uac00-\ud7af]"),
    "arabic": re.compile(r"[\u0600-\u06ff]"),
    "latin": re.compile(r"[A-Za-z]"),
}
_SPANISH_MARKERS = re.compile(r"[áéíóúñü¿¡]|\b(?:por favor|ingresos|ventas|cliente)\b", re.I)


def _language(text: str) -> LanguageDetection:
    if _SCRIPT_PATTERNS["hiragana_katakana"].search(text):
        return LanguageDetection("ja", 0.99, True, "limited")
    if _SCRIPT_PATTERNS["hangul"].search(text):
        return LanguageDetection("ko", 0.99, True, "limited")
    if _SCRIPT_PATTERNS["arabic"].search(text):
        return LanguageDetection("ar", 0.99, False, "unsupported")
    if _SCRIPT_PATTERNS["han"].search(text):
        return LanguageDetection("zh-Hant", 0.9, True, "full")
    if _SPANISH_MARKERS.search(text):
        return LanguageDetection("es", 0.85, True, "limited")
    if _SCRIPT_PATTERNS["latin"].search(text):
        return LanguageDetection("en", 0.8, True, "full")
    return LanguageDetection("und", 0.0, False, "unsupported")


def normalize_input(message: str) -> NormalizedInput:
    normalized = unicodedata.normalize("NFKC", message)
    signals: list[str] = []
    if normalized != message:
        signals.append("unicode_normalized")

    visible: list[str] = []
    removed_invisible = False
    for character in normalized:
        category = unicodedata.category(character)
        if category in {"Cf", "Cc"} and character not in {"\n", "\t", "\r"}:
            removed_invisible = True
            continue
        visible.append(character)
    if removed_invisible:
        signals.append("invisible_characters_removed")

    canonical = " ".join("".join(visible).casefold().split())
    scripts = {
        name
        for name, pattern in _SCRIPT_PATTERNS.items()
        if name != "latin" and pattern.search(canonical)
    }
    if _SCRIPT_PATTERNS["latin"].search(canonical):
        scripts.add("latin")
    if len(scripts) > 1:
        signals.append("mixed_scripts")

    return NormalizedInput(
        canonical=canonical,
        original_hash=hashlib.sha256(message.encode("utf-8")).hexdigest(),
        language=_language(canonical),
        signals=tuple(signals),
    )
