"""单元测试：覆盖模型校验、交叉算子合法性、算法单调收敛与可复现性。

运行::

    python -m pytest -q
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import unittest

from parking_ga.datasets import build_demo_problem, generate_garage, generate_permits
from parking_ga.ga import GAConfig, GeneticAlgorithm
from parking_ga.models import ParkingSlot, Permit, PermitCategory, Problem, manhattan


class TestModels(unittest.TestCase):
    def test_duplicate_slot_id_rejected(self):
        slot = ParkingSlot(slot_id="A1", x=0, y=0)
        with self.assertRaises(ValueError):
            Problem(
                slots=[slot, slot],
                permits=[Permit(permit_id="P1", category=PermitCategory.RESIDENT)],
            )

    def test_duplicate_permit_id_rejected(self):
        permit = Permit(permit_id="P1", category=PermitCategory.RESIDENT)
        with self.assertRaises(ValueError):
            Problem(slots=[ParkingSlot("A1", 0, 0)], permits=[permit, permit])

    def test_default_weight_by_category(self):
        self.assertEqual(
            Permit(permit_id="P1", category=PermitCategory.RESIDENT).effective_weight, 1.0
        )
        self.assertEqual(
            Permit(permit_id="P2", category=PermitCategory.VISITOR).effective_weight, 0.3
        )

    def test_manhattan_distance(self):
        self.assertAlmostEqual(manhattan((0, 0), (3, 4)), 7.0)


class TestOperators(unittest.TestCase):
    def setUp(self):
        self.problem = build_demo_problem()
        self.ga = GeneticAlgorithm(self.problem, GAConfig(population_size=8, seed=1))

    def test_pmx_children_are_permutations(self):
        """PMX 产生的子代必须无重复基因，否则解码会出现一车多占。"""
        for _ in range(50):
            a = self.ga._random_individual()
            b = self.ga._random_individual()
            ca, cb = self.ga._pmx(a, b)
            self.assertEqual(len(ca), len(a))
            self.assertEqual(len(set(ca)), len(ca))
            self.assertEqual(len(set(cb)), len(cb))

    def test_decode_length_matches_permits(self):
        ind = self.ga._random_individual()
        decoded = self.ga._decode(ind)
        self.assertEqual(len(decoded), len(self.problem.permits))

    def test_no_slot_assigned_twice(self):
        """解码后不允许两个许可绑定同一个车位。"""
        ga = GeneticAlgorithm(self.problem, GAConfig(population_size=10, generations=3, seed=7))
        solution = ga.run()
        used = [a.slot_id for a in solution.assignments if a.slot_id]
        self.assertEqual(len(used), len(set(used)))


class TestAlgorithm(unittest.TestCase):
    def test_reproducible_with_same_seed(self):
        cfg = GAConfig(population_size=20, generations=10, seed=2024)
        s1 = GeneticAlgorithm(build_demo_problem(), cfg).run()
        s2 = GeneticAlgorithm(build_demo_problem(), cfg).run()
        self.assertAlmostEqual(s1.total_score, s2.total_score, places=10)

    def test_beats_random_baseline(self):
        """GA 的效果必须显著优于随机分配，这是最有说服力的一个测试。"""
        ga = GeneticAlgorithm(
            build_demo_problem(),
            GAConfig(population_size=40, generations=20, seed=42),
        )
        baseline = ga.random_baseline()
        solution = ga.run()
        self.assertGreater(solution.total_score, baseline * 1.15)

    def test_history_is_nondecreasing(self):
        """精英保留保证了历史最优不会倒退，收敛曲线应当单调不降。"""
        ga = GeneticAlgorithm(
            build_demo_problem(), GAConfig(population_size=20, generations=15, seed=5)
        )
        ga.run()
        self.assertEqual(len(ga.history), 15)
        for prev, cur in zip(ga.history, ga.history[1:]):
            self.assertGreaterEqual(cur + 1e-12, prev)

    def test_handles_more_permits_than_slots(self):
        """许可数超过车位数时应优雅降级，而不是报错或死循环。"""
        slots = generate_garage(rows=1, cols=3)
        permits = generate_permits(n_resident=8, n_staff=2, n_visitor=2, seed=3)
        problem = Problem(slots=slots, permits=permits)
        solution = GeneticAlgorithm(
            problem, GAConfig(population_size=10, generations=5, seed=9)
        ).run()
        self.assertGreater(solution.unassigned, 0)
        max_assigned = min(len(slots), len(permits))
        assigned = len(permits) - solution.unassigned
        self.assertLessEqual(assigned, max_assigned)

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            GAConfig(population_size=2).validate()
        with self.assertRaises(ValueError):
            GAConfig(population_size=10, elite_size=10).validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
