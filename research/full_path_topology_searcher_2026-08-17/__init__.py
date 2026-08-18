"""Development-only full-path topology searcher.

This package builds structural evidence and bounded branch candidates.  It is
not a promotion lane and it never treats margin-only movement as efficacy.
"""

from .evaluator import evaluate_pairs
from .model import BranchSpec, ConditionalOutcomeValue, StateSignature

__all__ = ["BranchSpec", "ConditionalOutcomeValue", "StateSignature", "evaluate_pairs"]

