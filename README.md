# Desktop Pokémon

작업표시줄 위에서 포켓몬들이 돌아다니는 Windows용 데스크톱 펫.

## 실행

Python 3 (표준 라이브러리만 사용, 추가 설치 없음)

```
python desktop_pokemon.py
```

또는 `포켓몬 실행.bat` 더블클릭 (콘솔 창 없이 실행).

## 조작법

- **좌클릭**: 쓰다듬기 (자고 있으면 깨어남)
- **드래그**: 집어 들기 / 던지기
- **우클릭**: 메뉴 — 포켓몬 부르기(랜덤/도감 번호), 재우기, 돌려보내기, 5분 숨기기, 종료

## 스프라이트

스프라이트 이미지는 이 저장소에 포함되어 있지 않습니다. 처음 실행할 때
[PokeAPI/sprites](https://github.com/PokeAPI/sprites)에서 받아 `sprites/` 폴더에 캐시합니다.
모두 5세대(BW) 도트 스타일입니다. 1~649번은 공식 BW 애니메이션, 650번 이후는
[Smogon](https://www.smogon.com/) 팬메이드 BW 스타일 스프라이트(애니메이션이 없으면 정지 이미지 + 통통 튀는 효과)를
[Pokémon Showdown](https://play.pokemonshowdown.com/sprites/)에서 받아옵니다.

## Disclaimer

비상업적 팬 프로젝트입니다. Pokémon 및 관련 캐릭터 이름·이미지의 저작권과 상표권은
Nintendo, Creatures Inc., GAME FREAK inc.에 있습니다. 이 프로젝트는 이들과 무관하며
승인이나 후원을 받지 않았습니다.
