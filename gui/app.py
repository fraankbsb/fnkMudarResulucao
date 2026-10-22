import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.converter import convert_video, get_video_metadata, calculate_target_dimensions
from core.preview import generate_preview_frame
from core.updater import get_git_status, pull_updates, restart_app

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

class VideoConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('fnkMudarResolucao - Conversor 9:16 para 4:5')
        self.geometry('980x760')
        self.minsize(860, 680)

        self.input_files = []
        self.is_converting = False
        self.should_cancel = False
        self.current_preview_path = None

        self._build_ui()
        threading.Thread(target=self._check_update_silent, daemon=True).start()

    def _build_ui(self):
        # Grid Principal
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color='#1E222A')
        header_frame.grid(row=0, column=0, padx=15, pady=(15, 10), sticky='ew')
        header_frame.grid_columnconfigure(1, weight=1)

        header_top = ctk.CTkFrame(header_frame, fg_color='transparent')
        header_top.grid(row=0, column=0, padx=20, pady=(12, 4), sticky='ew')
        header_top.grid_columnconfigure(0, weight=1)

        title_lbl = ctk.CTkLabel(
            header_top,
            text='Conversor de Proporcao 9:16 -> 4:5',
            font=ctk.CTkFont(size=22, weight='bold'),
            text_color='#4CA1AF'
        )
        title_lbl.pack(side='left')

        self.btn_update = ctk.CTkButton(
            header_top,
            text='Atualizar App (Git Sync)',
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
            text='Preserva 100% da originalidade do video vertical adaptando perfeitamente para feed 4:5 (Instagram/Facebook)',
            font=ctk.CTkFont(size=13),
            text_color='#9EABB7'
        )
        sub_lbl.grid(row=1, column=0, padx=20, pady=(0, 12), sticky='w')

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
            btn_row, text='Selecionar Videos (9:16)', command=self._select_videos,
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
            highlightthickness=0, borderwidth=0, font=('Consolas', 10)
        )
        self.file_listbox.pack(fill='x', padx=10, pady=(0, 10))
        self.file_listbox.bind('<<ListboxSelect>>', self._on_file_selected)

        # Modo de Conversao
        mode_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        mode_sec.pack(fill='x', padx=10, pady=8)

        lbl_mode = ctk.CTkLabel(mode_sec, text='Modo de Preservacao da Originalidade:', font=ctk.CTkFont(weight='bold'))
        lbl_mode.pack(anchor='w', padx=10, pady=(10, 4))

        self.var_mode = ctk.StringVar(value='blur')
        self.radio_blur = ctk.CTkRadioButton(
            mode_sec, text='Fundo Desfocado Dinamico (Recomendado - Video central 100% original + bordas blur)',
            variable=self.var_mode, value='blur', command=self._update_preview_request
        )
        self.radio_blur.pack(anchor='w', padx=12, pady=4)

        self.radio_pillar = ctk.CTkRadioButton(
            mode_sec, text='Barras Laterais Solidas (Pillarbox - Video original sem cortes)',
            variable=self.var_mode, value='pillarbox', command=self._update_preview_request
        )
        self.radio_pillar.pack(anchor='w', padx=12, pady=4)

        self.radio_crop = ctk.CTkRadioButton(
            mode_sec, text='Preenchimento Total 4:5 (Corte proporcional do topo/base sem barras)',
            variable=self.var_mode, value='crop', command=self._update_preview_request
        )
        self.radio_crop.pack(anchor='w', padx=12, pady=(4, 10))

        # Ajustes Adicionais
        adv_sec = ctk.CTkFrame(left_panel, corner_radius=8)
        adv_sec.pack(fill='x', padx=10, pady=8)

        lbl_adv = ctk.CTkLabel(adv_sec, text='Parametros de Saida:', font=ctk.CTkFont(weight='bold'))
        lbl_adv.pack(anchor='w', padx=10, pady=(10, 8))

        row_res = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_res.pack(fill='x', padx=10, pady=4)
        ctk.CTkLabel(row_res, text='Resolucao Alvo (4:5):').pack(side='left')
        self.combo_res = ctk.CTkComboBox(
            row_res, values=['1080x1350 (Padrao Instagram HD)', '864x1080 (HD)', '1440x1800 (2K)'],
            width=240, command=lambda _: self._update_preview_request()
        )
        self.combo_res.set('1080x1350 (Padrao Instagram HD)')
        self.combo_res.pack(side='right')

        row_blur = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_blur.pack(fill='x', padx=10, pady=4)
        ctk.CTkLabel(row_blur, text='Intensidade do Desfoque:').pack(side='left')
        self.slider_blur = ctk.CTkSlider(row_blur, from_=10, to=80, number_of_steps=14, command=lambda _: self._update_preview_request())
        self.slider_blur.set(35)
        self.slider_blur.pack(side='right', expand=True, fill='x', padx=(10, 0))

        row_color = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_color.pack(fill='x', padx=10, pady=4)
        ctk.CTkLabel(row_color, text='Cor das Barras (Pillarbox):').pack(side='left')
        self.combo_color = ctk.CTkComboBox(row_color, values=['black', 'white', 'gray', '#111827'], width=120)
        self.combo_color.set('black')
        self.combo_color.pack(side='right')

        row_crf = ctk.CTkFrame(adv_sec, fg_color='transparent')
        row_crf.pack(fill='x', padx=10, pady=(4, 10))
        ctk.CTkLabel(row_crf, text='Qualidade Visual (CRF - 18 Maxima):').pack(side='left')
        self.slider_crf = ctk.CTkSlider(row_crf, from_=14, to=28, number_of_steps=14)
        self.slider_crf.set(18)
        self.slider_crf.pack(side='right', expand=True, fill='x', padx=(10, 0))

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

        # Coluna da Direita: Pre-Visualizacao 4:5
        right_panel = ctk.CTkFrame(content_frame, corner_radius=10)
        right_panel.grid(row=0, column=1, padx=(5, 0), pady=0, sticky='nsew')
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        lbl_prev_title = ctk.CTkLabel(right_panel, text='Pre-Visualizacao 4:5 em Tempo Real', font=ctk.CTkFont(weight='bold'))
        lbl_prev_title.grid(row=0, column=0, padx=10, pady=(10, 6), sticky='ew')

        self.preview_canvas_frame = ctk.CTkFrame(right_panel, fg_color='#15171C', corner_radius=8)
        self.preview_canvas_frame.grid(row=1, column=0, padx=12, pady=6, sticky='nsew')
        self.preview_canvas_frame.grid_rowconfigure(0, weight=1)
        self.preview_canvas_frame.grid_columnconfigure(0, weight=1)

        self.lbl_preview_img = ctk.CTkLabel(self.preview_canvas_frame, text='Selecione um video para gerar o preview')
        self.lbl_preview_img.grid(row=0, column=0, padx=10, pady=10)

        self.btn_refresh_prev = ctk.CTkButton(
            right_panel, text='Atualizar Preview', height=32, command=self._update_preview_request
        )
        self.btn_refresh_prev.grid(row=2, column=0, padx=12, pady=(6, 12), sticky='ew')

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
            action_row, text='INICIAR CONVERSAO 4:5', height=42,
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

    def _check_update_silent(self):
        info = get_git_status()
        if info.get('behind'):
            self.lbl_sync_status.configure(text='Nova versao disponivel!', text_color='#FFB74D')
            self.btn_update.configure(fg_color='#E65100', hover_color='#BF360C', text='Atualizar Agora!')
        else:
            self.lbl_sync_status.configure(text='App Sincronizado', text_color='#81C784')

    def _manual_update_check(self):
        self.btn_update.configure(state='disabled', text='Verificando...')
        self.lbl_sync_status.configure(text='Consultando GitHub...', text_color='#64B5F6')

        def run_update():
            info = get_git_status()
            if not info.get('success'):
                self.btn_update.configure(state='normal', text='Atualizar App (Git Sync)')
                self.lbl_sync_status.configure(text='Erro de conexao', text_color='#E57373')
                messagebox.showerror('Git Sync', f'Falha ao verificar atualizacoes:
' + str(info.get('message')))
                return

            if info.get('behind'):
                ok, msg = pull_updates()
                if ok:
                    messagebox.showinfo('Sucesso', 'Atualizacoes baixadas com sucesso! O aplicativo sera reiniciado.')
                    restart_app()
                else:
                    self.btn_update.configure(state='normal', text='Atualizar App (Git Sync)')
                    self.lbl_sync_status.configure(text='Erro ao puxar', text_color='#E57373')
                    messagebox.showerror('Erro', f'Falha ao baixar mudancas:
' + str(msg))
            else:
                self.btn_update.configure(state='normal', text='Atualizar App (Git Sync)')
                self.lbl_sync_status.configure(text='Ja esta na versao mais recente!', text_color='#81C784')
                messagebox.showinfo('Git Sync', 'O aplicativo ja esta 100% atualizado com o repositorio remoto!')

        threading.Thread(target=run_update, daemon=True).start()

    def _select_videos(self):
        files = filedialog.askopenfilenames(
            title='Selecione os Videos Verticais (9:16)',
            filetypes=[('Videos MP4/MOV/MKV/WEBM', '*.mp4 *.mov *.mkv *.webm'), ('Todos os arquivos', '*.*')]
        )
        if files:
            for f in files:
                if f not in self.input_files:
                    self.input_files.append(f)
                    self.file_listbox.insert(tk.END, os.path.basename(f))
            self.lbl_queue_count.configure(text=f'{len(self.input_files)} video(s) na fila')
            if len(self.input_files) > 0 and self.file_listbox.curselection() == ():
                self.file_listbox.selection_set(0)
                self._update_preview_request()

    def _clear_videos(self):
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
        self._update_preview_request()

    def _get_target_resolution(self):
        val = self.combo_res.get()
        if '1080x1350' in val:
            return 1080, 1350
        elif '864x1080' in val:
            return 864, 1080
        elif '1440x1800' in val:
            return 1440, 1800
        return 1080, 1350

    def _update_preview_request(self):
        sel = self.file_listbox.curselection()
        if not sel or not self.input_files:
            return
        idx = sel[0]
        video_path = self.input_files[idx]
        threading.Thread(target=self._generate_and_show_preview, args=(video_path,), daemon=True).start()

    def _generate_and_show_preview(self, video_path):
        try:
            self.lbl_preview_img.configure(text='Gerando previa...')
            temp_preview = os.path.join(os.environ.get('TEMP', '.'), 'preview_fnk_4_5.jpg')
            res = self._get_target_resolution()
            generate_preview_frame(
                video_path=video_path,
                output_image_path=temp_preview,
                timestamp_sec=1.0,
                mode=self.var_mode.get(),
                target_resolution=res,
                blur_strength=int(self.slider_blur.get()),
                bg_color=self.combo_color.get()
            )
            # Carrega a imagem e redimensiona para caber no frame de preview (proporcao 4:5)
            img = Image.open(temp_preview)
            disp_w = 260
            disp_h = int(disp_w * (5 / 4))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(disp_w, disp_h))
            self.lbl_preview_img.configure(image=ctk_img, text='')
        except Exception as e:
            self.lbl_preview_img.configure(text=f'Pre-visualizacao indisponivel\n{e}')

    def _start_conversion(self):
        if not self.input_files:
            messagebox.showwarning('Aviso', 'Por favor, adicione ao menos um video a fila.')
            return
        if self.is_converting:
            return

        self.is_converting = True
        self.should_cancel = False
        self.btn_start.configure(state='disabled')
        self.btn_select.configure(state='disabled')
        self.btn_clear.configure(state='disabled')
        self.btn_cancel.configure(state='normal')

        thread = threading.Thread(target=self._conversion_worker, daemon=True)
        thread.start()

    def _cancel_conversion(self):
        if self.is_converting:
            self.should_cancel = True
            self.lbl_status.configure(text='Cancelando processo...')

    def _conversion_worker(self):
        total_files = len(self.input_files)
        res = self._get_target_resolution()
        mode = self.var_mode.get()
        blur_val = int(self.slider_blur.get())
        color_val = self.combo_color.get()
        crf_val = int(self.slider_crf.get())

        custom_out_dir = self.entry_out_dir.get().strip()
        sucessos = 0

        for idx, file_path in enumerate(self.input_files, 1):
            if self.should_cancel:
                break

            base_dir = custom_out_dir if custom_out_dir else os.path.dirname(file_path)
            os.makedirs(base_dir, exist_ok=True)
            fname, ext = os.path.splitext(os.path.basename(file_path))
            out_file = os.path.join(base_dir, f'{fname}_4x5{ext}')

            self.lbl_status.configure(text=f'Convertendo [{idx}/{total_files}]: {os.path.basename(file_path)}')

            def update_progress(p, pct_text):
                overall = ((idx - 1) + p) / total_files
                self.progress_bar.set(overall)
                self.lbl_pct.configure(text=f'{int(overall * 100)}% ({pct_text})')

            try:
                ok = convert_video(
                    input_path=file_path,
                    output_path=out_file,
                    mode=mode,
                    target_resolution=res,
                    blur_strength=blur_val,
                    bg_color=color_val,
                    crf=crf_val,
                    progress_callback=update_progress,
                    cancel_check=lambda: self.should_cancel
                )
                if ok:
                    sucessos += 1
            except Exception as e:
                print(f'Erro no video {file_path}: {e}')

        self.is_converting = False
        self.btn_start.configure(state='normal')
        self.btn_select.configure(state='normal')
        self.btn_clear.configure(state='normal')
        self.btn_cancel.configure(state='disabled')

        if self.should_cancel:
            self.lbl_status.configure(text='Conversao cancelada pelo usuario.')
            messagebox.showinfo('Cancelado', 'A operacao foi interrompida.')
        else:
            self.progress_bar.set(1.0)
            self.lbl_pct.configure(text='100%')
            self.lbl_status.configure(text=f'Concluido! {sucessos} de {total_files} videos convertidos para 4:5.')
            messagebox.showinfo('Sucesso', f'Processamento concluido!\n{sucessos} video(s) convertidos em formato 4:5.')

    def _open_output_folder(self):
        target_dir = self.entry_out_dir.get().strip()
        if not target_dir and self.input_files:
            target_dir = os.path.dirname(self.input_files[0])
        if not target_dir:
            target_dir = os.getcwd()
        os.startfile(target_dir)

def run_gui():
    app = VideoConverterApp()
    app.mainloop()

if __name__ == '__main__':
    run_gui()