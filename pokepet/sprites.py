"""스프라이트 로딩: PMD 시트(상태별·방향별 애니메이션)와 5세대 GIF 대체 스프라이트."""
import tkinter as tk
import xml.etree.ElementTree as ET
from collections import namedtuple

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
        # 걷기 한 사이클 동안 몸 길이(옆모습 폭)만큼 나아간다고 보고 자연스러운 이동 속도 계산
        body = max((opaque_cols(i, range(bw - 1, -1, -1)) or 0) - (opaque_cols(i, range(bw)) or 0) + 1
                   for i in boxed["walk"][0])
        # 원본이 크게 그려진 포켓몬(롱스톤, 갸라도스 등)은 덜 확대해서 크기를 비슷하게
        idle_w = max((opaque_cols(i, range(bw - 1, -1, -1)) or 0) - (opaque_cols(i, range(bw)) or 0) + 1
                     for i in boxed["idle"][0])
        scale = PMD_SCALE_BIG if max(idle_w, ground - head + 1) > PMD_BIG else PMD_SCALE
        cycle = sum(boxed["walk"][2]) or 600
        self.walk_speed = STRIDE * body * scale / cycle      # px/ms
        cw, ch = x1 - x0 + 1, y1 - y0 + 1

        def crop(img):
            out = tk.PhotoImage(width=cw, height=ch)
            out.tk.call(out, "copy", img, "-from", x0, y0, x1 + 1, y1 + 1)
            return out.zoom(scale)

        self.anims = {s: Anim([crop(i) for i in l], [crop(i) for i in r], d)
                      for s, (l, r, d) in boxed.items()}
        self.scale = scale
        self.w, self.h = cw * scale, ch * scale
        self.pad_bottom = (y1 - ground) * scale
        self.head_top = (head - y0) * scale
        # 누운 자세 등이 걷기 때 발끝보다 아래로 내려가면 그만큼 올려 그려서 작업표시줄을 넘지 않게
        self.lift = {}
        for s, (l, r, _) in boxed.items():
            low = max(opaque_rows(i, range(bh - 1, -1, -1)) or 0 for i in l + r)
            self.lift[s] = max(0, low - ground) * scale


class GifSprite:
    """GIF 프레임을 합성해 좌/우 방향 확대 이미지 리스트로 보관. 모든 상태가 같은 애니메이션."""
    pause_sleep = True
    walk_speed = None             # 걷기 모션이 없으니 속도 맞추기도 없음
    lift = {}                     # 모든 상태가 같은 프레임이라 보정할 필요 없음

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
