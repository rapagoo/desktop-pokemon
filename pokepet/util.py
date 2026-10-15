"""작은 도우미 함수들: 네트워크, JSON, GIF 해석, 이름·조사, 스탯 계산."""
import ctypes
import json
import struct
import urllib.request

from .config import KO_NAMES


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
    from . import dex                 # 도감 표에 있으면 그 이름 (#1~493)
    if dex.name(num):
        return dex.name(num)
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


def josa_ro(word):
    """'로/으로': 받침이 없거나 ㄹ 받침이면 '로'. josa_ro('블래키') -> '블래키로', josa_ro('롱스톤') -> '롱스톤으로'"""
    ch = word[-1]
    final = (ord(ch) - 0xAC00) % 28 if "가" <= ch <= "힣" else 0
    return word + ("로" if final in (0, 8) else "으로")


def calc_stat(base, level, is_hp=False):
    if is_hp:
        return 2 * base * level // 100 + level + 10
    return 2 * base * level // 100 + 5


def exp_for(level):
    """해당 레벨이 되기 위한 누적 경험치 (원작의 '중간 빠름' 곡선)."""
    return level ** 3
