"""Symbol tagger — regex + name-alias allowlist.

Precision-first: only tag when the exact ticker or a configured alias
appears as a word-boundary match in title+snippet.
"""
from __future__ import annotations
import re
from functools import lru_cache
from pathlib import Path

import yaml

_ALIASES_PATH = Path(__file__).parent.parent / "data" / "symbol_aliases.yaml"


@lru_cache(maxsize=1)
def _aliases() -> dict[str, list[str]]:
    if not _ALIASES_PATH.exists():
        return {}
    with _ALIASES_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out: dict[str, list[str]] = {}
    for sym, names in data.items():
        sym_u = str(sym).upper()
        out[sym_u] = [sym_u] + [str(n) for n in (names or [])]
    return out


@lru_cache(maxsize=1)
def _compiled() -> list[tuple[str, re.Pattern]]:
    patterns: list[tuple[str, re.Pattern]] = []
    for sym, names in _aliases().items():
        alt = "|".join(re.escape(n) for n in names)
        patterns.append((sym, re.compile(rf"\b(?:{alt})\b", re.IGNORECASE)))
    return patterns


def tag(text: str) -> list[str]:
    if not text:
        return []
    hits: list[str] = []
    for sym, pat in _compiled():
        if pat.search(text):
            hits.append(sym)
    return hits


def clear_cache() -> None:
    """Test helper — reset lru_cache after mutating aliases file."""
    _aliases.cache_clear()
    _compiled.cache_clear()
