import sys
import os

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        sys.argv.pop(1)
        from cli.main import main as cli_main
        cli_main()
    elif len(sys.argv) > 1 and sys.argv[1] == '--app':
        sys.argv.pop(1)
        from gui.app import run_gui
        run_gui()
    else:
        from launcher import main as launcher_main
        launcher_main()

if __name__ == '__main__':
    main()