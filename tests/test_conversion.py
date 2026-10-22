import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

from core.converter import convert_video, get_video_metadata
from core.preview import generate_preview_frame


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg necessario')
class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='fnk_tests_')
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source.mp4'
        cls.silent = cls.root / 'silent.mp4'
        cls.cover = cls.root / 'cover.png'
        # Duas cores e mudanca temporal permitem conferir espelho e cortes.
        cls.run_ffmpeg('-f', 'lavfi', '-i',
            'color=red:s=160x120:r=12:d=2,drawbox=x=80:y=0:w=80:h=120:color=blue:t=fill',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=2',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(cls.source))
        cls.run_ffmpeg('-i', str(cls.source), '-an', '-c:v', 'copy', str(cls.silent))
        cls.temporal = cls.root / 'temporal.mp4'
        cls.run_ffmpeg('-f', 'lavfi', '-i', 'testsrc2=s=160x120:r=12:d=2',
                       '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.temporal))
        Image.new('RGB', (90, 160), (0, 255, 0)).save(cls.cover)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @staticmethod
    def run_ffmpeg(*args):
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *args],
                       check=True, capture_output=True)

    def probe(self, path):
        return json.loads(subprocess.check_output(['ffprobe', '-v', 'quiet',
            '-show_streams', '-show_format', '-of', 'json', str(path)]))

    def convert(self, source=None, **options):
        output = self.root / (self._testMethodName + '.mp4')
        self.assertTrue(convert_video(str(source or self.source), str(output),
            target_resolution=(120, 150), preset='ultrafast', **options))
        metadata = get_video_metadata(str(output))
        self.assertEqual((metadata.width, metadata.height), (120, 150))
        return output

    def frame(self, path, time=0):
        image = self.root / 'frame.png'
        self.run_ffmpeg('-ss', str(time), '-i', str(path), '-frames:v', '1', '-update', '1', str(image))
        with Image.open(image) as data:
            return data.convert('RGB')

    def test_modes_and_silent_sources(self):
        for mode in ('blur', 'pillarbox', 'crop'):
            with self.subTest(mode=mode):
                path = self.convert(source=self.silent, mode=mode, sharpen_strength=0.8)
                self.assertFalse(get_video_metadata(str(path)).has_audio)

    def test_unchanged_audio_is_copied(self):
        output = self.convert()
        def audio_hash(path):
            return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
                '-map', '0:a:0', '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'])
        self.assertEqual(audio_hash(self.source), audio_hash(output))

    def test_cover_cuts_speed_and_audio_sync(self):
        output = self.convert(corte_inicio=0.25, corte_fim=0.25, velocidade=2,
            capa_path=str(self.cover), capa_segundos=0.25, espelhar=True, sharpen_strength=1)
        data = self.probe(output)
        durations = [float(s['duration']) for s in data['streams']]
        for duration in durations:
            self.assertAlmostEqual(duration, 1.0, delta=0.09)
        pixel = self.frame(output).getpixel((60, 75))
        self.assertGreater(pixel[1], 230)
        # Audio da capa deve ser silencio; corpo deve conter o tom original.
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(output),
            '-map', '0:a:0', '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'])
        import array
        samples = array.array('f', raw)
        def rms(values):
            return math.sqrt(sum(x*x for x in values) / len(values))
        self.assertLess(rms(samples[:9000]), 0.001)
        self.assertGreater(rms(samples[16000:22000]), 0.02)

    def test_cover_on_silent_video_and_fit_modes(self):
        for fit in ('preencher', 'inteira', 'esticar'):
            with self.subTest(fit=fit):
                output = self.convert(source=self.silent, capa_path=str(self.cover),
                    capa_segundos=0.1, capa_ajuste=fit)
                self.assertFalse(get_video_metadata(str(output)).has_audio)
                self.assertAlmostEqual(get_video_metadata(str(output)).duration, 2 + 1/12, delta=0.1)

    def test_slow_and_fast_audio(self):
        for speed in (0.25, 0.5, 4):
            with self.subTest(speed=speed):
                output = self.convert(velocidade=speed, corte_fim=1)
                durations = [float(s['duration']) for s in self.probe(output)['streams']]
                for duration in durations:
                    self.assertAlmostEqual(duration, 1 / speed, delta=0.1)

    def test_mirror_pixels(self):
        output = self.convert(mode='pillarbox', espelhar=True)
        image = self.frame(output, 0.5)
        left, right = image.getpixel((20, 75)), image.getpixel((100, 75))
        self.assertGreater(left[2], left[0] + 150)
        self.assertGreater(right[0], right[2] + 150)

    def test_preview_matches_export_timeline(self):
        edits = dict(corte_inicio=0.5, corte_fim=0.5, velocidade=0.5,
                     capa_path=str(self.cover), capa_segundos=0.25, espelhar=True)
        output = self.convert(source=self.temporal, **edits)
        for timestamp in (0, 0.25, 0.75, 1.25):
            with self.subTest(timestamp=timestamp):
                preview = self.root / 'preview.png'
                generate_preview_frame(str(self.temporal), str(preview), timestamp_sec=timestamp,
                    target_resolution=(120, 150), **edits)
                with Image.open(preview) as image:
                    diff = ImageChops.difference(image.convert('RGB'), self.frame(output, timestamp))
                    self.assertLess(sum(ImageStat.Stat(diff).mean)/3, 12)

    def test_cli_with_all_edit_options(self):
        output = self.root / 'cli_result.mp4'
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'),
            '--cli', '-i', str(self.source), '-o', str(output), '--width', '120', '--height', '150',
            '--corte-inicio', '0.25', '--corte-fim', '0.25', '--velocidade', '2', '--espelhar',
            '--sharpen-strength', '0.8', '--capa', str(self.cover), '--capa-segundos', '0.25',
            '--preset', 'ultrafast'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertAlmostEqual(get_video_metadata(str(output)).duration, 1, delta=0.1)

    def test_cli_batch_reports_failure(self):
        batch = self.root / 'batch'
        batch.mkdir()
        (batch / 'broken.mp4').write_bytes(b'not a video')
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'),
            '--cli', '-i', str(batch)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)

    def test_invalid_edits_preserve_existing_output(self):
        output = self.root / 'existing.mp4'
        output.write_bytes(b'existing file')
        for edits in (dict(corte_inicio=2), dict(corte_fim=3), dict(velocidade=0),
                      dict(velocidade=float('nan')), dict(capa_path='missing.png'),
                      dict(sharpen_strength=9), dict(mode='invalid')):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                convert_video(str(self.source), str(output), **edits)
            self.assertEqual(output.read_bytes(), b'existing file')
        with self.assertRaises(ValueError):
            convert_video(str(self.source), str(self.source))

    def test_ffmpeg_failure_preserves_output_and_reports_error(self):
        output = self.root / 'existing_error.mp4'
        output.write_bytes(b'existing file')
        with self.assertRaisesRegex(RuntimeError, 'FFmpeg:'):
            convert_video(str(self.source), str(output), target_resolution=(120, 150), preset='invalid')
        self.assertEqual(output.read_bytes(), b'existing file')
        self.assertFalse(list(self.root.glob('.fnk_*')))

    def test_cancel_preserves_output_and_cleans_temporary(self):
        output = self.root / 'cancel.mp4'
        output.write_bytes(b'existing file')
        self.assertFalse(convert_video(str(self.source), str(output),
            target_resolution=(120, 150), cancel_check=lambda: True))
        self.assertEqual(output.read_bytes(), b'existing file')
        self.assertFalse(list(self.root.glob('.fnk_*')))


if __name__ == '__main__':
    unittest.main()
