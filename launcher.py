"""O atalho abre sempre o codigo desta pasta, inclusive as alteracoes locais."""
from pathlib import Path
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox


def sync_repository(repo_path):
    # Nunca commitar edicao em andamento ao abrir o aplicativo.
    from core.updater import get_git_status, pull_updates
    info = get_git_status(repo_path)
    if info.get('success') and info['behind'] and not info['ahead'] and not info['dirty']:
        return pull_updates(repo_path)
    return False, info.get('message', '')


def main():
    project_dir = Path(__file__).resolve().parent
    try:
        sync_repository(project_dir)
        python = Path(sys.executable)
        if os.name == 'nt' and python.with_name('pythonw.exe').is_file():
            python = python.with_name('pythonw.exe')
        subprocess.Popen([str(python), str(project_dir / 'main.py')], cwd=project_dir)
    except Exception as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('fnkMudarResolucao', f'Falha ao iniciar o aplicativo: {error}')
        root.destroy()


if __name__ == '__main__':
    main()
