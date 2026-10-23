import json
import uuid
import math
import os
import queue
import re
import tempfile
import threading
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass
class VideoMetadata:
    width: int
    height: int
    duration: float
    fps: float
    codec_name: str
    aspect_ratio: float
    has_audio: bool = False

PRESET_RATIOS = {
    "4:5 (Feed Instagram/FB - 1080x1350)": (1080, 1350),
    "9:16 (Stories/Reels/TikTok - 1080x1920)": (1080, 1920),
    "1:1 (Quadrado Feed - 1080x1080)": (1080, 1080),
    "16:9 (Horizontal/YouTube - 1920x1080)": (1920, 1080),
    "4:3 (Classico - 1440x1080)": (1440, 1080)
}

def get_video_metadata(video_path: str) -> VideoMetadata:
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_path
    ]
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, startupinfo=startupinfo)
    data = json.loads(res.stdout)

    video_stream = None
    for s in data.get('streams', []):
        if s.get('codec_type') == 'video':
            video_stream = s
            break

    if not video_stream:
        raise ValueError(f'Nenhum fluxo de video encontrado em: {video_path}')

    width = int(video_stream.get('width', 0))
    height = int(video_stream.get('height', 0))

    duration = 0.0
    if 'duration' in video_stream:
        try:
            duration = float(video_stream['duration'])
        except Exception:
            pass
    if duration <= 0 and 'format' in data and 'duration' in data['format']:
        try:
            duration = float(data['format']['duration'])
        except Exception:
            pass

    fps_str = video_stream.get('r_frame_rate', '30/1')
    fps = 30.0
    if '/' in fps_str:
        num, den = fps_str.split('/')
        den_val = float(den)
        if den_val > 0:
            fps = float(num) / den_val
    else:
        try:
            fps = float(fps_str)
        except Exception:
            pass

    codec = video_stream.get('codec_name', 'h264')
    ratio = (width / height) if height > 0 else (9 / 16)

    return VideoMetadata(
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        codec_name=codec,
        aspect_ratio=ratio,
        has_audio=any(s.get('codec_type') == 'audio' for s in data.get('streams', []))
    )

def ensure_even_dimensions(w: int, h: int) -> tuple[int, int]:
    if w < 2 or h < 2:
        raise ValueError('Largura e altura devem ser de pelo menos 2 pixels.')
    return int(w + w % 2), int(h + h % 2)


def _finite(value, name, minimum=0.0, maximum=None):
    value = float(value)
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'Valor invalido para {name}: {value}')
    return value


def get_edit_timeline(metadata, corte_inicio=0.0, corte_fim=0.0, velocidade=1.0,
                      capa_path=None, capa_segundos=0.1):
    start = _finite(corte_inicio, 'corte inicial')
    end = _finite(corte_fim, 'corte final')
    speed = _finite(velocidade, 'velocidade', 0.25, 4.0)
    duration = metadata.duration - start - end
    if duration <= 0:
        raise ValueError('Os cortes devem deixar algum trecho do video.')
    fps = metadata.fps if math.isfinite(metadata.fps) and metadata.fps > 0 else 30.0
    cover_duration = 0.0
    if capa_path:
        if not os.path.isfile(capa_path):
            raise ValueError(f'Imagem de capa nao encontrada: {capa_path}')
        seconds = _finite(capa_segundos, 'duracao da capa', 0.001)
        cover_duration = max(1, round(seconds * fps)) / fps
    return start, duration, speed, cover_duration, fps


