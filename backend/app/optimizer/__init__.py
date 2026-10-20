"""Constraint-aware itinerary optimizer (pure Python, no DB access)."""

from .domain import (
    Candidate,
    DayPlan,
    Issue,
    OptimizationResult,
    Point,
    ProblemSpec,
    TravelMatrix,
)
from .pipeline import optimize

__all__ = [
    "Candidate",
    "DayPlan",
    "Issue",
    "OptimizationResult",
    "Point",
    "ProblemSpec",
    "TravelMatrix",
    "optimize",
]
