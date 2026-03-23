from importlib.metadata import version

from .engine import (
    ApplyResult,
    Decision,
    Engine,
    State,
    compile_transcript,
    create_engine,
    get_policy_items,
    get_premise_value,
)

__version__ = version("context-compiler")

__all__ = [
    "ApplyResult",
    "Decision",
    "Engine",
    "State",
    "compile_transcript",
    "create_engine",
    "get_premise_value",
    "get_policy_items",
]
