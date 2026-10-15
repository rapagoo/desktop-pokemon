"""진화: 조건 확인, "…어라!?" 연출, 새 모습으로 교체. App에 섞어 쓰는 믹스인.

진화 조건 자체는 dex.evolution_for (순수 함수)가 판단한다. 확인 시점:
  - 레벨 업했을 때 (battle.py)
  - 친밀도가 충분한 상태에서 쓰다듬었을 때 (on_pat)
  - 다른 PC에서 저장된 포켓몬이 이 PC에서 깨어났을 때 = 통신 교환 (app._spawn)
"""
from datetime import datetime

from . import dex
from .config import FRIENDSHIP_PATS
from .pet import Pet
from .util import josa, josa_ro, poke_name

BLINK_MS = 180
BLINKS = 10


class EvolutionMixin:
    """App이 상속해서 쓰는 진화 관련 메서드 모음 (self는 App)."""

    def on_arrived(self, pet):
        """다른 PC에서 걸어 들어온 포켓몬이 자리에 도착함 → 인사하고 교환 진화 확인."""
        src = self.arrivals["from"] or "다른 PC"
        if not self.arrivals.get("announced"):
            self.arrivals["announced"] = True
            n = self.arrivals["seen"]          # 불러오기에 실패한 포켓몬은 빼고 실제로 온 수
            what = josa(pet.name, "이가") if n == 1 else f"포켓몬 {n}마리가"
            self.dialog.push(pet, "Happy", f"{src}에서 {what} 도착했다!")
        pet.say(f"{src}에서 왔어!", 2000)
        self.root.after(1500, lambda: self.try_evolve(pet, traded=True))

    def on_pat(self, pet):
        if pet.friendship >= FRIENDSHIP_PATS:          # 점프하고 착지한 뒤 확인
            self.root.after(1200, lambda: self.try_evolve(pet))

    def try_evolve(self, pet, traded=False):
        """진화 조건을 만족하면 진화를 시작하고 True."""
        if pet not in self.pets or pet.wild or pet.state not in ("walk", "idle", "sleep"):
            return False
        target = dex.evolution_for(pet.num, pet.level, pet.friendship,
                                   datetime.now().hour, traded)
        if not target:
            return False
        self.log(f"진화 시작: {pet.name} -> {poke_name(target, self.names)}"
                 f"{' (교환)' if traded else ''}")
        pet.set_state("evolving", 10 ** 9)
        pet.by_trade = traded
        pet.say("…어라!?", 4000)
        self.dialog.push(pet, "Surprised", f"…어라!? {pet.name}의 모습이…!")
        # 새 모습을 받는 동안 깜빡이고, 받으면 finish_evolution 에서 교체
        self.blink(pet, BLINKS)
        self.request(target, shiny=pet.shiny, save=False, replace=pet,
                     stats={"level": pet.level, "exp": pet.exp, "friendship": pet.friendship})
        return True

    def blink(self, pet, times):
        if pet not in self.pets or pet.state != "evolving":
            return
        pet.cv.itemconfigure(pet.img_id, state="hidden" if times % 2 else "normal")
        if times > 0:
            self.root.after(BLINK_MS, lambda: self.blink(pet, times - 1))

    def cancel_evolution(self, pet):
        """새 모습을 받지 못했을 때 (다음 기회에 다시)."""
        if pet in self.pets and pet.state == "evolving":
            pet.cv.itemconfigure(pet.img_id, state="normal")
            pet.set_state("idle", 1500)
            pet.say("…?", 1200)

    def finish_evolution(self, old, item):
        if old not in self.pets:                         # 그 사이 돌려보냄
            return
        num = item["num"]
        new = Pet(self, num, item["shiny"], self.sprites[item["path"].name],
                  poke_name(num, self.names), item["dex"], **item["stats"])
        new.x = old.cx - new.cw / 2
        new.y = new.floor
        new.set_state("idle", 3000)
        new.place()
        if self.hidden:
            new.win.withdraw()
        self.pets[self.pets.index(old)] = new
        old.destroy()
        new.say("✨ 진화!", 2500)
        how = "통신 교환으로 " if getattr(old, "by_trade", False) else ""
        self.dialog.push(new, "Joyous",
                         f"축하해! {how}{josa(old.name, '은는')} {josa_ro(new.name)} 진화했다!")
        self.log(f"진화 완료: {old.name} -> {new.name}")
        self.save()
