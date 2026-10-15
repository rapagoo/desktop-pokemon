"""설정값: 경로, 다운로드 주소, 화면·배틀 상수, 타입 상성표, 이름표."""
from pathlib import Path



# 프로젝트 루트 (sprites/, party.json 이 있는 곳)
BASE = Path(__file__).resolve().parent.parent
SPRITE_DIR = BASE / "sprites"
PARTY_FILE = BASE / "party.json"           # 클라우드 저장 위치를 안 정했을 때의 저장 파일
SETTINGS_FILE = BASE / "settings.json"     # 이 PC 전용 설정 (클라우드 저장 폴더 위치 등)
NAMES_FILE = BASE / "names.json"

# PMD 스프라이트·초상화 (CC BY-NC 4.0, PMDCollab/SpriteCollab)
PMD_ROOT = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master/sprite/"
PORTRAIT_URL = "https://raw.githubusercontent.com/PMDCollab/SpriteCollab/master/portrait/{num:04d}/{emo}.png"
PMD_VERSION = "v2"       # 쓰는 애니메이션 목록이 바뀌면 올려서 캐시를 다시 받게 함
PMD_SCALE = 3
PMD_SCALE_BIG = 2        # 원본 몸 크기가 PMD_BIG 픽셀을 넘으면 이 배율로
PMD_BIG = 40
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
SPRITE_SPARE = 4         # 화면에 없는 포켓몬 스프라이트를 메모리에 남겨 둘 개수 (하나에 6~7MB)
GRAVITY = 0.9
# 이동 속도 = 보폭 / 걷기 한 사이클 시간. 보폭은 몸 길이 x STRIDE.
# 화면에서 너무 빠르거나 느리지 않게 속도를 자르고, 그만큼 애니메이션 재생 속도를 같이 바꾼다.
STRIDE = 1.0
SPEED_RANGE = (0.8, 5.0)         # px / tick (초당 약 27~166px)
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

# 진화·야생 등장 (dex.py)
EVO_FALLBACK_LEVEL = {"stone": 30, "friendship": 22, "trade": 36, "other": 32}  # 레벨 진화가 아닐 때
FRIENDSHIP_PATS = 30             # 친밀도 진화에 필요한 쓰다듬기 횟수
LEGEND_MIN_LEVEL = 40            # 전설·환상 포켓몬이 야생에 나오기 시작하는 레벨
WILD_OVERLEVEL = 8               # 진화 레벨을 이만큼 넘으면 진화 전 모습으로는 안 나옴

# 수업 환경
CAPTURE_GUARD = True             # 화면 공유·녹화·스크린샷에 포켓몬이 안 찍히게 (내 화면엔 보임)
AUTO_HIDE_FULLSCREEN = True      # 영상·발표 같은 전체 화면 앱이 앞에 오면 자동으로 숨기기
FULLSCREEN_CHECK_MS = 1_000
AUTOSAVE_MS = 120_000            # 자동 저장 간격 (쓰다듬기·HP 회복 등도 저장되게)
HOTKEY = ("ctrl+alt", "P")       # 관리 창 단축키 (어디서든 동작)


def apply_debug():
    """--debug: 기다리지 않고 바로 테스트할 수 있게 시간을 줄인다. 다른 모듈을 import하기 전에 호출.

    진짜 파티(party.json)를 건드리지 않도록 저장 파일도 따로 쓴다.
    """
    g = globals()
    g.update(SPAWN_MS=(5_000, 8_000), FIRST_SPAWN_MS=(3_000, 3_000), FAINT_REST_MS=8_000,
             DAZED_MS=5_000, REGEN_FULL_MS=20_000, PARTY_FILE=BASE / "party-debug.json",
             SETTINGS_FILE=BASE / "settings-debug.json")

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
