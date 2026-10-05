"""Deterministic, offline-first content gap brief generator."""

__version__ = "0.1.0"

from .core import ValidationError, analyze

__all__ = ["ValidationError", "analyze", "__version__"]
