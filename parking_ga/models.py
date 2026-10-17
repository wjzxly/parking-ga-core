"""领域模型：车位、停车许可、分配方案。

设计要点
--------
- 车位与许可都用不可变数据结构（dataclass），避免遗传算法在反复复制个体时
  出现意外的共享引用。
- 坐标统一使用「米」为单位的平面直角坐标，方便后续接入真实停车场图纸。
- 所有距离计算都在 :mod:`parking_ga.fitness` 内完成，模型层保持纯数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


class PermitCategory(Enum):
    """许可类型。不同类型对应不同的停车偏好与权重。"""

    RESIDENT = "resident"        # 长期住户，固定车位，权重最高
    VISITOR = "visitor"          # 临时访客，允许短时停放，权重最低
    STAFF = "staff"              # 商户/员工，通勤时段使用


@dataclass(frozen=True)
class ParkingSlot:
    """一个物理车位。

    Attributes:
        slot_id: 车位编号，必须全局唯一。
        x: 车位中心点的 x 坐标（米）。
        y: 车位中心点的 y 坐标（米）。
        floor: 所在楼层，0 表示地面层。
        has_charger: 是否配备充电桩（新能源车优先）。
        accessible: 是否为无障碍车位。
    """

    slot_id: str
    x: float
    y: float
    floor: int = 0
    has_charger: bool = False
    accessible: bool = False


@dataclass(frozen=True, kw_only=True)
class Permit:
    """一条停车许可申请。

    使用 ``kw_only`` 是为了让子类能安全地改写 ``category`` 的默认值，
    同时避免「位置参数顺序」在不同子类间产生歧义。

    Attributes:
        permit_id: 许可编号，必须全局唯一。
        category: 许可类型。
        preferred_x / preferred_y: 申请人希望靠近的位置（如自家楼栋入户门）。
        needs_charger: 是否为新能源车，需要充电桩。
        needs_accessible: 是否需要无障碍车位。
        weight: 该许可在整体满意度中的权重，默认按类型给出。
    """

    permit_id: str
    category: PermitCategory
    preferred_x: float = 0.0
    preferred_y: float = 0.0
    needs_charger: bool = False
    needs_accessible: bool = False
    weight: Optional[float] = None

    @property
    def effective_weight(self) -> float:
        """未显式指定权重时，按许可类型取默认值。"""
        if self.weight is not None:
            return self.weight
        return _DEFAULT_WEIGHTS[self.category]


_DEFAULT_WEIGHTS: Dict[PermitCategory, float] = {
    PermitCategory.RESIDENT: 1.0,
    PermitCategory.STAFF: 0.6,
    PermitCategory.VISITOR: 0.3,
}


@dataclass(frozen=True)
class ResidentPermit(Permit):
    """住户许可的便捷构造器，默认类型为 RESIDENT。

    用法：``ResidentPermit(permit_id="P01", preferred_x=3, preferred_y=2)``
    """

    category: PermitCategory = field(default=PermitCategory.RESIDENT, init=False)


@dataclass(frozen=True)
class VisitorPermit(Permit):
    """访客许可的便捷构造器，默认类型为 VISITOR。"""

    category: PermitCategory = field(default=PermitCategory.VISITOR, init=False)


@dataclass
class Problem:
    """一个完整的分配问题实例。

    Attributes:
        slots: 全部可用车位。
        permits: 全部待分配的许可。
    """

    slots: Sequence[ParkingSlot]
    permits: Sequence[Permit]

    def __post_init__(self) -> None:
        if not self.slots:
            raise ValueError("至少需要一个车位")
        if not self.permits:
            raise ValueError("至少需要一个许可")
        slot_ids = [s.slot_id for s in self.slots]
        if len(set(slot_ids)) != len(slot_ids):
            raise ValueError("车位编号存在重复")
        permit_ids = [p.permit_id for p in self.permits]
        if len(set(permit_ids)) != len(permit_ids):
            raise ValueError("许可编号存在重复")

    @property
    def slot_index(self) -> Dict[str, ParkingSlot]:
        return {s.slot_id: s for s in self.slots}

    @property
    def perm_index(self) -> Dict[str, Permit]:
        return {p.permit_id: p for p in self.permits}


@dataclass(frozen=True)
class Assignment:
    """一条「许可 -> 车位」的映射。slot_id 为 None 表示未分配。"""

    permit_id: str
    slot_id: Optional[str]


@dataclass
class Solution:
    """算法输出的完整方案，附带可解释的评分明细。"""

    assignments: List[Assignment]
    walking_score: float = 0.0
    category_score: float = 0.0
    usage_score: float = 0.0
    total_score: float = 0.0
    unassigned: int = 0
    generation: int = 0

    def as_dict(self) -> Dict[str, object]:
        """转为可直接 JSON 序列化的字典，便于 Web 层复用。"""
        return {
            "assignments": [
                {"permit_id": a.permit_id, "slot_id": a.slot_id} for a in self.assignments
            ],
            "scores": {
                "walking": round(self.walking_score, 4),
                "category": round(self.category_score, 4),
                "usage": round(self.usage_score, 4),
                "total": round(self.total_score, 4),
            },
            "unassigned": self.unassigned,
            "generation": self.generation,
        }

    @property
    def utilization(self) -> float:
        """已分配许可占比，反映方案覆盖面。"""
        if not self.assignments:
            return 0.0
        assigned = sum(1 for a in self.assignments if a.slot_id is not None)
        return assigned / len(self.assignments)


def manhattan(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """曼哈顿距离。地下车库多为规则柱网，曼哈顿距离比欧氏距离更贴近实际步行路径。"""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def euclidean(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """欧氏距离，作为备选度量。"""
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5
