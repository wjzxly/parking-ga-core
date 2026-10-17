"""parking_ga —— 停车场车位分配遗传算法求解器。

纯 Python 实现，不依赖 numpy / Django，可独立作为库使用。
"""

from .models import (
    PermitCategory,
    Permit,
    ResidentPermit,
    VisitorPermit,
    ParkingSlot,
    Assignment,
    Solution,
)
from .fitness import FitnessEvaluator, FitnessWeights
from .ga import GeneticAlgorithm, GAConfig

__version__ = "1.0.0"

__all__ = [
    "PermitCategory",
    "Permit",
    "ResidentPermit",
    "VisitorPermit",
    "ParkingSlot",
    "Assignment",
    "Solution",
    "FitnessEvaluator",
    "FitnessWeights",
    "GeneticAlgorithm",
    "GAConfig",
]
