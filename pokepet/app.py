"""전체 조립: 포켓몬 불러오기, 메인 루프, 우클릭 메뉴, 숨기기, 저장."""
import ctypes
import json
import queue
from collections import OrderedDict
import random
import shutil
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .config import (
    AUTOSAVE_MS,
    AUTO_HIDE_FULLSCREEN,
    DEFAULT_PARTY,
    FULLSCREEN_CHECK_MS,
    FIRST_SPAWN_MS,
    GREETS,
    HOTKEY,
    KO_NAMES,
    MAX_NUM,
    MAX_PARTY,
    NAMES_FILE,
    PARTY_FILE,
    SETTINGS_FILE,
    SHINY_CHANCE,
    SPECIES_URL,
    SPRITE_DIR,
    SPRITE_SPARE,
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
from .manager import Manager
from .pet import Pet


class App(BattleMixin, EvolutionMixin):
    def __init__(self, debug=False, instance=None):
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
        self.sprites = OrderedDict()  # 스프라이트 캐시 (최근에 쓴 것이 뒤). prune_sprites 로 정리
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
        rec = self.store.load() or self.store.parse([{"num": n} for n in DEFAULT_PARTY])
        if not rec["party"] and not rec["box"]:
            rec["party"] = [{"num": n} for n in DEFAULT_PARTY]
        self.loading = 0                  # 불러오는 중인 파티 포켓몬 수 (0이 될 때까지 저장 안 함)
        self.restore(rec)
        self.heartbeat()
        self.root.after(AUTOSAVE_MS, self.autosave)

        self.menu = tk.Menu(self.root, tearoff=0, font=("맑은 고딕", 9))
        self.manager = None               # 관리 창 (처음 열 때 만듦)
        self.hotkeys = screen.start_hotkey(HOTKEY)   # Ctrl+Alt+P 또는 두 번째 실행 → 관리 창
        if instance:
            screen.listen_wake(instance, self.hotkeys)
        self.auto_hide = self.store.get_setting("auto_hide", AUTO_HIDE_FULLSCREEN)
        self.root.after(TICK, self.loop)
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
            if traded:
                self.arrivals["count"] += 1
                self.arrivals["from"] = self.store.label(p["machine"])
            self.loading += 1
            self.request(p["num"], p.get("shiny", False), save=False, traded=traded, record=p,
                         stats={k: p[k] for k in ("level", "exp", "hp", "friendship") if k in p})

    def restore(self, rec):
        """저장 기록(파티·보관함·도감·기록)으로 진행 상황을 채운다."""
        self.unloaded = []                # 불러오기에 실패한 포켓몬 기록 (저장할 때 그대로 유지)
        self.arrivals = {"count": 0, "from": None, "seen": 0}   # 다른 PC에서 건너온 포켓몬 (교환)
        self.box = list(rec["box"])       # 보관함: 파티 밖의 포켓몬 기록
        self.seen = set(rec["seen"])      # 도감: 만난 포켓몬 번호
        self.caught = set(rec["caught"])  # 도감: 잡은 포켓몬 번호 (진화·교환으로 얻은 것 포함)
        self.events = list(rec["log"])    # 기록 탭
        self.load_party(rec["party"])

    def replace_party(self, rec):
        """다른 PC에서 저장한 기록으로 바꾼다 (지금 화면의 내 포켓몬은 정리)."""
        if self.battle:
            self.abort_battle()
        for p in self.party():
            self.pets.remove(p)
            p.destroy()
        self.restore(rec)

    def pet_record(self, p):
        return {"num": p.num, "shiny": p.shiny, "level": p.level, "exp": p.exp,
                "hp": round(p.hp), "friendship": p.friendship, "machine": self.store.machine}

    def add_event(self, text):
        """기록 탭에 남길 일 (포획, 진화, 레벨 업 등)."""
        self.events.append({"t": time.time(), "pc": self.store.nickname, "text": text})
        self.log(f"기록: {text}")
        self.refresh_manager()

    def mark_caught(self, num):
        self.seen.add(num)
        self.caught.add(num)

    def save(self):
        if self.loading:                  # 파티를 다 불러오기 전에 저장하면 일부가 빠짐
            return
        party = [self.pet_record(p) for p in self.party()] + self.unloaded
        state = {"party": party, "box": self.box, "seen": self.seen, "caught": self.caught,
                 "log": self.events}
        try:
            where = self.store.save(state)
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

    def autosave(self):
        """쓰다듬기·HP처럼 따로 저장 시점이 없는 진행 상황을 위해 주기적으로 저장."""
        self.save()
        self.root.after(AUTOSAVE_MS, self.autosave)

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
            where = found["machines"].get(found["machine"]) or found["machine"] or "다른 PC"
            use_found = messagebox.askyesno(
                "저장 위치 바꾸기",
                f"그 폴더에 {where}에서 저장한 기록이 있어요.\n"
                f"(포켓몬 {len(found['party'])}마리, 최고 Lv.{top})\n\n"
                "그 기록으로 바꿀까요?\n아니요를 누르면 지금 이 PC의 기록으로 덮어써요.")
            if use_found:
                self.replace_party(self.store.load())
            else:
                self.store.loaded_at = found["saved_at"]
                self.save()
        else:
            self.save()
        self.store.heartbeat()
        self.log(f"저장 위치: {self.store.describe()}")

    def ask_nickname(self):
        """교환 대화창 등에 쓰는 이 PC의 별명 ("학원", "집")."""
        name = simpledialog.askstring("이 PC 별명", "이 PC를 뭐라고 부를까요? (예: 학원, 집)",
                                      initialvalue=self.store.nickname, parent=self.root)
        if name is not None:
            self.store.set_nickname(name)
            self.save()

    def use_local_save(self):
        self.store.release()
        self.store.set_save_dir(None)
        self.save()

    # -------------------------------------------------- loading
    def request(self, num, shiny=None, save=True, wild=False, stats=None, traded=False, replace=None,
                record=None):
        """포켓몬을 백그라운드에서 받아 화면에 올린다.

        traded : 다른 PC에서 옮겨 와서 깨어남 (교환 진화 확인)
        replace: 진화 — 이 포켓몬 자리에 새 모습으로 바꿔 넣음
        record : 저장 파일에서 불러온 원래 기록 (불러오기에 실패하면 그대로 보존)
        """
        if shiny is None:
            shiny = random.random() < SHINY_CHANCE
        extra = {"traded": traded, "replace": replace, "record": record}
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

    def prune_sprites(self):
        """화면에 없는 포켓몬의 스프라이트는 최근 몇 개만 남기고 버린다.

        스프라이트 하나가 6~7MB라서, 야생 포켓몬을 계속 캐시하면 하루에 1GB 가까이 쌓인다.
        파일 캐시(sprites/)는 그대로라 다시 나오면 디스크에서 금방 다시 읽는다.
        """
        in_use = {id(p.sp) for p in self.pets}
        spare = [k for k, s in self.sprites.items() if id(s) not in in_use]   # 오래된 것부터
        for key in spare[:max(0, len(spare) - SPRITE_SPARE)]:
            del self.sprites[key]

    def portrait(self, num, emotion, zoom=2):
        """표정 초상화 (원본 40px, zoom배). 없으면 Normal, 그것도 없으면 None."""
        for emo in (emotion, "Normal"):
            key = (num, emo, zoom)
            if key in self.portraits:
                return self.portraits[key]
            path = SPRITE_DIR / f"portrait-{num}-{emo}.png"
            if path.exists():
                try:
                    self.portraits[key] = tk.PhotoImage(file=str(path)).zoom(zoom)
                    return self.portraits[key]
                except tk.TclError:
                    pass
        return None

    def _spawn(self, item):
        if item.get("record") is not None:
            self.loading -= 1
        if item.get("failed"):
            if item.get("record") is not None:
                self.unloaded.append(item["record"])
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
                if item.get("record") is not None:
                    self.unloaded.append(item["record"])
                return
        self.sprites.move_to_end(key)
        num = item["num"]
        if item.get("replace"):
            self.finish_evolution(item["replace"], item)
            self.prune_sprites()
            return
        pet = Pet(self, num, item["shiny"], self.sprites[key], poke_name(num, self.names),
                  item["dex"], wild=item["wild"], **item["stats"])
        if self.hidden:
            pet.win.withdraw()
        self.pets.append(pet)
        self.prune_sprites()
        if not item["wild"]:               # 야생은 실제로 화면에 들어왔을 때 '만남' (battle.py)
            self.mark_caught(num)
        self.refresh_manager()
        if item["wild"]:
            self.wild, self.spawning = pet, False
            self.dialog.push(pet, "Determined",
                             f"야생 {josa(pet.name, '이가')} 나타났다! (Lv.{pet.level})")
        if item["save"]:
            self.save()
        if item.get("traded"):                      # 다른 PC에서 옴: 옆에서 걸어 들어옴
            pet.arrive(self.arrivals["seen"])
            self.arrivals["seen"] += 1

    # -------------------------------------------------- main loop
    def loop(self):
        while not self.loaded.empty():
            self._spawn(self.loaded.get())
        while not self.hotkeys.empty():               # Ctrl+Alt+P 또는 두 번째 실행
            self.hotkeys.get()
            self.log("관리 창 열기 (단축키 또는 다시 실행)")
            self.open_manager()
        if not self.hidden:
            for p in list(self.pets):
                p.tick(TICK)
            self.meet()
            self.battle_tick(TICK)
        self.warm_up()
        self.root.after(TICK, self.loop)

    def warm_up(self):
        """배틀·기절 모션 프레임을 미리 조금씩 만든다 (0.2초마다 한 묶음, 한 번에 40ms 안쪽).

        한꺼번에 만들면 배틀이 시작될 때 화면이 잠깐 멈추기 때문.
        """
        self.warm_t = getattr(self, "warm_t", 0) + TICK
        if self.warm_t < 200:
            return
        self.warm_t = 0
        for sp in {id(p.sp): p.sp for p in self.pets}.values():
            if sp.warm_step():
                return

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
        m.add_command(label="관리 창 열기  (Ctrl+Alt+P)", command=self.open_manager)
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
        save_menu.add_separator()
        save_menu.add_command(label=f"이 PC 별명: {self.store.nickname}  (바꾸기…)", command=self.ask_nickname)
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
            if len(self.party()) >= MAX_PARTY:          # 파티가 가득 차면 보관함으로
                self.box.append({"num": n, "level": START_LEVEL, "machine": self.store.machine})
                self.mark_caught(n)
                self.save()
                self.refresh_manager()
            else:
                self.request(n)

    def take_off_screen(self, pet):
        """화면에서 포켓몬 창을 치운다 (배틀 중이면 배틀 취소)."""
        if self.battle and pet in (self.battle["ally"], self.wild):
            self.abort_battle()
        if pet is self.wild:
            self.wild_gone(pet)
        elif pet in self.pets:
            self.pets.remove(pet)
            pet.destroy()

    def remove(self, pet):
        """돌려보내기. 내 포켓몬은 영영 사라지므로 한 번 더 묻는다."""
        if not pet.wild and not messagebox.askyesno(
                "돌려보내기", f"{josa(pet.name, '을를')} 정말 돌려보낼까요? (Lv.{pet.level})\n"
                "돌려보낸 포켓몬은 다시 불러올 수 없어요.\n\n보관함으로 보내려면 관리 창(Ctrl+Alt+P)을 쓰세요.",
                icon="warning", parent=self.root):
            return
        pet.say("바이바이~", 800)

        def bye():
            if pet in self.pets:
                if not pet.wild:
                    self.add_event(f"{pet.name}(Lv.{pet.level})을(를) 돌려보냈다")
                self.take_off_screen(pet)
                self.save()
                self.refresh_manager()
        self.root.after(800, bye)

    # -------------------------------------------------- box (보관함)
    def to_box(self, pet):
        if pet not in self.party() or len(self.party()) <= 1 or pet.state in ("battle", "evolving"):
            return False
        self.box.append(self.pet_record(pet))
        pet.say("다녀올게!", 800)
        self.root.after(600, lambda: (self.take_off_screen(pet), self.save(), self.refresh_manager()))
        return True

    def from_box(self, index):
        if len(self.party()) >= MAX_PARTY or not (0 <= index < len(self.box)):
            return False
        rec = self.box.pop(index)
        self.loading += 1                 # 실패하면 unloaded로 보존됨
        self.request(rec["num"], rec.get("shiny", False), save=True, record=rec,
                     stats={k: rec[k] for k in ("level", "exp", "hp", "friendship") if k in rec})
        self.refresh_manager()
        return True

    def release_from_box(self, index):
        if not (0 <= index < len(self.box)):
            return
        rec = self.box[index]
        name = poke_name(rec["num"], self.names)
        if messagebox.askyesno("놓아주기", f"보관함의 {josa(name, '을를')} 정말 놓아줄까요? "
                               f"(Lv.{rec.get('level', START_LEVEL)})\n다시 불러올 수 없어요.",
                               icon="warning", parent=self.manager.win if self.manager else self.root):
            self.box.pop(index)
            self.add_event(f"보관함의 {name}(Lv.{rec.get('level', START_LEVEL)})을(를) 놓아줬다")
            self.save()
            self.refresh_manager()

    # -------------------------------------------------- 관리 창
    def open_manager(self, tab=None):
        if self.manager is None:
            self.manager = Manager(self)
        self.manager.show(tab)

    def refresh_manager(self):
        if self.manager is not None:
            self.manager.refresh()

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
        if self.manager is not None:
            own.add(screen.hwnd_of(self.manager.win))
        self.set_hidden("fullscreen", self.auto_hide and screen.fullscreen_app_active(own))
        self.root.after(FULLSCREEN_CHECK_MS, self.check_fullscreen)

    def set_auto_hide(self, on):
        self.auto_hide = bool(on)
        self.store.set_setting("auto_hide", self.auto_hide)

    def quit(self):
        self.save()
        self.store.release()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
