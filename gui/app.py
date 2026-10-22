import os
import json
import math
import queue
import tempfile
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.converter import convert_video, get_video_metadata, PRESET_RATIOS, get_edit_timeline
from core.preview import generate_preview_frame
from core.updater import get_git_status, restart_app

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

class VideoConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('fnkMudarResolucao - Conversor Universal de Resolucao & Proporcao')
        self.geometry('1060x820')
        self.minsize(920, 720)

        self.input_files = []
        self.is_converting = False
        self.should_cancel = False
        self.selected_video_path = None
        self._preview_debounce_timer = None
        self._preview_request_id = 0
        self._preview_lock = threading.Lock()

        self._ui_events = queue.Queue()
        self._metadata_cache = {}
        self._preview_busy = False
        self._playing = False
        self._play_timer = None
        self._preview_duration = 0.0
        self._preview_position = 0.0
        self._closed = False
        self._build_ui()
        self.after(30, self._drain_ui_events)
        self.protocol('WM_DELETE_WINDOW', self._close)
        threading.Thread(target=self._check_update_silent, daemon=True).start()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header com Botao de Atualizar App
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color='#1E222A')
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky='ew')
        header_frame.grid_columnconfigure(0, weight=1)

        header_top = ctk.CTkFrame(header_frame, fg_color='transparent')
        header_top.pack(fill='x', padx=20, pady=(12, 4))

        title_lbl = ctk.CTkLabel(
            header_top,
            text='Conversor Universal de Proporcao (4:5 / 9:16 / 1:1)',
            font=ctk.CTkFont(size=22, weight='bold'),
            text_color='#4CA1AF'
        )
        title_lbl.pack(side='left')

        self.btn_update = ctk.CTkButton(
            header_top,
            text='Sincronizar GitHub',
            font=ctk.CTkFont(size=12, weight='bold'),
            fg_color='#1565C0',
            hover_color='#0D47A1',
            height=32,
            width=180,
            command=self._manual_update_check
        )
        self.btn_update.pack(side='right')

        self.lbl_sync_status = ctk.CTkLabel(
            header_top,
            text='Sincronizado',
            font=ctk.CTkFont(size=11),
            text_color='#81C784'
        )
        self.lbl_sync_status.pack(side='right', padx=(0, 10))

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text='Transforme qualquer video entre 9:16, 4:5, 1:1 e 16:9 preservando a originalidade sem distorcao.',
            font=ctk.CTkFont(size=13),
            text_color='#9EABB7'
        )
        sub_lbl.pack(anchor='w', padx=20, pady=(0, 12))

        # Conteudo em 2 colunas: Controles e Preview
        content_frame = ctk.CTkFrame(self, fg_color='transparent')
        content_frame.grid(row=1, column=0, padx=15, pady=5, sticky='nsew')
        content_frame.grid_columnconfigure(0, weight=3)
        content_frame.grid_columnconfigure(1, weight=2)
        content_frame.grid_rowconfigure(0, weight=1)

        # Coluna da esquerda: Configuracoes e Arquivos
        left_panel = ctk.CTkScrollableFrame(content_frame, label_text='Configuracoes e Fila de Videos')
        left_panel.grid(row=0, column=0, padx=(0, 10), pady=0, sticky='nsew')
        left_panel.grid_columnconfigure(0, weight=1)

        # Selecao de Arquivos
        file_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        file_sec.pack(fill='x', padx=10, pady=8)

        btn_row = ctk.CTkFrame(file_sec, fg_color='transparent')
        btn_row.pack(fill='x', padx=10, pady=10)

        self.btn_select = ctk.CTkButton(
            btn_row, text='Selecionar Videos', command=self._select_videos,
            font=ctk.CTkFont(size=14, weight='bold'), height=36
        )
        self.btn_select.pack(side='left', expand=True, fill='x', padx=(0, 5))

        self.btn_clear = ctk.CTkButton(
            btn_row, text='Limpar Fila', command=self._clear_videos,
            fg_color='#555555', hover_color='#666666', width=100, height=36
        )
        self.btn_clear.pack(side='right', padx=(5, 0))

        self.lbl_queue_count = ctk.CTkLabel(
            file_sec, text='Nenhum video selecionado', font=ctk.CTkFont(size=12, slant='italic')
        )
        self.lbl_queue_count.pack(anchor='w', padx=12, pady=(0, 8))

        self.file_listbox = tk.Listbox(
            file_sec, height=5, bg='#2B2D30', fg='#EDEDED',
            selectbackground='#3A7EBF', selectforeground='white',
            highlightthickness=0, borderwidth=0, font=('Consolas', 10),
            exportselection=False
        )
        self.file_listbox.pack(fill='x', padx=10, pady=(0, 10))
        self.file_listbox.bind('<<ListboxSelect>>', self._on_file_selected)

        # Proporcao de Destino Alvo
        target_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        target_sec.pack(fill='x', padx=10, pady=8)

        lbl_target = ctk.CTkLabel(target_sec, text='Proporcao / Resolucao de Destino:', font=ctk.CTkFont(weight='bold'))
        lbl_target.pack(anchor='w', padx=10, pady=(10, 6))

        row_preset = ctk.CTkFrame(target_sec, fg_color='transparent')
        row_preset.pack(fill='x', padx=10, pady=(0, 10))

        self.combo_target_preset = ctk.CTkComboBox(
            row_preset,
            values=list(PRESET_RATIOS),
            width=320,
            command=lambda _: self._schedule_preview_update(immediate=True)
        )
        self.combo_target_preset.set('4:5 (Feed Instagram/FB - 1080x1350)')
        self.combo_target_preset.pack(side='left', fill='x', expand=True)

        # Modo de Composicao
        mode_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        mode_sec.pack(fill='x', padx=10, pady=8)

        lbl_mode = ctk.CTkLabel(mode_sec, text='Modo de Preservacao da Originalidade:', font=ctk.CTkFont(weight='bold'))
        lbl_mode.pack(anchor='w', padx=10, pady=(10, 4))

        self.var_mode = ctk.StringVar(value='blur')
        self.radio_blur = ctk.CTkRadioButton(
            mode_sec, text='Fundo Desfocado Dinamico (Recomendado - Video 100% integro + fundo blur)',
            variable=self.var_mode, value='blur', command=lambda: self._schedule_preview_update(immediate=True)
        )
        self.radio_blur.pack(anchor='w', padx=12, pady=4)

        self.radio_pillar = ctk.CTkRadioButton(
            mode_sec, text='Barras Solidas (Pillarbox/Letterbox - Video original sem cortes)',
            variable=self.var_mode, value='pillarbox', command=lambda: self._schedule_preview_update(immediate=True)
        )
        self.radio_pillar.pack(anchor='w', padx=12, pady=4)

        self.radio_crop = ctk.CTkRadioButton(
            mode_sec, text='Preenchimento Total (Corte proporcional ajustado sem barras)',
            variable=self.var_mode, value='crop', command=lambda: self._schedule_preview_update(immediate=True)
        )
        self.radio_crop.pack(anchor='w', padx=12, pady=(4, 10))

        # Parametros Adicionais
        adv_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        adv_sec.pack(fill='x', padx=10, pady=8)

        lbl_adv = ctk.CTkLabel(adv_sec, text='Ajustes Visuais:', font=ctk.CTkFont(weight='bold'))
        lbl_adv.pack(anchor='w', padx=10, pady=(10, 8))

        row_blur = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_blur.pack(fill='x', padx=10, pady=4)
        ctk.CTkLabel(row_blur, text='Intensidade do Desfoque:').pack(side='left')
        self.slider_blur = ctk.CTkSlider(
            row_blur, from_=0, to=80, number_of_steps=80,
            command=lambda _: self._schedule_preview_update(immediate=False)
        )
        self.slider_blur.set(35)
        self.slider_blur.pack(side='right', expand=True, fill='x', padx=(10, 0))

        row_color = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_color.pack(fill='x', padx=10, pady=4)
        ctk.CTkLabel(row_color, text='Cor das Barras (Modo Solido):').pack(side='left')
        self.combo_color = ctk.CTkComboBox(
            row_color, values=['black', 'white', 'gray', '#111827'], width=120,
            command=lambda _: self._schedule_preview_update(immediate=True)
        )
        self.combo_color.set('black')
        self.combo_color.pack(side='right')

        row_crf = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_crf.pack(fill='x', padx=10, pady=(4, 10))
        ctk.CTkLabel(row_crf, text='Qualidade CRF (menor = melhor):').pack(side='left')
        self.slider_crf = ctk.CTkSlider(row_crf, from_=0, to=51, number_of_steps=51)
        self.slider_crf.set(18)
        self.slider_crf.pack(side='right', expand=True, fill='x', padx=(10, 0))

        edit_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        edit_sec.pack(fill='x', padx=10, pady=8)
        ctk.CTkLabel(edit_sec, text='Edicao do Video', font=ctk.CTkFont(weight='bold')).pack(anchor='w', padx=10, pady=8)
        self.var_sharpen = tk.StringVar(value='0')
        self.var_start = tk.StringVar(value='0')
        self.var_end = tk.StringVar(value='0')
        self.var_speed = tk.StringVar(value='1')
        self.var_mirror = tk.BooleanVar(value=False)
        self.var_cover = tk.StringVar(value='')
        self.var_cover_seconds = tk.StringVar(value='0.1')
        self.var_cover_fit = tk.StringVar(value='preencher')
        for label, variable in [('Nitidez (0 a 2):', self.var_sharpen),
                                ('Remover do inicio (segundos):', self.var_start),
                                ('Remover do fim (segundos):', self.var_end),
                                ('Velocidade (0.25 a 4x):', self.var_speed)]:
            row = ctk.CTkFrame(edit_sec, fg_color='transparent')
            row.pack(fill='x', padx=10, pady=4)
            ctk.CTkLabel(row, text=label).pack(side='left')
            ctk.CTkEntry(row, textvariable=variable, width=95).pack(side='right')
        ctk.CTkCheckBox(edit_sec, text='Espelhar horizontalmente', variable=self.var_mirror,
                        command=lambda: self._schedule_preview_update()).pack(anchor='w', padx=10, pady=8)
        ctk.CTkLabel(edit_sec, text='Capa de abertura (opcional):').pack(anchor='w', padx=10)
        ctk.CTkEntry(edit_sec, textvariable=self.var_cover).pack(fill='x', padx=10, pady=4)
        cover_buttons = ctk.CTkFrame(edit_sec, fg_color='transparent')
        cover_buttons.pack(fill='x', padx=10, pady=4)
        ctk.CTkButton(cover_buttons, text='Escolher imagem', command=self._select_cover, width=140).pack(side='left')
        ctk.CTkButton(cover_buttons, text='Remover capa', command=lambda: self.var_cover.set(''), width=120).pack(side='right')
        row = ctk.CTkFrame(edit_sec, fg_color='transparent')
        row.pack(fill='x', padx=10, pady=4)
        ctk.CTkLabel(row, text='Duracao da capa (segundos):').pack(side='left')
        ctk.CTkEntry(row, textvariable=self.var_cover_seconds, width=95).pack(side='right')
        ctk.CTkComboBox(edit_sec, variable=self.var_cover_fit,
                       values=['preencher', 'inteira', 'esticar'], state='readonly',
                       command=lambda _: self._schedule_preview_update()).pack(fill='x', padx=10, pady=(4, 10))
        for variable in (self.var_sharpen, self.var_start, self.var_end, self.var_speed,
                         self.var_cover, self.var_cover_seconds):
            variable.trace_add('write', lambda *_: self._schedule_preview_update())

        preset_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        preset_sec.pack(fill='x', padx=10, pady=8)
        ctk.CTkLabel(preset_sec, text='Configuracoes salvas', font=ctk.CTkFont(weight='bold')).pack(anchor='w', padx=10, pady=8)
        self._preset_paths = {}
        preset_dir = Path(__file__).resolve().parent.parent / 'presets'
        for path in sorted(preset_dir.glob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                self._preset_paths[data.get('name', path.stem)] = path
            except (ValueError, OSError):
                pass
        self.combo_saved_preset = ctk.CTkComboBox(preset_sec,
            values=list(self._preset_paths) or ['Nenhuma configuracao salva'], state='readonly')
        self.combo_saved_preset.pack(fill='x', padx=10, pady=4)
        buttons = ctk.CTkFrame(preset_sec, fg_color='transparent')
        buttons.pack(fill='x', padx=10, pady=(4, 10))
        ctk.CTkButton(buttons, text='Aplicar', width=85, command=self._apply_saved_preset).pack(side='left')
        ctk.CTkButton(buttons, text='Importar', width=85, command=self._import_preset).pack(side='left', padx=5)
        ctk.CTkButton(buttons, text='Salvar', width=85, command=self._save_preset).pack(side='right')

        # Pasta de Saida
        out_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        out_sec.pack(fill='x', padx=10, pady=8)

        lbl_out = ctk.CTkLabel(out_sec, text='Pasta de Destino:', font=ctk.CTkFont(weight='bold'))
        lbl_out.pack(anchor='w', padx=10, pady=(10, 4))

        row_out = ctk.CTkFrame(out_sec, fg_color='transparent')
        row_out.pack(fill='x', padx=10, pady=(0, 10))

        self.entry_out_dir = ctk.CTkEntry(row_out, placeholder_text='Mesma pasta do video de origem')
        self.entry_out_dir.pack(side='left', fill='x', expand=True, padx=(0, 6))

        btn_browse_out = ctk.CTkButton(row_out, text='Procurar...', width=90, command=self._select_output_dir)
        btn_browse_out.pack(side='right')

        # Coluna da Direita: Pre-Visualizacao em Tempo Real
        right_panel = ctk.CTkFrame(content_frame, corner_radius=10)
        right_panel.grid(row=0, column=1, padx=(5, 0), pady=0, sticky='nsew')
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        lbl_prev_title = ctk.CTkLabel(right_panel, text='Pre-Visualizacao do Resultado', font=ctk.CTkFont(weight='bold'))
        lbl_prev_title.grid(row=0, column=0, padx=10, pady=(10, 6), sticky='ew')

        self.preview_canvas_frame = ctk.CTkFrame(right_panel, fg_color='#15171C', corner_radius=8)
        self.preview_canvas_frame.grid(row=1, column=0, padx=12, pady=6, sticky='nsew')
        self.preview_canvas_frame.grid_rowconfigure(0, weight=1)
        self.preview_canvas_frame.grid_columnconfigure(0, weight=1)

        self.lbl_preview_img = ctk.CTkLabel(self.preview_canvas_frame, text='Selecione um video para gerar o preview')
        self.lbl_preview_img.grid(row=0, column=0, padx=10, pady=10)

        self.btn_refresh_prev = ctk.CTkButton(
            right_panel, text='Atualizar Preview', height=32,
            command=lambda: self._schedule_preview_update(immediate=True)
        )
        self.btn_refresh_prev.grid(row=2, column=0, padx=12, pady=(6, 12), sticky='ew')

        self.preview_slider = ctk.CTkSlider(right_panel, from_=0, to=1,
            command=self._seek_preview, state='disabled')
        self.preview_slider.set(0)
        self.preview_slider.grid(row=3, column=0, padx=12, pady=4, sticky='ew')
        self.lbl_preview_time = ctk.CTkLabel(right_panel, text='0.00 / 0.00 s')
        self.lbl_preview_time.grid(row=4, column=0, padx=12, pady=2)
        self.btn_play = ctk.CTkButton(right_panel, text='Reproduzir previa (sem audio)',
            state='disabled', command=self._toggle_play)
        self.btn_play.grid(row=5, column=0, padx=12, pady=(4, 12), sticky='ew')

        # Rodape: Progresso e Acoes
        footer_frame = ctk.CTkFrame(self, corner_radius=10, fg_color='#1E222A')
        footer_frame.grid(row=2, column=0, padx=15, pady=(10, 15), sticky='ew')
        footer_frame.grid_columnconfigure(0, weight=1)

        prog_row = ctk.CTkFrame(footer_frame, fg_color='transparent')
        prog_row.pack(fill='x', padx=15, pady=(10, 4))

        self.lbl_status = ctk.CTkLabel(prog_row, text='Pronto para iniciar.', font=ctk.CTkFont(weight='bold'))
        self.lbl_status.pack(side='left')

        self.lbl_pct = ctk.CTkLabel(prog_row, text='0%', font=ctk.CTkFont(weight='bold'), text_color='#4CA1AF')
        self.lbl_pct.pack(side='right')

        self.progress_bar = ctk.CTkProgressBar(footer_frame, height=12)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill='x', padx=15, pady=(0, 10))

        action_row = ctk.CTkFrame(footer_frame, fg_color='transparent')
        action_row.pack(fill='x', padx=15, pady=(0, 12))

        self.btn_start = ctk.CTkButton(
            action_row, text='INICIAR CONVERSAO DE PROPORCAO', height=42,
            font=ctk.CTkFont(size=15, weight='bold'), fg_color='#2E7D32', hover_color='#1B5E20',
            command=self._start_conversion
        )
        self.btn_start.pack(side='left', expand=True, fill='x', padx=(0, 10))

        self.btn_cancel = ctk.CTkButton(
            action_row, text='Cancelar', height=42, width=110,
            fg_color='#C62828', hover_color='#8E0000', state='disabled',
            command=self._cancel_conversion
        )
        self.btn_cancel.pack(side='right', padx=(0, 10))

        self.btn_open_folder = ctk.CTkButton(
            action_row, text='Abrir Pasta', height=42, width=120,
            fg_color='#37474F', hover_color='#263238',
            command=self._open_output_folder
        )
        self.btn_open_folder.pack(side='right')

    def _post_ui(self, callback):
        if not self._closed:
            self._ui_events.put(callback)

    def _drain_ui_events(self):
        for _ in range(100):
            try:
                callback = self._ui_events.get_nowait()
            except queue.Empty:
                break
            callback()
        if not self._closed:
            self.after(30, self._drain_ui_events)

    def _close(self):
        self._closed = True
        self.should_cancel = True
        self._pause_preview()
        self.withdraw()
        self._wait_close()

    def _wait_close(self):
        worker = getattr(self, '_conversion_thread', None)
        if worker and worker.is_alive():
            self.after(50, self._wait_close)
        else:
            self.destroy()

    def _check_update_silent(self):
        info = get_git_status()
        self._post_ui(lambda: self._show_git_status(info))

    def _show_git_status(self, info):
        if not info.get('success'):
            text, color = 'GitHub indisponivel', '#E57373'
        elif info.get('dirty') or info.get('ahead'):
            text, color = 'Alteracoes a enviar', '#FFB74D'
        elif info.get('behind'):
            text, color = 'Atualizacao disponivel', '#FFB74D'
        else:
            text, color = 'App Sincronizado', '#81C784'
        self.lbl_sync_status.configure(text=text, text_color=color)

    def _manual_update_check(self):
        if self.is_converting:
            messagebox.showinfo('Git Sync', 'Aguarde a conversao terminar antes de sincronizar.')
            return
        self.btn_update.configure(state='disabled', text='Sincronizando...')
        self.btn_start.configure(state='disabled')
        self.lbl_sync_status.configure(text='Testando e sincronizando...', text_color='#64B5F6')

        def run_update():
            info = get_git_status()
            try:
                from sync import synchronize
                synchronize()
                result = (True, 'Testes concluidos e projeto sincronizado com o GitHub.')
            except Exception as error:
                result = (False, str(error))
            self._post_ui(lambda: self._finish_update(info, result))
        threading.Thread(target=run_update, daemon=True).start()

    def _finish_update(self, info, result):
        ok, message = result
        self.btn_update.configure(state='normal', text='Sincronizar GitHub')
        self.btn_start.configure(state='normal')
        self.lbl_sync_status.configure(text='App Sincronizado' if ok else 'Erro ao atualizar')
        if ok:
            messagebox.showinfo('Git Sync', message)
            if info.get('behind'):
                restart_app()
        else:
            messagebox.showerror('Git Sync', message)

    def _select_videos(self):
        files = filedialog.askopenfilenames(
            title='Selecione os Videos',
            filetypes=[('Videos MP4/MOV/MKV/WEBM', '*.mp4 *.mov *.mkv *.webm'), ('Todos os arquivos', '*.*')]
        )
        if files:
            for f in files:
                if f not in self.input_files:
                    self.input_files.append(f)
                    self.file_listbox.insert(tk.END, os.path.basename(f))
            self.lbl_queue_count.configure(text=f'{len(self.input_files)} video(s) na fila')
            if len(self.input_files) > 0:
                if not self.selected_video_path or self.selected_video_path not in self.input_files:
                    self.selected_video_path = self.input_files[0]
                    self.file_listbox.selection_clear(0, tk.END)
                    self.file_listbox.selection_set(0)
                self._schedule_preview_update(immediate=True)

    def _clear_videos(self):
        self._pause_preview()
        self._preview_request_id += 1
        self._preview_position = 0.0
        self._preview_duration = 0.0
        self._preview_busy = False
        self.preview_slider.set(0)
        self.preview_slider.configure(state='disabled')
        self.btn_play.configure(state='disabled')
        self.lbl_preview_time.configure(text='0.00 / 0.00 s')
        if self._preview_debounce_timer:
            self.after_cancel(self._preview_debounce_timer)
            self._preview_debounce_timer = None
        self.selected_video_path = None
        self.input_files.clear()
        self.file_listbox.delete(0, tk.END)
        self.lbl_queue_count.configure(text='Nenhum video selecionado')
        self.lbl_preview_img.configure(image='', text='Selecione um video para gerar o preview')

    def _select_output_dir(self):
        folder = filedialog.askdirectory(title='Escolha a Pasta de Saida')
        if folder:
            self.entry_out_dir.delete(0, tk.END)
            self.entry_out_dir.insert(0, folder)

    def _on_file_selected(self, event):
        sel = self.file_listbox.curselection()
        if sel and self.input_files:
            idx = sel[0]
            if 0 <= idx < len(self.input_files):
                if self.selected_video_path != self.input_files[idx]:
                    self._pause_preview()
                    self._preview_position = 0.0
                self.selected_video_path = self.input_files[idx]
                self._schedule_preview_update(immediate=True)
        elif self.selected_video_path and self.selected_video_path in self.input_files:
            self._schedule_preview_update(immediate=True)

    def _get_target_resolution(self):
        return PRESET_RATIOS.get(self.combo_target_preset.get(), (1080, 1350))

    def _schedule_preview_update(self, immediate: bool = False):
        sel = self.file_listbox.curselection()
        if sel and self.input_files:
            idx = sel[0]
            if 0 <= idx < len(self.input_files):
                self.selected_video_path = self.input_files[idx]
        elif not self.selected_video_path and self.input_files:
            self.selected_video_path = self.input_files[0]
            self.file_listbox.selection_clear(0, tk.END)
            self.file_listbox.selection_set(0)

        if not self.selected_video_path or not os.path.exists(self.selected_video_path):
            return

        if self._preview_debounce_timer:
            self.after_cancel(self._preview_debounce_timer)
            self._preview_debounce_timer = None

        delay = 0 if immediate else 150
        self._preview_debounce_timer = self.after(delay, self._dispatch_preview_thread)

    def _select_cover(self):
        path = filedialog.askopenfilename(title='Escolha a capa',
            filetypes=[('Imagens', '*.png *.jpg *.jpeg *.webp *.bmp')])
        if path:
            self.var_cover.set(path)
            self._preview_position = 0.0
            self._schedule_preview_update(immediate=True)

    def _get_edit_options(self):
        def number(variable):
            return float(variable.get().strip().replace(',', '.'))
        return dict(sharpen_strength=number(self.var_sharpen), corte_inicio=number(self.var_start),
                    corte_fim=number(self.var_end), velocidade=number(self.var_speed),
                    espelhar=self.var_mirror.get(), capa_path=self.var_cover.get().strip() or None,
                    capa_segundos=number(self.var_cover_seconds), capa_ajuste=self.var_cover_fit.get())

    def _get_options(self):
        return dict(mode=self.var_mode.get(), target_resolution=self._get_target_resolution(),
                    blur_strength=int(self.slider_blur.get()), bg_color=self.combo_color.get(),
                    crf=int(self.slider_crf.get()), **self._get_edit_options())

    def _apply_preset_data(self, data):
        # Valida antes de alterar controles para evitar uma configuracao parcial.
        target = data.get('target_preset', self.combo_target_preset.get())
        mode = data.get('mode', 'blur')
        if target not in PRESET_RATIOS or mode not in ('blur', 'pillarbox', 'crop'):
            raise ValueError('Proporcao ou modo invalido na configuracao.')
        numeric = {'blur_strength': (0, 80, 35), 'sharpen_strength': (0, 2, 0),
                   'crf': (0, 51, 18), 'corte_inicio': (0, float('inf'), 0),
                   'corte_fim': (0, float('inf'), 0), 'velocidade': (0.25, 4, 1),
                   'capa_segundos': (0.001, float('inf'), 0.1)}
        for key, (low, high, default) in numeric.items():
            value = float(data.get(key, default))
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'Valor invalido: {key}')
        if data.get('capa_ajuste', 'preencher') not in ('preencher', 'inteira', 'esticar'):
            raise ValueError('Ajuste de capa invalido.')
        self._pause_preview()
        self.combo_target_preset.set(target)
        self.var_mode.set(mode)
        self.slider_blur.set(data.get('blur_strength', 35))
        self.slider_crf.set(data.get('crf', 18))
        self.combo_color.set(data.get('bg_color', 'black'))
        for variable, key, default in [(self.var_sharpen, 'sharpen_strength', 0),
                (self.var_start, 'corte_inicio', 0), (self.var_end, 'corte_fim', 0),
                (self.var_speed, 'velocidade', 1), (self.var_cover_seconds, 'capa_segundos', 0.1),
                (self.var_cover, 'capa_path', ''), (self.var_cover_fit, 'capa_ajuste', 'preencher')]:
            variable.set(data.get(key) or default)
        self.var_mirror.set(bool(data.get('espelhar', False)))
        self._preview_position = 0.0
        self._schedule_preview_update(immediate=True)

    def _apply_saved_preset(self):
        path = self._preset_paths.get(self.combo_saved_preset.get())
        if path:
            self._load_preset(path)

    def _load_preset(self, path):
        try:
            self._apply_preset_data(json.loads(Path(path).read_text(encoding='utf-8')))
        except (ValueError, OSError, TypeError) as error:
            messagebox.showerror('Configuracao', str(error))

    def _import_preset(self):
        path = filedialog.askopenfilename(filetypes=[('Configuracoes JSON', '*.json')])
        if path:
            self._load_preset(path)

    def _save_preset(self):
        try:
            data = self._get_options()
            data.pop('target_resolution')
            data['target_preset'] = self.combo_target_preset.get()
            path = filedialog.asksaveasfilename(defaultextension='.json',
                filetypes=[('Configuracoes JSON', '*.json')], initialfile='minha_configuracao.json')
            if path:
                data['name'] = Path(path).stem
                Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
                self._preset_paths[data['name']] = Path(path)
                self.combo_saved_preset.configure(values=list(self._preset_paths))
                self.combo_saved_preset.set(data['name'])
        except (ValueError, OSError) as error:
            messagebox.showerror('Configuracao', str(error))

    def _seek_preview(self, value):
        self._pause_preview()
        self._preview_position = float(value)
        self._schedule_preview_update()

    def _pause_preview(self):
        self._playing = False
        if self._play_timer:
            self.after_cancel(self._play_timer)
            self._play_timer = None
        self.btn_play.configure(text='Reproduzir previa (sem audio)')

    def _toggle_play(self):
        if self._playing:
            self._pause_preview()
            return
        if self._preview_position >= max(0, self._preview_duration - 0.05):
            self._preview_position = 0
        self._playing = True
        self._play_origin = time.monotonic() - self._preview_position
        self.btn_play.configure(text='Pausar previa')
        self._play_tick()

    def _play_tick(self):
        self._play_timer = None
        if not self._playing:
            return
        self._preview_position = min(self._preview_duration, time.monotonic() - self._play_origin)
        if not self._preview_busy:
            self._schedule_preview_update(immediate=True)
        if self._preview_position >= self._preview_duration:
            self._pause_preview()
        else:
            self._play_timer = self.after(200, self._play_tick)

    def _dispatch_preview_thread(self):
        self._preview_debounce_timer = None
        if not self.selected_video_path or not os.path.exists(self.selected_video_path):
            return
        self._preview_request_id += 1
        req_id = self._preview_request_id
        try:
            options = self._get_options()
            options.pop('crf')
        except ValueError:
            self.lbl_preview_img.configure(text='Preencha os ajustes com numeros validos.')
            return
        self._preview_busy = True
        threading.Thread(target=self._generate_and_show_preview,
            args=(req_id, self.selected_video_path, self._preview_position, options), daemon=True).start()

    def _generate_and_show_preview(self, req_id, video_path, timestamp, options):
        fd, temp_preview = tempfile.mkstemp(suffix='.png', prefix='preview_fnk_')
        os.close(fd)
        try:
            with self._preview_lock:
                if req_id != self._preview_request_id:
                    return
                cache_key = (video_path, os.path.getmtime(video_path))
                metadata = self._metadata_cache.get(cache_key)
                if metadata is None:
                    metadata = get_video_metadata(video_path)
                    self._metadata_cache[cache_key] = metadata
                _, duration, speed, cover, _ = get_edit_timeline(metadata,
                    options['corte_inicio'], options['corte_fim'], options['velocidade'],
                    options['capa_path'], options['capa_segundos'])
                total = duration / speed + cover
                timestamp = min(timestamp, total)
                generate_preview_frame(video_path=video_path, output_image_path=temp_preview,
                    timestamp_sec=timestamp, metadata=metadata, **options)
                with Image.open(temp_preview) as raw_img:
                    img = raw_img.copy()
            self._post_ui(lambda: self._apply_preview_image(req_id, img, total, timestamp))
        except Exception as error:
            self._post_ui(lambda message=str(error): self._apply_preview_error(req_id, message))
        finally:
            if os.path.exists(temp_preview):
                os.remove(temp_preview)
            self._post_ui(lambda: self._finish_preview(req_id))

    def _finish_preview(self, req_id):
        if req_id == self._preview_request_id:
            self._preview_busy = False

    def _apply_preview_image(self, req_id, image, duration, timestamp):
        if req_id != self._preview_request_id:
            return
        image.thumbnail((340, 440), Image.Resampling.LANCZOS)
        ctk_img = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
        self.lbl_preview_img.configure(image=ctk_img, text='')
        self.lbl_preview_img.image = ctk_img
        self._preview_duration = duration
        if not self._playing:
            self._preview_position = timestamp
        self.preview_slider.configure(to=max(0.001, duration), state='normal')
        self.preview_slider.set(timestamp)
        self.lbl_preview_time.configure(text=f'{timestamp:.2f} / {duration:.2f} s')
        self.btn_play.configure(state='normal')

    def _apply_preview_error(self, req_id, error_msg):
        if req_id == self._preview_request_id:
            self._pause_preview()
            self.lbl_preview_img.configure(image='', text=f'Previa indisponivel\n{error_msg[:300]}')
            self.btn_play.configure(state='disabled')
            self.preview_slider.configure(state='disabled')

    def _start_conversion(self):
        if not self.input_files:
            messagebox.showwarning('Aviso', 'Adicione ao menos um video a fila.')
            return
        if self.is_converting:
            return
        try:
            options = self._get_options()
        except ValueError:
            messagebox.showerror('Ajustes', 'Preencha os ajustes com numeros validos.')
            return
        self._pause_preview()
        self.is_converting = True
        self.should_cancel = False
        self.btn_start.configure(state='disabled')
        self.btn_select.configure(state='disabled')
        self.btn_clear.configure(state='disabled')
        self.btn_cancel.configure(state='normal')
        self.btn_update.configure(state='disabled')
        self.progress_bar.set(0)
        self.lbl_pct.configure(text='0%')
        self._conversion_thread = threading.Thread(target=self._conversion_worker,
            args=(tuple(self.input_files), options, self.entry_out_dir.get().strip()), daemon=True)
        self._conversion_thread.start()

    def _cancel_conversion(self):
        if self.is_converting:
            self.should_cancel = True
            self.lbl_status.configure(text='Cancelando processo...')

    def _conversion_worker(self, files, options, custom_out_dir):
        successes, errors = 0, []
        w, h = options['target_resolution']
        for idx, file_path in enumerate(files, 1):
            if self.should_cancel:
                break
            base_dir = custom_out_dir or os.path.dirname(file_path)
            name = Path(file_path).stem
            out_file = Path(base_dir) / f'{name}_{w}x{h}.mp4'
            number = 2
            while out_file.exists():
                out_file = Path(base_dir) / f'{name}_{w}x{h}_{number}.mp4'
                number += 1
            self._post_ui(lambda idx=idx, path=file_path: self.lbl_status.configure(
                text=f'Convertendo [{idx}/{len(files)}]: {os.path.basename(path)}'))

            def progress(value, _text, idx=idx):
                overall = ((idx - 1) + value) / len(files)
                self._post_ui(lambda: self._show_progress(overall))
            try:
                if convert_video(file_path, str(out_file), **options,
                                 progress_callback=progress, cancel_check=lambda: self.should_cancel):
                    successes += 1
            except Exception as error:
                errors.append(f'{os.path.basename(file_path)}: {error}')
        self._post_ui(lambda: self._finish_conversion(successes, len(files), errors))

    def _show_progress(self, value):
        self.progress_bar.set(value)
        self.lbl_pct.configure(text=f'{int(value * 100)}%')

    def _finish_conversion(self, successes, total, errors):
        self.is_converting = False
        for button in (self.btn_start, self.btn_select, self.btn_clear, self.btn_update):
            button.configure(state='normal')
        self.btn_cancel.configure(state='disabled')
        if self.should_cancel:
            self.lbl_status.configure(text=f'Cancelado. {successes} video(s) concluido(s).')
        else:
            self._show_progress(1)
            self.lbl_status.configure(text=f'Concluido: {successes} de {total} video(s).')
            if errors:
                messagebox.showerror('Falhas na conversao', '\n\n'.join(errors)[:6000])
            else:
                messagebox.showinfo('Concluido', f'{successes} video(s) convertido(s).')

    def _open_output_folder(self):
        target_dir = self.entry_out_dir.get().strip()
        if not target_dir and self.input_files:
            target_dir = os.path.dirname(self.input_files[0])
        os.startfile(target_dir or os.getcwd())


def run_gui():
    app = VideoConverterApp()
    app.mainloop()


if __name__ == '__main__':
    run_gui()
