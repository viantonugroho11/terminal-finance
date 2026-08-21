"""The package version must match the distribution version.

These drifted silently through the 0.3.0 release: pyproject said 0.3.0 while
`finance_mcp.__version__` still said 0.2.0. Anything that reports the running
version — provenance payloads, bug reports, the MCP handshake — was wrong.
"""
import pathlib
import re

import finance_mcp

PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"


def _declared_version() -> str:
    for line in PYPROJECT.read_text().splitlines():
        m = re.match(r'^version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    raise AssertionError(f"no version declared in {PYPROJECT}")


def test_package_version_matches_pyproject():
    assert finance_mcp.__version__ == _declared_version()
