# Runbooks

Procedures for ops + development tasks. Each runbook is self-contained. When to use each:

- [Refresh IDX ticker allowlist](#refresh-idx-ticker-allowlist) — new IDX listings appear
- [Add a new provider](#add-a-new-provider) — wrap a new upstream
- [Add a new capability + tool](#add-a-new-capability--tool) — expose a new field/endpoint
- [Debug a provider failure](#debug-a-provider-failure) — tool returns error unexpectedly
- [Tune router preferences](#tune-router-preferences) — reorder fallback chains
- [Rotate credentials](#rotate-credentials) — new BPS key, new SEC UA, new OJK snapshot
- [Cut a release](#cut-a-release) — version bump + tag + GitHub release
- [Recover from a bad deploy](#recover-from-a-bad-deploy) — roll back

## Refresh IDX ticker allowlist

**When:** new IDX listings visible in the wild (IPO, ticker rename); routing warnings mention "resolver fell through to US" for a symbol the user expects to be IDX.

**Prereq:** SSH into a host that can reach `https://www.idx.co.id`.

**Steps:**

```bash
cd terminal-finance
# Dry-run first — verifies the endpoint is reachable and returns sensible data.
python scripts/refresh_idx_tickers.py --dry-run | head -30

# If output looks correct, write in place:
python scripts/refresh_idx_tickers.py

# Review the diff.
git diff finance-mcp/finance_mcp/data/idx_tickers.txt

# Commit.
git add finance-mcp/finance_mcp/data/idx_tickers.txt
git commit -m "chore(data): refresh IDX allowlist"
git push origin main
```

**Rollback:** `git revert <sha>`. Router uses whatever ships in the file; a bad list only affects unsuffixed IDX resolution — users can still force with `.JK`.

**Failure modes:** Cloudflare 403 → script exits with error. Wait or run from a different network. Never commit a partial list.

## Add a new provider

**When:** wrapping a new upstream (Polygon, Alpha Vantage, CoinGecko, …).

**Steps:**

1. **Create the adapter.**
   ```bash
   touch finance-mcp/finance_mcp/providers/<name>.py
   ```
   Skeleton:
   ```python
   from __future__ import annotations
   import httpx
   from ..errors import FinanceError, ErrorCode
   from ..models import Quote  # + whatever normalized types you return


   class MyProvider:
       name = "myprovider"
       tier = "aggregator"          # primary | aggregator | scraped | mock
       markets = frozenset({"US"})
       capabilities = frozenset({"quote", "history"})
       requires_api_key = True
       attribution = "MyProvider Inc."

       def __init__(self, http: httpx.AsyncClient | None = None, api_key: str | None = None):
           # ...
           pass

       async def quote(self, symbol: str) -> Quote:
           # ... hit endpoint, raise FinanceError on failure, return Quote ...
           pass
   ```

2. **Register in `registry.py`:**
   ```python
   from .providers.myprovider import MyProvider
   # inside build_router():
   if os.getenv("FINANCE_MYPROVIDER", "on").lower() != "off":
       r.register(MyProvider())
   ```

3. **Preference in `config/finance.routing.yaml`:**
   ```yaml
   quote:
     US: [myprovider, yahoo]      # primary → fallback
   ```

4. **Mock stub** (so `FINANCE_PROVIDER=mock` still covers the tools):
   Add the new capability to `MockProvider.capabilities` and implement the method.

5. **Tests** — one file `tests/test_myprovider.py` using `httpx.MockTransport`. Cover: happy path, `SYMBOL_NOT_FOUND`, `AUTHENTICATION_FAILED`, `RATE_LIMITED`, timeout mapping, capability declarations.

6. **Env vars** — document in `.env.example` and `README.md § Configuration`.

7. **Docker** — add pass-through in `docker/docker-compose.yml`:
   ```yaml
   FINANCE_MYPROVIDER: ${FINANCE_MYPROVIDER:-on}
   FINANCE_MYPROVIDER_API_KEY: ${FINANCE_MYPROVIDER_API_KEY:-}
   ```

8. **ADR** — if it changes the routing story materially, extend ADR-0008; otherwise a `providers/README.md` note is enough.

9. **Run the suite:** `.venv/bin/python -m pytest -q` — must stay green.

10. **Commit** per the small-atomic pattern:
    - `feat(providers): <name> provider`
    - `test: cover <name> provider`
    - `chore(deploy): env + docker pass-through for <name>`

## Add a new capability + tool

**When:** exposing a new field or endpoint (e.g. `insider_transactions`, `analyst_ratings`).

**Steps:**

1. **Capability constant** — `finance_mcp/providers/__init__.py`:
   ```python
   CAP_INSIDER = "insider_transactions"
   ```

2. **Model** — `finance_mcp/models.py`:
   ```python
   @dataclass
   class InsiderTransaction:
       date: str
       insider: str
       kind: str          # buy | sell | option_exercise
       shares: int
       value: float | None
   ```

3. **Provider method** — add to each provider that can serve it, and to `MockProvider`. Ensure `capabilities` frozenset includes the constant.

4. **Router preference** — `finance_mcp/router.py::_DEFAULT_PREFERENCE` **and** `config/finance.routing.yaml`. Keep both in sync.

5. **TTL** — `finance_mcp/cache.py`:
   ```python
   TTL_INSIDER = _ttl("FINANCE_CACHE_TTL_INSIDER", 3600)
   ```

6. **Tool** — `finance_mcp/server.py`:
   ```python
   @mcp.tool()
   async def get_insider_transactions(symbol: str) -> dict:
       """Insider Form 4 transactions."""
       return await _do("get_insider_transactions", "insider_transactions",
                        (symbol.upper(),), _c.TTL_INSIDER,
                        lambda p: p.insider_transactions(symbol), symbol=symbol)
   ```

7. **Hermes whitelist** — `config/hermes.config.yaml`:
   ```yaml
   tools:
     include:
       - get_insider_transactions
   ```

8. **API doc** — add an entry to `docs/API.md`.

9. **Skill hint** — if a specialist skill should now surface it, add to the skill's `requires_tools` + Procedure section.

10. **Test** — one e2e via mock, plus unit tests for each real-provider method.

## Debug a provider failure

**Symptom:** a tool returns `{"error": {...}}` unexpectedly.

**Steps:**

1. **Read the error code + provider fields:**
   ```json
   {"error": {"code": "PROVIDER_UNAVAILABLE", "provider": "idx", "symbol": "BBCA", ...}}
   ```
   Code + provider narrows the fault.

2. **Check registry:**
   ```bash
   curl http://localhost:7800/mcp -d '{"tool": "cache_stats"}' | jq .
   ```
   Look at `providers[]` for tiers + markets, `routing_config` for the loaded YAML path, `routing_warnings` for misconfig.

3. **Check env:**
   ```bash
   docker exec finance-mcp env | grep FINANCE_
   ```
   Look for missing `FINANCE_BPS_API_KEY`, `FINANCE_SEC_USER_AGENT`, `FINANCE_OJK_SPI_PATH`.

4. **Reach the upstream from inside the container:**
   ```bash
   docker exec finance-mcp curl -sSI -A "Mozilla/5.0" https://www.idx.co.id/primary/TradingSummary/GetStockSummary
   ```
   `HTTP/2 200` → adapter bug (field parsing). `403/503` → Cloudflare; router will fall back.

5. **Live-tail logs:**
   ```bash
   docker logs -f finance-mcp | grep '"error":'
   ```

6. **Reproduce locally:**
   ```bash
   FINANCE_PROVIDER=mock .venv/bin/python -m pytest tests/test_<provider>.py -v
   ```
   All-green under mock → real-upstream problem. Failing under mock → adapter bug.

7. **Escalation:** if IDX Cloudflare rejection rate is > 20% sustained, swap the httpx transport for `curl_cffi` per the docstring in `providers/idx.py`. Contract stable; only the transport changes.

## Tune router preferences

**When:** deployment-specific ranking (e.g. an org has a paid Polygon plan, wants Polygon primary over Yahoo for US quotes).

**Steps:**

1. Edit `config/finance.routing.yaml` on the host.
2. Restart finance-mcp container: `docker compose restart finance-mcp` (config is read at startup).
3. Verify via `cache_stats`: `routing_config` should show the file path; `routing_warnings` should be empty.

**No code change. No rebuild.**

**Rollback:** revert the YAML edit, restart. Built-in `_DEFAULT_PREFERENCE` is the safety net if the YAML fails to parse.

## Rotate credentials

**BPS key:** register a new key at https://webapi.bps.go.id/developer, update `.env`, `docker compose up -d`.

**SEC UA:** update `FINANCE_SEC_USER_AGENT` in `.env` — SEC policy allows any identifying string; typical format `"Company Name contact@example.com"`.

**OJK snapshot:** re-run the operator's snapshot-mirror job, overwrite the file at `FINANCE_OJK_SPI_PATH`. No restart needed — adapter reads on every call.

## Cut a release

1. Bump version:
   ```bash
   # in finance-mcp/pyproject.toml → version = "X.Y.Z"
   # in finance-mcp/finance_mcp/__init__.py → __version__ = "X.Y.Z"
   ```

2. Add CHANGELOG entry describing user-visible changes, ADR deltas, tests delta, known limitations.

3. Commit:
   ```bash
   git add finance-mcp/pyproject.toml finance-mcp/finance_mcp/__init__.py CHANGELOG.md README.md
   git commit -m "docs(release): vX.Y.Z — ..."
   git push origin main
   ```

4. Tag + release:
   ```bash
   # Draft release notes in /tmp/release_notes.md (or copy from CHANGELOG).
   git tag -a vX.Y.Z -F /tmp/release_notes.md
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z — <headline>" --notes-file /tmp/release_notes.md
   ```

5. Verify: `gh release view vX.Y.Z` — link goes to the tag on GitHub.

## Recover from a bad deploy

**Symptom:** `finance-mcp` container crash-loops after a `docker compose up -d`.

**Steps:**

1. **Roll back the image:**
   ```bash
   cd terminal-finance
   git log --oneline -5
   git checkout <last-known-good-sha>
   cd docker
   docker compose up -d --build finance-mcp
   ```

2. **Rescue mode** — run mock provider only, so the tool surface stays live while you diagnose:
   ```bash
   FINANCE_PROVIDER=mock docker compose up -d finance-mcp
   ```
   Every tool returns deterministic mock data. Skills degrade to "n/a" for missing capabilities but Hermes stays responsive.

3. **Once fixed, forward-roll:**
   ```bash
   git checkout main
   git pull
   docker compose up -d --build finance-mcp
   ```

4. **Verify:** `curl http://localhost:7800/mcp` should not 500. `cache_stats` should return the expected provider list.
