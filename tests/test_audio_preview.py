import array
import math
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from PIL import Image
from core.converter import get_video_metadata
from core.audio_preview import AudioPreview, WindowsAudioSink, build_audio_command, RATE, CHANNELS, SAMPLE_BYTES


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg necessario')
class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='fnk_audio_')
        cls.root=Path(cls.temp.name)
        cls.source=cls.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=red:s=160x120:r=30:d=2',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2',
            '-af','volume=0.05','-c:v','libx264','-threads','2','-c:a','aac',str(cls.source)],
            capture_output=True,check=True)
        cls.metadata=get_video_metadata(str(cls.source))
        cls.cover=cls.root/'cover.png'
        Image.new('RGB',(90,160),'lime').save(cls.cover)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_audio_obeys_cover_cuts_speed_and_seek(self):
        options=dict(corte_inicio=0.25,corte_fim=0.25,velocidade=2,
                     capa_path=str(self.cover),capa_segundos=0.2)
        command,total=build_audio_command(str(self.source),self.metadata,**options)
        raw=subprocess.check_output(command)
        self.assertAlmostEqual(len(raw)/(RATE*CHANNELS*SAMPLE_BYTES),0.95,delta=0.001)
        samples=array.array('h',raw)
        def rms(values):return math.sqrt(sum(x*x for x in values)/len(values))
        self.assertLess(rms(samples[:int(0.15*RATE*CHANNELS)]),1)
        self.assertGreater(rms(samples[int(0.3*RATE*CHANNELS):int(0.5*RATE*CHANNELS)]),30)
        command,_=build_audio_command(str(self.source),self.metadata,position=0.4,**options)
        raw=subprocess.check_output(command)
        self.assertAlmostEqual(len(raw)/(RATE*CHANNELS*SAMPLE_BYTES),total-0.4,delta=0.001)
        self.assertGreater(rms(array.array('h',raw)[:8000]),30)

    def test_muted_from_first_buffer(self):
        buffers=[]
        class RecordingSink:
            position=0
            pending=0
            def write(self,data):buffers.append(data);return True
            def resume(self):pass
            def pause(self):pass
            def close(self):pass
        audio=AudioPreview(str(self.source),self.metadata,sink_factory=RecordingSink,muted=True)
        self.addCleanup(audio.close)
        self.assertTrue(audio.finished.wait(5))
        self.assertIsNone(audio.error)
        self.assertTrue(buffers)
        self.assertFalse(any(any(buffer) for buffer in buffers))

    @unittest.skipUnless(os.name=='nt','Saida nativa do Windows')
    def test_native_pause_resume_and_clock(self):
        try:sink=WindowsAudioSink()
        except OSError as error:self.skipTest(str(error))
        self.addCleanup(sink.close)
        self.assertTrue(sink.write(bytes(RATE*CHANNELS*SAMPLE_BYTES//3)))
        sink.resume()
        time.sleep(0.08)
        sink.pause()
        position=sink.position
        self.assertGreater(position,0)
        time.sleep(0.05)
        self.assertAlmostEqual(position,sink.position,delta=0.01)
        sink.resume()
        time.sleep(0.06)
        self.assertGreater(sink.position,position)

    @unittest.skipUnless(os.name=='nt','Saida nativa do Windows')
    def test_stream_starts_paused_and_stops_without_orphan_process(self):
        audio=AudioPreview(str(self.source),self.metadata)
        audio.muted=True
        self.addCleanup(audio.wait_closed)
        self.addCleanup(audio.close)
        self.assertTrue(audio.ready.wait(5))
        if audio.error:self.skipTest(audio.error)
        self.assertAlmostEqual(audio.position,0,delta=0.01)
        audio.resume()
        time.sleep(0.15)
        audio.pause()
        position=audio.position
        time.sleep(0.06)
        self.assertAlmostEqual(audio.position,position,delta=0.01)
        self.assertGreater(position,0)
        audio.resume()
        time.sleep(0.06)
        self.assertGreater(audio.position,position)
        audio.close()
        audio.wait_closed()
        self.assertTrue(audio.finished.is_set())
        self.assertIsNotNone(audio.process.poll())
