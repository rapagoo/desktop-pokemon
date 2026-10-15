"""바탕화면 포켓몬 - 작업표시줄 위에서 포켓몬들이 돌아다니고 야생 포켓몬과 알아서 싸우는 방치형 데스크톱 펫.

조작법
  - 좌클릭: 쓰다듬기 (자고 있으면 깨어남) / 쓰러진 야생 포켓몬 클릭: 포획
  - 드래그: 집어 들기 / 던지기
  - 우클릭: 메뉴 (상태 보기, 야생 포켓몬 부르기, 돌려보내기, 잠깐 숨기기, 종료)

게임 흐름
  - 1~2분마다 야생 포켓몬이 화면 가장자리에서 걸어 들어와 가장 가까운 내 포켓몬과 싸운다.
  - 이기면 경험치를 얻고 레벨이 오르며, 쓰러진 야생 포켓몬을 클릭하면 잡을 수 있다 (파티 최대 6마리).
  - 지면 잠시 쓰러져 쉬었다가 회복한다.
  - 중요한 순간에는 화면 구석에 표정 초상화 대화창이 뜬다.

스프라이트는 PMD 스타일(PMDCollab/SpriteCollab)의 애니메이션과 초상화를 쓰고,
PMD 스프라이트가 없는 포켓몬은 5세대 도트 GIF로 대신합니다. 처음 한 번만 받아서
sprites/ 폴더에 캐시합니다. 순수 파이썬 표준 라이브러리만 사용.
"""
import ctypes
import json
import math
import queue
import random
import shutil
import struct
import sys
import threading
import tkinter as tk
import urllib.request
import xml.etree.ElementTree as ET
from collections import namedtuple
from pathlib import Path
from tkinter import simpledialog

BASE = Path(__file__).resolve().parent
SPRITE_DIR = BASE / "sprites"
PARTY_FILE = BASE / "party.json"
NAMES_FILE = BASE / "names.json"

# PMD 스프라이트·초상화 (CC BY-NC 4.0, PMDCollab/SpriteCollab)
PMD_ROOT = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master/sprite/"
PORTRAIT_URL = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master/portrait/{num:04d}/{emo}.png"
PMD_VERSION = "v2"       # 쓰는 애니메이션 목록이 바뀌면 올려서 캐시를 다시 받게 함
PMD_SCALE = 3
# 상태별로 쓸 애니메이션 (없으면 다음 후보)
PMD_WANTED = {
    "walk": ["Walk"],
    "idle": ["Idle", "Walk"],
    "sleep": ["Sleep", "EventSleep", "Laying", "Idle", "Walk"],
    "attack": ["Attack", "Strike", "Swing", "Double", "Idle"],
    "shoot": ["Shoot", "Charge", "Attack", "Idle"],
    "hurt": ["Hurt", "Pain", "Idle"],
    "faint": ["Faint", "Laying", "EventSleep", "Sleep", "Idle"],
}
# 시트의 행 = 8방향: 0 아래, 1 오른아래, 2 오른, 3 오른위, 4 위, 5 왼위, 6 왼, 7 왼아래
PMD_ROWS = {"walk": (6, 2), "idle": (7, 1), "sleep": (0, 0), "attack": (6, 2),
            "shoot": (6, 2), "hurt": (6, 2), "faint": (6, 2)}   # (왼쪽 볼 때, 오른쪽 볼 때)
HOLD_LAST = {"faint"}    # 마지막 프레임에서 멈추는 애니메이션
EMOTIONS = ["Normal", "Happy", "Joyous", "Determined", "Pain", "Crying", "Surprised", "Angry"]

