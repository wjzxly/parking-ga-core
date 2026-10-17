"""命令行入口：求解一个模拟车库，并打印方案与收敛曲线。

用法::

    python -m parking_ga.cli --generations 20 --population 50
    python -m parking_ga.cli --json out.json
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
from typing import List

from .datasets import build_demo_problem
from .fitness import FitnessWeights
from .ga import GAConfig, GeneticAlgorithm
from .models import PermitCategory


def _sparkline(values: List[float], width: int = 40) -> str:
    """用字符画一条收敛曲线，无需 matplotlib。"""
    if not values:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = max(1, len(values) // width)
    sampled = values[::step][:width]
    return "".join(blocks[min(7, int((v - lo) / span * 7.999))] for v in sampled)


def _ensure_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，中文与方块字符会乱码。

    这里在启动时把标准输出重挂到 UTF-8，避免用户还要手动设置
    ``PYTHONIOENCODING``；已经支持 UTF-8 的环境则原样跳过。
    注意 Python 3.7+ 保留了 ``.buffer`` 属性，因此重挂后
    ``print`` 仍然走同一个底层句柄，不会出现输出丢失。
    """
    stream = sys.stdout
    encoding = (getattr(stream, "encoding", "") or "").lower()
    if encoding.replace("-", "") == "utf8":
        return
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return
    sys.stdout = io.TextIOWrapper(buffer, encoding="utf-8", errors="replace", line_buffering=True)


def _utf8_open(path: str, mode: str = "w"):
    """统一按 UTF-8 打开文件，无 BOM，跨平台行为一致。"""
    return open(path, mode, encoding="utf-8", newline="\n")


def main(argv: List[str] | None = None) -> int:
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="停车场车位分配遗传算法求解器")
    parser.add_argument("--rows", type=int, default=4, help="车位行数")
    parser.add_argument("--cols", type=int, default=8, help="每行车位数")
    parser.add_argument("--generations", type=int, default=20, help="进化代数")
    parser.add_argument("--population", type=int, default=50, help="种群规模")
    parser.add_argument("--seed", type=int, default=42, help="随机种子，保证结果可复现")
    parser.add_argument("--json", type=str, default=None, help="把结果写入 JSON 文件")
    args = parser.parse_args(argv)

    problem = build_demo_problem(rows=args.rows, cols=args.cols)
    config = GAConfig(
        population_size=args.population,
        generations=args.generations,
        seed=args.seed,
    )

    print(f"车位 {len(problem.slots)} 个 / 许可 {len(problem.permits)} 条")
    print(f"种群 {config.population_size} / 代数 {config.generations} / 种子 {config.seed}")

    t0 = time.perf_counter()
    ga = GeneticAlgorithm(problem, config, FitnessWeights())
    baseline = ga.random_baseline()
    solution = ga.run()
    elapsed = time.perf_counter() - t0

    print(f"\n随机基线得分 : {baseline:.4f}")
    print(f"GA  求解得分 : {solution.total_score:.4f}")
    if baseline:
        print(f"相对提升     : {(solution.total_score / baseline - 1) * 100:.1f}%")
    print(f"三维明细     : 步行 {solution.walking_score:.3f} | 类型 {solution.category_score:.3f} | 利用 {solution.usage_score:.3f}")
    print(f"未分配许可   : {solution.unassigned} 条")
    print(f"耗时         : {elapsed * 1000:.0f} ms")
    print(f"收敛曲线     : {_sparkline(ga.history)}")

    print("\n方案明细（前 10 条）：")
    perm_index = problem.perm_index
    slot_index = problem.slot_index
    for a in solution.assignments[:10]:
        permit = perm_index[a.permit_id]
        slot = slot_index[a.slot_id] if a.slot_id else None
        cat = {PermitCategory.RESIDENT: "住户", PermitCategory.STAFF: "员工", PermitCategory.VISITOR: "访客"}[permit.category]
        where = (
            f"{slot.slot_id} @({slot.x:.1f},{slot.y:.1f})" if slot else "未分配"
        )
        print(f"  {a.permit_id} [{cat}] -> {where}")

    if args.json:
        with _utf8_open(args.json) as fh:
            json.dump(
                {
                    "summary": {
                        "slots": len(problem.slots),
                        "permits": len(problem.permits),
                        "baseline": round(baseline, 4),
                        "elapsed_ms": round(elapsed * 1000, 1),
                    },
                    "history": [round(h, 4) for h in ga.history],
                    "solution": solution.as_dict(),
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
        print(f"\n结果已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
