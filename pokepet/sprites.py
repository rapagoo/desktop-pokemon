"""스프라이트 로딩: PMD 시트(상태별·방향별 애니메이션)와 5세대 GIF 대체 스프라이트."""
import json
import struct
import tkinter as tk
import xml.etree.ElementTree as ET
import zlib
from collections import namedtuple
from pathlib import Path

from .config import (
    BIG_SPRITE,
    PMD_BIG,
    PMD_ROWS,
    PMD_SCALE,
    PMD_SCALE_BIG,
    PMD_WANTED,
    SCALE,
    STRIDE,
)
from .util import gif_frame_info


# 스프라이트 공통 인터페이스:
#   anims[상태] = Anim(left, right, delays)  (모든 프레임은 같은 크기 w x h)
#   pad_bottom: 프레임 아래쪽의 빈 픽셀 수 (발이 작업표시줄에 닿게)
#   head_top: 대기 모션에서 머리 꼭대기의 y (HP 바·말풍선 위치용)
#   pause_sleep: 잘 때 애니메이션을 멈출지 / static: 정지 이미지라 코드로 움직일지
Anim = namedtuple("Anim", "left right delays")


class LazyFrames:
    """프레임 목록처럼 쓰지만 frames[i]를 처음 꺼낼 때 그 한 장만 만든다.

    포켓몬 하나에 프레임이 80장 안팎이고 큰 포켓몬은 한 장에 20ms 넘게 걸려서, 한꺼번에 만들면
    등장·배틀 때 화면이 멈춘다. 보여 줄 때 한 장씩(또는 한가할 때 warm_step으로) 만든다.
    """

    def __init__(self, count, make):
        self._items = [None] * count
        self._make = make

    def __len__(self):
        return len(self._items)

    def __getitem__(self, i):
        if self._items[i] is None:
            self._items[i] = self._make(i)
        return self._items[i]

    def build_next(self):
        """안 만든 프레임을 하나 만든다. 다 만들었으면 False."""
        for i, item in enumerate(self._items):
            if item is None:
                self[i]
                return True
        return False


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


# ---------------------------------------------------------------- 몸 경계 미리 계산 (Tk 없이)
# 예전에는 Tk 이미지에서 픽셀을 하나씩 물어봐서(transparency_get 수백만 번) 한 마리에 0.7초씩
# 화면이 멈췄다. 이제 다운로드 스레드에서 PNG의 투명도만 직접 읽어 계산하고 meta.json에 저장한다.
META_VERSION = 2                      # 2: 시트 크기(sheets) 추가


def png_alpha(path):
    """RGBA 8비트 PNG의 투명도 채널만 읽는다 -> (폭, 높이, [행마다 bytes]). 다른 형식이면 None.

    PNG 필터는 같은 채널의 바이트끼리만 계산되므로(bpp=4) 4바이트 중 알파만 풀면 된다.
    """
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i, idat = 8, []
    while i < len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        i += 12 + n
        if kind == b"IHDR":
            w, h, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if (depth, color, interlace) != (8, 6, 0):
                return None
        elif kind == b"IDAT":
            idat.append(body)
    raw = zlib.decompress(b"".join(idat))
    stride = w * 4 + 1
    prev = bytes(w)
    rows = []
    for y in range(h):
        line = raw[y * stride:(y + 1) * stride]
        kind, a = line[0], line[4::4]           # 알파 = 각 픽셀의 4번째 바이트
        if kind == 0:
            cur = a
        elif kind == 2:
            cur = bytes((x + p) & 255 for x, p in zip(a, prev))
        else:
            cur = bytearray(w)
            left = up_left = 0
            for k in range(w):
                up = prev[k]
                if kind == 1:
                    v = a[k] + left
                elif kind == 3:
                    v = a[k] + ((left + up) >> 1)
                else:                               # 4: Paeth
                    p = left + up - up_left
                    pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                    v = a[k] + (left if pa <= pb and pa <= pc else up if pb <= pc else up_left)
                left = cur[k] = v & 255
                up_left = up
            cur = bytes(cur)
        rows.append(cur)
        prev = cur
    return w, h, rows


