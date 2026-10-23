import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

from core.converter import convert_video, get_video_metadata, clean_metadata
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

    def tagged_source(self):
        chapters = self.root / 'chapters.txt'
        chapters.write_text(';FFMETADATA1\ntitle=TITULO PRIVADO\nartist=AUTOR PRIVADO\ncomment=COMENTARIO PRIVADO\n'
            '[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=CAPITULO PRIVADO\n', encoding='utf-8')
        tagged = self.root / 'tagged.mp4'
        self.run_ffmpeg('-i', str(self.source), '-i', str(chapters), '-map', '0',
            '-map_metadata', '1', '-map_chapters', '1', '-c', 'copy',
            '-metadata', 'creation_time=2020-01-01T00:00:00Z',
            '-metadata', 'location=+01.23+004.56/', '-metadata', 'make=FNK_TEST_PHONE',
            '-metadata', 'model=FNK_TEST_MODEL', '-metadata', 'serial_number=FNK_TEST_SERIAL',
            '-movflags', '+use_metadata_tags', str(tagged))
        return tagged

    def assert_metadata_clean(self, path):
        raw = subprocess.check_output(['ffprobe', '-v', 'quiet', '-show_format',
            '-show_streams', '-show_chapters', '-of', 'json', str(path)]).decode('utf-8')
        for value in ('PRIVADO', '2020-01-01', '+01.23', 'FNK_TEST_PHONE', 'FNK_TEST_MODEL', 'FNK_TEST_SERIAL'):
            self.assertNotIn(value, raw)
        self.assertFalse(json.loads(raw).get('chapters'))

    def test_metadata_removal_without_reencoding(self):
        source = self.tagged_source()
        output = self.root / 'cleaned.mp4'
        self.assertTrue(clean_metadata(str(source), str(output)))
        self.assert_metadata_clean(output)
        for stream in ('0:v:0', '0:a:0'):
            def packet_hash(path):
                return subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path),
                    '-map', stream, '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-'])
            self.assertEqual(packet_hash(source), packet_hash(output))

    def test_metadata_removal_during_conversion_and_opt_out(self):
        source = self.tagged_source()
        output = self.convert(source=source)
        self.assert_metadata_clean(output)
        output = self.convert(source=source, limpar_metadados=False)
        self.assertEqual(self.probe(output)['format']['tags']['title'], 'TITULO PRIVADO')

    def test_cli_metadata_only(self):
        source = self.tagged_source()
        output = self.root / 'cli_clean.mp4'
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'),
            '--cli', '-i', str(source), '-o', str(output), '--somente-limpar-metadados'],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_metadata_clean(output)
        self.assertEqual(get_video_metadata(str(output)).width, 160)

    def test_unique_identity_and_mobile_profile(self):
        import uuid
        source=self.tagged_source()
        identities=[]
        for n in (1,2):
            output=self.root/f'mobile_{n}.mp4'
            convert_video(str(source),str(output),target_resolution=(120,150),preset='ultrafast',
                          identidade_unica=True,perfil_celular=True)
            self.assert_metadata_clean(output)
            data=self.probe(output)
            identifier=data['format']['tags']['content_identifier']
            self.assertEqual(uuid.UUID(identifier).version,4)
            identities.append(identifier)
            self.assertEqual(data['format']['tags']['major_brand'],'mp42')
            self.assertEqual([s['codec_name'] for s in data['streams']],['h264','aac'])
            self.assertEqual(data['streams'][0]['pix_fmt'],'yuv420p')
        self.assertNotEqual(*identities)
        output=self.root/'clean_uuid.mp4'
        clean_metadata(str(source),str(output),identidade_unica=True)
        self.assert_metadata_clean(output)
        self.assertEqual(uuid.UUID(self.probe(output)['format']['tags']['content_identifier']).version,4)

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

    def test_converter_imagem_capa_1080x1920(self):
        import os
        from PIL import Image
        from core.converter import converter_imagem_capa_1080x1920
        raw_img_path = self.root / 'capa_teste_horizontal.png'
        img = Image.new('RGB', (1920, 1080), color=(255, 120, 0))
        img.save(raw_img_path)

        out_path = converter_imagem_capa_1080x1920(str(raw_img_path))
        self.assertTrue(os.path.isfile(out_path))
        with Image.open(out_path) as res:
            self.assertEqual(res.size, (1080, 1920))


if __name__ == '__main__':
    unittest.main()
