"""Tela de entrada: versao local, consulta ao GitHub, atualizacao e abertura do editor."""
from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
import customtkinter as ctk
from core.updater import get_git_status, pull_updates, local_version, PROJECT_DIR


def sync_repository(repo_path):
    # Compatibilidade para chamadas explicitas; nunca salva codigo em andamento.
    info = get_git_status(repo_path)
    if info.get('success') and info['behind'] and not info['ahead'] and not info['dirty']:
        return pull_updates(repo_path)
    return False, info.get('message', '')


class LauncherWindow(ctk.CTk):
    def __init__(self, project_dir=PROJECT_DIR):
        ctk.set_appearance_mode('dark')
        super().__init__()
        self.project_dir=Path(project_dir)
        self.title('fnkMudarResolucao')
        self.geometry('490x420')
        self.resizable(False,False)
        self.configure(fg_color='#101114')
        self.events=queue.Queue()
        self.closed=False
        self.info=None
        ctk.CTkLabel(self,text='fnkMudarResolucao',font=ctk.CTkFont(size=25,weight='bold')).pack(pady=(36,6))
        ctk.CTkLabel(self,text='Proporcao  |  Resolucao  |  Edicao de videos',text_color='#9EABB7').pack(pady=(0,14))
        self.version_label=ctk.CTkLabel(self,text=f'Versao local: {local_version(self.project_dir)}',text_color='#9EABB7')
        self.version_label.pack(pady=(0,22))
        self.btn_enter=ctk.CTkButton(self,text='▶ Entrar na ferramenta',height=48,
            font=ctk.CTkFont(size=16,weight='bold'),state='disabled',command=self._enter)
        self.btn_enter.pack(fill='x',padx=40,pady=(0,10))
        self.btn_update=ctk.CTkButton(self,text='Atualizar app',height=44,fg_color='transparent',
            border_width=1,border_color='#89929D',state='disabled',command=self._update)
        self.btn_update.pack(fill='x',padx=40)
        self.status=ctk.CTkLabel(self,text='Consultando GitHub...',text_color='#9EABB7',wraplength=410)
        self.status.pack(padx=25,pady=18)
        self.protocol('WM_DELETE_WINDOW',self._close)
        self.timer=self.after(40,self._drain)
        self._check()

    def _drain(self):
        while True:
            try:callback=self.events.get_nowait()
            except queue.Empty:break
            if not self.closed:callback()
        if not self.closed:self.timer=self.after(40,self._drain)

    def _check(self):
        def work():
            info=get_git_status(self.project_dir)
            self.events.put(lambda:self._show_status(info))
        threading.Thread(target=work,daemon=True).start()

    def _show_status(self,info):
        self.info=info
        self.btn_enter.configure(state='normal')
        self.btn_update.configure(state='normal',text='Atualizar app')
        self.version_label.configure(text=f'Versao local: {local_version(self.project_dir)}')
        if not info.get('success'):
            text='GitHub indisponivel. Voce pode entrar na versao local.'
        elif info.get('dirty') or info.get('ahead'):
            text='Ha trabalho local a enviar. A atualizacao preserva seus arquivos.'
            self.btn_update.configure(state='disabled')
        elif info.get('behind'):
            text='Nova atualizacao disponivel no GitHub.'
            self.btn_update.configure(text='Baixar atualizacao')
        else:
            text='Aplicativo atualizado com o GitHub.'
        self.status.configure(text=text)

    def _update(self):
        self.btn_enter.configure(state='disabled')
        self.btn_update.configure(state='disabled')
        self.status.configure(text='Consultando e atualizando pelo GitHub...')
        def work():
            try:
                ok,message=pull_updates(self.project_dir)
                info=get_git_status(self.project_dir,fetch=False)
            except Exception as error:
                ok,message,info=False,str(error),{'success':False}
            self.events.put(lambda:self._finish_update(ok,message,info))
        threading.Thread(target=work,daemon=True).start()

    def _finish_update(self,ok,message,info):
        self._show_status(info)
        self.status.configure(text='Atualizacao concluida. Pode entrar na ferramenta.' if ok else f'Falha ao atualizar: {message[:220]}')

    def _enter(self):
        python=Path(sys.executable)
        if os.name=='nt' and python.with_name('pythonw.exe').is_file():
            python=python.with_name('pythonw.exe')
        try:
            subprocess.Popen([str(python),str(self.project_dir/'main.py'),'--app'],cwd=self.project_dir)
        except OSError as error:
            self.status.configure(text=f'Falha ao abrir: {error}')
            return
        self._close()

    def _close(self):
        self.closed=True
        self.after_cancel(self.timer)
        self.destroy()


def main():
    ctk.set_appearance_mode('dark')
    LauncherWindow().mainloop()


if __name__=='__main__':
    main()