def frame_bounds(rows, x, y, w, h):
    """시트의 (x, y, w, h) 칸에서 불투명 픽셀의 경계 (왼, 위, 오른, 아래). 비어 있으면 None."""
    top = bottom = None
    left, right = w, -1
    for dy in range(h):
        seg = rows[y + dy][x:x + w]
        body = seg.strip(b"\x00")
        if not body:
            continue
        top = dy if top is None else top
        bottom = dy
        lead = len(seg) - len(seg.lstrip(b"\x00"))
        left, right = min(left, lead), max(right, lead + len(body) - 1)
    return None if top is None else (left, top, right, bottom)


def pmd_meta(folder):
    """PMD 폴더의 몸 경계 정보. PmdSprite가 쓰는 공통 박스 좌표(원본 크기) 기준.

    {"box": [x0, y0, x1, y1], "ground", "head", "body", "idle_w", "lift": {상태: px}}
    """
    info = parse_anim_data((folder / "AnimData.xml").read_bytes())
    bw = max(v[1] for v in info.values())
    bh = max(v[2] for v in info.values())
    sheets = {}
    per_state = {}                                  # 상태 -> (왼쪽 프레임 경계들, 오른쪽 프레임 경계들)
    for state, (name, fw, fh, durs) in info.items():
        if name not in sheets:
            sheets[name] = png_alpha(folder / f"{name}-Anim.png")
            if sheets[name] is None:
                return None
        sw, sh, rows = sheets[name]
        nrows, n = sh // fh, min(len(durs), sw // fw)
        ox, oy = (bw - fw) // 2, (bh - fh) // 2     # 셀 중심을 공통 박스 중심에 맞춤
        dirs = []
        for row in PMD_ROWS[state]:
            row = row if row < nrows else 0
            bounds = []
            for k in range(n):
                b = frame_bounds(rows, k * fw, row * fh, fw, fh)
                bounds.append(b and (b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy))
            dirs.append(bounds)
        per_state[state] = dirs
    every = [b for l, r in per_state.values() for b in l + r if b]
    walk, idle = [b for b in per_state["walk"][0] if b], [b for b in per_state["idle"][0] if b]
    ground = max((b[3] for b in walk), default=0)
    return {
        "version": META_VERSION,
        "box": [min(b[0] for b in every), min(b[1] for b in every),
                max(b[2] for b in every), max(b[3] for b in every)],
        "ground": ground,                           # 걷기 프레임의 발끝 = 바닥
        "head": min((b[1] for b in idle), default=bh),
        "body": max((b[2] - b[0] + 1 for b in walk), default=1),
        "idle_w": max((b[2] - b[0] + 1 for b in idle), default=1),
        "sheets": {name: [sh[0], sh[1]] for name, sh in sheets.items()},   # 시트 폭·높이 (프레임 수 계산용)
        "lift": {s: max(0, max((b[3] for b in l + r if b), default=0) - ground)
                 for s, (l, r) in per_state.items()},
    }


def ensure_meta(folder):
    """meta.json이 없거나 옛 버전이면 계산해서 저장 (다운로드 스레드에서 호출)."""
    path = folder / "meta.json"
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        if meta.get("version") == META_VERSION:
            return meta
    except (OSError, ValueError):
        pass
    meta = pmd_meta(folder)
    if meta:
        path.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def opaque_rows(img, rows, step=1):
    """rows 순서대로 훑어서 불투명 픽셀이 처음 나오는 y. 없으면 None. (GIF 대체 스프라이트용, 느림)"""
    w = img.width()
    for y in rows:
        for x in range(0, w, step):
            if not img.transparency_get(x, y):
                return y
    return None


