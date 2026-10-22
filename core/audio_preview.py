"""Audio da previa por PCM em fluxo e saida nativa do Windows, sem pacote extra."""
import ctypes as ct
import os
import subprocess
import tempfile
import threading
from .converter import _atempo, get_edit_timeline

RATE, CHANNELS, SAMPLE_BYTES = 48000, 2, 2


def build_audio_command(video_path, metadata, position=0.0, **options):
    start, duration, speed, cover, _ = get_edit_timeline(metadata,
        options.get('corte_inicio', 0), options.get('corte_fim', 0),
        options.get('velocidade', 1), options.get('capa_path'), options.get('capa_segundos', 0.1))
    total = duration/speed + cover
    position = max(0, min(position, total))
    body = max(0, position-cover)
    silence = max(0, cover-position)
    filters = (f'asetpts=PTS-STARTPTS,aresample={RATE},{_atempo(speed)},'
               f'adelay={round(silence*RATE)}S:all=1,apad,'
               f'atrim=end_sample={round((total-position)*RATE)},asetpts=N/SR/TB')
    return ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-threads', '2',
            '-ss', str(start+body*speed), '-t', str(max(0.001,duration-body*speed)),
            '-i', str(video_path), '-map', '0:a:0', '-vn', '-sn', '-dn', '-af', filters,
            '-ac', str(CHANNELS), '-ar', str(RATE), '-f', 's16le', 'pipe:1'], total


class _Format(ct.Structure):
    _pack_ = 2
    _fields_ = [('tag',ct.c_uint16),('channels',ct.c_uint16),('rate',ct.c_uint32),
                ('bytes_per_second',ct.c_uint32),('block',ct.c_uint16),
                ('bits',ct.c_uint16),('extra',ct.c_uint16)]


class _Header(ct.Structure):
    _fields_ = [('data',ct.c_void_p),('length',ct.c_uint32),('recorded',ct.c_uint32),
                ('user',ct.c_size_t),('flags',ct.c_uint32),('loops',ct.c_uint32),
                ('next',ct.c_void_p),('reserved',ct.c_size_t)]


class _TimeValue(ct.Union):
    _fields_ = [('value',ct.c_uint32),('padding',ct.c_byte*8)]


class _Time(ct.Structure):
    _fields_ = [('kind',ct.c_uint32),('u',_TimeValue)]


class WindowsAudioSink:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('A saida de audio desta previa requer Windows.')
        self.api = ct.WinDLL('winmm')
        for name, arguments in {
            'waveOutOpen':[ct.POINTER(ct.c_void_p),ct.c_uint,ct.POINTER(_Format),ct.c_size_t,ct.c_size_t,ct.c_uint],
            'waveOutPrepareHeader':[ct.c_void_p,ct.POINTER(_Header),ct.c_uint],
            'waveOutUnprepareHeader':[ct.c_void_p,ct.POINTER(_Header),ct.c_uint],
            'waveOutWrite':[ct.c_void_p,ct.POINTER(_Header),ct.c_uint],
            'waveOutGetPosition':[ct.c_void_p,ct.POINTER(_Time),ct.c_uint],
            'waveOutPause':[ct.c_void_p], 'waveOutRestart':[ct.c_void_p],
            'waveOutReset':[ct.c_void_p], 'waveOutClose':[ct.c_void_p],
        }.items():
            function = getattr(self.api,name)
            function.argtypes, function.restype = arguments, ct.c_uint
        self.handle = ct.c_void_p()
        self.lock = threading.RLock()
        self.buffers = []
        self.closed = False
        fmt = _Format(1,CHANNELS,RATE,RATE*CHANNELS*SAMPLE_BYTES,CHANNELS*SAMPLE_BYTES,16,0)
        self._check(self.api.waveOutOpen(ct.byref(self.handle),0xFFFFFFFF,ct.byref(fmt),0,0,0))
        try:
            self.pause()
        except Exception:
            self.close()
            raise

    @staticmethod
    def _check(result):
        if result:
            raise OSError(f'Falha no dispositivo de som (codigo {result}).')

    def _collect(self):
        remaining=[]
        for header,data in self.buffers:
            if header.flags & 1:
                self._check(self.api.waveOutUnprepareHeader(self.handle,ct.byref(header),ct.sizeof(header)))
            else:
                remaining.append((header,data))
        self.buffers=remaining

    @property
    def pending(self):
        with self.lock:
            if self.closed:return 0
            self._collect()
            return len(self.buffers)

    def write(self, data):
        with self.lock:
            if self.closed:return False
            self._collect()
            if len(self.buffers)>=4:return False
            storage=ct.create_string_buffer(data)
            header=_Header(ct.cast(storage,ct.c_void_p),len(data),0,0,0,0,None,0)
            self._check(self.api.waveOutPrepareHeader(self.handle,ct.byref(header),ct.sizeof(header)))
            self.buffers.append((header,storage))
            self._check(self.api.waveOutWrite(self.handle,ct.byref(header),ct.sizeof(header)))
            return True

    @property
    def position(self):
        with self.lock:
            if self.closed:return 0.0
            position=_Time(2,_TimeValue())
            self._check(self.api.waveOutGetPosition(self.handle,ct.byref(position),ct.sizeof(position)))
            divisor={1:1000,2:RATE,4:RATE*CHANNELS*SAMPLE_BYTES}.get(position.kind)
            if divisor is None:raise OSError('Relogio do dispositivo de som indisponivel.')
            return position.u.value/divisor

    def pause(self):
        with self.lock:
            if not self.closed:self._check(self.api.waveOutPause(self.handle))

    def resume(self):
        with self.lock:
            if not self.closed:self._check(self.api.waveOutRestart(self.handle))

    def close(self):
        with self.lock:
            if self.closed:return
            self.api.waveOutReset(self.handle)
            for header,storage in self.buffers:
                self.api.waveOutUnprepareHeader(self.handle,ct.byref(header),ct.sizeof(header))
            self.buffers.clear()
            self.api.waveOutClose(self.handle)
            self.closed=True


