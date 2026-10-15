"""도감 데이터 (pokepet/data/dex.json, tools/build_dex.py로 생성)와 그걸 쓰는 규칙들.

화면·네트워크와 무관한 순수 함수라 tests/test_dex.py 에서 바로 검사한다.

  min_level(num)        야생에서 나올 수 있는 최소 레벨 (리자드 16, 리자몽 36 …)
  wild_candidates(lv)   그 레벨에 나올 수 있는 포켓몬과 가중치(포획률 기반 희귀도)
  pick_wild(lv)         야생 포켓몬 하나 고르기
  evolution_for(...)    지금 조건(레벨·친밀도·시간·교환)으로 진화할 대상
"""
import json
import random
from functools import lru_cache
from pathlib import Path

from .config import (
    EVO_FALLBACK_LEVEL,
    FRIENDSHIP_PATS,
    LEGEND_MIN_LEVEL,
    WILD_OVERLEVEL,
)

DATA_FILE = Path(__file__).resolve().parent / "data" / "dex.json"
DATA = {int(k): v for k, v in json.loads(DATA_FILE.read_text(encoding="utf-8")).items()}


def entry(num):
    return DATA.get(num)


def name(num):
    e = entry(num)
    return e["name"] if e else None


def is_day(hour):
    """원작처럼 낮/밤 구분. 낮 06~18시 (학원), 밤 18~06시 (집)."""
    return 6 <= hour < 18


# ---------------------------------------------------------------- 레벨
def evo_level(src, evo):
    """진화가 일어나는 레벨. 레벨 진화가 아니면 대체 레벨 (진화 전 최소 레벨 + 10 이상)."""
    if evo["method"] == "level":
        return evo["level"]
    return max(min_level(src) + 10, EVO_FALLBACK_LEVEL[evo["method"]])


@lru_cache(maxsize=None)
def min_level(num):
    """야생에서 나올 수 있는 최소 레벨."""
    e = entry(num)
    if e["legendary"]:
        return LEGEND_MIN_LEVEL
    prev = e["from"]
    if prev is None or entry(prev)["baby"]:      # 피츄의 진화형 피카츄는 기본형 취급
        return 2
    rec = next((x for x in entry(prev)["evo"] if x["to"] == num), None)
    return evo_level(prev, rec) if rec else 2


def max_level(num):
    """진화하고도 한참 지난 레벨에는 진화 전 모습으로 나오지 않게."""
    evos = entry(num)["evo"]
    if not evos:
        return 100
    return min(evo_level(num, e) for e in evos) + WILD_OVERLEVEL


# ---------------------------------------------------------------- 야생 등장
def wild_candidates(level):
    """{번호: 가중치}. 아기 포켓몬은 야생에 안 나옴. 포획률이 높을수록 흔하다."""
    out = {}
    for num, e in DATA.items():
        if e["baby"] or not (min_level(num) <= level <= max_level(num)):
            continue
        out[num] = e["capture"] ** 0.7           # 255(구구) ≈ 48, 45(미뇽) ≈ 14, 3(전설) ≈ 2
    return out


def pick_wild(level, rng=random):
    cands = wild_candidates(level) or {n: 1 for n, e in DATA.items() if min_level(n) == 2}
    nums = list(cands)
    return rng.choices(nums, weights=[cands[n] for n in nums])[0]


# ---------------------------------------------------------------- 진화
def evolution_for(num, level, friendship, hour, traded=False, rng=random):
    """진화 조건을 만족하는 대상 번호 (없으면 None).

    - level      : 진화 레벨 도달
    - stone/other: 대체 레벨 도달 (이 게임엔 진화의 돌이 없음)
    - friendship : 쓰다듬은 횟수 FRIENDSHIP_PATS 이상 (+ 낮/밤 조건)
    - trade      : 다른 PC로 옮겨 가서 깨어났을 때 (학원 ↔ 집 = 통신 교환)
    친밀도 진화가 가능하면 그쪽을 먼저 (이브이: 에브이/블래키가 돌 진화보다 우선).
    """
    e = entry(num)
    if not e:
        return None
    friendly, others = [], []
    for evo in e["evo"]:
        m = evo["method"]
        if m == "trade":
            if traded:
                others.append(evo["to"])
        elif m == "friendship":
            time = evo.get("time")
            if friendship >= FRIENDSHIP_PATS and (time is None or (time == "day") == is_day(hour)):
                friendly.append(evo["to"])
        elif level >= evo_level(num, evo):
            others.append(evo["to"])
    pool = friendly or others
    return rng.choice(pool) if pool else None


def evolution_hint(num, friendship=0):
    """관리 창에 보여 줄 '다음 진화' 안내. 진화하지 않으면 None.

    예: "리자드까지 Lv.16", "피카츄: 쓰다듬기 12/30", "팬텀: 다른 PC에서 켜면", "블래키: 쓰다듬기 30/30 (밤)"
    """
    e = entry(num)
    if not e or not e["evo"]:
        return None
    parts = []
    order = {"friendship": 0, "trade": 1}               # 직접 노릴 수 있는 진화를 먼저 보여 줌
    for evo in sorted(e["evo"], key=lambda x: order.get(x["method"], 2)):
        to = name(evo["to"])
        m = evo["method"]
        if m == "trade":
            parts.append(f"{to}: 다른 PC에서 켜면")
        elif m == "friendship":
            when = {"day": " (낮)", "night": " (밤)"}.get(evo.get("time"), "")
            parts.append(f"{to}: 쓰다듬기 {min(friendship, FRIENDSHIP_PATS)}/{FRIENDSHIP_PATS}{when}")
        else:
            parts.append(f"{to}까지 Lv.{evo_level(num, evo)}")
    if len(parts) > 2:                                   # 이브이처럼 갈래가 많으면 줄여서
        return " / ".join(parts[:2]) + f" 외 {len(parts) - 2}가지"
    return " / ".join(parts)
