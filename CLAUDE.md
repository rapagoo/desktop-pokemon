# Desktop Pokémon — 개발 안내

Windows 작업표시줄 위에서 포켓몬이 돌아다니고 야생 포켓몬과 자동으로 싸우는 방치형 데스크톱 펫.
Python 3 표준 라이브러리(tkinter)만 사용한다. 외부 패키지를 추가하지 않는다.

## 대화

- 사용자에게는 **한국어**로 답한다. 코드 주석·사용자에게 보이는 글도 한국어.
- 커밋 메시지는 영어.

## 실행 / 테스트

```
python desktop_pokemon.py            # 보통 실행 (포켓몬 실행.bat 과 같음)
python -m pokepet --debug            # 개발용: 야생 포켓몬이 몇 초마다 등장, 이벤트를 콘솔에 출력,
                                     #         저장은 party-debug.json (진짜 파티는 안 건드림)
python -m pokepet --debug --capturable   # 위 + 스크린샷에 포켓몬이 찍히게
python -m unittest                   # 화면·네트워크 없이 도는 로직 테스트
python -m pyflakes pokepet tests tools  # 빠진 import / 안 쓰는 이름 검사 (pip install pyflakes)
python tools/build_dex.py           # 도감 표(pokepet/data/dex.json) 다시 만들기 (PokeAPI, 1분 정도)
```

화면 동작을 바꿨으면 `--debug --capturable`로 실제로 띄워 확인한다. 스크린샷은 PowerShell
`System.Drawing.Graphics.CopyFromScreen`으로 찍을 수 있다. **기본 실행에서는 포켓몬 창이
캡처에서 빠지므로(`CAPTURE_GUARD`) 스크린샷에 안 찍힌다.**

## 구조 (`pokepet/`)

| 모듈 | 역할 |
|---|---|
| `config.py` | 모든 상수: 경로, 다운로드 주소, 배율·속도·배틀 수치, 타입 상성표, 이름표, `apply_debug()` |
| `util.py` | 작은 순수 함수: `http_get`, GIF 프레임 해석, 조사(`josa`), 스탯·경험치 계산 |
| `assets.py` | 다운로드와 캐시. 모두 `sprites/` 폴더 (gitignore) |
| `sprites.py` | `PmdSprite`(PMD 시트 → 상태별·방향별 프레임), `GifSprite`(대체용) |
| `dialog.py` | 표정 초상화 대화창 |
| `pet.py` | `Pet`: 포켓몬 한 마리의 창·상태 머신·애니메이션·말풍선·HP 바 |
| `storage.py` | `SaveStore`: 로컬 또는 클라우드 폴더 저장, 다른 PC 실행 감지(running.json), 덮어쓰기 방지 |
| `dex.py` | `data/dex.json` 도감 표 + 규칙(순수 함수): 야생 최소 레벨, 야생 후보·희귀도, 진화 조건 |
| `evolution.py` | `EvolutionMixin`: 진화 확인 시점, "…어라!?" 연출, 새 모습으로 교체 |
| `battle.py` | `calc_damage`·`type_effect`(순수 함수) + `BattleMixin`(야생 등장, 배틀, 포획) |
| `screen.py` | Windows API: 화면 공유·녹화에서 창 빼기, 전체 화면 앱 감지 |
| `app.py` | `App(BattleMixin, EvolutionMixin)`: 불러오기, 메인 루프(30ms), 메뉴, 숨기기(이유별 `set_hidden`), 저장 |

- config 값은 각 모듈이 import 시점에 가져간다. 실행 중에 바꾸려면 다른 모듈 import 전에 바꿔야 한다 (`__main__.py` 참고).
- Tk 객체는 메인 스레드에서만 만든다. 다운로드는 스레드에서 하고 `App.loaded` 큐로 넘긴다.

## 스프라이트 규칙 (포켓몬마다 손으로 고치지 말고 데이터에서 규칙을 찾는다)

- 기본은 PMDCollab SpriteCollab (CC BY-NC 4.0). 도감 범위는 #1~493 (전원 핵심 모션 보유).
- 시트 행 = 8방향, 프레임은 셀 중심 정렬. `PMD_WANTED`에 상태별 후보 애니메이션과 대체 순서가 있다.
- 바닥선은 걷기 모션의 발끝. 그보다 내려가는 모션은 `lift`만큼 올려 그린다.
- 이동 속도 = 몸 길이 × `STRIDE` ÷ 걷기 사이클. `SPEED_RANGE`로 자르고 애니메이션 속도를 같이 맞춘다.
- 원본 몸 크기가 `PMD_BIG`을 넘으면 `PMD_SCALE_BIG`(2배), 아니면 `PMD_SCALE`(3배).
- `PMD_WANTED`를 바꾸면 `PMD_VERSION`을 올려서 캐시를 다시 받게 한다.

## 진화·야생 규칙 (`dex.py`, 수치는 `config.py`)

- 야생: 상대할 내 포켓몬을 먼저 고르고 그 레벨 ±2로 등장. 그 레벨에 나올 수 있는 종류만, 포획률^0.7 가중치.
  진화형은 진화 레벨부터, 진화 레벨 + `WILD_OVERLEVEL`이 지나면 진화 전 모습은 안 나옴. 아기 포켓몬은 야생에 없음.
  전설은 `LEGEND_MIN_LEVEL`부터.
- 진화: 레벨 진화는 그대로. 돌·기타는 `EVO_FALLBACK_LEVEL` 레벨에서. 친밀도 = 쓰다듬기 `FRIENDSHIP_PATS`회
  (낮 06~18시 / 밤). 교환 = 다른 PC에서 저장된 포켓몬이 이 PC에서 깨어날 때 (저장 항목 `machine`).
  교환으로 온 포켓몬은 화면 옆에서 걸어 들어와(`Pet.arrive`) 도착하면 `on_arrived` → 교환 진화 확인.

## 저장 (`storage.py`, 사용자용 안내는 docs/SYNC.md)

- 저장은 2분마다(`AUTOSAVE_MS`) + 이벤트 때. 파티를 다 불러오기 전(`App.loading > 0`)에는 저장하지 않는다.
- 불러오기에 실패한 포켓몬은 `App.unloaded`에 원래 기록을 두고 저장할 때 그대로 다시 쓴다 (데이터 유실 방지).
- PC 별명은 `settings.json`의 `nickname`, 저장 파일 `machines`(PC 이름 → 별명)로 모든 PC가 공유.
- 화면 코드를 python으로 고칠 때 Windows에서는 `write_text(..., newline="\n")` (아니면 CRLF가 섞임).

## 주의

- 스프라이트·초상화 이미지는 저장소에 올리지 않는다 (저작권). `sprites/`는 캐시.
- `party.json`, `settings.json`(클라우드 저장 위치)은 사용자 것이므로 테스트 중 덮어쓰지 않는다
  (`--debug`는 party-debug.json / settings-debug.json 을 씀). 클라우드 폴더의 save.json도 마찬가지.
