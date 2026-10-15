"""야생 포켓몬 등장, 자동 턴제 배틀, 경험치, 포획. App에 섞어 쓰는 믹스인."""
import random

from .config import (
    DAZED_MS,
    FAINT_REST_MS,
    MAX_PARTY,
    MOVE_POWER,
    SPAWN_MS,
    TYPE_CHART,
)
from . import dex
from .util import chant, josa


def type_effect(move_type, defender_types):
    """공격 타입이 방어 타입들에 주는 배율 (0, 0.25, 0.5, 1, 2, 4)."""
    eff = 1.0
    for t in defender_types:
        eff *= TYPE_CHART.get(move_type, {}).get(t, 1.0)
    return eff


def calc_damage(att, dfn, rand=random.uniform):
    """데미지와 상성 배율. att/dfn은 level, dex["types"], stat(이름)을 가진 객체.

    공격 기술은 공격자의 첫 번째 타입(자속 1.5배), 물리/특수는 공격·특공 중 높은 쪽.
    """
    eff = type_effect(att.dex["types"][0], dfn.dex["types"])
    physical = att.stat("attack") >= att.stat("special-attack")
    a_stat = att.stat("attack" if physical else "special-attack")
    d_stat = dfn.stat("defense" if physical else "special-defense")
    base = (2 * att.level / 5 + 2) * MOVE_POWER * a_stat / max(1, d_stat) / 50 + 2
    dmg = 0 if eff == 0 else max(1, int(base * 1.5 * eff * rand(.85, 1)))
    return dmg, eff


