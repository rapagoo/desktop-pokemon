"""실행용 파일. 실제 코드는 pokepet/ 패키지에 있습니다.

    python desktop_pokemon.py            # 보통 실행
    python desktop_pokemon.py --debug    # 개발용 빠른 모드
"""
from pokepet.__main__ import main

if __name__ == "__main__":
    main()