# PMD가 없을 때 쓰는 5세대 도트 스프라이트
POKEAPI_ROOT = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/"
SHOWDOWN_ROOT = "https://play.pokemonshowdown.com/sprites/"
# 모두 5세대 도트 스타일. 우선순위대로 시도 (태그, URL 템플릿, 최대 번호)
#  - bw : 공식 BW 애니메이션 (1~649)
#  - g5a: Smogon 팬메이드 BW 스타일 애니메이션
#  - g5 : Smogon 팬메이드 BW 스타일 정지 이미지 (코드로 통통 움직임)
SPRITE_SOURCES = [
    ("bw", POKEAPI_ROOT + "versions/generation-v/black-white/animated/{shiny}{num}.gif", 649),
    ("g5a", SHOWDOWN_ROOT + "gen5ani{shiny_sfx}/{sd}.gif", None),
    ("g5", SHOWDOWN_ROOT + "gen5{shiny_sfx}/{sd}.png", None),
]
SPECIES_URL = "https://pokeapi.co/api/v2/pokemon-species/{num}/"
POKEMON_URL = "https://pokeapi.co/api/v2/pokemon/{num}/"
MAX_NUM = 493            # 4세대까지 (전원 PMD 핵심 모션 보유)
SCALE = 2                # GIF 스프라이트 확대 배율 (큰 스프라이트는 1배)
BIG_SPRITE = 100         # 이 픽셀보다 크면 확대하지 않음
KEY = "#fe00fe"          # 투명 처리할 배경색
TICK = 30                # ms
GRAVITY = 0.9
SHINY_CHANCE = 1 / 40
DEFAULT_PARTY = [25, 133, 4]

# 배틀
START_LEVEL = 5
MAX_PARTY = 6
SPAWN_MS = (60_000, 120_000)     # 야생 포켓몬 등장 간격
FIRST_SPAWN_MS = (15_000, 25_000)
MOVE_POWER = 35                  # 보통 3~4방, 약점이면 2방 정도
FAINT_REST_MS = 45_000           # 쓰러진 뒤 쉬는 시간
DAZED_MS = 9_000                 # 쓰러진 야생 포켓몬을 잡을 수 있는 시간
REGEN_FULL_MS = 90_000           # 평소 HP가 0에서 가득 차는 시간 (잘 때는 3배 빠름)

# 공격 타입 -> {방어 타입: 배율} (1배는 생략)
TYPE_CHART = {
    "normal": {"rock": .5, "ghost": 0, "steel": .5},
    "fire": {"fire": .5, "water": .5, "grass": 2, "ice": 2, "bug": 2, "rock": .5, "dragon": .5, "steel": 2},
    "water": {"fire": 2, "water": .5, "grass": .5, "ground": 2, "rock": 2, "dragon": .5},
    "electric": {"water": 2, "electric": .5, "grass": .5, "ground": 0, "flying": 2, "dragon": .5},
    "grass": {"fire": .5, "water": 2, "grass": .5, "poison": .5, "ground": 2, "flying": .5, "bug": .5,
              "rock": 2, "dragon": .5, "steel": .5},
    "ice": {"fire": .5, "water": .5, "grass": 2, "ice": .5, "ground": 2, "flying": 2, "dragon": 2, "steel": .5},
    "fighting": {"normal": 2, "ice": 2, "poison": .5, "flying": .5, "psychic": .5, "bug": .5, "rock": 2,
                 "ghost": 0, "dark": 2, "steel": 2, "fairy": .5},
    "poison": {"grass": 2, "poison": .5, "ground": .5, "rock": .5, "ghost": .5, "steel": 0, "fairy": 2},
    "ground": {"fire": 2, "electric": 2, "grass": .5, "poison": 2, "flying": 0, "bug": .5, "rock": 2, "steel": 2},
    "flying": {"electric": .5, "grass": 2, "fighting": 2, "bug": 2, "rock": .5, "steel": .5},
    "psychic": {"fighting": 2, "poison": 2, "psychic": .5, "dark": 0, "steel": .5},
    "bug": {"fire": .5, "grass": 2, "fighting": .5, "poison": .5, "flying": .5, "psychic": 2, "ghost": .5,
            "dark": 2, "steel": .5, "fairy": .5},
    "rock": {"fire": 2, "ice": 2, "fighting": .5, "ground": .5, "flying": 2, "bug": 2, "steel": .5},
    "ghost": {"normal": 0, "psychic": 2, "ghost": 2, "dark": .5},
    "dragon": {"dragon": 2, "steel": .5, "fairy": 0},
    "dark": {"fighting": .5, "psychic": 2, "ghost": 2, "dark": .5, "fairy": .5},
    "steel": {"fire": .5, "water": .5, "electric": .5, "ice": 2, "rock": 2, "steel": .5, "fairy": 2},
    "fairy": {"fire": .5, "fighting": 2, "poison": .5, "dragon": 2, "dark": 2, "steel": .5},
}
DEFAULT_DEX = {"types": ["normal"], "base_exp": 60,
               "stats": {k: 50 for k in ("hp", "attack", "defense", "special-attack",
                                         "special-defense", "speed")}}

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
    """GIF를 직접 훑어서 프레임별 (disposal, delay_ms, (x, y, w, h))를 얻는다."""
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
                rect = struct.unpack("<HHHH", data[i:i + 8])
                fp = data[i + 8]
                i += 9 + (3 * 2 ** ((fp & 7) + 1) if fp & 0x80 else 0) + 1
                while data[i]:
                    i += data[i] + 1
                i += 1
                info.append(gce + (rect,))
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


