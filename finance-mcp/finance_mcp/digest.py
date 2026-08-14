"""Morning digest composer — ADR-0023.

Pure composition on top of existing router capabilities. Deterministic —
no LLM. Output ≤ 4096 chars (Telegram cap). Language via DIGEST_LANG env.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Any

from .retry import with_retry
from .portfolio import watchlist as pwl


TELEGRAM_CAP = 4096


async def _safe(coro):
    try:
        return await coro
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def _quote(symbol: str) -> dict[str, Any]:
    async def _fetch(p, s):
        return await with_retry(lambda: p.quote(s), provider=p.name, symbol=symbol)
    try:
        from .registry import router
        value, _, _ = await router.call(
            "quote", symbol=symbol,
            fetch=lambda p: _fetch(p, symbol),
        )
        return value if isinstance(value, dict) else {"error": "bad_shape"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def _market_overview(market: str) -> dict[str, Any]:
    async def _fetch(p):
        # not all providers implement market_overview; router will pick
        return await with_retry(lambda: p.market_overview(),
                                provider=p.name, symbol=None)
    try:
        from .registry import router
        value, _, _ = await router.call(
            "market_overview", symbol=None, market=market,
            fetch=lambda p: _fetch(p),
        )
        return value or {}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def _bi_rate() -> dict[str, Any]:
    async def _fetch(p):
        return await with_retry(lambda: p.macro("bi_rate"),
                                provider=p.name, symbol=None)
    try:
        from .registry import router
        value, _, _ = await router.call(
            "macro", symbol=None, market="IDX",
            fetch=lambda p: _fetch(p),
        )
        return value or {}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _fmt_pct(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    return f"{v:+.2f}%"


def _fmt_price(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    return f"{v:,.2f}"


def _render_id(payload: dict) -> str:
    d = payload
    lines: list[str] = []
    date = d["generated_at"][:10]
    lines.append(f"*Morning Digest* · {date}")
    lines.append("")
    ihsg = d.get("ihsg", {})
    lines.append(f"*IHSG* {_fmt_price(ihsg.get('last'))} "
                 f"({_fmt_pct(ihsg.get('change_pct'))})")
    us = d.get("us_overnight", {})
    if us:
        lines.append(f"*US o/n* SPX {_fmt_pct(us.get('spx_change_pct'))} · "
                     f"NDX {_fmt_pct(us.get('ndx_change_pct'))}")
    fx = d.get("fx", {})
    if fx:
        lines.append(f"*FX* DXY {_fmt_price(fx.get('dxy'))} · "
                     f"USDIDR {_fmt_price(fx.get('usdidr'))}")
    macro = d.get("macro", {})
    if macro.get("bi_rate") is not None:
        lines.append(f"*BI Rate* {macro['bi_rate']:.2f}%")
    movers = d.get("movers", [])
    if movers:
        lines.append("")
        lines.append("*Top movers IDX*")
        for m in movers[:5]:
            lines.append(f"  {m.get('symbol','?')}  "
                         f"{_fmt_pct(m.get('change_pct'))}")
    flow = d.get("foreign_flow", [])
    if flow:
        lines.append("")
        lines.append("*Foreign net (Rp M)*")
        for f in flow[:5]:
            lines.append(f"  {f.get('symbol','?')}  "
                         f"{f.get('net_idr',0)/1_000_000:,.0f}")
    wl = d.get("watchlist", [])
    if wl:
        lines.append("")
        lines.append("*Watchlist*")
        for w in wl[:10]:
            lines.append(f"  {w.get('symbol','?')}  "
                         f"{_fmt_price(w.get('last'))}  "
                         f"{_fmt_pct(w.get('change_pct'))}")
    out = "\n".join(lines)
    if len(out) > TELEGRAM_CAP:
        out = out[: TELEGRAM_CAP - 20] + "\n…lihat terminal"
    return out


def _render_en(payload: dict) -> str:
    return _render_id(payload).replace("Morning Digest", "Morning Digest").replace(
        "Top movers IDX", "IDX Top Movers"
    ).replace("Foreign net (Rp M)", "Foreign Net Flow (IDR M)").replace(
        "Watchlist", "Watchlist"
    ).replace("…lihat terminal", "…see terminal")


async def build_payload(watchlist_symbols: list[str] | None = None) -> dict:
    """Gather all inputs; returns structured payload (LLM-safe)."""
    now = datetime.now(timezone.utc).isoformat()
    ihsg = await _quote("^JKSE")
    spx = await _quote("^GSPC")
    ndx = await _quote("^NDX")
    dxy = await _quote("DX-Y.NYB")
    usdidr = await _quote("USDIDR=X")

    idx_ov = await _market_overview("IDX")
    macro = await _bi_rate()

    movers = idx_ov.get("movers") if isinstance(idx_ov, dict) else None
    flow = idx_ov.get("foreign_flow") if isinstance(idx_ov, dict) else None

    if watchlist_symbols is not None:
        wl_symbols = watchlist_symbols
    else:
        try:
            wl_symbols = pwl.items("default")
        except Exception:
            wl_symbols = []
    wl_out = []
    for s in wl_symbols[:15]:
        q = await _quote(s)
        wl_out.append({
            "symbol": s,
            "last": q.get("last") if isinstance(q, dict) else None,
            "change_pct": q.get("change_pct") if isinstance(q, dict) else None,
        })

    return {
        "generated_at": now,
        "ihsg": {"last": ihsg.get("last"),
                 "change_pct": ihsg.get("change_pct")} if isinstance(ihsg, dict) else {},
        "us_overnight": {
            "spx_change_pct": spx.get("change_pct") if isinstance(spx, dict) else None,
            "ndx_change_pct": ndx.get("change_pct") if isinstance(ndx, dict) else None,
        },
        "fx": {
            "dxy": dxy.get("last") if isinstance(dxy, dict) else None,
            "usdidr": usdidr.get("last") if isinstance(usdidr, dict) else None,
        },
        "macro": {"bi_rate": macro.get("bi_rate") if isinstance(macro, dict) else None},
        "movers": movers or [],
        "foreign_flow": flow or [],
        "watchlist": wl_out,
    }


def render(payload: dict, lang: str | None = None) -> str:
    lang = lang or os.getenv("DIGEST_LANG", "id")
    if lang.lower().startswith("en"):
        return _render_en(payload)
    return _render_id(payload)


async def build_and_render(watchlist_symbols: list[str] | None = None,
                           lang: str | None = None) -> str:
    payload = await build_payload(watchlist_symbols)
    return render(payload, lang)
