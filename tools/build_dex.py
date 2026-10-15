"""PokeAPI에서 #1~MAX_NUM 포켓몬 정보를 받아 pokepet/data/dex.json 을 만든다 (개발용, 가끔만 실행).

    python tools/build_dex.py

결과 (번호 -> 정보)
  name        한국어 이름
  types       타입 목록
  stats       종족값 {hp, attack, defense, special-attack, special-defense, speed}
  base_exp    기초 경험치
  capture     포획률 (3=전설급 ~ 255=흔함) → 야생 등장 가중치
  legendary   전설·환상 여부
  baby        아기 포켓몬 여부 (피츄 등)
  from        진화 전 번호 (없으면 null)
  evo         진화 방법 목록 [{to, method, level?, item?, time?}]
              method: level | friendship | stone | trade | other
"""
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pokepet.config import MAX_NUM  # noqa: E402

API = "https://pokeapi.co/api/v2/"
OUT = ROOT / "pokepet" / "data" / "dex.json"
PRIORITY = ["level", "friendship", "stone", "trade", "other"]


def get(url, tries=4):
    req = urllib.request.Request(url if url.startswith("http") else API + url,
                                 headers={"User-Agent": "desktop-pokemon/1.0"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except (TimeoutError, OSError):
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def num_of(url):
    return int(url.rstrip("/").split("/")[-1])


def classify(det):
    """PokeAPI evolution_details 하나 -> (method, 추가정보)."""
    trig = det["trigger"]["name"]
    if trig == "level-up" and det.get("min_level"):
        return "level", {"level": det["min_level"]}
    if trig == "level-up" and det.get("min_happiness"):
        return "friendship", {"time": det.get("time_of_day") or None}
    if trig == "use-item":
        return "stone", {"item": det["item"]["name"]}
    if trig == "trade":
        return "trade", {}
    return "other", {}


def evolutions(chain_node, out):
    """진화 트리를 돌며 {진화 전 번호: [진화 방법...]} 를 채운다."""
    src = num_of(chain_node["species"]["url"])
    for nxt in chain_node["evolves_to"]:
        dst = num_of(nxt["species"]["url"])
        if dst <= MAX_NUM and src <= MAX_NUM:
            options = [classify(d) for d in nxt["evolution_details"]] or [("other", {})]
            method, extra = min(options, key=lambda o: PRIORITY.index(o[0]))
            out.setdefault(src, []).append({"to": dst, "method": method, **extra})
        evolutions(nxt, out)


def main():
    nums = range(1, MAX_NUM + 1)
    with ThreadPoolExecutor(8) as pool:
        species = dict(zip(nums, pool.map(lambda n: get(f"pokemon-species/{n}/"), nums)))
        pokemon = dict(zip(nums, pool.map(lambda n: get(f"pokemon/{n}/"), nums)))
        chain_urls = sorted({s["evolution_chain"]["url"] for s in species.values()})
        chains = list(pool.map(get, chain_urls))
    print(f"species {len(species)}, chains {len(chains)}")

    evo = {}
    for c in chains:
        evolutions(c["chain"], evo)

    # 피오네 → 마나피처럼 환상·전설 포켓몬으로 '진화'하는 데이터는 실제 진화가 아니라 뺀다
    special = {n for n in nums if species[n]["is_legendary"] or species[n]["is_mythical"]}
    evo = {src: [e for e in lst if e["to"] not in special] for src, lst in evo.items()}

    dex = {}
    for n in nums:
        s, p = species[n], pokemon[n]
        prev = s["evolves_from_species"]
        dex[str(n)] = {
            "name": next((x["name"] for x in s["names"] if x["language"]["name"] == "ko"), s["name"]),
            "types": [t["type"]["name"] for t in p["types"]],
            "stats": {x["stat"]["name"]: x["base_stat"] for x in p["stats"]},
            "base_exp": p.get("base_experience") or 60,
            "capture": s["capture_rate"],
            "legendary": bool(s["is_legendary"] or s["is_mythical"]),
            "baby": bool(s["is_baby"]),
            "from": num_of(prev["url"]) if prev and num_of(prev["url"]) <= MAX_NUM else None,
            "evo": evo.get(n, []),
        }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(dex, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
