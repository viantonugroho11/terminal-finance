"""Broker-flow history — ADR-0026 follow-up.

ADR-0026 shipped `broker_flow_agg(symbol, days=5)`, but the upstream endpoint
answers for the latest session only, so the tool always returned one day while
its signature promised several. This package accumulates a daily snapshot so
the promise can be kept.
"""
from . import db, service, store  # noqa: F401