class PmdSprite:
    """PMD 스프라이트 시트에서 상태별·방향별 프레임을 잘라 같은 크기로 맞춘다."""
    pause_sleep = False
    static = False

    def __init__(self, folder):
        # 몸 경계는 다운로드 스레드에서 미리 계산해 둔 meta.json (없으면 여기서 계산, 수십 ms)
        meta = ensure_meta(folder)
        info = parse_anim_data((folder / "AnimData.xml").read_bytes())
        bw = max(v[1] for v in info.values())
        bh = max(v[2] for v in info.values())
        x0, y0, x1, y1 = meta["box"]                 # 모든 프레임의 불투명 영역 = 잘라 낼 크기
        ground, head = meta["ground"], meta["head"]  # 걷기 발끝 = 바닥, 대기 머리 꼭대기
        cw, ch = x1 - x0 + 1, y1 - y0 + 1
        # 원본이 크게 그려진 포켓몬(롱스톤, 갸라도스 등)은 덜 확대해서 크기를 비슷하게
        scale = PMD_SCALE_BIG if max(meta["idle_w"], ground - head + 1) > PMD_BIG else PMD_SCALE

        sheets = {}

        strips = meta.get("strips") or {}

        def frames_of(state, row):
            """한 방향의 프레임 목록. 각 프레임은 처음 쓸 때 잘라 확대한다 (copy 한 번).

            미리 만든 스트립(prep.py)이 있으면 그 작은 이미지에서, 없으면 원본 시트에서 자른다.
            """
            name, fw, fh, durs = info[state]
            sw, sh = meta["sheets"][name]
            nrows, n = sh // fh, min(len(durs), sw // fw)
            key = f"{state}-{row}"
            if key in strips:
                file = folder / f"strip-{key}.png"

                def from_strip(k):
                    if file not in sheets:
                        sheets[file] = tk.PhotoImage(file=str(file))
                    img = tk.PhotoImage(width=cw * scale, height=ch * scale)
                    img.tk.call(img, "copy", sheets[file], "-from", k * cw, 0, (k + 1) * cw, ch,
                                "-zoom", scale)
                    return img
                return LazyFrames(strips[key], from_strip), durs[:strips[key]]
            row = row if row < nrows else 0
            ox, oy = (bw - fw) // 2 - x0, (bh - fh) // 2 - y0     # 셀 중심을 공통 박스 중심에 맞춘 뒤 자르기

            def make(k):
                if name not in sheets:
                    sheets[name] = tk.PhotoImage(file=str(folder / f"{name}-Anim.png"))
                sx0, sy0 = k * fw + max(0, -ox), row * fh + max(0, -oy)
                sx1, sy1 = k * fw + min(fw, cw - ox), row * fh + min(fh, ch - oy)
                img = tk.PhotoImage(width=cw * scale, height=ch * scale)
                if sx1 > sx0 and sy1 > sy0:
                    img.tk.call(img, "copy", sheets[name], "-from", sx0, sy0, sx1, sy1,
                                "-to", max(0, ox) * scale, max(0, oy) * scale, "-zoom", scale)
                return img
            return LazyFrames(n, make), durs[:n]

        self.anims = {}
        for state in info:
            left_row, right_row = PMD_ROWS[state]
            left, delays = frames_of(state, left_row)
            right = left if right_row == left_row else frames_of(state, right_row)[0]   # 잠자기는 방향 하나
            self.anims[state] = Anim(left, right, delays)
        self._sheets = sheets

        # 걷기 한 사이클 동안 몸 길이(옆모습 폭)만큼 나아간다고 보고 자연스러운 이동 속도 계산
        cycle = sum(self.anims["walk"].delays) or 600
        self.walk_speed = STRIDE * meta["body"] * scale / cycle      # px/ms
        self.scale = scale
        self.w, self.h = cw * scale, ch * scale
        self.pad_bottom = (y1 - ground) * scale
        self.head_top = (head - y0) * scale
        # 누운 자세 등이 걷기 때 발끝보다 아래로 내려가면 그만큼 올려 그려서 작업표시줄을 넘지 않게
        self.lift = {s: v * scale for s, v in meta["lift"].items()}

    def warm_step(self):
        """아직 안 만든 프레임을 한 장 만든다 (한가할 때 조금씩). 할 게 남았으면 True."""
        for anim in self.anims.values():
            if anim.left.build_next() or anim.right.build_next():
                return True
        self._sheets.clear()                        # 다 만들었으면 원본 시트는 메모리에서 버림
        return False


class GifSprite:
    """GIF 프레임을 합성해 좌/우 방향 확대 이미지 리스트로 보관. 모든 상태가 같은 애니메이션."""
    pause_sleep = True
    walk_speed = None             # 걷기 모션이 없으니 속도 맞추기도 없음
    lift = {}                     # 모든 상태가 같은 프레임이라 보정할 필요 없음

    def warm_step(self):
        return False              # 처음에 다 만들어 둠

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
