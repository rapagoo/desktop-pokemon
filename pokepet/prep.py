"""PMD 폴더 준비 (별도 프로세스에서 실행): 몸 경계(meta.json) + 쓰는 프레임만 잘라 낸 작은 스트립 PNG.

    python -m pokepet.prep <pmd 폴더>

시트 PNG는 8방향 전부가 들어 있어 크다 (갸라도스 원거리 공격 시트 1248x1024, Tk로 읽는 데 0.4초).
실제로 쓰는 건 왼쪽/오른쪽 두 줄뿐이라, 그 프레임들만 (몸 경계로 잘라) 가로로 이어 붙인 스트립을
미리 만들어 두면 화면 쪽은 훨씬 작은 이미지만 읽으면 된다.
화면과 같은 프로세스에서 하면 그동안 애니메이션이 멈추므로 다운로드 스레드가 이 모듈을 따로 띄운다.
"""
import json
import sys
import tkinter as tk
from pathlib import Path

from .config import PMD_ROWS
from .sprites import META_VERSION, ensure_meta, parse_anim_data


def strip_name(state, row):
    return f"strip-{state}-{row}.png"


def make_strips(folder):
    folder = Path(folder)
    meta = ensure_meta(folder)
    if not meta:
        return None
    if meta.get("strips"):
        return meta
    info = parse_anim_data((folder / "AnimData.xml").read_bytes())
    bw = max(v[1] for v in info.values())
    bh = max(v[2] for v in info.values())
    x0, y0, x1, y1 = meta["box"]
    cw, ch = x1 - x0 + 1, y1 - y0 + 1

    root = tk.Tk()
    root.withdraw()
    sheets, strips = {}, {}
    for state, (name, fw, fh, durs) in info.items():
        sw, sh = meta["sheets"][name]
        nrows, n = sh // fh, min(len(durs), sw // fw)
        ox, oy = (bw - fw) // 2 - x0, (bh - fh) // 2 - y0
        for row in set(PMD_ROWS[state]):
            r = row if row < nrows else 0
            if name not in sheets:
                sheets[name] = tk.PhotoImage(file=str(folder / f"{name}-Anim.png"))
            strip = tk.PhotoImage(width=cw * n, height=ch)
            for k in range(n):
                sx0, sy0 = k * fw + max(0, -ox), r * fh + max(0, -oy)
                sx1, sy1 = k * fw + min(fw, cw - ox), r * fh + min(fh, ch - oy)
                if sx1 > sx0 and sy1 > sy0:
                    strip.tk.call(strip, "copy", sheets[name], "-from", sx0, sy0, sx1, sy1,
                                  "-to", k * cw + max(0, ox), max(0, oy))
            strip.write(str(folder / strip_name(state, row)), format="png")
            strips[f"{state}-{row}"] = n
    root.destroy()
    meta["strips"] = strips
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


if __name__ == "__main__":
    ok = make_strips(sys.argv[1])
    sys.exit(0 if ok and ok.get("version") == META_VERSION else 1)
