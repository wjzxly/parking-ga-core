"""可复现的示例数据生成器。

在没有真实停车场图纸的情况下，用网格 + 高斯聚集的方式模拟一个
「住宅 + 商业混合」的地下车库，方便压测算法和写基准测试。
"""

from __future__ import annotations

import random
from typing import List, Tuple

from .models import ParkingSlot, Permit, PermitCategory, Problem


def generate_garage(
    rows: int = 4,
    cols: int = 8,
    slot_width: float = 2.5,
    row_spacing: float = 6.0,
) -> List[ParkingSlot]:
    """生成规则柱网的地下车位，坐标单位为米。"""
    slots: List[ParkingSlot] = []
    idx = 0
    for r in range(rows):
        for c in range(cols):
            idx += 1
            slots.append(
                ParkingSlot(
                    slot_id=f"A{idx:03d}",
                    x=c * slot_width,
                    y=r * row_spacing,
                    floor=0,
                    has_charger=(idx % 7 == 0),
                    accessible=(idx % 11 == 0),
                )
            )
    return slots


def generate_permits(
    n_resident: int = 18,
    n_staff: int = 4,
    n_visitor: int = 3,
    seed: int = 42,
) -> List[Permit]:
    """在车库范围内按簇生成许可申请，模拟楼栋入口与商铺位置。"""
    rng = random.Random(seed)
    # 三个需求热点：左上（1 号楼）、中下（2 号楼）、右上（商业区）
    hotspots: List[Tuple[float, float]] = [(3.0, 2.0), (10.0, 17.0), (17.0, 3.0)]
    permits: List[Permit] = []
    counter = 0

    def make(category: PermitCategory, spread: float) -> Permit:
        nonlocal counter
        counter += 1
        hx, hy = rng.choice(hotspots)
        return Permit(
            permit_id=f"P{counter:03d}",
            category=category,
            preferred_x=max(0.0, rng.gauss(hx, spread)),
            preferred_y=max(0.0, min(18.0, rng.gauss(hy, spread))),
            needs_charger=(rng.random() < 0.25),
            needs_accessible=(rng.random() < 0.08),
        )

    for _ in range(n_resident):
        permits.append(make(PermitCategory.RESIDENT, 4.0))
    for _ in range(n_staff):
        permits.append(make(PermitCategory.STAFF, 6.0))
    for _ in range(n_visitor):
        permits.append(make(PermitCategory.VISITOR, 8.0))
    return permits


def build_demo_problem(
    rows: int = 4,
    cols: int = 8,
    n_resident: int = 18,
    n_staff: int = 4,
    n_visitor: int = 3,
    seed: int = 42,
) -> Problem:
    """一行代码拿到可直接求解的演示问题实例。"""
    return Problem(
        slots=generate_garage(rows=rows, cols=cols),
        permits=generate_permits(
            n_resident=n_resident, n_staff=n_staff, n_visitor=n_visitor, seed=seed
        ),
    )
