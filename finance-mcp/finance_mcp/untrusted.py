"""Handling for text this system did not author.

RSS headlines, article snippets, IDX disclosure titles and company-filed
descriptions all arrive from outside and end up in two dangerous places: an
LLM prompt, and the user's screen. Neither treats text as inert.

The concrete path that motivated this module: news/sentiment.py passes a raw
headline as the user turn of a classification prompt, and the resulting label
feeds the `sentiment_spike` alert metric. Anyone able to place a headline in
an ingested feed can therefore aim at someone's alerts. Output validation
already clamps the label to an enum and the confidence to 0..1, so the ceiling
is a flipped label rather than arbitrary values — but a flipped label is
exactly what the alert reads.

Two defences, because either alone is weak:

1. **Fence the data.** Untrusted text goes inside explicit delimiters, and any
   lookalike of those delimiters is stripped from the text first so it cannot
   close the fence early and speak as the prompt.
2. **Instruct last.** The standing instruction is repeated after the data.
   Text that says "ignore the above" is then arguing against something that
   has not been said yet.

This does not make injection impossible. It makes the easy version fail, and
it keeps untrusted text visibly separated from instructions.
"""
from __future__ import annotations

import re

OPEN = "<<<UNTRUSTED"
CLOSE = "UNTRUSTED>>>"

# Delimiter lookalikes: the exact tokens, and near-misses with stray spacing
# or repeated angle brackets. Matched case-insensitively.
_FENCE = re.compile(r"<*\s*/?\s*UNTRUSTED\s*>*", re.IGNORECASE)

# C0/C1 control characters except tab and newline. These can hide text from a
# human reader while remaining visible to a model.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def sanitize(text: str | None, *, max_len: int = 1500) -> str:
    """Strip fence lookalikes and control characters, then truncate.

    Content is preserved otherwise: this is not an attempt to detect
    instructions, which is not reliably possible. It only removes the
    characters that let text escape its container.
    """
    if not text:
        return ""
    cleaned = _FENCE.sub(" ", text)
    cleaned = _CONTROL.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    return cleaned[:max_len]


def fence(text: str | None, *, source: str | None = None,
          max_len: int = 1500) -> str:
    """Wrap untrusted text in delimiters it cannot break out of."""
    label = f" source={sanitize(source, max_len=40)}" if source else ""
    return f"{OPEN}{label}\n{sanitize(text, max_len=max_len)}\n{CLOSE}"
