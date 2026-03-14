from importlib.metadata import version

from .engine import Decision, Engine, State, create_engine

__version__ = version("context-compiler")

__all__ = ["Decision", "Engine", "State", "create_engine"]
