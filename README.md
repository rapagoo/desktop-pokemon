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

스프라이트 이미지는 이 저장소에 포함되어 있지 않습니다. 처음 실행할 때 받아서
`sprites/` 폴더에 캐시합니다.

- **기본**: [PMDCollab/SpriteCollab](https://github.com/PMDCollab/SpriteCollab)의
  포켓몬 불가사의 던전 스타일 스프라이트. 걷기(Walk) / 대기(Idle) / 잠자기(Sleep) 애니메이션을
  상태에 맞게 재생합니다. 1025마리 중 980마리 지원.
- **대체**: PMD 스프라이트가 없는 포켓몬은 5세대 도트 스프라이트를 씁니다.
  1~649번은 [PokeAPI/sprites](https://github.com/PokeAPI/sprites)의 공식 BW 애니메이션,
  650번 이후는 [Pokémon Showdown](https://play.pokemonshowdown.com/sprites/)의
  [Smogon](https://www.smogon.com/) 팬메이드 BW 스타일 스프라이트입니다.

### Credits

PMD 스프라이트는 PMDCollab SpriteCollab 기여자들의 작품이며
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) 라이선스를 따릅니다.
포켓몬별 작가 정보는 [PMD Sprite Repository](https://sprites.pmdcollab.org/)에서 확인할 수 있습니다.

## Disclaimer

비상업적 팬 프로젝트입니다. Pokémon 및 관련 캐릭터 이름·이미지의 저작권과 상표권은
Nintendo, Creatures Inc., GAME FREAK inc.에 있습니다. 이 프로젝트는 이들과 무관하며
승인이나 후원을 받지 않았습니다.
