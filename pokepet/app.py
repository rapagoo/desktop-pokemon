"""전체 조립: 포켓몬 불러오기, 메인 루프, 우클릭 메뉴, 숨기기, 저장."""
import ctypes
import json
import queue
import random
import shutil
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .config import (
    AUTO_HIDE_FULLSCREEN,
    DEFAULT_PARTY,
    FULLSCREEN_CHECK_MS,
    FIRST_SPAWN_MS,
    GREETS,
    KO_NAMES,
    MAX_NUM,
    NAMES_FILE,
    PARTY_FILE,
    SETTINGS_FILE,
    SHINY_CHANCE,
    SPECIES_URL,
    SPRITE_DIR,
    START_LEVEL,
    TICK,
)
from .storage import SAVE_FOLDER, SaveStore
from .util import chant, exp_for, http_get, josa, load_json, poke_name, work_area
from .sprites import load_sprite
from . import assets, dex, screen
from .battle import BattleMixin
from .evolution import EvolutionMixin
from .dialog import Dialog
from .pet import Pet


class App(BattleMixin, EvolutionMixin):
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
        self.hide_reasons = set()     # 비어 있지 않으면 숨긴 상태 (hidden 속성)
        self.dialog = Dialog(self)

        # 배틀 상태
        self.wild = None              # 지금 화면에 있는 야생 포켓몬
        self.spawning = False         # 야생 포켓몬을 받는 중
        self.battle = None            # {"ally", "turn", "cool"}
        self.wild_target = None       # 야생 포켓몬이 상대하러 가는 내 포켓몬 (레벨을 맞춤)
        self.spawn_t = random.randint(*FIRST_SPAWN_MS)

        # 저장소 (클라우드 폴더를 정했으면 학원 PC ↔ 집 PC 연동)
        self.store = SaveStore(PARTY_FILE, SETTINGS_FILE)
        other = self.store.other_running()
        if other and not messagebox.askyesno(
                "바탕화면 포켓몬",
                f"다른 PC({other})에서 실행 중인 것 같아요.\n"
                "두 곳에서 같이 켜 두면 한쪽 진행 상황이 저장되지 않을 수 있어요.\n\n그래도 실행할까요?"):
            self.root.destroy()
            sys.exit(0)
        rec = self.store.load()
        self.load_party(rec["party"] if rec and rec["party"] else [{"num": n} for n in DEFAULT_PARTY])
        self.heartbeat()

        self.menu = tk.Menu(self.root, tearoff=0, font=("맑은 고딕", 9))
        self.root.after(TICK, self.loop)
        if AUTO_HIDE_FULLSCREEN:
            self.root.after(FULLSCREEN_CHECK_MS, self.check_fullscreen)

    def log(self, msg):
        """--debug 일 때만 콘솔에 이벤트 출력."""
        if self.debug:
            print(msg, flush=True)

    # -------------------------------------------------- party / save
    def load_party(self, party):
        for p in party:
            # 다른 PC에서 저장된 포켓몬이 이 PC에서 깨어나면 통신 교환으로 친다
            traded = p.get("machine") not in (None, self.store.machine)
            self.request(p["num"], p.get("shiny", False), save=False, traded=traded,
                         stats={k: p[k] for k in ("level", "exp", "hp", "friendship") if k in p})

    def replace_party(self, party):
        """다른 PC에서 저장한 파티로 바꾼다 (지금 화면의 내 포켓몬은 정리)."""
        if self.battle:
            self.abort_battle()
        for p in self.party():
            self.pets.remove(p)
            p.destroy()
        self.load_party(party)

    def save(self):
        party = [{"num": p.num, "shiny": p.shiny, "level": p.level, "exp": p.exp,
                  "hp": round(p.hp), "friendship": p.friendship, "machine": self.store.machine}
                 for p in self.party()]
        try:
            where = self.store.save(party)
            if where != self.store.save_file:
                self.log(f"다른 PC가 먼저 저장해서 {where.name} 에 따로 저장했어요")
        except OSError as ex:
            print(f"저장 실패: {ex}", file=sys.stderr)
        NAMES_FILE.write_text(json.dumps(self.names, ensure_ascii=False), encoding="utf-8")

    def heartbeat(self):
        """클라우드 저장 중이면 '이 PC에서 실행 중' 표시를 1분마다 갱신."""
        try:
            self.store.heartbeat()
        except OSError:
            pass
        self.root.after(60_000, self.heartbeat)

    def choose_save_dir(self):
        """학원 PC와 집 PC가 같이 보는 클라우드 폴더를 저장 위치로 고른다."""
        home = Path.home()
        initial = next((p for p in (home / "Dropbox", home / "OneDrive") if p.exists()), home)
        folder = filedialog.askdirectory(
            parent=self.root, initialdir=str(initial),
            title="학원 PC와 집 PC가 같이 보는 폴더 (Dropbox, OneDrive 등)")
        if not folder:
            return
        found = self.store.peek(Path(folder) / SAVE_FOLDER / "save.json")
        self.store.set_save_dir(folder)
        if found and found["party"]:
            top = max(p.get("level", START_LEVEL) for p in found["party"])
            use_found = messagebox.askyesno(
                "저장 위치 바꾸기",
                f"그 폴더에 {found['machine'] or '다른 PC'}에서 저장한 기록이 있어요.\n"
                f"(포켓몬 {len(found['party'])}마리, 최고 Lv.{top})\n\n"
                "그 기록으로 바꿀까요?\n아니요를 누르면 지금 이 PC의 기록으로 덮어써요.")
            if use_found:
                self.replace_party(self.store.load()["party"])
            else:
                self.store.loaded_at = found["saved_at"]
                self.save()
        else:
            self.save()
        self.store.heartbeat()
        self.log(f"저장 위치: {self.store.describe()}")

    def use_local_save(self):
        self.store.release()
        self.store.set_save_dir(None)
        self.save()

    # -------------------------------------------------- loading
    def request(self, num, shiny=None, save=True, wild=False, stats=None, traded=False, replace=None):
        """포켓몬을 백그라운드에서 받아 화면에 올린다.

        traded : 다른 PC에서 옮겨 와서 깨어남 (교환 진화 확인)
        replace: 진화 — 이 포켓몬 자리에 새 모습으로 바꿔 넣음
        """
        if shiny is None:
            shiny = random.random() < SHINY_CHANCE
        extra = {"traded": traded, "replace": replace}
        threading.Thread(target=self._fetch, args=(num, shiny, save, wild, stats or {}, extra),
                         daemon=True).start()

    def _fetch(self, num, shiny, save, wild, stats, extra):
        try:
            # PMD(이로치) → PMD(일반) → 5세대 도트 순서. PMD 이로치가 없으면 일반으로.
            path = assets.download_pmd(num, shiny)
            if path is None and shiny:
                path = assets.download_pmd(num, False)
                shiny = False if path else shiny
            if path is None:
                path = assets.download_sprite(num, shiny)
            if not dex.name(num) and num not in KO_NAMES and str(num) not in self.names:
                try:
                    sp = json.loads(http_get(SPECIES_URL.format(num=num)))
                    ko = next((n["name"] for n in sp["names"] if n["language"]["name"] == "ko"), None)
                    if ko:
                        self.names[str(num)] = ko
                except Exception:
                    pass
            info = assets.download_dex(num)
            assets.download_portraits(num)
            self.loaded.put({"num": num, "shiny": shiny, "path": path, "save": save,
                             "wild": wild, "stats": stats, "dex": info, **extra})
        except Exception as ex:
            print(f"#{num} 불러오기 실패: {ex}", file=sys.stderr)
            self.loaded.put({"failed": True, "wild": wild, **extra})

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
            if item.get("replace"):                 # 진화할 모습을 못 받음 → 다음 기회에
                self.cancel_evolution(item["replace"])
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
                if item.get("replace"):
                    self.cancel_evolution(item["replace"])
                return
        num = item["num"]
        if item.get("replace"):
            self.finish_evolution(item["replace"], item)
            return
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
        if item.get("traded"):                      # 착지한 뒤 교환 진화 확인
            self.root.after(2500, lambda: self.try_evolve(pet, traded=True))

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
        save_menu = tk.Menu(m, tearoff=0, font=("맑은 고딕", 9))
        save_menu.add_command(label=f"지금: {self.store.describe()}", state="disabled")
        save_menu.add_command(label="클라우드 폴더로 바꾸기… (학원 ↔ 집 연동)", command=self.choose_save_dir)
        if self.store.save_dir:
            save_menu.add_command(label="이 PC에만 저장하기", command=self.use_local_save)
        m.add_cascade(label="저장 위치", menu=save_menu)
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

    # -------------------------------------------------- hiding
    @property
    def hidden(self):
        return bool(self.hide_reasons)

    def set_hidden(self, reason, on):
        """숨기는 이유("timer", "fullscreen")별로 켜고 끈다. 이유가 하나라도 남아 있으면 숨긴 상태."""
        was = self.hidden
        if on:
            self.hide_reasons.add(reason)
        else:
            self.hide_reasons.discard(reason)
        if self.hidden == was:
            return
        self.log(f"{'숨김' if self.hidden else '다시 보임'} ({reason})")
        for p in self.pets:
            if self.hidden:
                p.win.withdraw()
            else:
                p.win.deiconify()
                p.win.attributes("-topmost", True)
                if reason == "timer" and not p.wild:
                    p.say("다녀왔어!", 1500)
        if self.hidden:
            self.dialog.clear()

    def hide(self, ms):
        self.set_hidden("timer", True)
        self.root.after(ms, lambda: self.set_hidden("timer", False))

    def check_fullscreen(self):
        """영상·발표 같은 전체 화면 앱이 앞에 있으면 숨기고, 끝나면 다시 보인다."""
        own = {screen.hwnd_of(p.win) for p in self.pets} | {screen.hwnd_of(self.dialog.win)}
        self.set_hidden("fullscreen", screen.fullscreen_app_active(own))
        self.root.after(FULLSCREEN_CHECK_MS, self.check_fullscreen)

    def quit(self):
        self.save()
        self.store.release()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
