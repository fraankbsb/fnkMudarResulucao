import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

def sync_repository(repo_path):
    try:
        # Busca commits remotos e faz pull se necessário
        cmd_pull = ['git', '-C', repo_path, 'pull', '--rebase', 'origin', 'main']
        subprocess.run(cmd_pull, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
    except Exception:
        pass

def main():
    # Caminho do projeto onde este launcher reside ou caminho padrao
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Se o executavel estiver empacotado fora ou na raiz
    if not os.path.exists(os.path.join(base_dir, 'main.py')):
        # Tenta no diretorio D:\fnkSocialMidia\COMPLETOS\fnkMudarResulucao
        alt_dir = r'D:\fnkSocialMidia\COMPLETOS\fnkMudarResulucao'
        if os.path.exists(os.path.join(alt_dir, 'main.py')):
            base_dir = alt_dir
        else:
            alt_local = r'C:\Users\FRANK\Documents\ChatGPT\fnkMudarResolucao'
            if os.path.exists(os.path.join(alt_local, 'main.py')):
                base_dir = alt_local

    # Sincroniza silenciosamente com o GitHub antes de abrir
    sync_repository(base_dir)

    # Inicia o app principal usando o interpretador Python do sistema
    main_script = os.path.join(base_dir, 'main.py')
    python_exe = sys.executable
    # Se o sys.executable for o proprio launcher empacotado, localiza o python padrao
    if python_exe.lower().endswith('launcher.exe') or not python_exe.lower().endswith('python.exe'):
        python_candidates = [
            r'C:\Users\FRANK\AppData\Local\Programs\Python\Python311\python.exe',
            r'C:\Users\FRANK\AppData\Local\Programs\Python\Python311\pythonw.exe',
            'python.exe',
            'pythonw.exe'
        ]
        for cand in python_candidates:
            if os.path.exists(cand):
                python_exe = cand
                break

    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    subprocess.Popen([python_exe, main_script], cwd=base_dir, startupinfo=startupinfo)

if __name__ == '__main__':
    main()