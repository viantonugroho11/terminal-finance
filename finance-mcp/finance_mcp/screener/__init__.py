"""Conversational screener — ADR-0025.

Screens a stored daily snapshot rather than the live providers: filtering 435
IDX tickers per question would be 435 upstream calls for one answer.
"""
from . import db, fields, service, store  # noqa: F401
