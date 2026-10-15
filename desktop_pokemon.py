"""바탕화면 포켓몬 - 작업표시줄 위에서 포켓몬들이 돌아다니는 데스크톱 펫.

조작법
  - 좌클릭: 쓰다듬기 (자고 있으면 깨어남)
  - 드래그: 집어 들기 / 던지기
  - 우클릭: 메뉴 (포켓몬 추가, 돌려보내기, 잠깐 숨기기, 종료)

스프라이트는 PokeAPI(github.com/PokeAPI/sprites)의 5세대 애니메이션 GIF를
처음 한 번만 받아서 sprites/ 폴더에 캐시합니다. 순수 파이썬 표준 라이브러리만 사용.
"""
import ctypes
import json
import math
import queue
import random
import struct
import sys
import threading
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import simpledialog

BASE = Path(__file__).resolve().parent
SPRITE_DIR = BASE / "sprites"
PARTY_FILE = BASE / "party.json"
NAMES_FILE = BASE / "names.json"

SPRITE_ROOT = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/"
# 우선순위: 5세대 BW 도트 애니(1~649) → Showdown 애니 → 정지 이미지
SPRITE_SOURCES = [
    ("versions/generation-v/black-white/animated/{shiny}{num}.gif", 649),
    ("other/showdown/{shiny}{num}.gif", None),
    ("{shiny}{num}.png", None),
]
SPECIES_URL = "https://pokeapi.co/api/v2/pokemon-species/{num}/"
MAX_NUM = 1025           # 전체 도감
SCALE = 2                # 스프라이트 확대 배율 (큰 스프라이트는 1배)
BIG_SPRITE = 100         # 이 픽셀보다 크면 확대하지 않음
KEY = "#fe00fe"          # 투명 처리할 배경색
TICK = 30                # ms
GRAVITY = 0.9
SHINY_CHANCE = 1 / 40
DEFAULT_PARTY = [25, 133, 4]

KO_NAMES = {
    1: "이상해씨", 4: "파이리", 7: "꼬부기", 25: "피카츄", 39: "푸린", 52: "나옹",
    54: "고라파덕", 94: "팬텀", 129: "잉어킹", 133: "이브이", 143: "잠만보",
    150: "뮤츠", 151: "뮤", 152: "치코리타", 155: "브케인", 158: "리아코",
    175: "토게피", 185: "꼬지모", 196: "에브이", 197: "블래키", 252: "나무지기",
    255: "아차모", 258: "물짱이", 280: "랄토스", 302: "깜까미", 359: "앱솔",
    387: "모부기", 390: "불꽃숭이", 393: "팽도리", 448: "루카리오", 495: "주리비얀",
    498: "뚜꾸리", 501: "수댕이", 570: "조로아", 607: "불켜미",
}

HAPPY = ["♥", "♪", "♥♥", "^ㅁ^", "헤헤", "좋아!"]
GREETS = ["안녕!", "놀자!", "!", "?", "같이 가자"]


# ---------------------------------------------------------------- utilities
def work_area():
    """작업표시줄을 제외한 주 모니터 영역 (left, top, right, bottom)."""
    try:
        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                        ("r", ctypes.c_long), ("b", ctypes.c_long)]
        r = RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0)
        return r.l, r.t, r.r, r.b
    except Exception:
        return None


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "desktop-pokemon/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def gif_frame_info(data):
    """GIF를 직접 훑어서 프레임별 (disposal, delay_ms)를 얻는다."""
    info = []
    try:
        pk = data[10]
        i = 13 + (3 * 2 ** ((pk & 7) + 1) if pk & 0x80 else 0)
        gce = (0, 100)
        while i < len(data):
            b = data[i]
            i += 1
            if b == 0x21:
                label = data[i]
                i += 1
                if label == 0xF9:
                    packed = data[i + 1]
                    delay = struct.unpack("<H", data[i + 2:i + 4])[0] * 10
                    gce = ((packed >> 2) & 7, delay if delay >= 20 else 100)
                while data[i]:
                    i += data[i] + 1
                i += 1
            elif b == 0x2C:
                fp = data[i + 8]
                i += 9 + (3 * 2 ** ((fp & 7) + 1) if fp & 0x80 else 0) + 1
                while data[i]:
                    i += data[i] + 1
                i += 1
                info.append(gce)
                gce = (0, 100)
            else:
                break
    except IndexError:
        pass
    return info


def poke_name(num, names):
    if num in KO_NAMES:
        return KO_NAMES[num]
    return names.get(str(num), f"#{num}")


def chant(name):
    """'피카츄' -> '피카 피카!' 처럼 울음소리 흉내."""
    if name.startswith("#"):
        return "!!"
    s = name[:2]
    return f"{s} {s}!"


