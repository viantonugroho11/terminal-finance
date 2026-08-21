"""Watch engine — ADR-0023.

Rule store + evaluator + delivery. Reuses portfolio.db connection.
"""
from . import db, evaluator, metrics, rules, store  # noqa: F401
