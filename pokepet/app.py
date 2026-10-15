"""전체 조립: 포켓몬 불러오기, 메인 루프, 우클릭 메뉴, 숨기기, 저장."""
import ctypes
import json
import queue
import random
import shutil
import sys
import threading
import tkinter as tk
from tkinter import simpledialog

from .config import (
    DEFAULT_PARTY,
    FIRST_SPAWN_MS,
    GREETS,
    KO_NAMES,
    MAX_NUM,
    NAMES_FILE,
    PARTY_FILE,
    SHINY_CHANCE,
    SPECIES_URL,
    SPRITE_DIR,
    TICK,
)
from .util import chant, exp_for, http_get, josa, load_json, poke_name, work_area
from .sprites import load_sprite
from . import assets
from .battle import BattleMixin
from .dialog import Dialog
from .pet import Pet


class App(BattleMixin):
    def __init__(self, debug=False):
        self.debug = debug
        if debug:
            sys.stdout.reconfigure(encoding="utf-8")
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("바탕화면 포켓몬")
        self.area = work_area() or (0, 0, self.root.winfo_screenwidth(),
                                    self.root.winfo_screenheight() - 40)
        SPRITE_DIR.mkdir(exist_ok=True)
        self.names = load_json(NAMES_FILE, {})
        self.pets = []
        self.sprites = {}
        self.portraits = {}
        self.loaded = queue.Queue()
        self.hidden = False
        self.dialog = Dialog(self)

        # 배틀 상태
        self.wild = None              # 지금 화면에 있는 야생 포켓몬
        self.spawning = False         # 야생 포켓몬을 받는 중
        self.battle = None            # {"ally", "turn", "cool"}
        self.spawn_t = random.randint(*FIRST_SPAWN_MS)

        party = load_json(PARTY_FILE, None) or [{"num": n} for n in DEFAULT_PARTY]
        for p in party:
            self.request(p["num"], p.get("shiny", False), save=False,
                         stats={k: p[k] for k in ("level", "exp", "hp") if k in p})

        self.menu = tk.Menu(self.root, tearoff=0, font=("맑은 고딕", 9))
        self.root.after(TICK, self.loop)

    def log(self, msg):
        """--debug 일 때만 콘솔에 이벤트 출력."""
        if self.debug:
            print(msg, flush=True)

    # -------------------------------------------------- loading
    def request(self, num, shiny=None, save=True, wild=False, stats=None):
        if shiny is None:
            shiny = random.random() < SHINY_CHANCE
        threading.Thread(target=self._fetch, args=(num, shiny, save, wild, stats or {}),
                         daemon=True).start()

    def _fetch(self, num, shiny, save, wild, stats):
        try:
            # PMD(이로치) → PMD(일반) → 5세대 도트 순서. PMD 이로치가 없으면 일반으로.
            path = assets.download_pmd(num, shiny)
            if path is None and shiny:
                path = assets.download_pmd(num, False)
                shiny = False if path else shiny
            if path is None:
                path = assets.download_sprite(num, shiny)
            if num not in KO_NAMES and str(num) not in self.names:
                try:
                    sp = json.loads(http_get(SPECIES_URL.format(num=num)))
                    ko = next((n["name"] for n in sp["names"] if n["language"]["name"] == "ko"), None)
                    if ko:
                        self.names[str(num)] = ko
                except Exception:
                    pass
            dex = assets.download_dex(num)
            assets.download_portraits(num)
            self.loaded.put({"num": num, "shiny": shiny, "path": path, "save": save,
                             "wild": wild, "stats": stats, "dex": dex})
        except Exception as ex:
            print(f"#{num} 불러오기 실패: {ex}", file=sys.stderr)
            self.loaded.put({"failed": True, "wild": wild})

    def portrait(self, num, emotion):
        for emo in (emotion, "Normal"):
            key = (num, emo)
            if key in self.portraits:
                return self.portraits[key]
            path = SPRITE_DIR / f"portrait-{num}-{emo}.png"
            if path.exists():
                try:
                    self.portraits[key] = tk.PhotoImage(file=str(path)).zoom(2)
                    return self.portraits[key]
                except tk.TclError:
                    pass
        return None

    def _spawn(self, item):
        if item.get("failed"):
            if item["wild"]:
                self.spawning = False
                self.spawn_t = 10_000
            return
        path = item["path"]
        key = path.name
        if key not in self.sprites:
            try:
                self.sprites[key] = load_sprite(path)
            except Exception as ex:
                print(f"{key} 읽기 실패: {ex}", file=sys.stderr)
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
                if item["wild"]:
                    self.spawning = False
                    self.spawn_t = 10_000
                return
        num = item["num"]
        pet = Pet(self, num, item["shiny"], self.sprites[key], poke_name(num, self.names),
                  item["dex"], wild=item["wild"], **item["stats"])
        if self.hidden:
            pet.win.withdraw()
        self.pets.append(pet)
        if item["wild"]:
            self.wild, self.spawning = pet, False
            self.dialog.push(pet, "Determined",
                             f"야생 {josa(pet.name, '이가')} 나타났다! (Lv.{pet.level})")
        if item["save"]:
            self.save()

    def save(self):
        party = [{"num": p.num, "shiny": p.shiny, "level": p.level, "exp": p.exp,
                  "hp": round(p.hp)} for p in self.pets if not p.wild]
        PARTY_FILE.write_text(json.dumps(party), encoding="utf-8")
        NAMES_FILE.write_text(json.dumps(self.names, ensure_ascii=False), encoding="utf-8")

    # -------------------------------------------------- main loop
    def loop(self):
        while not self.loaded.empty():
            self._spawn(self.loaded.get())
        if not self.hidden:
            for p in list(self.pets):
                p.tick(TICK)
            self.meet()
            self.battle_tick(TICK)
        self.root.after(TICK, self.loop)

    def meet(self):
        """걷다가 서로 마주치면 인사."""
        party = [p for p in self.pets if not p.wild]
        for i, a in enumerate(party):
            for b in party[i + 1:]:
                if a.state in ("walk", "idle") and b.state in ("walk", "idle") \
                        and not a.cool and not b.cool \
                        and abs(a.cx - b.cx) < 40:
                    a.cool = b.cool = 15000
                    a.say(random.choice(GREETS))
                    self.root.after(600, lambda b=b: b.say(chant(b.name)))

    # -------------------------------------------------- battle
    # -------------------------------------------------- menu
    def show_menu(self, pet, x, y):
        m = self.menu
        m.delete(0, "end")
        m.add_command(label=f"{pet.display_name}  HP {int(pet.hp)}/{pet.max_hp}", state="disabled")
        if not pet.wild:
            nxt = exp_for(pet.level + 1) - pet.exp
            m.add_command(label=f"타입 {'/'.join(pet.dex['types'])} · 다음 레벨까지 {nxt}", state="disabled")
        m.add_separator()
        m.add_command(label="야생 포켓몬 부르기", command=self.call_wild)
        m.add_command(label="도감 번호로 부르기…", command=self.ask_number)
        if not pet.wild:
            m.add_command(label=f"{pet.name} 재우기", command=lambda: pet.set_state("sleep", 20000))
        m.add_command(label=f"{pet.name} 돌려보내기", command=lambda: self.remove(pet))
        m.add_separator()
        m.add_command(label="수업 집중! 5분 숨기기", command=lambda: self.hide(5 * 60 * 1000))
        m.add_command(label="종료", command=self.quit)
        m.tk_popup(x, y)

    def call_wild(self):
        if self.wild is None and not self.spawning and self.party():
            self.spawn_wild()

    def ask_number(self):
        n = simpledialog.askinteger("포켓몬 부르기", f"도감 번호 (1~{MAX_NUM})",
                                    minvalue=1, maxvalue=MAX_NUM, parent=self.root)
        if n:
            self.request(n)

    def remove(self, pet):
        pet.say("바이바이~", 800)

        def bye():
            if pet in self.pets:
                if self.battle and pet in (self.battle["ally"], self.wild):
                    self.abort_battle()
                if pet is self.wild:
                    self.wild_gone(pet)
                    return
                self.pets.remove(pet)
                pet.destroy()
                self.save()
        self.root.after(800, bye)

    def hide(self, ms):
        self.hidden = True
        for p in self.pets:
            p.win.withdraw()
        self.root.after(ms, self.show)

    def show(self):
        self.hidden = False
        for p in self.pets:
            p.win.deiconify()
            p.win.attributes("-topmost", True)
            if not p.wild:
                p.say("다녀왔어!", 1500)

    def quit(self):
        self.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
