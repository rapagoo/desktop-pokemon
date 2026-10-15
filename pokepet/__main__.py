"""실행 진입점: python -m pokepet [--debug]"""
import argparse

from . import config


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pokepet", description="바탕화면 포켓몬")
    parser.add_argument("--debug", action="store_true",
                        help="개발용: 야생 포켓몬이 몇 초마다 나오고, 이벤트를 콘솔에 출력")
    parser.add_argument("--capturable", action="store_true",
                        help="개발용: 스크린샷·화면 공유에도 포켓몬이 찍히게 (기본은 안 찍힘)")
    args = parser.parse_args(argv)

    # 다른 모듈이 config 값을 가져가기 전에 바꿔야 적용된다
    if args.debug:
        config.apply_debug()
    if args.capturable:
        config.CAPTURE_GUARD = False

    # 이미 켜져 있으면 두 번째로 띄우지 않고, 켜져 있는 쪽의 관리 창을 연다
    from . import screen
    instance = "DesktopPokemon" + ("-debug" if args.debug else "")
    if not screen.claim_single_instance(instance):
        screen.wake_existing(instance)
        print("이미 실행 중이에요. 켜져 있는 쪽의 관리 창을 열었어요.")
        return

    from .app import App
    App(debug=args.debug, instance=instance).run()


if __name__ == "__main__":
    main()
