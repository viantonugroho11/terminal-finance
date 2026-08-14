"""Sentiment worker — DeepSeek zero-shot classifier.

Injectable classifier for tests. Production classifier uses DeepSeek via
OpenAI-compatible HTTP; falls back to a lexicon-only heuristic if
DEEPSEEK_API_KEY unset (still deterministic — useful for offline runs).
"""
from __future__ import annotations
import json
import os
import re
from typing import Callable

import httpx

from . import store


Classifier = Callable[[str], dict]


_POS = re.compile(
    r"\b(surge|rally|gain|beat|record|strong|profit|growth|upgrade|"
    r"naik|meningkat|untung|positif|melonjak|rekor|kuat|laba)\b",
    re.IGNORECASE,
)
_NEG = re.compile(
    r"\b(plunge|fall|drop|miss|loss|weak|cut|downgrade|risk|fraud|"
    r"turun|anjlok|rugi|melemah|negatif|risiko|penurunan|jatuh)\b",
    re.IGNORECASE,
)


def lexicon_classify(text: str) -> dict:
    pos = len(_POS.findall(text or ""))
    neg = len(_NEG.findall(text or ""))
    if pos == 0 and neg == 0:
        return {"label": "neutral", "confidence": 0.4,
                "rationale": "no polarity terms"}
    if pos > neg:
        return {"label": "positive",
                "confidence": min(0.5 + 0.1 * (pos - neg), 0.9),
                "rationale": f"pos={pos} neg={neg}"}
    if neg > pos:
        return {"label": "negative",
                "confidence": min(0.5 + 0.1 * (neg - pos), 0.9),
                "rationale": f"pos={pos} neg={neg}"}
    return {"label": "neutral", "confidence": 0.5,
            "rationale": f"pos={pos} neg={neg}"}


_SYSTEM = (
    "You classify financial news for polarity toward the referenced "
    "company/security. Reply with strict JSON only: "
    '{"label":"positive|neutral|negative","confidence":0..1,"rationale":"..."}. '
    "Confidence must reflect certainty; short rationale ≤120 chars."
)


async def deepseek_classify(text: str) -> dict:
    key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        return lexicon_classify(text)
    base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    body = {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": text[:1500]},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=body,
            )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        label = str(parsed.get("label", "neutral")).lower()
        if label not in ("positive", "neutral", "negative"):
            label = "neutral"
        conf = float(parsed.get("confidence", 0.5))
        conf = max(0.0, min(conf, 1.0))
        return {"label": label, "confidence": conf,
                "rationale": str(parsed.get("rationale", ""))[:200]}
    except Exception as e:
        return {"label": "neutral", "confidence": 0.3,
                "rationale": f"llm_error:{type(e).__name__}"}


async def score_missing(*, classifier: Classifier | None = None,
                        limit: int = 50) -> int:
    """Score up to `limit` articles that lack sentiment. Returns count scored.

    `classifier` may be sync (returns dict) or async (returns awaitable).
    """
    import inspect
    clf = classifier or deepseek_classify
    is_async = inspect.iscoroutinefunction(clf)
    scored = 0
    for art in store.sentiment_missing()[:limit]:
        text = f"{art.get('title', '')}. {art.get('snippet') or ''}"
        result = await clf(text) if is_async else clf(text)
        store.set_sentiment(
            art["id"],
            result.get("label", "neutral"),
            float(result.get("confidence", 0.5)),
            result.get("rationale"),
        )
        scored += 1
    return scored