def cover_filter(w, h, adjustment):
    if adjustment == 'preencher':
        result = (f'scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,'
                  f'crop={w}:{h}')
    elif adjustment == 'inteira':
        result = (f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                  f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black')
    elif adjustment == 'esticar':
        result = f'scale={w}:{h}'
    else:
        raise ValueError(f'Ajuste de capa desconhecido: {adjustment}')
    return result + ',setsar=1,format=yuv420p'


def build_filter_complex(input_w, input_h, target_w, target_h, mode='blur',
                         blur_strength=35, bg_color='black', sharpen_strength=0.0):
    w, h = ensure_even_dimensions(target_w, target_h)
    strength = _finite(sharpen_strength, 'nitidez', 0, 2)
    blur = _finite(blur_strength, 'desfoque', 0, 80)
    # Somente nomes e cores hexadecimais; nao aceitar sintaxe de filtros na cor.
    if not re.fullmatch(r'[a-zA-Z]+|#[0-9a-fA-F]{6}|0x[0-9a-fA-F]{6}', bg_color):
        raise ValueError('Cor das barras invalida.')
    sharpen = f',unsharp=5:5:{strength:.3f}:5:5:0' if strength > 0 else ''
    fit = f'scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1'
    fill = f'scale={w}:{h}:force_original_aspect_ratio=increase:force_divisible_by=2,setsar=1'
    if mode == 'blur':
        return (f'[0:v:0]split=2[fg_in][bg_in];'
                f'[bg_in]{fill},crop={w}:{h},'
                f"boxblur=luma_radius='min({blur},max(0,min(w,h)/2-1))':luma_power=5:"
                f"chroma_radius='min({blur},max(0,min(cw,ch)/2-1))':chroma_power=5,"
                f'eq=brightness=-0.08:saturation=1.1[bg];'
                f'[fg_in]{fit}{sharpen}[fg];'
                f'[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[outv]')
    if mode == 'pillarbox':
        return (f'[0:v:0]{fit}{sharpen},'
                f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={bg_color},format=yuv420p[outv]')
    if mode == 'crop':
        return f'[0:v:0]{fill}{sharpen},crop={w}:{h},format=yuv420p[outv]'
    raise ValueError(f'Modo desconhecido: {mode}')


def _atempo(speed):
    factors = []
    while speed < 0.5:
        factors.append('atempo=0.5')
        speed /= 0.5
    while speed > 2:
        factors.append('atempo=2')
        speed /= 2
    factors.append(f'atempo={speed:.8f}')
    return ','.join(factors)


def convert_video(
    input_path: str, output_path: str, mode: str = 'blur',
    target_resolution: tuple = (1080, 1350), blur_strength: int = 35,
    bg_color: str = 'black', sharpen_strength: float = 0.0,
    crf: int = 18, preset: str = 'fast', corte_inicio: float = 0.0,
    corte_fim: float = 0.0, espelhar: bool = False, velocidade: float = 1.0,
    capa_path: Optional[str] = None, capa_segundos: float = 0.1,
    capa_ajuste: str = 'preencher',
    limpar_metadados: bool = True,
    identidade_unica: bool = False,
    perfil_celular: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> bool:
    input_path, output_path = os.path.abspath(input_path), os.path.abspath(output_path)
    same_path = os.path.normcase(input_path) == os.path.normcase(output_path)
    if same_path or (os.path.exists(output_path) and os.path.samefile(input_path, output_path)):
        raise ValueError('Escolha uma saida diferente do video original.')
    if os.path.splitext(output_path)[1].lower() not in ('.mp4', '.mov', '.mkv'):
        raise ValueError('Use uma saida MP4, MOV ou MKV para a codificacao H.264.')
    if perfil_celular and os.path.splitext(output_path)[1].lower() != '.mp4':
        raise ValueError('O perfil para celular usa saida MP4.')
    _finite(crf, 'qualidade CRF', 0, 51)
    metadata = get_video_metadata(input_path)
    w, h = ensure_even_dimensions(*target_resolution)
    start, duration, speed, cover_duration, fps = get_edit_timeline(
        metadata, corte_inicio, corte_fim, velocidade, capa_path, capa_segundos)
    filters = build_filter_complex(metadata.width, metadata.height, w, h, mode,
                                   blur_strength, bg_color, sharpen_strength)
    filters = filters.replace('[outv]', '[composition]')
    mirror = ',hflip' if espelhar else ''
    filters += (f';[composition]setpts=(PTS-STARTPTS)/{speed:.8f}{mirror},'
                f'fps={fps:.8f},setsar=1[body]')
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
           '-ss', str(start), '-t', str(duration), '-i', input_path]
    map_video = '[body]'
    if capa_path:
        cmd += ['-loop', '1', '-framerate', str(fps), '-t', str(cover_duration), '-i', capa_path]
        filters += (f';[1:v:0]{cover_filter(w, h, capa_ajuste)},fps={fps:.8f},'
                    f'settb=AVTB,setpts=PTS-STARTPTS[cover];'
                    f'[body]settb=AVTB[body_tb];'
                    f'[cover][body_tb]concat=n=2:v=1:a=0[outv]')
        map_video = '[outv]'
    total = duration / speed + cover_duration
    audio_args = []
    if metadata.has_audio:
        # Copia sem perdas quando a linha de tempo nao foi editada.
        copy_audio = speed == 1 and not capa_path and start == 0 and float(corte_fim) == 0 and not perfil_celular
        if copy_audio:
            audio_args = ['-map', '0:a:0', '-c:a', 'copy']
        else:
            filters += (f';[0:a:0]asetpts=PTS-STARTPTS,aresample=48000,{_atempo(speed)},'
                        f'adelay={round(cover_duration * 48000)}S:all=1,'
                        f'apad,atrim=end_sample={round(total * 48000)},asetpts=N/SR/TB[outa]')
            audio_args = ['-map', '[outa]', '-c:a', 'aac', '-b:a', '192k']
    cmd += ['-filter_complex', filters, '-map', map_video, *audio_args,
            '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-pix_fmt', 'yuv420p']
    if limpar_metadados:
        cmd += metadata_removal_args(output_path)
    else:
        cmd += ['-map_metadata', '0']
    if perfil_celular:
        cmd += ['-brand', 'mp42']
    cmd += identity_args(output_path, identidade_unica)
    cmd += ['-movflags', '+faststart+use_metadata_tags' if identidade_unica else '+faststart']
    return _run_output(cmd, output_path, total, progress_callback, cancel_check)


def identity_args(output_path, enabled):
    # UUID identifica esta copia, sem inventar fabricante, modelo, GPS ou serial.
    if not enabled:
        return []
    return ['-metadata', f'content_identifier={uuid.uuid4()}']


def metadata_removal_args(output_path):
    args = ['-map_metadata', '-1', '-map_metadata:s', '-1', '-map_chapters', '-1',
            '-metadata', 'encoder=', '-metadata:s', 'encoder=', '-fflags', '+bitexact']
    if os.path.splitext(output_path)[1].lower() in ('.mp4', '.mov'):
        args += ['-write_tmcd', '0']
    return args


def clean_metadata(input_path, output_path, progress_callback=None, cancel_check=None, identidade_unica=False):
    """Remuxa video/audio sem recodificar; mantem orientacao e dados tecnicos."""
    input_path, output_path = os.path.abspath(input_path), os.path.abspath(output_path)
    if os.path.normcase(input_path) == os.path.normcase(output_path) or (
            os.path.exists(output_path) and os.path.samefile(input_path, output_path)):
        raise ValueError('Escolha uma saida diferente do video original.')
    if os.path.splitext(input_path)[1].lower() != os.path.splitext(output_path)[1].lower():
        raise ValueError('A limpeza sem conversao deve manter a extensao do original.')
    metadata = get_video_metadata(input_path)
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', input_path,
           '-map', '0:v:0', '-map', '0:a?', '-c', 'copy', *metadata_removal_args(output_path),
           *identity_args(output_path, identidade_unica)]
    if os.path.splitext(output_path)[1].lower() in ('.mp4', '.mov'):
        cmd += ['-movflags', '+faststart+use_metadata_tags' if identidade_unica else '+faststart']
    return _run_output(cmd, output_path, max(0.001, metadata.duration), progress_callback, cancel_check)


def _run_output(cmd, output_path, total, progress_callback, cancel_check):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fd, temp_output = tempfile.mkstemp(prefix='.fnk_', suffix=os.path.splitext(output_path)[1],
                                     dir=os.path.dirname(output_path))
    os.close(fd)
    cmd = [*cmd, '-progress', 'pipe:1', '-nostats', temp_output]
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    process = None
    try:
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors,
                                       text=True, encoding='utf-8', errors='replace',
                                       startupinfo=startupinfo)
            lines = queue.Queue()

            def read_progress():
                for line in process.stdout:
                    lines.put(line.strip())
                lines.put(None)

            reader = threading.Thread(target=read_progress, daemon=True)
            reader.start()
            while True:
                if cancel_check and cancel_check():
                    return False
                try:
                    line = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                if line.startswith('out_time_us=') and progress_callback:
                    try:
                        progress = max(0, min(0.99, int(line.split('=')[1]) / 1_000_000 / total))
                        progress_callback(progress, f'{int(progress * 100)}%')
                    except ValueError:
                        pass
            process.wait()
            if cancel_check and cancel_check():
                return False
            if process.returncode:
                errors.seek(0)
                detail = errors.read().decode('utf-8', errors='replace')[-5000:]
                raise RuntimeError(f'Erro ao converter video com FFmpeg: {detail}')
        os.replace(temp_output, output_path)
        if progress_callback:
            progress_callback(1.0, '100%')
        return True
    finally:
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if process.stdout:
                process.stdout.close()
        if os.path.exists(temp_output):
            os.remove(temp_output)
