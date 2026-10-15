# Desktop Pokémon

작업표시줄 위에서 포켓몬들이 돌아다니고, 야생 포켓몬과 알아서 싸우며 성장하는
Windows용 방치형 데스크톱 펫.

## 게임 방법

- 1~2분마다 **야생 포켓몬**(도감 #1~493)이 화면 가장자리에서 걸어 들어옵니다.
- 가장 가까운 내 포켓몬과 **자동으로 턴제 배틀**을 합니다. 타입 상성이 적용됩니다.
- 이기면 **경험치**를 얻고 레벨이 오릅니다. 쓰러진 야생 포켓몬을 **클릭하면 포획**합니다 (파티 최대 6마리).
- 지면 잠시 쓰러져 쉬었다가 회복합니다. 평소에는 HP가 천천히 차고, 자는 동안은 더 빨리 찹니다.
- 등장·승리·레벨 업·패배·포획 때는 화면 오른쪽 아래에 **표정 초상화 대화창**이 뜹니다.
- 레벨과 경험치는 `party.json`에 저장되어 다시 켜도 이어집니다.

## 실행

Python 3 (표준 라이브러리만 사용, 추가 설치 없음)

```
python desktop_pokemon.py
```

또는 `포켓몬 실행.bat` 더블클릭 (콘솔 창 없이 실행).

## 조작법

- **좌클릭**: 쓰다듬기 (자고 있으면 깨어남) / 쓰러진 야생 포켓몬은 포획
- **드래그**: 집어 들기 / 던지기
- **우클릭**: 메뉴 — 레벨·HP·타입 보기, 야생 포켓몬 부르기, 도감 번호로 부르기, 재우기, 돌려보내기, 5분 숨기기, 종료

## 스프라이트

스프라이트 이미지는 이 저장소에 포함되어 있지 않습니다. 처음 실행할 때 받아서
`sprites/` 폴더에 캐시합니다.

- **기본**: [PMDCollab/SpriteCollab](https://github.com/PMDCollab/SpriteCollab)의
  포켓몬 불가사의 던전 스타일 스프라이트와 표정 초상화. 걷기 / 대기 / 잠자기 / 공격 / 원거리 공격 /
  피격 / 기절 애니메이션을 상태에 맞게 재생합니다. 1025마리 중 980마리 지원 (#1~493은 전원).
- **포켓몬 데이터**: 타입·종족값·기초 경험치는 [PokeAPI](https://pokeapi.co/)에서 받아옵니다.
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
