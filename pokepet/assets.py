"""다운로드와 캐시: PMD 스프라이트, 5세대 GIF, 초상화, 도감 데이터 (모두 sprites/ 폴더)."""
import json
from pathlib import Path

from .config import (
    DEFAULT_DEX,
    EMOTIONS,
    PMD_ROOT,
    PMD_VERSION,
    POKEMON_URL,
    PORTRAIT_URL,
    SPECIES_URL,
    SPRITE_DIR,
    SPRITE_SOURCES,
)
from . import dex
from .util import http_get, load_json
from .sprites import parse_anim_data


def download_dex(num):
    """타입·종족값·기초 경험치. 도감 표에 있으면 그걸 쓰고, 없으면 PokeAPI에서 받아 캐시."""
    known = dex.entry(num)
    if known:
        return {k: known[k] for k in ("types", "stats", "base_exp")}
    path = SPRITE_DIR / f"dex-{num}.json"
    cached = load_json(path, None)
    if cached:
        return cached
    try:
        d = json.loads(http_get(POKEMON_URL.format(num=num)))
        info = {"types": [t["type"]["name"] for t in d["types"]],
                "stats": {s["stat"]["name"]: s["base_stat"] for s in d["stats"]},
                "base_exp": d.get("base_experience") or 60}
        path.write_text(json.dumps(info), encoding="utf-8")
        return info
    except Exception:
        return DEFAULT_DEX


def download_portraits(num):
    for emo in EMOTIONS:
        path = SPRITE_DIR / f"portrait-{num}-{emo}.png"
        miss = SPRITE_DIR / f"portrait-{num}-{emo}.none"
        if path.exists() or miss.exists():
            continue
        try:
            path.write_bytes(http_get(PORTRAIT_URL.format(num=num, emo=emo)))
        except Exception:
            miss.write_text("")

def download_pmd(num, shiny):
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

def download_sprite(num, shiny):
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
