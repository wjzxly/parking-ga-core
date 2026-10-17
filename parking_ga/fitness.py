"""适应度函数：把「一个分配方案」量化为可比较的综合得分。

三维评分机制
------------
1. **步行距离得分 (walking)**：许可偏好位置到实际车位的距离，越近越高，
   按曼哈顿距离做指数衰减，并乘以许可自身权重。
2. **类型匹配得分 (category)**：住户优先获得固定/近端车位，访客被引导到
   边缘车位，减少高峰时段的内部拥堵；无障碍与充电需求给予硬约束奖励。
3. **空间利用得分 (usage)**：鼓励方案尽早填满车位、避免出现大面积空洞，
   同时惩罚把访客车停进核心区域的行为。

三项得分归一化到 [0, 1] 后按权重加权求和，权重可由调用方调整，
以便在「住户满意度优先」和「整体利用率优先」之间做权衡。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence

from .models import (
    Assignment,
    ParkingSlot,
    Permit,
    PermitCategory,
    Problem,
    manhattan,
)


@dataclass(frozen=True)
class FitnessWeights:
    """三维评分权重。三个值不需要归一，内部会按总和折算。"""

    walking: float = 0.5
    category: float = 0.3
    usage: float = 0.2

    def normalized(self) -> "FitnessWeights":
        total = self.walking + self.category + self.usage
        if total <= 0:
            raise ValueError("权重总和必须为正数")
        return FitnessWeights(
            walking=self.walking / total,
            category=self.category / total,
            usage=self.usage / total,
        )


class FitnessEvaluator:
    """在预处理阶段缓存常量，让内层循环足够快。

    遗传算法会调用这个函数上万次，因此把车位坐标、类型索引等
    一次性算好放进字典，避免在循环里重复查找。
    """

    def __init__(
        self,
        problem: Problem,
        weights: FitnessWeights = FitnessWeights(),
        distance_decay: float = 40.0,
    ) -> None:
        self.problem = problem
        self.weights = weights.normalized()
        self.distance_decay = distance_decay

        self.slots: Sequence[ParkingSlot] = problem.slots
        self.permits: Sequence[Permit] = problem.permits
        self.slot_pos: Dict[str, tuple] = {s.slot_id: (s.x, s.y) for s in self.slots}
        self.slot_obj: Dict[str, ParkingSlot] = {s.slot_id: s for s in self.slots}
        self._cache: Dict[tuple, float] = {}

        # 车位的「边缘度」：距离所有车位中心越远越边缘，用于区分住户/访客档次
        xs = [s.x for s in self.slots]
        ys = [s.y for s in self.slots]
        self.centroid = (sum(xs) / len(xs), sum(ys) / len(ys))
        max_radial = max(manhattan(self.centroid, (s.x, s.y)) for s in self.slots) or 1.0
        self.slot_marginality: Dict[str, float] = {
            s.slot_id: manhattan(self.centroid, (s.x, s.y)) / max_radial for s in self.slots
        }

    # ------------------------------------------------------------------ 子评分

    def _walking_pair_score(self, permit: Permit, slot: ParkingSlot) -> float:
        """单个「许可-车位」的步行友好度，已乘以许可权重。"""
        key = (permit.permit_id, slot.slot_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        dist = manhattan((permit.preferred_x, permit.preferred_y), (slot.x, slot.y))
        base = 1.0 / (1.0 + dist / self.distance_decay)
        score = base * permit.effective_weight
        self._cache[key] = score
        return score

    def _category_pair_score(self, permit: Permit, slot: ParkingSlot) -> float:
        """类型匹配度：住户应靠近中心，访客应被推向边缘。"""
        marginal = self.slot_marginality[slot.slot_id]
        if permit.category is PermitCategory.RESIDENT:
            fit = 1.0 - marginal
        elif permit.category is PermitCategory.VISITOR:
            fit = marginal
        else:  # STAFF
            fit = 1.0 - abs(marginal - 0.5) * 2.0

        # 充电桩 / 无障碍是硬性需求，如果被忽略要显著扣分
        if permit.needs_charger and not slot.has_charger:
            fit -= 0.6
        if permit.needs_accessible and not slot.accessible:
            fit -= 0.6
        return max(0.0, fit) * permit.effective_weight

    # ------------------------------------------------------------------ 主入口

    def score(
        self, assignment: Assignment
    ) -> tuple:
        """返回 (walking, category)，供增量计算复用。"""
        if assignment.slot_id is None:
            return 0.0, 0.0
        permit = self.problem.perm_index[assignment.permit_id]
        slot = self.slot_obj[assignment.slot_id]
        return (
            self._walking_pair_score(permit, slot),
            self._category_pair_score(permit, slot),
        )

    def evaluate(self, assignments: Sequence[Assignment]) -> tuple:
        """计算完整方案的三维得分。

        Returns:
            (walking_score, category_score, usage_score, total_score)
            前两项为「已分配许可的平均分」，第三项为车位填充与分布质量。
        """
        n_assigned = 0
        walking_sum = 0.0
        category_sum = 0.0
        used_slots = set()

        for a in assignments:
            w, c = self.score(a)
            if a.slot_id is not None:
                n_assigned += 1
                used_slots.add(a.slot_id)
            walking_sum += w
            category_sum += c

        denom = n_assigned or 1
        total_weight = sum(p.effective_weight for p in self.permits) or 1.0

        walking_norm = walking_sum / total_weight
        category_norm = category_sum / total_weight

        # 使用率：车位填充比例，避免算法为了省事而少分配
        capacity = len(self.slots)
        fill = n_assigned / capacity if capacity else 0.0
        fill = min(1.0, fill)

        # 核心区占用惩罚：住户未分配而访客占了中心车位时会拉低该项
        core_used_by_visitor = 0
        for a in assignments:
            if a.slot_id is None:
                continue
            permit = self.problem.perm_index[a.permit_id]
            if (
                permit.category is PermitCategory.VISITOR
                and self.slot_marginality[a.slot_id] < 0.35
            ):
                core_used_by_visitor += 1
        penalty = min(1.0, core_used_by_visitor / max(1, n_assigned * 0.2))
        usage_norm = max(0.0, fill * (1.0 - 0.5 * penalty))

        total = (
            self.weights.walking * walking_norm
            + self.weights.category * category_norm
            + self.weights.usage * usage_norm
        )
        return walking_norm, category_norm, usage_norm, total

    def fitness(self, assignments: Sequence[Assignment]) -> float:
        """只取总分，供遗传算法内层调用。"""
        return self.evaluate(assignments)[3]
