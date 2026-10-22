import sys
import os

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        sys.argv.pop(1)
        from cli.main import main as cli_main
        cli_main()
    else:
        from gui.app import run_gui
        run_gui()

if __name__ == '__main__':
    main()