# Contributing

Developer onboarding and PR flow. See [ARCHITECTURE](ARCHITECTURE.md) for design intent, [RUNBOOKS](RUNBOOKS.md) for common tasks.

## Environment setup

**Requirements:**
- Python ≥ 3.11 for production. Tests also pass on 3.9 via the FastMCP shim (`finance_mcp/__init__.py`).
- Docker + Docker Compose for the full Hermes + finance-mcp stack.
- `gh` CLI for release cutting.

**Local dev:**

```bash
git clone git@github.com:viantonugroho11/terminal-finance.git
cd terminal-finance/finance-mcp

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"    # or: pip install -e . && pip install pytest httpx pyyaml

.venv/bin/python -m pytest -q   # should print "211 passed"
```

**Full stack (Hermes + finance-mcp in Docker):**

```bash
cd terminal-finance
cp .env.example .env
# edit .env: FINANCE_BPS_API_KEY, FINANCE_SEC_USER_AGENT if you want live macro/SEC
./scripts/bootstrap.sh
docker exec -it hermes hermes chat
> analisis BBCA
```

## Repo layout

```
terminal-finance/
├── config/
│   ├── hermes.config.yaml          # MCP tool whitelist for Hermes
│   ├── finance.routing.yaml        # Router preference table (ADR-0012)
│   └── SOUL.md                     # Hermes finance persona
├── docker/
│   └── docker-compose.yml
├── docs/
│   ├── ARCHITECTURE.md · API.md · PROVIDERS.md · RUNBOOKS.md · CONTRIBUTING.md
│   ├── report-format-template.md   # ADR-0019 canonical template
│   └── adr/                        # 23 ADRs + supporting docs
├── finance-mcp/                    # Python MCP sidecar
│   ├── finance_mcp/
│   │   ├── server.py               # @mcp.tool decorators; _do orchestrator
│   │   ├── registry.py             # Router singleton
│   │   ├── router.py               # capability + market routing
│   │   ├── resolver.py             # symbol → market classifier
│   │   ├── cache.py · retry.py · errors.py · models.py · schema.py
│   │   ├── technical.py · calc.py · valuation.py · evaluator.py · subagents.py
│   │   ├── providers/              # yahoo · idx · bi · bps · ojk · sec · mock
│   │   ├── portfolio/              # SQLite portfolio state
│   │   └── data/idx_tickers.txt    # IDX allowlist for resolver
│   └── tests/                      # 211 tests
├── finance-skills/                 # 12 Hermes skills
│   ├── stock-analysis · market-overview · portfolio-analysis · crypto-analysis · risk-analysis
│   ├── fundamental-analysis · technical-analysis · valuation-analysis
│   ├── catalyst-analysis · peer-analysis · macro-context · equity-research
├── scripts/
│   ├── bootstrap.sh
│   └── refresh_idx_tickers.py
├── .env.example
├── CHANGELOG.md
└── README.md
```

## Running tests

```bash
cd finance-mcp

# All 211 tests
.venv/bin/python -m pytest -q

# One file
.venv/bin/python -m pytest tests/test_router.py -v

# One test, with prints visible
.venv/bin/python -m pytest tests/test_valuation.py::test_dcf_end_to_end -v -s

# Coverage (add coverage.py if you want a run)
.venv/bin/pip install pytest-cov
.venv/bin/python -m pytest --cov=finance_mcp --cov-report=term-missing
```

Every test uses `FINANCE_PROVIDER=mock` or `httpx.MockTransport` — no network. Failing to add mocked HTTP for a new provider will make CI flaky.

## Writing a new test

**Provider tests** — mock HTTP:
```python
import httpx, asyncio
from finance_mcp.providers.myprovider import MyProvider

def test_quote_parses():
    def handler(req):
        return httpx.Response(200, json={"data": {...}})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                               base_url="https://api.example.com")
    p = MyProvider(http=client)
    q = asyncio.run(p.quote("AAPL"))
    assert q.symbol == "AAPL"
```