# ---------------------------------------------------------------- sprites
class Sprite:
    """GIF 프레임을 합성해 좌/우 방향 확대 이미지 리스트로 보관."""

    def __init__(self, path):
        if path.suffix == ".png":
            info, raw = [], [self._load_png(path)]
        else:
            info = gif_frame_info(path.read_bytes())
            raw = []
            while True:
                try:
                    raw.append(tk.PhotoImage(file=str(path), format=f"gif -index {len(raw)}"))
                except tk.TclError:
                    break
        if not raw:
            raise ValueError("빈 이미지")
        w, h = raw[0].width(), raw[0].height()
        scale = SCALE if max(w, h) <= BIG_SPRITE else 1

        # disposal 방식에 맞게 프레임 합성
        frames, base = [], tk.PhotoImage(width=w, height=h)
        for k, img in enumerate(raw):
            disp = info[k][0] if k < len(info) else 2
            comp = tk.PhotoImage(width=w, height=h)
            comp.tk.call(comp, "copy", base)
            comp.tk.call(comp, "copy", img, "-compositingrule", "overlay")
            frames.append(comp)
            if disp == 1 or disp == 0:
                base = comp
            elif disp == 2:
                base = tk.PhotoImage(width=w, height=h)
        self.delays = [(info[k][1] if k < len(info) else 100) for k in range(len(frames))]
        self.left = [f.zoom(scale) for f in frames]                 # 원본은 왼쪽을 봄
        self.right = [f.subsample(-1, 1).zoom(scale) for f in frames]
        self.w, self.h = w * scale, h * scale
        self.pad_bottom = self._bottom_padding(frames[0]) * scale

    @staticmethod
    def _load_png(path):
        """반투명 픽셀은 투명색 창에서 테두리가 생기므로 완전 투명/불투명으로 정리."""
        img = tk.PhotoImage(file=str(path))
        for y in range(img.height()):
            for x in range(img.width()):
                a = img.tk.call(img, "get", x, y, "-withalpha")[3]
                if 0 < int(a) < 255:
                    img.transparency_set(x, y, int(a) < 128)
        return img

    @staticmethod
    def _bottom_padding(img):
        w, h = img.width(), img.height()
        for y in range(h - 1, -1, -1):
            for x in range(0, w, 2):
                if not img.transparency_get(x, y):
                    return h - 1 - y
        return 0