def josa(word, pair):
    """받침에 따라 조사 고르기. josa('피카츄', '이가') -> '피카츄가'"""
    ch = word[-1]
    has_final = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 != 0
    return word + (pair[0] if has_final else pair[1])


def calc_stat(base, level, is_hp=False):
    if is_hp:
        return 2 * base * level // 100 + level + 10
    return 2 * base * level // 100 + 5


def exp_for(level):
    """해당 레벨이 되기 위한 누적 경험치 (원작의 '중간 빠름' 곡선)."""
    return level ** 3


# ---------------------------------------------------------------- sprites
# 스프라이트 공통 인터페이스:
#   anims[상태] = Anim(left, right, delays)  (모든 프레임은 같은 크기 w x h)
#   pad_bottom: 프레임 아래쪽의 빈 픽셀 수 (발이 작업표시줄에 닿게)
#   head_top: 대기 모션에서 머리 꼭대기의 y (HP 바·말풍선 위치용)
#   pause_sleep: 잘 때 애니메이션을 멈출지 / static: 정지 이미지라 코드로 움직일지
Anim = namedtuple("Anim", "left right delays")


def load_sprite(path):
    return PmdSprite(path) if path.is_dir() else GifSprite(path)


def parse_anim_data(xml_bytes):
    """AnimData.xml -> {상태: (시트 이름, 프레임 폭, 프레임 높이, [지속시간 ms])}"""
    raw = {}
    for a in ET.fromstring(xml_bytes).iter("Anim"):
        name = a.findtext("Name")
        if a.findtext("CopyOf"):
            raw[name] = a.findtext("CopyOf")
        else:
            raw[name] = (int(a.findtext("FrameWidth")), int(a.findtext("FrameHeight")),
                         [int(d.text) * 1000 // 60 for d in a.iter("Duration")])
    out = {}
    for state, candidates in PMD_WANTED.items():
        for name in candidates:
            for _ in range(5):                      # CopyOf 따라가기
                if isinstance(raw.get(name), str):
                    name = raw[name]
            if isinstance(raw.get(name), tuple):
                out[state] = (name,) + raw[name]
                break
    return out


def opaque_rows(img, rows, step=1):
    """rows 순서대로 훑어서 불투명 픽셀이 처음 나오는 y. 없으면 None."""
    w = img.width()
    for y in rows:
        for x in range(0, w, step):
            if not img.transparency_get(x, y):
                return y
    return None


def opaque_cols(img, cols, step=2):
    h = img.height()
    for x in cols:
        for y in range(0, h, step):
            if not img.transparency_get(x, y):
                return x
    return None


class PmdSprite:
    """PMD 스프라이트 시트에서 상태별·방향별 프레임을 잘라 같은 크기로 맞춘다."""
    pause_sleep = False
    static = False

    def __init__(self, folder):
        info = parse_anim_data((folder / "AnimData.xml").read_bytes())
        bw = max(v[1] for v in info.values())
        bh = max(v[2] for v in info.values())
        sheets, boxed = {}, {}
        for state, (name, fw, fh, durs) in info.items():
            if name not in sheets:
                sheets[name] = tk.PhotoImage(file=str(folder / f"{name}-Anim.png"))
            sheet = sheets[name]
            rows, n = sheet.height() // fh, min(len(durs), sheet.width() // fw)
            dirs = []
            for row in PMD_ROWS[state]:
                row = row if row < rows else 0
                frames = []
                for k in range(n):             # 셀 중심을 공통 박스 중심에 맞춤
                    img = tk.PhotoImage(width=bw, height=bh)
                    img.tk.call(img, "copy", sheet, "-from", k * fw, row * fh,
                                (k + 1) * fw, (row + 1) * fh, "-to", (bw - fw) // 2, (bh - fh) // 2)
                    frames.append(img)
                dirs.append(frames)
            boxed[state] = (dirs[0], dirs[1], durs[:n])

        # 모든 프레임의 불투명 영역으로 잘라내기 (가장자리부터 훑어서 빨리 끝냄)
        x0, y0, x1, y1 = bw, bh, 0, 0
        for left, right, _ in boxed.values():
            for img in left + right:
                top = opaque_rows(img, range(bh), 2)
                if top is None:
                    continue
                y0 = min(y0, top)
                y1 = max(y1, opaque_rows(img, range(bh - 1, -1, -1), 2))
                x0 = min(x0, opaque_cols(img, range(bw)))
                x1 = max(x1, opaque_cols(img, range(bw - 1, -1, -1)))
        x0, y0 = max(0, x0 - 1), max(0, y0 - 1)          # 2픽셀 간격으로 훑었으니 1픽셀 여유
        x1, y1 = min(bw - 1, x1 + 1), min(bh - 1, y1 + 1)
        # 걷기 프레임의 발끝 = 바닥, 대기 프레임의 머리 꼭대기
        ground = max(opaque_rows(i, range(bh - 1, -1, -1)) or 0 for i in boxed["walk"][0])
        head = min(opaque_rows(i, range(bh)) or bh for i in boxed["idle"][0])
        cw, ch = x1 - x0 + 1, y1 - y0 + 1

        def crop(img):
            out = tk.PhotoImage(width=cw, height=ch)
            out.tk.call(out, "copy", img, "-from", x0, y0, x1 + 1, y1 + 1)
            return out.zoom(PMD_SCALE)

        self.anims = {s: Anim([crop(i) for i in l], [crop(i) for i in r], d)
                      for s, (l, r, d) in boxed.items()}
        self.w, self.h = cw * PMD_SCALE, ch * PMD_SCALE
        self.pad_bottom = (y1 - ground) * PMD_SCALE
        self.head_top = (head - y0) * PMD_SCALE


class GifSprite:
    """GIF 프레임을 합성해 좌/우 방향 확대 이미지 리스트로 보관. 모든 상태가 같은 애니메이션."""
    pause_sleep = True

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

        # disposal 방식에 맞게 프레임 합성.
        # 2(배경으로 복원)는 캔버스 전체가 아니라 그 프레임 영역만 지워야 한다.
        # 다음 프레임이 바뀐 부분만 담고 있으면 나머지는 이전 내용을 그대로 써야 하기 때문.
        frames, base = [], tk.PhotoImage(width=w, height=h)
        for k, img in enumerate(raw):
            disp, _, (rx, ry, rw, rh) = info[k] if k < len(info) else (2, 100, (0, 0, w, h))
            comp = tk.PhotoImage(width=w, height=h)
            comp.tk.call(comp, "copy", base)
            comp.tk.call(comp, "copy", img, "-compositingrule", "overlay")
            frames.append(comp)
            if disp == 2:
                base = tk.PhotoImage(width=w, height=h)
                base.tk.call(base, "copy", comp)
                if rw and rh:
                    hole = tk.PhotoImage(width=rw, height=rh)
                    base.tk.call(base, "copy", hole, "-to", rx, ry, "-compositingrule", "set")
            elif disp != 3:
                base = comp
        delays = [(info[k][1] if k < len(info) else 100) for k in range(len(frames))]
        anim = Anim([f.zoom(scale) for f in frames],                 # 원본은 왼쪽을 봄
                    [f.subsample(-1, 1).zoom(scale) for f in frames], delays)
        self.anims = {s: anim for s in PMD_WANTED}
        self.w, self.h = w * scale, h * scale
        self.static = len(frames) == 1
        self.pad_bottom = (h - 1 - (opaque_rows(frames[0], range(h - 1, -1, -1), 2) or h - 1)) * scale
        self.head_top = (opaque_rows(frames[0], range(h), 2) or 0) * scale

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


# ---------------------------------------------------------------- portrait dialog
class Dialog:
    """화면 오른쪽 아래에 PMD 스타일 대화창 (표정 초상화 + 글)을 차례로 띄운다."""
    SHOW_MS = 3200

    def __init__(self, app):
        self.app = app
        self.queue = []
        self.busy = False
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg="#9fc5e8")
        box = tk.Frame(self.win, bg="#0d1b3d", padx=10, pady=8)
        box.pack(padx=2, pady=2)
        self.face = tk.Label(box, bg="#0d1b3d", bd=0)
        self.face.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        self.title = tk.Label(box, bg="#0d1b3d", fg="#ffd966", anchor="w",
                              font=("맑은 고딕", 10, "bold"))
        self.title.grid(row=0, column=1, sticky="w")
        self.text = tk.Label(box, bg="#0d1b3d", fg="white", anchor="w", justify="left",
                             wraplength=240, font=("맑은 고딕", 10))
        self.text.grid(row=1, column=1, sticky="w")
        self.win.withdraw()
        self.win.bind("<Button-1>", lambda e: self._next())

    def push(self, pet, emotion, text):
        if self.app.hidden:
            return
        self.queue.append((pet.num, pet.display_name, emotion, text))
        if not self.busy:
            self._next()

    def _next(self):
        if not self.queue:
            self.busy = False
            self.win.withdraw()
            return
        self.busy = True
        num, title, emotion, text = self.queue.pop(0)
        img = self.app.portrait(num, emotion)
        self.face.config(image=img or "", width=80 if img else 0)
        self.title.config(text=title)
        self.text.config(text=text)
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        l, t, r, b = self.app.area
        self.win.geometry(f"+{r - w - 16}+{b - h - 16}")
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        token = object()
        self._token = token
        self.app.root.after(self.SHOW_MS, lambda: self._token is token and self._next())


# ---------------------------------------------------------------- pet
class Pet:
    BUBBLE_H = 34
    GROUNDED = ("walk", "idle", "sleep", "battle", "fainted", "dazed", "approach", "leave")

    def __init__(self, app, num, shiny, sprite, name, dex, wild=False,
                 level=START_LEVEL, exp=None, hp=None):
        self.app, self.num, self.shiny, self.sp, self.name = app, num, shiny, sprite, name
        self.dex, self.wild, self.level = dex, wild, level
        self.exp = exp if exp is not None else exp_for(level)
        self.hp = float(hp) if hp is not None else float(self.max_hp)
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
                                           image=sprite.anims["idle"].left[0])
        # HP 바는 머리 위, 말풍선은 그 위
        self.bar_y = max(self.BUBBLE_H - 8, self.BUBBLE_H + sprite.head_top - 10)
        self.bar_ids = []
        self.bubble_ids = []
        self.bubble_ttl = 0

        l, t, r, b = app.area
        self.vx = self.vy = 0.0
        self.facing = random.choice((-1, 1))
        self.anim_name, self.frame, self.frame_t, self.bob_t = "idle", 0, 0, 0
        self.action, self.action_done = None, None
        self.drag = None
        self.pets = 0
        self.cool = 0                 # 다른 포켓몬과 인사 쿨타임
        if wild:                      # 화면 가장자리 밖에서 걸어 들어옴
            self.facing = random.choice((-1, 1))
            self.x = l - self.cw if self.facing > 0 else r
            self.y = self.floor
            self.state, self.state_t = "approach", 0
        else:
            self.x = random.uniform(l, r - self.cw)
            self.y = t - self.ch          # 화면 위에서 떨어지며 등장
            self.state, self.state_t = "fall", 0

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_motion)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Button-3>", self.on_menu)
        self.place()
        if shiny and not wild:
            self.say("✨ 색이 다르다!", 2500)

    # -------------------------------------------------- stats
    @property
    def display_name(self):
        return f"{'야생 ' if self.wild else ''}{'✨' if self.shiny else ''}{self.name} Lv.{self.level}"

    @property
    def max_hp(self):
        return calc_stat(self.dex["stats"]["hp"], self.level, is_hp=True)

    def stat(self, key):
        return calc_stat(self.dex["stats"][key], self.level)

    @property
    def cx(self):
        return self.x + self.cw / 2

    def gain_exp(self, amount):
        """경험치를 얻고 오른 레벨 수를 돌려준다."""
        self.exp += amount
        ups = 0
        while self.exp >= exp_for(self.level + 1) and self.level < 100:
            old = self.max_hp
            self.level += 1
            self.hp += self.max_hp - old
            ups += 1
        return ups

    # -------------------------------------------------- geometry
    @property
    def floor(self):
        return self.app.area[3] - self.ch + self.sp.pad_bottom

    def place(self):
        self.win.geometry(f"{self.cw}x{self.ch}+{int(self.x)}+{int(self.y)}")

    # -------------------------------------------------- speech bubble & HP bar
    def say(self, text, ms=1800):
        for i in self.bubble_ids:
            self.cv.delete(i)
        y = max(14, self.bar_y - 16)
        tid = self.cv.create_text(self.cw // 2, y, text=text, fill="#222",
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

    def draw_bar(self):
        show = self.wild or self.state in ("battle", "fainted") or self.hp < self.max_hp - 0.5
        key = (show, self.level, int(self.hp))
        if key == getattr(self, "_bar_key", None):
            return
        self._bar_key = key
        for i in self.bar_ids:
            self.cv.delete(i)
        self.bar_ids = []
        if not show:
            return
        w, x0, y = 56, self.cw // 2 - 20, self.bar_y
        ratio = max(0.0, self.hp / self.max_hp)
        color = "#3cb043" if ratio > .5 else "#f1c232" if ratio > .2 else "#e06666"
        # 글자는 흰 바탕 위에 (투명색 위에 바로 쓰면 가장자리가 분홍색으로 번짐)
        label = self.cv.create_text(x0 - 5, y + 2, text=f"Lv{self.level}", anchor="e", fill="#111",
                                    font=("맑은 고딕", 8, "bold"))
        lx1, ly1, lx2, ly2 = self.cv.bbox(label)
        self.bar_ids = [
            self.cv.create_rectangle(lx1 - 2, ly1, lx2 + 1, ly2, fill="white", outline="#111"),
            label,
            self.cv.create_rectangle(x0, y, x0 + w, y + 5, fill="#444", outline="#111"),
            self.cv.create_rectangle(x0 + 1, y + 1, x0 + 1 + int((w - 1) * ratio), y + 5,
                                     fill=color, outline=""),
        ]
        self.cv.tag_raise(label)
        for i in self.bubble_ids:
            self.cv.tag_raise(i)

    # -------------------------------------------------- AI
    def play(self, anim, on_done=None):
        """한 번만 재생하는 동작 (공격, 피격 등)."""
        self.action, self.action_done = anim, on_done
        self.anim_name, self.frame, self.frame_t = anim, 0, 0

    def set_state(self, s, duration=None):
        self.state = s
        self.state_t = duration if duration is not None else 0
        if s == "walk":
            self.facing = random.choice((-1, 1))
            self.vx = self.facing * random.uniform(1.2, 2.4)
        elif s in ("idle", "battle", "fainted", "dazed"):
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

    def leave(self):
        """화면 밖으로 걸어 나간다 (야생 포켓몬)."""
        l, t, r, b = self.app.area
        self.state = "leave"
        self.vx = -3.0 if self.cx < (l + r) / 2 else 3.0

    def land(self):
        if self.hp <= 0:
            self.set_state("dazed" if self.wild else "fainted", 5000 if self.wild else 20000)
        elif self.wild:
            self.state = "approach"
        else:
            self.choose_next()

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
                    self.land()
        elif self.state in ("approach", "leave"):
            self.y = self.floor
            self.x += self.vx
            if self.state == "leave" and (self.x + self.cw < l or self.x > r):
                self.app.wild_gone(self)
                return
        elif self.state in ("battle",):
            self.y = self.floor
        elif self.state in ("fainted", "dazed"):
            self.y = self.floor
            self.state_t -= dt
            if self.state_t <= 0:
                if self.state == "fainted":
                    self.hp = self.max_hp
                    self.say("다시 힘이 났어!", 1800)
                    self.set_state("idle", 2000)
                else:
                    self.app.wild_escape(self)
        else:
            self.y = self.floor
            self.state_t -= dt
            if self.state == "walk":
                self.x += self.vx
            if self.state_t <= 0:
                if self.state == "sleep":
                    self.say("하암~", 1200)
                self.choose_next()

        # 평소엔 HP가 천천히 회복 (자면 더 빨리)
        if not self.wild and self.state not in ("battle", "fainted") and self.hp < self.max_hp:
            rate = 3 if self.state == "sleep" else 1
            self.hp = min(self.max_hp, self.hp + self.max_hp * dt * rate / REGEN_FULL_MS)

        # 벽에 부딪히면 반대로 (야생 포켓몬이 들어오고 나갈 때는 제외)
        if self.state not in ("approach", "leave"):
            if self.x < l:
                self.x, self.vx = l, abs(self.vx)
            elif self.x > r - self.cw:
                self.x, self.vx = r - self.cw, -abs(self.vx)
        if self.vx:
            self.facing = 1 if self.vx > 0 else -1

        self.animate(dt)

        if self.bubble_ids:
            self.bubble_ttl -= dt
            if self.bubble_ttl <= 0:
                if self.state == "sleep":
                    self.say(random.choice(["Zzz…", "zZz…", "Zz…"]), 1500)
                else:
                    self.clear_bubble()
        self.draw_bar()
        self.cool = max(0, self.cool - dt)
        self.place()

    def animate(self, dt):
        if self.action:
            name = self.action
        else:
            name = {"walk": "walk", "approach": "walk", "leave": "walk", "sleep": "sleep",
                    "fainted": "faint", "dazed": "faint"}.get(self.state, "idle")
        if name != self.anim_name:
            self.anim_name, self.frame, self.frame_t = name, 0, 0
        anim = self.sp.anims[name]
        frozen = (self.state == "sleep" and self.sp.pause_sleep) or \
                 (name in HOLD_LAST and self.frame == len(anim.left) - 1)
        if not frozen:
            self.frame_t += dt
            while self.frame_t >= anim.delays[self.frame]:
                self.frame_t -= anim.delays[self.frame]
                if self.frame + 1 < len(anim.left):
                    self.frame += 1
                elif self.action:                     # 한 번 재생하는 동작이 끝남
                    done, self.action, self.action_done = self.action_done, None, None
                    if done:
                        done()
                    return self.animate(0)
                elif name in HOLD_LAST:
                    break
                else:
                    self.frame = 0
        frames = anim.right if self.facing > 0 else anim.left
        self.cv.itemconfig(self.img_id, image=frames[self.frame])
        if self.sp.static:
            self.bob_t += dt
            if self.state in ("walk", "approach", "leave"):   # 걸을 땐 통통 튀기
                off = abs(math.sin(self.bob_t / 110)) * 7
            elif self.state in ("idle", "drag", "battle"):   # 가만히 있을 땐 숨쉬기
                off = 2 if (self.bob_t // 550) % 2 else 0
            else:
                off = 0
            self.cv.coords(self.img_id, self.cw // 2, self.ch - int(off))

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
            self.action = None
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
        # 그냥 클릭
        if self.wild:
            if self.state == "dazed":
                self.app.catch(self)
            else:
                self.say(random.choice(["!", "크르르…", "?!"]), 1000)
            return
        if self.state == "sleep":
            self.say("…!? 깼다!", 1500)
            self.set_state("idle", 2000)
            return
        if self.state in ("battle", "fainted"):      # 응원만
            self.say("♥ 힘내!" if self.state == "battle" else "…", 1000)
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

    # -------------------------------------------------- loading
    def request(self, num, shiny=None, save=True, wild=False, stats=None):
        if shiny is None:
            shiny = random.random() < SHINY_CHANCE
        threading.Thread(target=self._fetch, args=(num, shiny, save, wild, stats or {}),
                         daemon=True).start()

    def _fetch(self, num, shiny, save, wild, stats):
        try:
            # PMD(이로치) → PMD(일반) → 5세대 도트 순서. PMD 이로치가 없으면 일반으로.
            path = self._download_pmd(num, shiny)
            if path is None and shiny:
                path = self._download_pmd(num, False)
                shiny = False if path else shiny
            if path is None:
                path = self._download_sprite(num, shiny)
            if num not in KO_NAMES and str(num) not in self.names:
                try:
                    sp = json.loads(http_get(SPECIES_URL.format(num=num)))
                    ko = next((n["name"] for n in sp["names"] if n["language"]["name"] == "ko"), None)
                    if ko:
                        self.names[str(num)] = ko
                except Exception:
                    pass
            dex = self._download_dex(num)
            self._download_portraits(num)
            self.loaded.put({"num": num, "shiny": shiny, "path": path, "save": save,
                             "wild": wild, "stats": stats, "dex": dex})
        except Exception as ex:
            print(f"#{num} 불러오기 실패: {ex}", file=sys.stderr)
            self.loaded.put({"failed": True, "wild": wild})

    @staticmethod
    def _download_dex(num):
        """타입·종족값·기초 경험치 (PokeAPI)를 sprites/dex-<번호>.json 에 캐시."""
        path = SPRITE_DIR / f"dex-{num}.json"
        dex = load_json(path, None)
        if dex:
            return dex
        try:
            d = json.loads(http_get(POKEMON_URL.format(num=num)))
            dex = {"types": [t["type"]["name"] for t in d["types"]],
                   "stats": {s["stat"]["name"]: s["base_stat"] for s in d["stats"]},
                   "base_exp": d.get("base_experience") or 60}
            path.write_text(json.dumps(dex), encoding="utf-8")
            return dex
        except Exception:
            return DEFAULT_DEX

    @staticmethod
    def _download_portraits(num):
        for emo in EMOTIONS:
            path = SPRITE_DIR / f"portrait-{num}-{emo}.png"
            miss = SPRITE_DIR / f"portrait-{num}-{emo}.none"
            if path.exists() or miss.exists():
                continue
            try:
                path.write_bytes(http_get(PORTRAIT_URL.format(num=num, emo=emo)))
            except Exception:
                miss.write_text("")

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

    @staticmethod
    def _download_pmd(num, shiny):
        """PMD 스프라이트 폴더를 받아 sprites/pmd-<번호>/ 에 저장. 없으면 None."""
        folder = SPRITE_DIR / f"pmd-{'s' if shiny else ''}{num}"
        if (folder / f"ready-{PMD_VERSION}").exists():
            return folder
        base = f"{PMD_ROOT}{num:04d}/{'0000/0001/' if shiny else ''}"
        try:
            xml = http_get(base + "AnimData.xml")
            info = parse_anim_data(xml)
            if "walk" not in info:
                return None
            sheets = {v[0]: http_get(base + f"{v[0]}-Anim.png") for v in info.values()}
        except Exception:
            return None
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "AnimData.xml").write_bytes(xml)
        for name, data in sheets.items():
            (folder / f"{name}-Anim.png").write_bytes(data)
        (folder / f"ready-{PMD_VERSION}").write_text("ok")
        return folder

    @staticmethod
    def _download_sprite(num, shiny):
        stem = f"{'s' if shiny else ''}{num}"
        for tag, tmpl, _ in SPRITE_SOURCES:
            cached = SPRITE_DIR / f"{stem}-{tag}{Path(tmpl).suffix}"
            if cached.exists():
                return cached
        sd = None                    # Showdown 스프라이트 이름 (예: iron-treads -> irontreads)
        last = None
        for tag, tmpl, max_num in SPRITE_SOURCES:
            if max_num and num > max_num:
                continue
            if "{sd}" in tmpl and sd is None:
                sd = json.loads(http_get(SPECIES_URL.format(num=num)))["name"].replace("-", "")
            url = tmpl.format(num=num, sd=sd, shiny="shiny/" if shiny else "",
                              shiny_sfx="-shiny" if shiny else "")
            try:
                data = http_get(url)
            except Exception as ex:
                last = ex
                continue
            path = SPRITE_DIR / f"{stem}-{tag}{Path(tmpl).suffix}"
            path.write_bytes(data)
            return path
        raise last or RuntimeError("스프라이트 없음")

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
    def party(self):
        return [p for p in self.pets if not p.wild]

    def spawn_wild(self):
        party = self.party()
        avg = sum(p.level for p in party) / len(party)
        level = max(2, round(avg) + random.randint(-2, 1))
        self.spawning = True
        self.request(random.randint(1, MAX_NUM), save=False, wild=True,
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
            t = min(healthy or targets, key=lambda p: abs(p.cx - w.cx))
            dx = t.cx - w.cx
            w.vx = 2.4 if dx > 0 else -2.4
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
        move_type = att.dex["types"][0]
        eff = 1.0
        for t in dfn.dex["types"]:
            eff *= TYPE_CHART.get(move_type, {}).get(t, 1.0)
        physical = att.stat("attack") >= att.stat("special-attack")
        a_stat = att.stat("attack" if physical else "special-attack")
        d_stat = dfn.stat("defense" if physical else "special-defense")
        base = (2 * att.level / 5 + 2) * MOVE_POWER * a_stat / max(1, d_stat) / 50 + 2
        dmg = 0 if eff == 0 else max(1, int(base * 1.5 * eff * random.uniform(.85, 1)))
        dfn.hp = max(0.0, dfn.hp - dmg)
        note = {0: " 효과가 없다…", .25: " 별로…", .5: " 별로…", 2: " 굉장해!", 4: " 굉장해!!"}.get(eff, "")
        dfn.say(f"-{dmg}{note}", 1100)
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
        if len(self.party()) >= MAX_PARTY:
            wild.say("파티가 가득 찼어!", 1500)
            return
        wild.wild = False
        wild.hp = wild.max_hp
        wild.set_state("idle", 2000)
        wild.say("♥", 1500)
        self.wild = None
        self.spawn_t = random.randint(*SPAWN_MS)
        self.dialog.push(wild, "Joyous", f"{josa(wild.name, '을를')} 잡았다! 잘 부탁해!")
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


if __name__ == "__main__":
    App().run()
