import queue
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from core.converter import get_video_metadata, PRESET_RATIOS, convert_video
from core.playback import PreviewStream, preview_dimensions


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg necessario')
class PlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='fnk_playback_')
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'testsrc2=s=320x240:r=30:d=2', '-c:v', 'libx264', '-threads', '2', str(cls.source)],
            check=True, capture_output=True)
        cls.metadata = get_video_metadata(str(cls.source))
        cls.cover = cls.root / 'cover.png'
        Image.new('RGB', (100, 200), 'lime').save(cls.cover)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def read_stream(self, stream, keep=(0,)):
        self.addCleanup(stream.wait_closed)
        self.addCleanup(stream.close)
        count, saved = 0, {}
        deadline = time.monotonic() + 15
        while not stream.finished.is_set() or not stream.frames.empty():
            self.assertLess(time.monotonic(), deadline, 'Decodificacao nao terminou')
            try:
                frame = stream.frames.get(timeout=0.05)
                if count in keep:
                    saved[count] = frame
                count += 1
            except queue.Empty:
                pass
        self.assertIsNone(stream.error)
        return count, saved

    def test_all_resolution_ratios_and_frame_count(self):
        for target in PRESET_RATIOS.values():
            with self.subTest(target=target):
                stream = PreviewStream(str(self.source), self.metadata, target_resolution=target)
                self.assertAlmostEqual(stream.size[0]/stream.size[1], target[0]/target[1])
                self.assertLessEqual(stream.size[0], 960)
                self.assertLessEqual(stream.size[1], 720)
                count, _ = self.read_stream(stream)
                self.assertEqual(count, 60)
                self.assertEqual(stream.process.poll(), 0)

    def test_queue_is_bounded_and_stop_releases_decoder(self):
        stream = PreviewStream(str(self.source), self.metadata, target_resolution=(1080, 1920))
        self.addCleanup(stream.wait_closed)
        self.addCleanup(stream.close)
        deadline = time.monotonic()+5
        while stream.frames.qsize() < 6 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(stream.frames.qsize(), 6)
        stream.close()
        stream.wait_closed()
        self.assertTrue(stream.finished.is_set())
        self.assertIsNotNone(stream.process.poll())

    def test_cover_seek_cuts_and_speed(self):
        options = dict(target_resolution=(120, 150), corte_inicio=0.25, corte_fim=0.25,
                       velocidade=2, capa_path=str(self.cover), capa_segundos=0.2, espelhar=True)
        stream = PreviewStream(str(self.source), self.metadata, **options)
        count, saved = self.read_stream(stream, keep=(0, 6))
        self.assertEqual(count, 29)  # 0.2 s de capa + 0.75 s do corpo, arredondado aos quadros.
        self.assertGreater(saved[0][1].getpixel((60,75))[1], 230)
        self.assertNotEqual(saved[0][1].tobytes(), saved[6][1].tobytes())
        seeked = PreviewStream(str(self.source), self.metadata, position=0.45, **options)
        _, frames = self.read_stream(seeked)
        self.assertAlmostEqual(frames[0][0], 0.45)
        self.assertNotEqual(frames[0][1].tobytes(), saved[0][1].tobytes())

    def test_composition_matches_export_in_all_modes(self):
        for mode in ('blur', 'pillarbox', 'crop'):
            with self.subTest(mode=mode):
                options = dict(target_resolution=(120,150), mode=mode, espelhar=True,
                               sharpen_strength=0.8, corte_inicio=0.2)
                stream = PreviewStream(str(self.source), self.metadata, **options)
                _, frames = self.read_stream(stream)
                output = self.root / 'result.mp4'
                convert_video(str(self.source), str(output), preset='ultrafast', **options)
                image_path = self.root / 'export.png'
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(output),
                    '-frames:v', '1', '-update', '1', str(image_path)], check=True, capture_output=True)
                with Image.open(image_path) as exported:
                    diff = ImageChops.difference(frames[0][1], exported.convert('RGB'))
                    self.assertLess(sum(ImageStat.Stat(diff).mean)/3, 8)

    def test_dimensions_do_not_upscale_small_outputs(self):
        self.assertEqual(preview_dimensions((120,150)), (120,150))
