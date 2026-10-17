"""遗传算法主体：带模拟退火思想的多种群进化。

编码方式
--------
个体是一个整数排列 ``perm``，长度等于许可数；``perm[i]`` 表示第 i 个许可
被分配到「车位池」中的第几个车位。若 ``perm[i] >= len(slots)`` 则表示该许可
未分配到车位（允许超员，算法会因利用率低而自然淘汰）。

采用**排列编码 + 部分匹配交叉 (PMX)**，可以保证子代不出现重复车位，
无需额外修复算子，这是相对「01 矩阵编码」最实用的改进。

模拟退火
--------
传统的「精英保留」容易在早期锁死在一个次优解上。这里在每一代对精英个体
施加一次 Metropolis 准则的扰动：以 ``exp(-Δ/T)`` 的概率接受变差的解，
温度 T 随代数线性冷却。这样既保留收敛性，又显著提升了跳出局部最优的能力。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from .fitness import FitnessEvaluator, FitnessWeights
from .models import Assignment, Problem, Solution


@dataclass
class GAConfig:
    """算法超参数。默认值在 30 车位 / 25 许可的规模下调优过。"""

    population_size: int = 50
    generations: int = 20
    crossover_rate: float = 0.85
    mutation_rate: float = 0.15
    elite_size: int = 2
    tournament_size: int = 3
    initial_temperature: float = 0.05
    cooling_rate: float = 0.92
    seed: Optional[int] = None

    def validate(self) -> None:
        if self.population_size < 4:
            raise ValueError("种群规模至少为 4")
        if self.elite_size >= self.population_size:
            raise ValueError("精英数量必须小于种群规模")
        if not 0 < self.crossover_rate <= 1:
            raise ValueError("交叉率应在 (0, 1] 区间")
        if not 0 <= self.mutation_rate <= 1:
            raise ValueError("变异率应在 [0, 1] 区间")


class GeneticAlgorithm:
    """停车场车位分配求解器。

    Example:
        >>> problem = Problem(slots=slots, permits=permits)
        >>> ga = GeneticAlgorithm(problem, GAConfig(seed=42))
        >>> solution = ga.run()
        >>> solution.total_score
    """

    def __init__(
        self,
        problem: Problem,
        config: Optional[GAConfig] = None,
        weights: FitnessWeights = FitnessWeights(),
        on_generation: Optional[Callable[[int, float], None]] = None,
    ) -> None:
        self.problem = problem
        self.config = config or GAConfig()
        self.config.validate()
        self.evaluator = FitnessEvaluator(problem, weights)
        self.on_generation = on_generation
        self.rng = random.Random(self.config.seed)

        self._n_permits = len(problem.permits)
        self._n_slots = len(problem.slots)
        self._gene_space = self._n_slots + 1  # 多出一个「未分配」状态
        self.history: List[float] = []

    # ------------------------------------------------------------------ 编码

    def _random_individual(self) -> List[int]:
        """随机生成一个合法排列。

        PMX 交叉依赖「基因互不重复」这个前提。当许可数超过车位池容量时，
        「未分配」状态必然重复出现，因此这里改用虚拟车位补齐：
        第 i 个虚拟车位（下标 >= n_slots）解码后同样视为未分配，
        但它在编码层是唯一的，PMX 仍然成立。
        """
        genes = list(range(self._gene_space))
        if len(genes) < self._n_permits:
            genes.extend(range(self._gene_space, self._n_permits))
        self.rng.shuffle(genes)
        return genes[: self._n_permits]

    def _decode(self, individual: Sequence[int]) -> List[Assignment]:
        """把排列解码成许可-车位映射。下标越界即视为未分配。"""
        out: List[Assignment] = []
        for idx, permit in enumerate(self.problem.permits):
            gene = individual[idx]
            slot_id = (
                self.problem.slots[gene].slot_id if gene < self._n_slots else None
            )
            out.append(Assignment(permit_id=permit.permit_id, slot_id=slot_id))
        return out

    def _flatten(self, assignments: Sequence[Assignment]) -> Tuple[str, ...]:
        """用于去重比较的紧凑表示。"""
        return tuple(a.slot_id or "-" for a in assignments)

    # ------------------------------------------------------------------ 适应度

    def _fitness(self, individual: Sequence[int]) -> float:
        return self.evaluator.fitness(self._decode(individual))

    # ------------------------------------------------------------------ 选择

    def _tournament(self, population: Sequence[List[int]], scores: Sequence[float]) -> List[int]:
        """锦标赛选择：随机抽 k 个，取最优。比轮盘赌更抗适应度尺度差异。"""
        k = min(self.config.tournament_size, len(population))
        contenders = self.rng.sample(range(len(population)), k)
        best = max(contenders, key=lambda i: scores[i])
        return list(population[best])

    # ------------------------------------------------------------------ 交叉

    def _pmx(self, parent_a: List[int], parent_b: List[int]) -> Tuple[List[int], List[int]]:
        """部分匹配交叉，天然保证子代基因不重复。"""
        n = len(parent_a)
        if n < 2:
            return list(parent_a), list(parent_b)
        left, right = sorted(self.rng.sample(range(n), 2))
        if left == right:
            right = min(n - 1, left + 1)

        def build(pa: List[int], pb: List[int]) -> List[int]:
            child = [None] * n  # type: ignore[list-item]
            # 1. 直接把父代的片段拷进子代
            for i in range(left, right + 1):
                child[i] = pa[i]
            # 2. 把父代另一侧中未出现过的基因按顺序填入空位
            fill = [g for g in pb if g not in child]
            cursor = 0
            for i in range(n):
                if child[i] is None:
                    child[i] = fill[cursor]
                    cursor += 1
            return child  # type: ignore[return-value]

        return build(parent_a, parent_b), build(parent_b, parent_a)

    # ------------------------------------------------------------------ 变异

    def _mutate(self, individual: List[int]) -> None:
        """swap / insertion 双算子突变，随机选其一。"""
        n = len(individual)
        if n < 2:
            return
        i, j = self.rng.sample(range(n), 2)
        if self.rng.random() < 0.5:
            individual[i], individual[j] = individual[j], individual[i]
        else:
            gene = individual.pop(i)
            individual.insert(j, gene)

    # ------------------------------------------------------------------ 退火

    def _anneal(self, elite: List[int], elite_score: float, temperature: float) -> Tuple[List[int], float]:
        """Metropolis 准则扰动精英个体，帮助跳出局部最优。"""
        if temperature <= 1e-9 or len(elite) < 2:
            return elite, elite_score
        candidate = list(elite)
        self._mutate(candidate)
        cand_score = self._fitness(candidate)
        delta = cand_score - elite_score
        if delta >= 0:
            return candidate, cand_score
        import math

        if self.rng.random() < math.exp(delta / temperature):
            return candidate, cand_score
        return elite, elite_score

    # ------------------------------------------------------------------ 主循环

    def run(self) -> Solution:
        cfg = self.config
        population = [self._random_individual() for _ in range(cfg.population_size)]
        scores = [self._fitness(ind) for ind in population]
        self.history = []

        best_ind = population[max(range(len(scores)), key=lambda i: scores[i])]
        best_score = max(scores)
        temperature = cfg.initial_temperature

        for gen in range(cfg.generations):
            ranked = sorted(zip(scores, population), key=lambda x: x[0], reverse=True)
            # 精英保留 + 退火扰动
            elites = [list(ind) for _, ind in ranked[: cfg.elite_size]]
            elite_scores = [s for s, _ in ranked[: cfg.elite_size]]
            annealed, annealed_score = self._anneal(elites[0], elite_scores[0], temperature)

            next_pop: List[List[int]] = [annealed]
            next_scores: List[float] = [annealed_score]
            for ind, sc in zip(elites, elite_scores):
                next_pop.append(ind)
                next_scores.append(sc)

            while len(next_pop) < cfg.population_size:
                parent_a = self._tournament(population, scores)
                parent_b = self._tournament(population, scores)
                if self.rng.random() < cfg.crossover_rate:
                    child_a, child_b = self._pmx(parent_a, parent_b)
                else:
                    child_a, child_b = parent_a, parent_b
                for child in (child_a, child_b):
                    if self.rng.random() < cfg.mutation_rate:
                        self._mutate(child)
                    if len(next_pop) >= cfg.population_size:
                        break
                    next_pop.append(child)
                    next_scores.append(self._fitness(child))

            population, scores = next_pop, next_scores
            gen_best_idx = max(range(len(scores)), key=lambda i: scores[i])
            if scores[gen_best_idx] > best_score:
                best_score = scores[gen_best_idx]
                best_ind = list(population[gen_best_idx])

            self.history.append(best_score)
            if self.on_generation:
                self.on_generation(gen + 1, best_score)

            temperature *= cfg.cooling_rate

        assignments = self._decode(best_ind)
        walking, category, usage, total = self.evaluator.evaluate(assignments)
        unassigned = sum(1 for a in assignments if a.slot_id is None)
        return Solution(
            assignments=assignments,
            walking_score=walking,
            category_score=category,
            usage_score=usage,
            total_score=total,
            unassigned=unassigned,
            generation=cfg.generations,
        )

    # ------------------------------------------------------------------ 辅助

    def random_baseline(self, trials: int = 200) -> float:
        """随机分配的平均得分，作为算法效果的对照组。"""
        total = 0.0
        for _ in range(trials):
            ind = self._random_individual()
            total += self._fitness(ind)
        return total / max(1, trials)
