"""실행 진입점: python -m pokepet [--debug]"""
import argparse

from . import config


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pokepet", description="바탕화면 포켓몬")
    parser.add_argument("--debug", action="store_true",
                        help="개발용: 야생 포켓몬이 몇 초마다 나오고, 이벤트를 콘솔에 출력")
    args = parser.parse_args(argv)

    # 다른 모듈이 config 값을 가져가기 전에 바꿔야 적용된다
    if args.debug:
        config.apply_debug()

    from .app import App
    App(debug=args.debug).run()


if __name__ == "__main__":
    main()
