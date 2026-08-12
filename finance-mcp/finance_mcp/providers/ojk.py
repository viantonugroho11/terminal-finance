"""OJK (Otoritas Jasa Keuangan) macro provider.

Serves banking-sector aggregates from OJK's Statistik Perbankan Indonesia
(SPI): NPL, CAR, credit growth, NIM, LDR. OJK has migrated SPI to the
Portal Data SJK (https://data.ojk.go.id/SJKPublic) which does not
publish a stable public REST API — it serves XLSX/PDF and an
interactive portal. This adapter reads a locally-mirrored snapshot
under `FINANCE_OJK_SPI_PATH` (JSON file the operator populates from
the portal). Without a mirror configured the provider fails
`DATA_UNAVAILABLE` and skills surface the gap honestly.

Attribution: "OJK — Statistik Perbankan Indonesia".
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

from ..errors import FinanceError, ErrorCode
from ..models import MacroObservation, MacroSeries


# Indicators the SPI snapshot may contain.
_INDICATORS = {"npl", "car", "nim", "ldr", "credit_growth"}


class OjkProvider:
    """OJK SPI adapter reading a locally-mirrored JSON snapshot."""

    name = "ojk"
    tier = "primary"
    markets = frozenset({"MACRO"})
    capabilities = frozenset({"macro:banking_spi"})
    requires_api_key = False
    attribution = "OJK — Statistik Perbankan Indonesia"

    def __init__(self, snapshot_path: str | Path | None = None):
        self._path = Path(
            snapshot_path
            or os.getenv("FINANCE_OJK_SPI_PATH", "")
        ).expanduser() if (snapshot_path or os.getenv("FINANCE_OJK_SPI_PATH")) else None

    async def macro_indicator(self, indicator: str) -> MacroSeries:
        ind = indicator.lower()
        # Accept both "banking_spi:npl" style and bare names.
        if ":" in ind:
            ind = ind.split(":", 1)[1]
        if ind not in _INDICATORS:
            raise FinanceError(
                ErrorCode.DATA_UNAVAILABLE,
                f"OJK snapshot does not carry indicator {indicator!r}. "
                f"Known: {sorted(_INDICATORS)}",
                provider=self.name,
            )
        if self._path is None or not self._path.exists():
            raise FinanceError(
                ErrorCode.DATA_UNAVAILABLE,
                "OJK SPI snapshot not configured "
                "(set FINANCE_OJK_SPI_PATH to a JSON file mirrored from "
                "https://data.ojk.go.id/SJKPublic)",
                provider=self.name,
            )

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               f"OJK snapshot unreadable: {e}",
                               provider=self.name) from e

        rows = (payload or {}).get(ind) or []
        obs: list[MacroObservation] = []
        for r in rows:
            val = _f(r.get("value"))
            if val is None:
                continue
            obs.append(MacroObservation(
                period=str(r.get("period") or "")[:10],
                value=val, unit=r.get("unit") or "%",
            ))
        if not obs:
            raise FinanceError(
                ErrorCode.DATA_UNAVAILABLE,
                f"OJK snapshot has no observations for {ind}",
                provider=self.name,
            )
        obs.sort(key=lambda o: o.period)
        meta = (payload or {}).get("_meta") or {}
        return MacroSeries(
            indicator=ind, source=self.name,
            unit=obs[0].unit, observations=obs,
            frequency=meta.get("frequency", "monthly"),
            description=meta.get(f"{ind}_description",
                                 f"OJK SPI aggregate: {ind}"),
            attribution=self.attribution,
        )


def _f(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        f = float(str(v).replace(",", "."))
        return None if f != f else f
    except (TypeError, ValueError):
        return None
