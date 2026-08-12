"""Shim mcp.server.fastmcp for offline / older-Python test envs.

Production always uses the real `mcp` package; this shim only kicks in when
the module cannot be imported (e.g. Python 3.9). It preserves the public
surface that server.py touches: FastMCP() with .tool decorator, .settings,
and .run().
"""
import sys
import types


try:
    import mcp.server.fastmcp  # noqa: F401
except Exception:
    _mcp = types.ModuleType("mcp")
    _server = types.ModuleType("mcp.server")
    _fast = types.ModuleType("mcp.server.fastmcp")

    class _Settings:
        host = "0.0.0.0"
        port = 7800

    class FastMCP:
        def __init__(self, name: str):
            self.name = name
            self.settings = _Settings()
            self.tools = {}

        def tool(self, *dargs, **dkwargs):
            def _wrap(fn):
                self.tools[fn.__name__] = fn
                return fn
            return _wrap

        def run(self, *a, **kw):  # not exercised in tests
            raise RuntimeError("shim FastMCP cannot run; install the real 'mcp' package")

    _fast.FastMCP = FastMCP
    _server.fastmcp = _fast
    _mcp.server = _server
    sys.modules["mcp"] = _mcp
    sys.modules["mcp.server"] = _server
    sys.modules["mcp.server.fastmcp"] = _fast
