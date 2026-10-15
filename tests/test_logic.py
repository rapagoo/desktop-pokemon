"""화면·네트워크 없이 도는 로직 테스트.  실행: python -m unittest"""
import struct
import unittest

from pokepet.battle import calc_damage, type_effect
from pokepet.sprites import parse_anim_data
from pokepet.util import calc_stat, exp_for, gif_frame_info, josa, josa_ro


class FakeMon:
    """calc_damage가 쓰는 것만 가진 가짜 포켓몬."""

    def __init__(self, types, level=10, **stats):
        self.level = level
        base = {"attack": 50, "defense": 50, "special-attack": 50, "special-defense": 50}
        base.update(stats)
        self.dex = {"types": types, "stats": base}

    def stat(self, key):
        return calc_stat(self.dex["stats"][key], self.level)


NO_RANDOM = lambda a, b: 1.0  # noqa: E731  데미지 난수를 고정


class TestJosa(unittest.TestCase):
    def test_final_consonant(self):
        self.assertEqual(josa("이브이", "이가"), "이브이가")
        self.assertEqual(josa("롱스톤", "이가"), "롱스톤이")
        self.assertEqual(josa("피카츄", "을를"), "피카츄를")
        self.assertEqual(josa("파이리", "은는"), "파이리는")

    def test_non_hangul_uses_second_form(self):
        self.assertEqual(josa("#25", "이가"), "#25가")

    def test_ro_euro(self):
        self.assertEqual(josa_ro("블래키"), "블래키로")      # 받침 없음
        self.assertEqual(josa_ro("마릴"), "마릴로")          # ㄹ 받침
        self.assertEqual(josa_ro("롱스톤"), "롱스톤으로")    # 그 외 받침


class TestStats(unittest.TestCase):
    def test_exp_curve_is_cubic(self):
        self.assertEqual(exp_for(5), 125)
        self.assertLess(exp_for(10) - exp_for(9), exp_for(20) - exp_for(19))

    def test_pikachu_level5(self):
        # 피카츄 종족값 HP 35, 스피드 90
        self.assertEqual(calc_stat(35, 5, is_hp=True), 18)
        self.assertEqual(calc_stat(90, 5), 14)


class TestTypes(unittest.TestCase):
    def test_effectiveness(self):
        self.assertEqual(type_effect("fire", ["grass"]), 2)
        self.assertEqual(type_effect("water", ["fire", "ground"]), 4)
        self.assertEqual(type_effect("grass", ["fire", "flying"]), .25)
        self.assertEqual(type_effect("electric", ["ground"]), 0)
        self.assertEqual(type_effect("normal", ["water"]), 1)


class TestDamage(unittest.TestCase):
    def test_immune_deals_zero(self):
        dmg, eff = calc_damage(FakeMon(["electric"]), FakeMon(["ground"]), NO_RANDOM)
        self.assertEqual((dmg, eff), (0, 0))

    def test_super_effective_doubles(self):
        neutral, _ = calc_damage(FakeMon(["fire"]), FakeMon(["normal"]), NO_RANDOM)
        strong, eff = calc_damage(FakeMon(["fire"]), FakeMon(["grass"]), NO_RANDOM)
        self.assertEqual(eff, 2)
        self.assertAlmostEqual(strong, neutral * 2, delta=1)

    def test_uses_higher_attack_stat(self):
        # 특공이 높으면 상대 특방으로 계산 → 특방이 높은 상대에게 덜 들어감
        att = FakeMon(["normal"], **{"attack": 20, "special-attack": 120})
        soft, _ = calc_damage(att, FakeMon(["normal"], **{"special-defense": 20}), NO_RANDOM)
        hard, _ = calc_damage(att, FakeMon(["normal"], **{"special-defense": 150}), NO_RANDOM)
        self.assertGreater(soft, hard)

    def test_battle_lasts_a_few_hits(self):
        # 같은 레벨·같은 종족값끼리 보통 3~4방에 끝나도록 밸런스를 잡았음
        mon = FakeMon(["normal"], level=5)
        dmg, _ = calc_damage(mon, FakeMon(["fire"], level=5), NO_RANDOM)
        hp = calc_stat(50, 5, is_hp=True)
        self.assertTrue(3 <= -(-hp // dmg) <= 5, f"hp {hp}, dmg {dmg}")


def tiny_gif(disposal, delay_cs, rect):
    """프레임 하나짜리 최소 GIF 바이트."""
    x, y, w, h = rect
    return (b"GIF89a" + struct.pack("<HHBBB", 4, 4, 0, 0, 0)
            + b"\x21\xF9\x04" + bytes([disposal << 2]) + struct.pack("<H", delay_cs) + b"\x00\x00"
            + b"\x2C" + struct.pack("<HHHHB", x, y, w, h, 0)
            + b"\x02\x02\x44\x01\x00" + b"\x3B")


class TestGif(unittest.TestCase):
    def test_reads_disposal_delay_rect(self):
        info = gif_frame_info(tiny_gif(2, 5, (1, 2, 3, 1)))
        self.assertEqual(info, [(2, 50, (1, 2, 3, 1))])

    def test_too_short_delay_becomes_100ms(self):
        self.assertEqual(gif_frame_info(tiny_gif(1, 0, (0, 0, 1, 1)))[0][1], 100)


ANIM_XML = b"""<AnimData><Anims>
  <Anim><Name>Walk</Name><FrameWidth>32</FrameWidth><FrameHeight>40</FrameHeight>
    <Durations><Duration>6</Duration><Duration>12</Duration></Durations></Anim>
  <Anim><Name>Idle</Name><CopyOf>Walk</CopyOf></Anim>
  <Anim><Name>Hurt</Name><FrameWidth>48</FrameWidth><FrameHeight>48</FrameHeight>
    <Durations><Duration>3</Duration></Durations></Anim>
</Anims></AnimData>"""


class TestAnimData(unittest.TestCase):
    def setUp(self):
        self.info = parse_anim_data(ANIM_XML)

    def test_durations_in_ms(self):
        self.assertEqual(self.info["walk"], ("Walk", 32, 40, [100, 200]))

    def test_copy_of_is_followed(self):
        self.assertEqual(self.info["idle"][0], "Walk")

    def test_missing_anims_fall_back(self):
        # Sleep·Attack 등이 없으면 후보 목록을 따라 Idle(=Walk)로
        self.assertEqual(self.info["sleep"][0], "Walk")
        self.assertEqual(self.info["attack"][0], "Walk")
        self.assertEqual(self.info["hurt"][0], "Hurt")


if __name__ == "__main__":
    unittest.main()