**End-to-end via mock provider:**
```python
import os, tempfile
os.environ["FINANCE_PROVIDER"] = "mock"
os.environ.setdefault("FINANCE_DB", tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)

from finance_mcp import server
import asyncio

def test_my_new_tool():
    r = asyncio.run(server.my_new_tool("NVDA"))
    assert "error" not in r
```

Use `setdefault` for `FINANCE_DB` — collision with existing test files' tempfiles breaks portfolio tests.

## Code style

- **No premature abstraction.** Concrete first; abstract when a second real caller exists.
- **No comments explaining WHAT the code does.** Names carry that. Comment only WHY (non-obvious constraints, workarounds, invariants).
- **Never return a fake default on error.** Raise `FinanceError` with a stable code; the router / skill decides how to react.
- **Never call an LLM from `finance_mcp/`.** All math + selection is deterministic. LLM lives one layer up in the skill.
- **Normalize provider output at the provider boundary.** Skills should never see provider-shaped dicts.
- **Every skill line that cites a number must be traceable to a tool result this turn.** Skills enforce this in their Verification section.

## PR flow

1. Branch from `main`. Small, atomic commits (see recent history — one logical change per commit).
2. Run the suite: `.venv/bin/python -m pytest -q` — must stay green.
3. If touching a provider, add / update its test module.
4. If touching a tool, update `docs/API.md`.
5. If introducing a new ADR-worthy decision, add `docs/adr/00NN-<slug>.md` using `docs/adr/0000-template.md`.
6. Push branch, open PR with:
   - What changed
   - Why (link ADR if relevant)
   - Test coverage delta
   - Known limitations
7. Request review; address inline comments; merge to `main` (squash or fast-forward per repo policy).
8. If it's user-visible, add a CHANGELOG entry (unreleased section — batch into next release).

## Common gotchas

- **Python 3.9 test env:** `asyncio.Semaphore()` needs a running loop. Lazy-init inside the async fn, not at module import. See `finance_mcp/subagents.py::SubagentRuntime.fan_out` for the pattern.
- **Test file collision on `FINANCE_DB`:** always `os.environ.setdefault(...)`, never unconditional set.
- **Router chain hits the wrong provider:** check `provider.markets` frozenset uses venue codes (`IDX`), not country codes (`ID`) — resolver emits `market="IDX"`.
- **Cache key collision across markets:** `_do()` includes the resolved market bucket in the key. Do not build cache keys yourself; use `_do()`.
- **New capability doesn't appear to Hermes:** it must be in `config/hermes.config.yaml`'s `tools.include` list. Hermes has a whitelist for tool selection reliability.

## Where to ask for what

- Adding a provider / capability → [RUNBOOKS](RUNBOOKS.md)
- Design intent / why a component exists → [ARCHITECTURE](ARCHITECTURE.md) + linked ADR
- Tool reference → [API](API.md)
- Provider-specific quirks → [PROVIDERS](PROVIDERS.md)
- Skill authoring → existing `finance-skills/*/SKILL.md` as templates
- Release process → [RUNBOOKS § Cut a release](RUNBOOKS.md#cut-a-release)

## What NOT to do

- Do NOT rebuild Hermes. If Hermes has a feature (memory, cron, subagents), use it — don't parallel-implement.
- Do NOT bypass the router in new tools. `_do()` orchestrates for a reason.
- Do NOT put quantitative math inside a skill. Skills describe procedure; `finance_mcp/` owns math.
- Do NOT commit `.env`. `.gitignore` excludes it but double-check on staging.
- Do NOT vendor third-party MCPs (saham-mcp, IDX-API, idx-bei). Reimplement the endpoints in-tree so error mapping / provenance / cache stay ours. See [ADR-0020](adr/0020-indonesian-market-data-providers.md).
