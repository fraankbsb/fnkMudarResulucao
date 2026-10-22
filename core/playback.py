"""Decodificacao continua da previa: um FFmpeg, fila limitada e sem arquivos por quadro."""
import math
import os
import queue
import subprocess
import tempfile
import threading
from PIL import Image
from .converter import build_filter_complex, cover_filter, get_edit_timeline


def preview_dimensions(target, bounds=(640, 640)):
    w, h = target
    divisor = math.gcd(w, h)
    rw, rh = w // divisor, h // divisor
    multiple = min(divisor, int(min(bounds[0] / rw, bounds[1] / rh)))
    if rw % 2 or rh % 2:
        multiple -= multiple % 2
    multiple = max(2, multiple)
    return rw * multiple, rh * multiple


def build_preview_command(video_path, metadata, position=0.0, **options):
    target = options.get('target_resolution', (1080, 1350))
    w, h = preview_dimensions(target)
    start, duration, speed, cover, source_fps = get_edit_timeline(metadata,
        options.get('corte_inicio', 0), options.get('corte_fim', 0),
        options.get('velocidade', 1), options.get('capa_path'), options.get('capa_segundos', 0.1))
    total = duration / speed + cover
    fps = min(30.0, source_fps)
    position = max(0, min(float(position), max(0, total - 1 / fps)))
    remaining_cover = max(0, cover - position)
    body_position = max(0, position - cover)
    seek = start + body_position * speed
    remaining_source = max(0.001, duration - body_position * speed)
    # Mesmo enquadramento da exportacao, em tamanho leve e com desfoque proporcional.
    scale = w / target[0]
    filters = build_filter_complex(metadata.width, metadata.height, w, h,
        options.get('mode', 'blur'), options.get('blur_strength', 35) * scale,
        options.get('bg_color', 'black'), options.get('sharpen_strength', 0))
    filters = filters.replace('[outv]', '[composed]')
    mirror = ',hflip' if options.get('espelhar') else ''
    filters += (f';[composed]setpts=(PTS-STARTPTS)/{speed:.8f}{mirror},'
                f'fps={fps:.8f},settb=AVTB,setsar=1[body]')
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
           '-threads', '2', '-filter_complex_threads', '2',
           '-ss', str(seek), '-t', str(remaining_source), '-i', str(video_path)]
    label = '[body]'
    if remaining_cover:
        cmd += ['-loop', '1', '-framerate', str(fps), '-t', str(remaining_cover),
                '-i', options['capa_path']]
        filters += (f';[1:v:0]{cover_filter(w, h, options.get("capa_ajuste", "preencher"))},'
                    f'fps={fps:.8f},settb=AVTB,setpts=PTS-STARTPTS[cover];'
                    f'[cover][body]concat=n=2:v=1:a=0[outv]')
        label = '[outv]'
    cmd += ['-filter_complex', filters, '-map', label, '-an', '-sn', '-dn',
            '-pix_fmt', 'rgb24', '-threads', '2', '-f', 'rawvideo', 'pipe:1']
    return cmd, (w, h), fps, total, position


class PreviewStream:
    def __init__(self, video_path, metadata, position=0.0, **options):
        cmd, self.size, self.fps, self.duration, self.position = build_preview_command(
            video_path, metadata, position, **options)
        self.frames = queue.Queue(maxsize=6)
        self.stopped = threading.Event()
        self.finished = threading.Event()
        self.error = None
        self.errors = tempfile.TemporaryFile()
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=self.errors,
                                             startupinfo=startupinfo, bufsize=0)
        except Exception:
            self.errors.close()
            raise
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        length = self.size[0] * self.size[1] * 3
        index = 0
        try:
            while not self.stopped.is_set():
                data = bytearray()
                while len(data) < length and not self.stopped.is_set():
                    block = self.process.stdout.read(length - len(data))
                    if not block:
                        break
                    data.extend(block)
                if len(data) != length or self.stopped.is_set():
                    break
                frame = (self.position + index / self.fps, Image.frombytes('RGB', self.size, bytes(data)))
                while not self.stopped.is_set():
                    try:
                        self.frames.put(frame, timeout=0.05)
                        break
                    except queue.Full:
                        pass
                index += 1
            self.process.wait()
            if self.process.returncode and not self.stopped.is_set():
                self.errors.seek(0)
                self.error = self.errors.read().decode('utf-8', errors='replace')[-2000:]
        finally:
            self.process.stdout.close()
            self.errors.close()
            self.finished.set()

    def close(self):
        self.stopped.set()
        if self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass

    def wait_closed(self, timeout=3):
        self.thread.join(timeout)
        if self.thread.is_alive():
            self.process.kill()
            self.thread.join(timeout)
