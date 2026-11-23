"""Entry point.

    python -m ai_compare                 -> GUI
    python -m ai_compare cli REF TGT     -> headless, writes an HTML report
"""
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        from .cli import main as cli_main
        sys.exit(cli_main(sys.argv[2:]))
    from .gui import main as gui_main
    sys.exit(gui_main())


if __name__ == "__main__":
    main()