class AudioPreview:
    def __init__(self, video_path, metadata, position=0.0, sink_factory=WindowsAudioSink, muted=False, **options):
        self.position_start=position
        self.cmd,self.duration=build_audio_command(video_path,metadata,position,**options)
        self.stopped=threading.Event()
        self.finished=threading.Event()
        self.ready=threading.Event()
        self.error=None
        self.sink=None
        self.process=None
        self._elapsed=0.0
        self._playing=False
        self.muted=bool(muted)
        self.lock=threading.RLock()
        self.thread=threading.Thread(target=self._run,args=(sink_factory,),daemon=True)
        self.thread.start()

    def _run(self,sink_factory):
        try:
            with tempfile.TemporaryFile() as errors:
                startupinfo=None
                if os.name=='nt':
                    startupinfo=subprocess.STARTUPINFO()
                    startupinfo.dwFlags|=subprocess.STARTF_USESHOWWINDOW
                with self.lock:
                    if self.stopped.is_set():return
                    self.sink=sink_factory()
                    self.process=subprocess.Popen(self.cmd,stdout=subprocess.PIPE,stderr=errors,
                                                   startupinfo=startupinfo,bufsize=0)
                    if self._playing:self.sink.resume()
                chunk=RATE*CHANNELS*SAMPLE_BYTES//20  # 50 ms; no maximo 200 ms na saida.
                while not self.stopped.is_set():
                    data=bytearray()
                    while len(data)<chunk and not self.stopped.is_set():
                        part=self.process.stdout.read(chunk-len(data))
                        if not part:break
                        data.extend(part)
                    if not data:break
                    while not self.stopped.is_set():
                        if self.sink.write(bytes(len(data)) if self.muted else bytes(data)):
                            self.ready.set()
                            break
                        self.stopped.wait(0.005)
                if not self.stopped.is_set():
                    self.process.wait()
                    if self.process.returncode:
                        errors.seek(0)
                        raise RuntimeError(errors.read().decode('utf-8',errors='replace')[-1500:])
                    while self.sink.pending and not self.stopped.wait(0.005):
                        pass
        except Exception as error:
            if not self.stopped.is_set():self.error=str(error)
        finally:
            with self.lock:
                if self.process:
                    if self.process.poll() is None:
                        self.process.terminate()
                        try:self.process.wait(timeout=2)
                        except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
                    self.process.stdout.close()
                if self.sink:
                    try:self._elapsed=self.sink.position
                    except OSError:pass
                    try:self.sink.close()
                    except OSError:pass
                    self.sink=None
            self.ready.set()
            self.finished.set()

    @property
    def position(self):
        with self.lock:
            if self.sink:
                try:self._elapsed=self.sink.position
                except OSError as error:self.error=str(error)
            return min(self.duration,self.position_start+self._elapsed)

    def pause(self):
        with self.lock:
            self._playing=False
            if self.sink:
                try:self.sink.pause()
                except OSError as error:self.error=str(error)

    def resume(self):
        with self.lock:
            self._playing=True
            if self.sink:
                try:self.sink.resume()
                except OSError as error:self.error=str(error)

    def close(self):
        self.stopped.set()
        with self.lock:
            if self.sink:
                try:self.sink.pause()
                except OSError as error:self.error=str(error)
            if self.process and self.process.poll() is None:
                try:self.process.terminate()
                except OSError:pass

    def wait_closed(self,timeout=3):
        self.thread.join(timeout)