# ---------------------------------------------------------------- pet
class Pet:
    BUBBLE_H = 30

    def __init__(self, app, num, shiny, sprite, name):
        self.app, self.num, self.shiny, self.sp, self.name = app, num, shiny, sprite, name
        self.cw = max(sprite.w, 120)
        self.ch = sprite.h + self.BUBBLE_H

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg=KEY)
        try:
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        self.cv = tk.Canvas(self.win, width=self.cw, height=self.ch, bg=KEY,
                            highlightthickness=0, bd=0)
        self.cv.pack()
        self.img_id = self.cv.create_image(self.cw // 2, self.ch, anchor="s",
                                           image=sprite.left[0])
        self.bubble_ids = []
        self.bubble_ttl = 0

        l, t, r, b = app.area
        self.x = random.uniform(l, r - self.cw)
        self.y = t - self.ch          # 화면 위에서 떨어지며 등장
        self.vx = self.vy = 0.0
        self.facing = random.choice((-1, 1))
        self.frame, self.frame_t = 0, 0
        self.state, self.state_t = "fall", 0
        self.drag = None
        self.pets = 0
        self.cool = 0                 # 다른 포켓몬과 인사 쿨타임

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_motion)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Button-3>", self.on_menu)
        self.place()
        if shiny:
            self.say("✨ 색이 다르다!", 2500)

    # -------------------------------------------------- geometry
    @property
    def floor(self):
        return self.app.area[3] - self.ch + self.sp.pad_bottom

    def place(self):
        self.win.geometry(f"{self.cw}x{self.ch}+{int(self.x)}+{int(self.y)}")

    # -------------------------------------------------- speech bubble
    def say(self, text, ms=1800):
        for i in self.bubble_ids:
            self.cv.delete(i)
        tid = self.cv.create_text(self.cw // 2, 15, text=text, fill="#222",
                                  font=("맑은 고딕", 9, "bold"))
        x1, y1, x2, y2 = self.cv.bbox(tid)
        rid = self.cv.create_rectangle(x1 - 7, y1 - 3, x2 + 7, y2 + 3,
                                       fill="white", outline="#555")
        self.cv.tag_raise(tid)
        self.bubble_ids = [rid, tid]
        self.bubble_ttl = ms

    def clear_bubble(self):
        for i in self.bubble_ids:
            self.cv.delete(i)
        self.bubble_ids = []

    # -------------------------------------------------- AI
    def set_state(self, s, duration=None):
        self.state = s
        self.state_t = duration if duration is not None else 0
        if s == "walk":
            self.facing = random.choice((-1, 1))
            self.vx = self.facing * random.uniform(1.2, 2.4)
        elif s == "idle":
            self.vx = 0
        elif s == "sleep":
            self.vx = 0
            self.say("Zzz…", duration)
        elif s == "jump":
            self.vy = -random.uniform(9, 13)
            self.state = "fall"

    def choose_next(self):
        r = random.random()
        if r < 0.40:
            self.set_state("idle", random.randint(1500, 5000))
        elif r < 0.85:
            self.set_state("walk", random.randint(2000, 6000))
        elif r < 0.95:
            self.set_state("sleep", random.randint(6000, 15000))
        else:
            self.set_state("jump")
            if random.random() < 0.5:
                self.say(chant(self.name))

    def tick(self, dt):
        l, t, r, b = self.app.area

        if self.state == "drag":
            pass
        elif self.state == "fall":
            self.vy += GRAVITY
            self.x += self.vx
            self.y += self.vy
            if self.y >= self.floor:
                self.y = self.floor
                if self.vy > 6:                      # 통통 튀기
                    self.vy = -self.vy * 0.35
                    self.vx *= 0.6
                else:
                    self.vy = 0
                    self.choose_next()
        else:
            self.y = self.floor
            self.state_t -= dt
            if self.state == "walk":
                self.x += self.vx
            if self.state_t <= 0:
                if self.state == "sleep":
                    self.say("하암~", 1200)
                self.choose_next()

        # 벽에 부딪히면 반대로
        if self.x < l:
            self.x, self.vx = l, abs(self.vx)
        elif self.x > r - self.cw:
            self.x, self.vx = r - self.cw, -abs(self.vx)
        if self.vx:
            self.facing = 1 if self.vx > 0 else -1

        # 애니메이션 (자는 중엔 멈춤)
        if self.state != "sleep":
            self.frame_t += dt
            while self.frame_t >= self.sp.delays[self.frame]:
                self.frame_t -= self.sp.delays[self.frame]
                self.frame = (self.frame + 1) % len(self.sp.left)
        frames = self.sp.right if self.facing > 0 else self.sp.left
        self.cv.itemconfig(self.img_id, image=frames[self.frame])

        if self.bubble_ids:
            self.bubble_ttl -= dt
            if self.bubble_ttl <= 0:
                if self.state == "sleep":
                    self.say(random.choice(["Zzz…", "zZz…", "Zz…"]), 1500)
                else:
                    self.clear_bubble()
        self.cool = max(0, self.cool - dt)
        self.place()

    # -------------------------------------------------- mouse
    def on_press(self, e):
        self.drag = {"ox": e.x_root - self.x, "oy": e.y_root - self.y,
                     "sx": e.x_root, "sy": e.y_root, "moved": False,
                     "hist": [(e.x_root, e.y_root)]}

    def on_motion(self, e):
        d = self.drag
        if not d:
            return
        if not d["moved"] and abs(e.x_root - d["sx"]) + abs(e.y_root - d["sy"]) > 4:
            d["moved"] = True
            self.state = "drag"
            self.say(random.choice(["으앗!", "?!", "내려줘~"]), 99999)
        if d["moved"]:
            self.x, self.y = e.x_root - d["ox"], e.y_root - d["oy"]
            d["hist"] = (d["hist"] + [(e.x_root, e.y_root)])[-4:]
            self.place()

    def on_release(self, e):
        d, self.drag = self.drag, None
        if not d:
            return
        if d["moved"]:                               # 던지기
            (x0, y0), (x1, y1) = d["hist"][0], d["hist"][-1]
            n = max(1, len(d["hist"]) - 1)
            self.vx = max(-25, min(25, (x1 - x0) / n))
            self.vy = max(-25, min(25, (y1 - y0) / n))
            self.state = "fall"
            self.clear_bubble()
            if math.hypot(self.vx, self.vy) > 12:
                self.say("우와아아~!", 1200)
            return
        # 그냥 클릭 = 쓰다듬기
        if self.state == "sleep":
            self.say("…!? 깼다!", 1500)
            self.set_state("idle", 2000)
            return
        self.pets += 1
        if self.pets % 5 == 0:
            self.say("♥♥♥ 최고야!", 2000)
        else:
            self.say(random.choice(HAPPY + [chant(self.name)]), 1300)
        if self.state != "fall":
            self.set_state("jump")

    def on_menu(self, e):
        self.app.show_menu(self, e.x_root, e.y_root)

    def destroy(self):
        self.win.destroy()


