"""Compatibility shim for heuristic preprocessing module name.

Prefer importing from ``experimental.preprocessor.heuristic_preprocessor``.
This module is kept to avoid breaking older imports.
"""

from .heuristic_preprocessor import *  # noqa: F403