class BattleMixin:
    """App이 상속해서 쓰는 배틀 관련 메서드 모음 (self는 App)."""

    def party(self):
        return [p for p in self.pets if not p.wild]

    def spawn_wild(self):
        """상대할 내 포켓몬을 먼저 정하고, 그 레벨에 맞는 야생 포켓몬을 부른다."""
        party = self.party()
        rested = [p for p in party if p.state != "fainted" and p.hp >= p.max_hp * .4]
        self.wild_target = random.choice(rested or party)
        level = max(2, self.wild_target.level + random.randint(-2, 1))
        self.spawning = True
        self.request(dex.pick_wild(level), save=False, wild=True,
                     stats={"level": level})

    def battle_tick(self, dt):
        w = self.wild
        if w is None:
            if not self.spawning and self.party():
                self.spawn_t -= dt
                if self.spawn_t <= 0:
                    self.spawn_wild()
            return

        b = self.battle
        if b:
            a = b["ally"]
            if a not in self.pets or a.state != "battle" or w.state != "battle":
                self.abort_battle()
                return
            if a.action or w.action:
                return
            b["cool"] -= dt
            if b["cool"] > 0:
                return
            att, dfn = (a, w) if b["turn"] == "ally" else (w, a)
            att.facing = 1 if dfn.cx > att.cx else -1
            dfn.facing = -att.facing
            kind = "attack" if att.stat("attack") >= att.stat("special-attack") else "shoot"
            att.play(kind, lambda: self.hit(att, dfn))
            b["turn"] = "wild" if b["turn"] == "ally" else "ally"
            b["cool"] = 600
            return

        if w.state == "approach":
            targets = [p for p in self.party() if p.state in ("walk", "idle", "sleep")]
            if not targets:                     # 싸울 상대가 없으면 돌아감
                if not any(p.state in ("fall", "drag", "battle") for p in self.party()):
                    w.leave()
                return
            healthy = [p for p in targets if p.hp >= p.max_hp * .4]   # 지친 포켓몬은 되도록 쉬게
            target = self.wild_target
            if target in healthy:               # 레벨을 맞춰 둔 상대에게 다가간다
                t = target
            else:
                t = min(healthy or targets, key=lambda p: abs(p.cx - w.cx))
            dx = t.cx - w.cx
            if not getattr(w, "approach_speed", None):
                w.approach_speed = w.pick_speed(1.1)
            w.vx = w.approach_speed if dx > 0 else -w.approach_speed
            if abs(dx) < (t.sp.w + w.sp.w) / 4 + 24:
                self.start_battle(t, w)

    def start_battle(self, ally, wild):
        if ally.state == "sleep":
            ally.say("…!? 깼다!", 1200)
        ally.set_state("battle")
        wild.set_state("battle")
        ally.facing = 1 if wild.cx > ally.cx else -1
        wild.facing = -ally.facing
        first = "ally" if ally.stat("speed") >= wild.stat("speed") else "wild"
        self.battle = {"ally": ally, "turn": first, "cool": 700}

    def abort_battle(self):
        self.battle = None
        w = self.wild
        if w and w.state == "battle":
            w.state = "approach"
        for p in self.party():
            if p.state == "battle":
                p.set_state("idle", 1500)

    def hit(self, att, dfn):
        b = self.battle
        if not b or dfn.state != "battle" or att.state != "battle":
            return
        dmg, eff = calc_damage(att, dfn)
        dfn.hp = max(0.0, dfn.hp - dmg)
        note = {0: " 효과가 없다…", .25: " 별로…", .5: " 별로…", 2: " 굉장해!", 4: " 굉장해!!"}.get(eff, "")
        dfn.say(f"-{dmg}{note}", 1100)
        self.log(f"  {att.name} -> {dfn.name}: -{dmg} (x{eff})  HP {dfn.hp:.0f}/{dfn.max_hp}")
        if dmg:
            dfn.play("hurt")
        if dfn.hp <= 0:
            self.battle_over(att, dfn)

    def battle_over(self, winner, loser):
        self.battle = None
        if loser.wild:
            loser.set_state("dazed", DAZED_MS)
            loser.say("지금이야! 클릭해서 잡기", DAZED_MS)
            gain = max(5, loser.dex["base_exp"] * loser.level // 7)
            ups = winner.gain_exp(gain)
            winner.set_state("idle", 2500)
            self.dialog.push(winner, "Happy", f"이겼다! 경험치 {gain} 획득")
            if ups:
                winner.say(f"레벨 업! Lv.{winner.level}", 2500)
                self.dialog.push(winner, "Joyous", f"레벨 업! Lv.{winner.level} 달성!")
                self.add_event(f"{winner.name} Lv.{winner.level} 달성")
                self.root.after(2700, lambda: self.try_evolve(winner))
            self.save()
        else:
            loser.set_state("fainted", FAINT_REST_MS)
            loser.say("…", 2000)
            self.dialog.push(loser, "Crying", f"{josa(loser.name, '은는')} 쓰러졌다… 조금 쉬면 괜찮아질 거야")
            winner.say(chant(winner.name), 1200)
            self.root.after(1500, lambda: winner in self.pets and winner.leave())
            self.save()

    def catch(self, wild):
        if wild is not self.wild or wild.state != "dazed":
            return
        self.mark_caught(wild.num)
        self.spawn_t = random.randint(*SPAWN_MS)
        if len(self.party()) >= MAX_PARTY:          # 파티가 가득 차면 보관함으로
            wild.hp = wild.max_hp
            wild.wild = False
            self.box.append(self.pet_record(wild))
            wild.wild = True
            wild.set_state("idle", 10 ** 9)          # 사라질 때까지 다시 클릭해도 또 잡히지 않게
            wild.say("♥ 보관함으로!", 1200)
            self.dialog.push(wild, "Joyous", f"{josa(wild.name, '을를')} 잡았다! 파티가 가득 차서 보관함으로 보냈어요")
            self.add_event(f"{wild.name}(Lv.{wild.level})을(를) 잡아서 보관함으로 보냈다")
            self.root.after(900, lambda: self.wild_gone(wild))
        else:
            wild.wild = False
            wild.hp = wild.max_hp
            wild.set_state("idle", 2000)
            wild.say("♥", 1500)
            self.wild = None
            self.dialog.push(wild, "Joyous", f"{josa(wild.name, '을를')} 잡았다! 잘 부탁해!")
            self.add_event(f"{wild.name}(Lv.{wild.level})을(를) 잡았다")
        self.save()

    def wild_escape(self, wild):
        wild.hp = max(1.0, wild.hp)
        wild.say("휘익~", 1000)
        wild.leave()

    def wild_gone(self, wild):
        if wild in self.pets:
            self.pets.remove(wild)
            wild.destroy()
        if self.wild is wild:
            self.wild = None
            self.battle = None
            self.spawn_t = random.randint(*SPAWN_MS)
