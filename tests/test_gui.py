import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from core.converter import PRESET_RATIOS


@unittest.skipUnless((os.name == 'nt' or os.environ.get('DISPLAY')) and shutil.which('ffmpeg'),
                     'Interface requer ambiente grafico e FFmpeg')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='fnk_gui_')
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'testsrc2=s=160x120:r=30:d=2', '-c:v', 'libx264', '-threads', '2', str(cls.source)],
            capture_output=True, check=True)
        from gui.app import VideoConverterApp
        cls.status_patch = patch('gui.app.get_git_status', return_value={'success': True})
        cls.status_patch.start()
        cls.app = VideoConverterApp()
        cls.app.withdraw()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app._close()
        cls.status_patch.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.app._clear_videos()
        self.app.var_speed.set('1')
        self.app.var_sharpen.set('0')
        self.app.entry_out_dir.delete(0, 'end')
        self.info_patch = patch('gui.app.messagebox.showinfo')
        self.info_patch.start()
        self.addCleanup(self.info_patch.stop)
        self.error_patch = patch('gui.app.messagebox.showerror')
        self.errors = self.error_patch.start()
        self.addCleanup(self.error_patch.stop)
        self.app.input_files = [str(self.source)]
        self.app.selected_video_path = str(self.source)
        self.app.file_listbox.insert('end', self.source.name)
        self.app.file_listbox.selection_set(0)

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.005)
        self.assertTrue(predicate(), 'Interface nao terminou a operacao')

    def pump(self, seconds):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.003)

    def load(self):
        self.app._schedule_preview_update(immediate=True)
        self.wait_for(lambda: self.app._last_preview_image is not None)

    def test_center_click_play_pause_is_continuous(self):
        app = self.app
        self.load()
        process = app._preview_stream.process.pid
        self.assertEqual(app.btn_play.place_info()['relx'], '0.5')
        self.assertEqual(app.btn_play.place_info()['rely'], '0.5')
        with patch.object(app, '_draw_preview', wraps=app._draw_preview) as draw:
            app.btn_play.invoke()
            self.pump(0.65)
            self.assertGreaterEqual(draw.call_count, 10)
            self.assertEqual(app._preview_stream.process.pid, process)
            # O mesmo controle central pausa e retoma sem trocar o decodificador.
            app.btn_play.invoke()
            self.assertFalse(app._playing)
            position = app._preview_position
            self.pump(0.15)
            self.assertEqual(app._preview_position, position)
            app.btn_play.invoke()
            self.pump(0.15)
            self.assertGreater(app._preview_position, position)

    def test_each_target_replaces_previous_preview_and_shows_percentages(self):
        app = self.app
        for name, size in PRESET_RATIOS.items():
            app.combo_target_preset.set(name)
            self.load()
            image = app._last_preview_image
            self.assertAlmostEqual(image.width/image.height, size[0]/size[1])
            self.assertIn(f'{size[0]} x {size[1]}', app.lbl_preview_format.cget('text'))
        self.assertIn('44%', app.lbl_blur_value.cget('text'))
        self.assertIn('CRF 18', app.lbl_crf_value.cget('text'))
        app.var_sharpen.set('0.8')
        app.var_speed.set('1.25')
        self.assertEqual(app.lbl_sharpen_value.cget('text'), '40%')
        self.assertEqual(app.lbl_speed_value.cget('text'), '125%')
        self.assertIn('%', app.lbl_preview_time.cget('text'))

    def test_metadata_only_button_works_without_valid_edit_fields(self):
        app = self.app
        app.var_speed.set('campo incompleto')
        app.entry_out_dir.insert(0, str(self.root))
        app.btn_clean_metadata.invoke()
        self.wait_for(lambda: not app.is_converting)
        self.assertFalse(self.errors.called, self.errors.call_args)
        self.assertTrue((self.root / 'source_metadados_limpos.mp4').exists())
