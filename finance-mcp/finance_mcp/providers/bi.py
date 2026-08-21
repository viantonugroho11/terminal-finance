"""Bank Indonesia macro provider — HTML scraper.

BI publishes BI-Rate + JISDOR through SharePoint-rendered HTML pages,
not a JSON API. This adapter fetches those pages and parses the
rate table with regex against Indonesian month names + numeric cells.
When BI redesigns the page, parsing may return `DATA_UNAVAILABLE` —
router surfaces honestly, no fake defaults.

See ADR-0020. Attribution: "Bank Indonesia".
"""
from __future__ import annotations

import re

import httpx

from ..errors import ErrorCode, FinanceError
from ..models import JisdorRate, MacroObservation, MacroSeries

_BASE = "https://www.bi.go.id"
_BI_RATE_URL = _BASE + "/id/statistik/indikator/bi-rate.aspx"
_JISDOR_URL  = _BASE + "/id/statistik/informasi-kurs/jisdor/default.aspx"

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": "https://www.bi.go.id/",
}

# Indonesian months → month numbers.
_ID_MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5,
    "juni": 6, "juli": 7, "agustus": 8, "september": 9, "oktober": 10,
    "november": 11, "desember": 12,
}


def _parse_id_date(raw: str) -> str | None:
    """Normalize '22 Juli 2026' / '22-Jul-2026' / '2026-07-22' → 'YYYY-MM-DD'."""
    s = raw.strip().lower()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{1,2})[\s\-/]+([a-z]+)[\s\-/]+(\d{4})", s)
    if not m:
        return None
    day = int(m.group(1)); mon = m.group(2)[:3]
    # Accept short ("jul") + full ("juli"); normalize.
    long_key = next((k for k in _ID_MONTHS if k.startswith(mon)), None)
    if long_key is None:
        return None
    return f"{int(m.group(3)):04d}-{_ID_MONTHS[long_key]:02d}-{day:02d}"


def _parse_id_number(raw: str) -> float | None:
    """Normalize Indonesian formatting: '17.882,00' → 17882.00, '5,75%' → 5.75."""
    s = raw.strip().replace("%", "").strip()
    if not s:
        return None
    # Indonesian: thousands sep '.', decimal ','. Detect by presence of ','.
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    # No comma but multiple dots: likely thousands sep only.
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        f = float(s)
        return None if f != f else f
    except ValueError:
        return None


# Match an Indonesian date cell. Use two separate value patterns:
#   - percent cell (BI-Rate: "5,75%")
#   - IDR-style thousands cell (JISDOR: "17.882,00")
_DATE_CELL = r">\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*<"

_ROW_PERCENT = re.compile(
    _DATE_CELL + r"(?:.*?)" +
    r">\s*(\d+(?:[.,]\d+)?\s*%)\s*<",
    re.DOTALL,
)

# IDR values: permissive — any numeric cell after the date, then filter
# after parsing to drop tiny false positives (row counters, pagination).
_ROW_IDR = re.compile(
    _DATE_CELL + r"(?:.*?)" +
    r">\s*([\d\.,]+)\s*<",
    re.DOTALL,
)
# JISDOR values are always ≥ 1000 IDR/USD — anything below is noise.
_JISDOR_MIN = 1000.0


class BiProvider:
    """Bank Indonesia macro adapter — HTML scraping."""

    name = "bi"
    tier = "primary"
    markets = frozenset({"MACRO"})
    capabilities = frozenset({
        "macro:bi_rate", "macro:jisdor",
        "fx:jisdor_rate",   # ADR-0031 single-value convenience
    })
    requires_api_key = False
    attribution = "Bank Indonesia"

    def __init__(self, http: httpx.AsyncClient | None = None,
                 *, timeout: float = 20.0):
        self._owned = http is None
        self._http = http or httpx.AsyncClient(
            headers=_HEADERS, timeout=timeout, follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owned:
            await self._http.aclose()

    async def _get_html(self, url: str) -> str:
        try:
            r = await self._http.get(url)
        except httpx.TimeoutException as e:
            raise FinanceError(ErrorCode.TIMEOUT, str(e), provider=self.name) from e
        except httpx.HTTPError as e:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE, str(e),
                               provider=self.name) from e
        if r.status_code in (403, 503):
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"BI blocked (HTTP {r.status_code})",
                               provider=self.name)
        if r.status_code >= 400:
            raise FinanceError(ErrorCode.PROVIDER_UNAVAILABLE,
                               f"BI HTTP {r.status_code}", provider=self.name)
        return r.text

    def _parse_series(self, html: str, *, unit: str,
                      pattern: re.Pattern[str],
                      min_value: float | None = None) -> list[MacroObservation]:
        obs: list[MacroObservation] = []
        seen: set[str] = set()
        for m in pattern.finditer(html):
            date = _parse_id_date(m.group(1))
            val = _parse_id_number(m.group(2))
            if date is None or val is None or date in seen:
                continue
            if min_value is not None and val < min_value:
                continue
            seen.add(date)
            obs.append(MacroObservation(period=date, value=val, unit=unit))
        obs.sort(key=lambda o: o.period)
        return obs

    async def macro_indicator(self, indicator: str) -> MacroSeries:
        ind = indicator.lower()
        if ind == "bi_rate":
            return await self._bi_rate()
        if ind in ("jisdor", "fx_usd_idr"):
            return await self._jisdor()
        raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                           f"BI does not serve indicator {indicator!r}",
                           provider=self.name)

    async def _bi_rate(self) -> MacroSeries:
        html = await self._get_html(_BI_RATE_URL)
        obs = self._parse_series(html, unit="%", pattern=_ROW_PERCENT)
        if not obs:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               "BI-Rate table not parseable (page redesign?)",
                               provider=self.name)
        return MacroSeries(
            indicator="bi_rate", source=self.name, unit="%",
            observations=obs, frequency="monthly",
            description="BI 7-Day Reverse Repo Rate (BI-Rate)",
            attribution=self.attribution,
        )

    async def _jisdor(self) -> MacroSeries:
        html = await self._get_html(_JISDOR_URL)
        obs = self._parse_series(html, unit="IDR/USD", pattern=_ROW_IDR,
                                 min_value=_JISDOR_MIN)
        if not obs:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               "JISDOR table not parseable (page redesign?)",
                               provider=self.name)
        return MacroSeries(
            indicator="jisdor", source=self.name, unit="IDR/USD",
            observations=obs, frequency="daily",
            description="Jakarta Interbank Spot Dollar Rate (USD/IDR)",
            attribution=self.attribution,
        )

    async def jisdor_rate(self, date: str | None = None) -> JisdorRate:
        """Single-row JISDOR — latest by default, or on `date` if provided.

        Reuses the same scrape as `_jisdor`; picks the matching observation.
        """
        series = await self._jisdor()
        if not series.observations:
            raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                               "no JISDOR observations parsed",
                               provider=self.name)
        if date is None:
            latest = max(series.observations, key=lambda o: o.date)
            return JisdorRate(date=latest.date, rate=float(latest.value))
        for o in series.observations:
            if o.date == date:
                return JisdorRate(date=o.date, rate=float(o.value))
        raise FinanceError(ErrorCode.DATA_UNAVAILABLE,
                           f"JISDOR has no rate for {date}",
                           provider=self.name)
