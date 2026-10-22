import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

def sync_repository(repo_path):
    try:
        cmd_pull = ['git', '-C', repo_path, 'pull', '--rebase', 'origin', 'main']
        subprocess.run(cmd_pull, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Procura a pasta do projeto caso executável esteja em dist/ ou isolado
    candidate_dirs = [
        base_dir,
        os.path.abspath(os.path.join(base_dir, '..', '..')),
        os.path.abspath(os.path.join(base_dir, '..')),
        r'D:\fnkSocialMidia\COMPLETOS\fnkMudarResulucao',
        r'C:\Users\FRANK\Documents\ChatGPT\fnkMudarResolucao'
    ]

    project_dir = None
    for cand in candidate_dirs:
        if os.path.exists(os.path.join(cand, 'main.py')):
            project_dir = cand
            break

    if not project_dir:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('Erro', 'Nao foi possivel localizar os arquivos do projeto fnkMudarResolucao.')
        return

    # Sincroniza silenciosamente antes de abrir
    sync_repository(project_dir)

    # Identifica o executável do python
    python_candidates = [
        r'C:\Users\FRANK\AppData\Local\Programs\Python\Python311\python.exe',
        r'C:\Users\FRANK\AppData\Local\Programs\Python\Python311\pythonw.exe',
        sys.executable
    ]

    selected_python = None
    for py in python_candidates:
        if os.path.exists(py) and ('python.exe' in py.lower() or 'pythonw.exe' in py.lower()):
            selected_python = py
            break

    if not selected_python:
        selected_python = 'python'

    main_script = os.path.join(project_dir, 'main.py')
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        subprocess.Popen([selected_python, main_script], cwd=project_dir, startupinfo=startupinfo)
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('Erro ao iniciar', f'Falha ao iniciar a interface:\n{e}')

if __name__ == '__main__':
    main()
