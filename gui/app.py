import re
import uuid
import os
import json
import math
import queue
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
import customtkinter as ctk
from PIL import Image, ImageTk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.converter import convert_video, get_video_metadata, PRESET_RATIOS, get_edit_timeline, clean_metadata
from core.playback import PreviewStream
from core.audio_preview import AudioPreview
from core.updater import get_git_status, restart_app

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

class VideoConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('fnkMudarResolucao - Conversor Universal de Resolucao & Proporcao')
        self.geometry(f'{min(1440, self.winfo_screenwidth()-70)}x{min(960, self.winfo_screenheight()-90)}')
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
        self._preview_stream = None
        self._poll_timer = None
        self._overlay_timer = None
        self._last_preview_image = None
        self._pending_frame = None
        self._playing = False
        self._can_play = False
        self._preview_expanded = False
        self._preview_duration = 0.0
        self._preview_position = 0.0
        self._custom_ratios_file = Path(__file__).resolve().parent.parent / 'presets' / 'custom_ratios.json'
        self._custom_ratios = {}
        self._load_custom_ratios()
        self._closed = False
        self._build_ui()
        self.bind('<Escape>', lambda _: self._toggle_preview_size() if self._preview_expanded else None)
        self._ui_timer = self.after(30, self._drain_ui_events)
        self.protocol('WM_DELETE_WINDOW', self._close)
        threading.Thread(target=self._check_update_silent, daemon=True).start()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header com Botao de Atualizar App
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color='#1E222A')
        header_frame.grid(row=0, column=0, padx=15, pady=(10, 5), sticky='ew')
        self._header_panel = header_frame
        header_frame.grid_columnconfigure(0, weight=1)

        header_top = ctk.CTkFrame(header_frame, fg_color='transparent')
        header_top.pack(fill='x', padx=20, pady=(12, 4))

        title_lbl = ctk.CTkLabel(
            header_top,
            text='fnkMudarResolucao',
            font=ctk.CTkFont(size=18, weight='bold'),
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
        sub_lbl.pack(anchor='w', padx=20, pady=(0, 5))

        # Conteudo em 2 colunas: Controles e Preview
        content_frame = ctk.CTkFrame(self, fg_color='transparent')
        content_frame.grid(row=1, column=0, padx=15, pady=5, sticky='nsew')
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=2)
        self._content_panel = content_frame
        content_frame.grid_rowconfigure(0, weight=1)

        # Coluna da esquerda: Configuracoes e Arquivos
        left_panel = ctk.CTkScrollableFrame(content_frame, label_text='Configuracoes e Fila de Videos')
        left_panel.grid(row=0, column=0, padx=(0, 10), pady=0, sticky='nsew')
        left_panel.grid_columnconfigure(0, weight=1)
        self._settings_panel = left_panel

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
            values=self._get_all_target_preset_names(),
            width=280,
            command=lambda _: self._schedule_preview_update(immediate=True)
        )
        self.combo_target_preset.set('9:16 (Stories/Reels/TikTok - 1080x1920)')
        self.combo_target_preset.pack(side='left', fill='x', expand=True, padx=(0, 6))

        self.btn_new_ratio = ctk.CTkButton(
            row_preset, text='+ Definicao', width=90, command=self._open_new_ratio_dialog
        )
        self.btn_new_ratio.pack(side='right')

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
        self.slider_blur.pack(side='left', expand=True, fill='x', padx=10)
        self.lbl_blur_value = ctk.CTkLabel(row_blur, width=95)
        self.lbl_blur_value.pack(side='right')

        row_color = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_color.pack(fill='x', padx=10, pady=4)
        ctk.CTkLabel(row_color, text='Cor das Barras (Solido #):').pack(side='left')

        self.btn_pick_color = ctk.CTkButton(
            row_color, text='Escolher...', width=80, command=self._pick_bar_color
        )
        self.btn_pick_color.pack(side='right', padx=(6, 0))

        self.entry_color = ctk.CTkEntry(row_color, width=90, placeholder_text='#000000')
        self.entry_color.insert(0, '#000000')
        self.entry_color.pack(side='right', padx=(6, 0))
        self.entry_color.bind('<KeyRelease>', lambda _: self._on_color_entry_change())

        self.color_preview_box = ctk.CTkLabel(row_color, text='', width=24, height=24, corner_radius=4, fg_color='#000000')
        self.color_preview_box.pack(side='right')

        # Compatibilidade com scripts e testes que usavam combo_color
        class _ColorAdapter:
            def __init__(self, entry, callback):
                self._entry = entry
                self._callback = callback
            def get(self):
                val = self._entry.get().strip()
                return val if val else '#000000'
            def set(self, val):
                self._entry.delete(0, 'end')
                self._entry.insert(0, str(val))
                self._callback()
        self.combo_color = _ColorAdapter(self.entry_color, self._update_color_box)

        row_crf = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_crf.pack(fill='x', padx=10, pady=(4, 4))
        ctk.CTkLabel(row_crf, text='Qualidade CRF (menor = melhor):').pack(side='left')
        self.slider_crf = ctk.CTkSlider(row_crf, from_=0, to=51, number_of_steps=51,
            command=lambda _: self._on_crf_slider_change())
        self.slider_crf.set(18)
        self.slider_crf.pack(side='left', expand=True, fill='x', padx=10)
        self.lbl_crf_value = ctk.CTkLabel(row_crf, width=155)
        self.lbl_crf_value.pack(side='right')

        row_max_q = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_max_q.pack(fill='x', padx=10, pady=(0, 10))
        self.var_max_quality = tk.BooleanVar(value=False)
        self.chk_max_quality = ctk.CTkCheckBox(
            row_max_q,
            text='Qualidade Maxima (CRF 0 - Fidelidade visual total sem perdas)',
            variable=self.var_max_quality,
            command=self._on_toggle_max_quality
        )
        self.chk_max_quality.pack(anchor='w')

        edit_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        edit_sec.pack(fill='x', padx=10, pady=8)
        ctk.CTkLabel(edit_sec, text='Edicao do Video', font=ctk.CTkFont(weight='bold')).pack(anchor='w', padx=10, pady=8)
        self.var_sharpen = tk.StringVar(value='0.8')
        self.var_start = tk.StringVar(value='0.25')
        self.var_end = tk.StringVar(value='0.25')
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
            if variable is self.var_sharpen:
                self.lbl_sharpen_value = ctk.CTkLabel(row, width=80)
                self.lbl_sharpen_value.pack(side='right', padx=8)
            elif variable is self.var_speed:
                self.lbl_speed_value = ctk.CTkLabel(row, width=80)
                self.lbl_speed_value.pack(side='right', padx=8)
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

        ctk.CTkLabel(edit_sec, text='100% de velocidade = normal; nitidez 100% = 2.0.',
            font=ctk.CTkFont(size=11), wraplength=440).pack(anchor='w', padx=10, pady=4)
        self._update_percentages()

        metadata_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        metadata_sec.pack(fill='x', padx=10, pady=8)
        ctk.CTkLabel(metadata_sec, text='Limpeza de Metadados e Identidade', font=ctk.CTkFont(weight='bold')).pack(anchor='w', padx=10, pady=8)
        self.var_clean_metadata = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(metadata_sec, text='Remover metadados pessoais na conversao',
                       variable=self.var_clean_metadata).pack(anchor='w', padx=10, pady=4)
        ctk.CTkLabel(metadata_sec, text='Remove autor, titulo, comentarios, datas e localizacao.\nMantem os dados tecnicos necessarios para reproduzir o video.',
                    justify='left', wraplength=450, font=ctk.CTkFont(size=11)).pack(anchor='w', padx=10, pady=4)
        self.var_unique_identity = tk.BooleanVar(value=True)
        self.var_unique_filename = tk.BooleanVar(value=False)
        self.var_mobile_profile = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(metadata_sec, text='Nome de arquivo unico e exclusivo por video (sufixo unico)',
            variable=self.var_unique_filename).pack(anchor='w', padx=10, pady=4)
        ctk.CTkCheckBox(metadata_sec, text='Gerar identificador unico por video (UUID nos metadados)',
            variable=self.var_unique_identity).pack(anchor='w', padx=10, pady=4)
        ctk.CTkCheckBox(metadata_sec, text='Formato para celular: MP4 / H.264 / AAC',
            variable=self.var_mobile_profile).pack(anchor='w', padx=10, pady=4)
        ctk.CTkLabel(metadata_sec, text='Limpeza local inspirada no padrao do Metadata2Go.\nRemove dados pessoais; conserva imagem e som.\nO UUID identifica a copia, sem inventar dados de aparelho.',
            justify='left', wraplength=450, font=ctk.CTkFont(size=11)).pack(anchor='w', padx=10, pady=4)
        self.btn_clean_metadata = ctk.CTkButton(metadata_sec,
            text='Limpar metadados da fila (sem converter)',
            command=lambda: self._start_conversion(metadata_only=True))
        self.btn_clean_metadata.pack(fill='x', padx=10, pady=(4, 10))

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
        self._preview_panel = right_panel
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        lbl_prev_title = ctk.CTkLabel(right_panel, text='Pre-Visualizacao do Resultado', font=ctk.CTkFont(weight='bold'))
        lbl_prev_title.grid(row=0, column=0, padx=10, pady=(10, 6), sticky='ew')

        self.preview_canvas_frame = ctk.CTkFrame(right_panel, fg_color='#15171C', corner_radius=8)
        self.preview_canvas_frame.grid(row=1, column=0, padx=12, pady=6, sticky='nsew')
        self.preview_canvas_frame.grid_rowconfigure(0, weight=1)
        self.preview_canvas_frame.grid_columnconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(self.preview_canvas_frame, bg='#15171C',
            highlightthickness=0, width=280, height=300)
        self.preview_canvas.grid(row=0, column=0, sticky='nsew', padx=4, pady=4)
        self.preview_canvas.bind('<Configure>', lambda _: self._draw_preview())
        self.preview_canvas.bind('<Button-1>', self._click_preview)
        self.preview_canvas.bind('<space>', lambda _: self._toggle_play())
        self.preview_canvas.bind('<Leave>', lambda _: self._hide_play_overlay())
        self.preview_canvas.bind('<Motion>', lambda _: self._show_play_overlay())
        self.preview_canvas.create_text(140, 150, text='Selecione um video', fill='white', tags='message')
        # Icone desenhado no canvas: sem quadrado, circulo ou fundo cobrindo o video.
        self._play_glyph = '▶'
        self.lbl_preview_format = ctk.CTkLabel(right_panel, text='4:5 | 1080 x 1350 | audio ao reproduzir')
        self.lbl_preview_format.grid(row=2, column=0, padx=12, pady=2, sticky='ew')
        self.preview_slider = ctk.CTkSlider(right_panel, from_=0, to=1,
            command=self._seek_preview, state='disabled')
        self.preview_slider.set(0)
        self.preview_slider.grid(row=3, column=0, padx=12, pady=4, sticky='ew')
        self.lbl_preview_time = ctk.CTkLabel(right_panel, text='0.00 / 0.00 s | 0%')
        self.lbl_preview_time.grid(row=4, column=0, padx=12, pady=2)
        preview_controls = ctk.CTkFrame(right_panel, fg_color='transparent')
        preview_controls.grid(row=5, column=0, padx=12, pady=(4, 8), sticky='ew')
        self.btn_refresh_prev = ctk.CTkButton(preview_controls, text='Atualizar previa', width=130,
            height=28, command=lambda: self._schedule_preview_update(immediate=True))
        self.btn_refresh_prev.pack(side='left', padx=(0, 5))
        self.btn_expand_preview = ctk.CTkButton(preview_controls, text='Ampliar previa', width=135,
            height=28, command=self._toggle_preview_size)
        self.btn_expand_preview.pack(side='left', padx=5)
        self.var_muted = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(preview_controls, text='Sem som', variable=self.var_muted,
            width=95, command=self._set_preview_muted).pack(side='right', padx=5)

        # Rodape: Progresso e Acoes
        footer_frame = ctk.CTkFrame(self, corner_radius=10, fg_color='#1E222A')
        footer_frame.grid(row=2, column=0, padx=15, pady=(10, 15), sticky='ew')
        footer_frame.grid_columnconfigure(0, weight=1)
        self._footer_panel = footer_frame

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
            self._ui_timer = self.after(30, self._drain_ui_events)

    def _close(self):
        self._closed = True
        self.should_cancel = True
        self._pause_preview()
        self._stop_preview_stream()
        self._preview_request_id += 1
        for timer in (self._ui_timer, self._overlay_timer, self._preview_debounce_timer):
            if timer:
                self.after_cancel(timer)
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
        self.btn_clean_metadata.configure(state='disabled')
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
        self.btn_clean_metadata.configure(state='normal')
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
        self._stop_preview_stream()
        self._preview_request_id += 1
        self._preview_position = 0.0
        self._preview_duration = 0.0
        self._preview_busy = False
        self.preview_slider.set(0)
        self.preview_slider.configure(state='disabled')
        self._set_play_enabled(False)
        self.lbl_preview_time.configure(text='0.00 / 0.00 s | 0%')
        if self._preview_debounce_timer:
            self.after_cancel(self._preview_debounce_timer)
            self._preview_debounce_timer = None
        self.selected_video_path = None
        self.input_files.clear()
        self.file_listbox.delete(0, tk.END)
        self.lbl_queue_count.configure(text='Nenhum video selecionado')
        self._last_preview_image = None
        self._preview_message('Selecione um video')

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

    def _load_custom_ratios(self):
        self._custom_ratios = {}
        if self._custom_ratios_file.exists():
            try:
                data = json.loads(self._custom_ratios_file.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, (list, tuple)) and len(v) == 2:
                            self._custom_ratios[k] = (int(v[0]), int(v[1]))
            except Exception:
                pass

    def _save_custom_ratios(self):
        try:
            self._custom_ratios_file.parent.mkdir(parents=True, exist_ok=True)
            self._custom_ratios_file.write_text(
                json.dumps(self._custom_ratios, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as error:
            messagebox.showerror('Definicoes', f'Erro ao salvar definicoes personalizadas: {error}')

    def _get_all_target_preset_names(self):
        return list(PRESET_RATIOS) + list(self._custom_ratios)

    def _get_target_resolution(self):
        key = self.combo_target_preset.get()
        if key in self._custom_ratios:
            return self._custom_ratios[key]
        return PRESET_RATIOS.get(key, (1080, 1350))

    def _open_new_ratio_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title('Criar Nova Definicao de Proporcao')
        dialog.geometry('420x290')
        dialog.resizable(False, False)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text='Criar Proporcao / Resolucao Personalizada', font=ctk.CTkFont(size=14, weight='bold')).pack(pady=(16, 10))

        frame = ctk.CTkFrame(dialog, fg_color='transparent')
        frame.pack(fill='x', padx=20, pady=5)

        ctk.CTkLabel(frame, text='Nome da Definicao:').pack(anchor='w', pady=(0, 2))
        entry_name = ctk.CTkEntry(frame, placeholder_text='Ex: 16:9 Ultra HD (3840x2160)')
        entry_name.pack(fill='x', pady=(0, 8))

        row_dims = ctk.CTkFrame(frame, fg_color='transparent')
        row_dims.pack(fill='x', pady=4)

        col_w = ctk.CTkFrame(row_dims, fg_color='transparent')
        col_w.pack(side='left', expand=True, fill='x', padx=(0, 5))
        ctk.CTkLabel(col_w, text='Largura (px):').pack(anchor='w')
        entry_w = ctk.CTkEntry(col_w, placeholder_text='1080')
        entry_w.pack(fill='x')

        col_h = ctk.CTkFrame(row_dims, fg_color='transparent')
        col_h.pack(side='right', expand=True, fill='x', padx=(5, 0))
        ctk.CTkLabel(col_h, text='Altura (px):').pack(anchor='w')
        entry_h = ctk.CTkEntry(col_h, placeholder_text='1920')
        entry_h.pack(fill='x')

        def save_ratio():
            name = entry_name.get().strip()
            w_str = entry_w.get().strip()
            h_str = entry_h.get().strip()
            if not name:
                messagebox.showerror('Erro', 'Informe um nome para a definicao.')
                return
            try:
                w, h = int(w_str), int(h_str)
                if w < 16 or h < 16:
                    raise ValueError('Dimensoes minimas de 16x16 pixels.')
            except ValueError as e:
                messagebox.showerror('Erro', f'Dimensoes invalidas: {e}')
                return
            label = f'{name} ({w}x{h})' if f'{w}x{h}' not in name else name
            self._custom_ratios[label] = (w, h)
            self._save_custom_ratios()
            names = self._get_all_target_preset_names()
            self.combo_target_preset.configure(values=names)
            self.combo_target_preset.set(label)
            self._schedule_preview_update(immediate=True)
            dialog.destroy()
            messagebox.showinfo('Sucesso', f'Definicao "{label}" criada e salva com sucesso!')

        btn_row = ctk.CTkFrame(dialog, fg_color='transparent')
        btn_row.pack(fill='x', padx=20, pady=(16, 10))
        ctk.CTkButton(btn_row, text='Salvar Definicao', command=save_ratio).pack(side='left', expand=True, fill='x', padx=(0, 6))
        ctk.CTkButton(btn_row, text='Cancelar', fg_color='#555555', hover_color='#444444', command=dialog.destroy).pack(side='right', expand=True, fill='x', padx=(6, 0))

    def _on_crf_slider_change(self):
        val = int(self.slider_crf.get())
        if val != 0 and self.var_max_quality.get():
            self.var_max_quality.set(False)
        self._update_percentages()

    def _on_toggle_max_quality(self):
        if self.var_max_quality.get():
            self.slider_crf.set(0)
        else:
            self.slider_crf.set(18)
        self._update_percentages()

    def _update_color_box(self):
        color = self.entry_color.get().strip()
        try:
            self.color_preview_box.configure(fg_color=color)
        except Exception:
            pass

    def _on_color_entry_change(self):
        color = self.entry_color.get().strip()
        self._update_color_box()
        if re.fullmatch(r'[a-zA-Z]+|#[0-9a-fA-F]{6}|0x[0-9a-fA-F]{6}', color):
            self._schedule_preview_update(immediate=True)

    def _pick_bar_color(self):
        current = self.entry_color.get().strip() or '#000000'
        chosen = colorchooser.askcolor(color=current, title='Escolher cor das barras solidas')
        if chosen and chosen[1]:
            hex_color = chosen[1].lower()
            self.entry_color.delete(0, 'end')
            self.entry_color.insert(0, hex_color)
            self._update_color_box()
            self._schedule_preview_update(immediate=True)

    def _schedule_preview_update(self, immediate: bool = False):
        self._update_percentages()
        self._resume_after_load = False
        self._pause_preview()
        self._stop_preview_stream()
        self._preview_request_id += 1
        self._last_preview_image = None
        self._preview_message('Preparando previa...')
        self._update_format_label()
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
            try:
                from core.converter import converter_imagem_capa_1080x1920
                caminho_convertido = converter_imagem_capa_1080x1920(path)
                self.var_cover.set(caminho_convertido)
            except Exception as e:
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
                    crf=int(self.slider_crf.get()), limpar_metadados=self.var_clean_metadata.get(),
                    identidade_unica=self.var_unique_identity.get(), nome_unico=self.var_unique_filename.get(), perfil_celular=self.var_mobile_profile.get(),
                    **self._get_edit_options())

    def _apply_preset_data(self, data):
        # Valida antes de alterar controles para evitar uma configuracao parcial.
        target = data.get('target_preset', self.combo_target_preset.get())
        mode = data.get('mode', 'blur')
        if target not in self._get_all_target_preset_names() or mode not in ('blur', 'pillarbox', 'crop'):
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
        self.var_clean_metadata.set(bool(data.get('limpar_metadados', True)))
        self.var_unique_identity.set(bool(data.get('identidade_unica', True)))
        self.var_unique_filename.set(bool(data.get('nome_unico', False)))
        self.var_mobile_profile.set(bool(data.get('perfil_celular', True)))
        self._update_percentages()
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

    def _update_percentages(self):
        if not hasattr(self, 'lbl_blur_value'):
            return
        blur = int(self.slider_blur.get())
        crf = int(self.slider_crf.get())
        self.lbl_blur_value.configure(text=f'{blur / 80:.0%} ({blur})')
        if crf == 0:
            self.lbl_crf_value.configure(text='100% | Maxima (CRF 0)')
        else:
            self.lbl_crf_value.configure(text=f'{(51-crf)/51:.0%} escala | CRF {crf}')
        try:
            self.lbl_sharpen_value.configure(text=f'{float(self.var_sharpen.get().replace(",", "."))/2:.0%}')
            self.lbl_speed_value.configure(text=f'{float(self.var_speed.get().replace(",", ".")):.0%}')
        except (ValueError, AttributeError):
            pass

    def _update_format_label(self):
        w, h = self._get_target_resolution()
        divisor = math.gcd(w, h)
        stream = self._preview_stream
        audio = getattr(stream, 'audio', None)
        if audio and audio.error:
            sound = 'audio indisponivel'
        elif audio:
            sound = 'som desativado' if self.var_muted.get() else 'com audio'
        elif stream is not None:
            sound = 'video sem faixa de audio'
        else:
            sound = 'audio ao reproduzir'
        self.lbl_preview_format.configure(text=f'{w//divisor}:{h//divisor} | {w} x {h} | {sound}')

    def _preview_message(self, message):
        self.preview_canvas.delete('all')
        self.preview_canvas.create_text(max(1, self.preview_canvas.winfo_width())/2,
            max(1, self.preview_canvas.winfo_height())/2, text=message, fill='white',
            width=max(100, self.preview_canvas.winfo_width()-24), tags='message')
        self._set_play_enabled(False)

    def _draw_preview(self):
        if self._last_preview_image is None:
            self.preview_canvas.coords('message', self.preview_canvas.winfo_width()/2,
                                       self.preview_canvas.winfo_height()/2)
            return
        image = self._last_preview_image
        cw, ch = self.preview_canvas.winfo_width(), self.preview_canvas.winfo_height()
        factor = min(max(1, cw-8)/image.width, max(1, ch-8)/image.height)
        size = (max(1, round(image.width*factor)), max(1, round(image.height*factor)))
        self._preview_photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.BILINEAR))
        self.preview_canvas.delete('message')
        if not self.preview_canvas.find_withtag('video'):
            self.preview_canvas.create_image(cw/2, ch/2, image=self._preview_photo, tags='video')
        else:
            self.preview_canvas.coords('video', cw/2, ch/2)
            self.preview_canvas.itemconfigure('video', image=self._preview_photo)
        self.preview_canvas.tag_raise('play_overlay')

    def _set_play_enabled(self, enabled):
        self._can_play = enabled
        if not enabled:
            self.preview_canvas.delete('play_overlay')

    def _click_preview(self, _event=None):
        self.preview_canvas.focus_set()
        self._toggle_play()

    def _show_play_overlay(self):
        if not self._can_play:
            return
        self.preview_canvas.delete('play_overlay')
        x, y = self.preview_canvas.winfo_width()/2, self.preview_canvas.winfo_height()/2
        self.preview_canvas.create_text(x+1, y+1, text=self._play_glyph, fill='#202020',
            font=('Segoe UI Symbol', 21), tags='play_overlay')
        self.preview_canvas.create_text(x, y, text=self._play_glyph, fill='white',
            font=('Segoe UI Symbol', 21), tags='play_overlay')
        if self._overlay_timer:
            self.after_cancel(self._overlay_timer)
        self._overlay_timer = self.after(600, self._hide_play_overlay)

    def _hide_play_overlay(self):
        self._overlay_timer = None
        self.preview_canvas.delete('play_overlay')

    def _toggle_preview_size(self):
        self._preview_expanded = not self._preview_expanded
        if self._preview_expanded:
            self._settings_panel.grid_remove()
            self._header_panel.grid_remove()
            self._footer_panel.grid_remove()
            self._preview_panel.grid_configure(column=0, columnspan=2)
            self.btn_expand_preview.configure(text='Restaurar painel')
        else:
            self._settings_panel.grid()
            self._header_panel.grid()
            self._footer_panel.grid()
            self._preview_panel.grid_configure(column=1, columnspan=1)
            self.btn_expand_preview.configure(text='Ampliar previa')
        self.after_idle(self._draw_preview)

    def _set_preview_muted(self):
        audio = getattr(self._preview_stream, 'audio', None)
        if audio:
            audio.muted = self.var_muted.get()
        self._update_format_label()

    def _seek_preview(self, value):
        self._preview_position = float(value)
        self._schedule_preview_update()

    def _stop_preview_stream(self):
        if self._poll_timer:
            self.after_cancel(self._poll_timer)
            self._poll_timer = None
        stream = self._preview_stream
        self._preview_stream = None
        self._pending_frame = None
        if stream:
            audio = getattr(stream, 'audio', None)
            if audio:
                audio.close()
            stream.close()

    def _pause_preview(self):
        self._playing = False
        audio = getattr(self._preview_stream, 'audio', None)
        if audio:
            audio.pause()
        self._play_glyph = '▶'
        self._show_play_overlay()

    def _toggle_play(self):
        if self._playing:
            self._pause_preview()
            return
        if self._preview_stream is None or not self._can_play:
            return
        if self._preview_position >= self._preview_duration - 1/self._preview_stream.fps:
            self._preview_position = 0
            self._schedule_preview_update(immediate=True)
            self._resume_after_load = True
            return
        self._playing = True
        self._play_origin = time.monotonic() - self._preview_position
        audio = getattr(self._preview_stream, 'audio', None)
        if audio and not audio.error:
            audio.resume()
        self._play_glyph = 'Ⅱ'
        self._show_play_overlay()

    def _dispatch_preview_thread(self):
        self._preview_debounce_timer = None
        if not self.selected_video_path or not os.path.exists(self.selected_video_path):
            return
        req_id = self._preview_request_id
        try:
            options = self._get_options()
            options.pop('crf')
            options.pop('limpar_metadados')
            options.pop('identidade_unica')
            options.pop('perfil_celular')
        except ValueError:
            self._preview_message('Preencha os ajustes com numeros validos.')
            return
        self._preview_busy = True
        threading.Thread(target=self._prepare_preview,
            args=(req_id, self.selected_video_path, self._preview_position, options, self.var_muted.get()), daemon=True).start()

    def _prepare_preview(self, req_id, video_path, timestamp, options, muted=False):
        try:
            with self._preview_lock:
                if self._closed or req_id != self._preview_request_id:
                    return
                cache_key = (video_path, os.path.getmtime(video_path))
                metadata = self._metadata_cache.get(cache_key)
                if metadata is None:
                    metadata = get_video_metadata(video_path)
                    self._metadata_cache = {cache_key: metadata}
                stream = PreviewStream(video_path, metadata, timestamp, **options)
                stream.audio = AudioPreview(video_path, metadata, stream.position, muted=muted, **options) if metadata.has_audio else None
                if self._closed or req_id != self._preview_request_id:
                    if stream.audio: stream.audio.close()
                    stream.close()
                    return
                self._preview_stream = stream
                if self._closed:
                    if stream.audio: stream.audio.close()
                    stream.close()
                    return
            self._post_ui(lambda: self._accept_preview(req_id, stream))
        except Exception as error:
            self._post_ui(lambda message=str(error): self._apply_preview_error(req_id, message))

    def _accept_preview(self, req_id, stream):
        if req_id != self._preview_request_id or self._closed:
            if stream.audio: stream.audio.close()
            stream.close()
            return
        self._preview_duration = stream.duration
        self._audio_failed = False
        self._set_preview_muted()
        self._preview_position = stream.position
        self.preview_slider.configure(to=max(0.001, stream.duration), state='normal')
        self._poll_preview()

    def _update_preview_time(self):
        self.preview_slider.set(self._preview_position)
        percent = self._preview_position / self._preview_duration if self._preview_duration else 0
        self.lbl_preview_time.configure(text=f'{self._preview_position:.2f} / {self._preview_duration:.2f} s | {percent:.0%}')

    def _poll_preview(self):
        self._poll_timer = None
        stream = self._preview_stream
        if stream is None or self._closed:
            return
        audio = getattr(stream, 'audio', None)
        if audio and audio.error and not self._audio_failed:
            self._audio_failed = True
            audio.close()
            self._play_origin = time.monotonic()-self._preview_position
            self._update_format_label()
            self.lbl_status.configure(text=f'Som indisponivel: {audio.error[:180]}')
        desired = time.monotonic()-self._play_origin if self._playing else self._preview_position
        if self._playing and audio and not audio.error:
            desired = audio.position if audio.ready.is_set() else self._preview_position
        frame_to_show = None
        if self._playing or self._last_preview_image is None:
            while True:
                if self._pending_frame is None:
                    try:
                        self._pending_frame = stream.frames.get_nowait()
                    except queue.Empty:
                        break
                timestamp, image = self._pending_frame
                if self._last_preview_image is not None and timestamp > desired + 0.001:
                    break
                frame_to_show = self._pending_frame
                self._pending_frame = None
                if not self._playing:
                    break
        if frame_to_show:
            self._preview_position, self._last_preview_image = frame_to_show
            self._draw_preview()
            self._update_preview_time()
            self._set_play_enabled(True)
            self._preview_busy = False
            if getattr(self, '_resume_after_load', False):
                self._resume_after_load = False
                self._toggle_play()
        if stream.finished.is_set() and stream.frames.empty() and self._pending_frame is None:
            if stream.error:
                self._apply_preview_error(self._preview_request_id, stream.error)
                return
            if self._playing and (not audio or audio.error or audio.position >= stream.duration-0.015):
                self._preview_position = stream.duration
                self._update_preview_time()
                self._pause_preview()
        self._poll_timer = self.after(10, self._poll_preview)

    def _apply_preview_error(self, req_id, error_msg):
        if req_id == self._preview_request_id:
            self._pause_preview()
            self._stop_preview_stream()
            self._preview_busy = False
            self._last_preview_image = None
            self._preview_message(f'Previa indisponivel\n{error_msg[:300]}')
            self.preview_slider.configure(state='disabled')

    def _start_conversion(self, metadata_only=False):
        if not self.input_files:
            messagebox.showwarning('Aviso', 'Adicione ao menos um video a fila.')
            return
        if self.is_converting:
            return
        try:
            options = {'target_resolution': self._get_target_resolution(), 'identidade_unica': self.var_unique_identity.get()} if metadata_only else self._get_options()
        except ValueError:
            messagebox.showerror('Ajustes', 'Preencha os ajustes com numeros validos.')
            return
        self._pause_preview()
        self._stop_preview_stream()
        self._set_play_enabled(False)
        self.is_converting = True
        self.should_cancel = False
        self.btn_start.configure(state='disabled')
        self.btn_select.configure(state='disabled')
        self.btn_clear.configure(state='disabled')
        self.btn_cancel.configure(state='normal')
        self.btn_update.configure(state='disabled')
        self.btn_clean_metadata.configure(state='disabled')
        self.progress_bar.set(0)
        self.lbl_pct.configure(text='0%')
        unique_filename = bool(self.var_unique_filename.get())
        self._conversion_thread = threading.Thread(target=self._conversion_worker,
            args=(tuple(self.input_files), options, self.entry_out_dir.get().strip(), metadata_only, unique_filename), daemon=True)
        self._conversion_thread.start()

    def _cancel_conversion(self):
        if self.is_converting:
            self.should_cancel = True
            self.lbl_status.configure(text='Cancelando processo...')

    def _conversion_worker(self, files, options, custom_out_dir, metadata_only=False, unique_filename=False):
        successes, errors = 0, []
        w, h = options['target_resolution']
        for idx, file_path in enumerate(files, 1):
            if self.should_cancel:
                break
            base_dir = custom_out_dir or os.path.dirname(file_path)
            name = Path(file_path).stem
            unique_token = f'_{uuid.uuid4().hex[:8]}' if unique_filename else ''
            suffix = f'_metadados_limpos{unique_token}' if metadata_only else f'_{w}x{h}{unique_token}'
            extension = Path(file_path).suffix if metadata_only else '.mp4'
            out_file = Path(base_dir) / f'{name}{suffix}{extension}'
            number = 2
            while out_file.exists():
                out_file = Path(base_dir) / f'{name}{suffix}_{number}{extension}'
                number += 1
            action = 'Limpando metadados' if metadata_only else 'Convertendo'
            self._post_ui(lambda idx=idx, path=file_path: self.lbl_status.configure(
                text=f'{action} [{idx}/{len(files)}]: {os.path.basename(path)}'))

            def progress(value, _text, idx=idx):
                overall = ((idx - 1) + value) / len(files)
                self._post_ui(lambda: self._show_progress(overall))
            try:
                function = clean_metadata if metadata_only else convert_video
                arguments = {'identidade_unica': options['identidade_unica']} if metadata_only else options
                if function(file_path, str(out_file), **arguments,
                            progress_callback=progress, cancel_check=lambda: self.should_cancel):
                    successes += 1
                    if unique_filename and out_file.exists():
                        try:
                            now = time.time()
                            os.utime(str(out_file), (now, now))
                        except Exception:
                            pass
            except Exception as error:
                errors.append(f'{os.path.basename(file_path)}: {error}')
        self._post_ui(lambda: self._finish_conversion(successes, len(files), errors))

    def _show_progress(self, value):
        self.progress_bar.set(value)
        self.lbl_pct.configure(text=f'{int(value * 100)}%')

    def _finish_conversion(self, successes, total, errors):
        self.is_converting = False
        for button in (self.btn_start, self.btn_select, self.btn_clear, self.btn_update, self.btn_clean_metadata):
            button.configure(state='normal')
        self.btn_cancel.configure(state='disabled')
        if self.selected_video_path:
            self._schedule_preview_update(immediate=True)
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