# ---------------------------------------------------------------- app
class App:
    def __init__(self):
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
        self.loaded = queue.Queue()
        self.hidden = False

        party = load_json(PARTY_FILE, None) or [{"num": n, "shiny": False} for n in DEFAULT_PARTY]
        for p in party:
            self.request(p["num"], p.get("shiny", False), save=False)

        self.menu = tk.Menu(self.root, tearoff=0, font=("맑은 고딕", 9))
        self.menu_target = None
        self.root.after(TICK, self.loop)

    # -------------------------------------------------- loading
    def request(self, num, shiny=None, save=True):
        if shiny is None:
            shiny = random.random() < SHINY_CHANCE
        threading.Thread(target=self._fetch, args=(num, shiny, save), daemon=True).start()

    def _fetch(self, num, shiny, save):
        try:
            path = self._download_sprite(num, shiny)
            if num not in KO_NAMES and str(num) not in self.names:
                try:
                    sp = json.loads(http_get(SPECIES_URL.format(num=num)))
                    ko = next((n["name"] for n in sp["names"] if n["language"]["name"] == "ko"), None)
                    if ko:
                        self.names[str(num)] = ko
                except Exception:
                    pass
            self.loaded.put((num, shiny, path, save))
        except Exception as ex:
            print(f"#{num} 불러오기 실패: {ex}", file=sys.stderr)

    @staticmethod
    def _download_sprite(num, shiny):
        stem = f"{'s' if shiny else ''}{num}"
        for ext in (".gif", ".png"):
            if (SPRITE_DIR / f"{stem}{ext}").exists():
                return SPRITE_DIR / f"{stem}{ext}"
        last = None
        for tmpl, max_num in SPRITE_SOURCES:
            if max_num and num > max_num:
                continue
            url = SPRITE_ROOT + tmpl.format(num=num, shiny="shiny/" if shiny else "")
            try:
                data = http_get(url)
            except Exception as ex:
                last = ex
                continue
            path = SPRITE_DIR / (stem + Path(tmpl).suffix)
            path.write_bytes(data)
            return path
        raise last or RuntimeError("스프라이트 없음")

    def _spawn(self, num, shiny, path, save):
        key = path.name
        if key not in self.sprites:
            try:
                self.sprites[key] = Sprite(path)
            except Exception as ex:
                print(f"{key} 읽기 실패: {ex}", file=sys.stderr)
                path.unlink(missing_ok=True)
                return
        pet = Pet(self, num, shiny, self.sprites[key], poke_name(num, self.names))
        if self.hidden:
            pet.win.withdraw()
        self.pets.append(pet)
        if save:
            self.save()

    def save(self):
        PARTY_FILE.write_text(json.dumps([{"num": p.num, "shiny": p.shiny} for p in self.pets]),
                              encoding="utf-8")
        NAMES_FILE.write_text(json.dumps(self.names, ensure_ascii=False), encoding="utf-8")

    # -------------------------------------------------- main loop
    def loop(self):
        while not self.loaded.empty():
            self._spawn(*self.loaded.get())
        if not self.hidden:
            for p in self.pets:
                p.tick(TICK)
            self.meet()
        self.root.after(TICK, self.loop)

    def meet(self):
        """걷다가 서로 마주치면 인사."""
        for i, a in enumerate(self.pets):
            for b in self.pets[i + 1:]:
                if a.state in ("walk", "idle") and b.state in ("walk", "idle") \
                        and not a.cool and not b.cool \
                        and abs((a.x + a.cw / 2) - (b.x + b.cw / 2)) < 40:
                    a.cool = b.cool = 15000
                    a.say(random.choice(GREETS))
                    self.root.after(600, lambda b=b: b.say(chant(b.name)))

    # -------------------------------------------------- menu
    def show_menu(self, pet, x, y):
        self.menu_target = pet
        m = self.menu
        m.delete(0, "end")
        m.add_command(label=f"{'✨' if pet.shiny else ''}{pet.name} (#{pet.num})", state="disabled")
        m.add_separator()
        m.add_command(label="랜덤 포켓몬 부르기", command=lambda: self.request(random.randint(1, MAX_NUM)))
        m.add_command(label="도감 번호로 부르기…", command=self.ask_number)
        m.add_command(label=f"{pet.name} 재우기", command=lambda: pet.set_state("sleep", 20000))
        m.add_command(label=f"{pet.name} 돌려보내기", command=lambda: self.remove(pet))
        m.add_separator()
        m.add_command(label="수업 집중! 5분 숨기기", command=lambda: self.hide(5 * 60 * 1000))
        m.add_command(label="종료", command=self.quit)
        m.tk_popup(x, y)

    def ask_number(self):
        n = simpledialog.askinteger("포켓몬 부르기", f"도감 번호 (1~{MAX_NUM})",
                                    minvalue=1, maxvalue=MAX_NUM, parent=self.root)
        if n:
            self.request(n)

    def remove(self, pet):
        pet.say("바이바이~", 800)
        def bye():
            if pet in self.pets:
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
            p.say("다녀왔어!", 1500)

    def quit(self):
        self.save()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
