"""CMP-08 Rules engine: deterministic evaluation of a rule version against typed
inputs. Pure Python. Imports nothing from Django or the apps (doc 04 §4).
"""

from .definition import MODULES, unapproved, validate
from .engine import evaluate, evaluator
from .operators import FAIL, OPERATORS, PASS, UNKNOWN

__all__ = [
    "FAIL", "MODULES", "OPERATORS", "PASS", "UNKNOWN", "evaluate", "evaluator", "unapproved",
    "validate",
]  # fmt: skip
