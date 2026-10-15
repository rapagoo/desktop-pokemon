"""도감 규칙 테스트: 야생 등장 레벨과 진화 조건이 원작 느낌대로 나오는지."""
import random
import unittest

from pokepet import dex
from pokepet.config import FRIENDSHIP_PATS, LEGEND_MIN_LEVEL

DAY, NIGHT = 14, 21
EEVEE_STONES = {134, 135, 136, 470, 471}     # 샤미드·쥬피썬더·부스터·리피아·글레이시아


class TestData(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(len(dex.DATA), 493)
        self.assertEqual(dex.name(25), "피카츄")

    def test_evolution_targets_exist_and_point_forward(self):
        for num, e in dex.DATA.items():
            for evo in e["evo"]:
                self.assertIn(evo["to"], dex.DATA)
                self.assertEqual(dex.entry(evo["to"])["from"], num)


class TestMinLevel(unittest.TestCase):
    def test_level_evolution_lines(self):
        self.assertEqual([dex.min_level(n) for n in (4, 5, 6)], [2, 16, 36])

    def test_baby_evolution_counts_as_base(self):
        self.assertEqual(dex.min_level(25), 2)       # 피카츄 (피츄의 진화형)

    def test_stone_evolution_uses_fallback(self):
        self.assertEqual(dex.min_level(26), 30)      # 라이츄

    def test_legendary(self):
        self.assertEqual(dex.min_level(150), LEGEND_MIN_LEVEL)

    def test_evolved_forms_never_below_previous(self):
        for num, e in dex.DATA.items():
            if e["from"] and not dex.entry(e["from"])["baby"] and not e["legendary"]:
                self.assertGreater(dex.min_level(num), dex.min_level(e["from"]), dex.name(num))


class TestWild(unittest.TestCase):
    def test_low_level_only_base_forms(self):
        cands = dex.wild_candidates(5)
        self.assertIn(4, cands)                      # 파이리
        self.assertNotIn(6, cands)                   # 리자몽은 안 나옴
        self.assertNotIn(150, cands)                 # 전설도 안 나옴
        self.assertNotIn(172, cands)                 # 아기 포켓몬은 야생에 없음

    def test_high_level_drops_unevolved(self):
        cands = dex.wild_candidates(50)
        self.assertIn(6, cands)
        self.assertNotIn(4, cands)                   # Lv.50 파이리는 안 나옴

    def test_common_is_more_likely_than_rare(self):
        cands = dex.wild_candidates(5)
        self.assertGreater(cands[16], cands[147])    # 구구 > 미뇽

    def test_pick_respects_level(self):
        rng = random.Random(1)
        for _ in range(300):
            n = dex.pick_wild(8, rng)
            self.assertLessEqual(dex.min_level(n), 8, dex.name(n))

    def test_every_level_has_candidates(self):
        for lv in range(2, 101):
            self.assertTrue(dex.wild_candidates(lv), lv)


class TestEvolution(unittest.TestCase):
    def evo(self, num, level=5, friendship=0, hour=DAY, traded=False):
        return dex.evolution_for(num, level, friendship, hour, traded, random.Random(0))

    def test_level(self):
        self.assertIsNone(self.evo(4, level=15))
        self.assertEqual(self.evo(4, level=16), 5)

    def test_stone_becomes_level(self):
        self.assertIsNone(self.evo(25, level=29))
        self.assertEqual(self.evo(25, level=30), 26)

    def test_friendship_by_pats(self):
        self.assertIsNone(self.evo(172, friendship=FRIENDSHIP_PATS - 1))
        self.assertEqual(self.evo(172, friendship=FRIENDSHIP_PATS), 25)

    def test_eevee_day_and_night(self):
        self.assertEqual(self.evo(133, friendship=FRIENDSHIP_PATS, hour=DAY), 196)     # 에브이
        self.assertEqual(self.evo(133, friendship=FRIENDSHIP_PATS, hour=NIGHT), 197)   # 블래키
        self.assertTrue(dex.is_day(6) and not dex.is_day(18))

    def test_eevee_without_friendship_uses_stones(self):
        self.assertIsNone(self.evo(133, level=29))
        self.assertIn(self.evo(133, level=30), EEVEE_STONES)

    def test_trade_only_when_traded(self):
        self.assertIsNone(self.evo(93, level=100))
        self.assertEqual(self.evo(93, traded=True), 94)      # 고우스트 → 팬텀

    def test_no_evolution(self):
        self.assertIsNone(self.evo(6, level=100, friendship=999, traded=True))


if __name__ == "__main__":
    unittest.main()
