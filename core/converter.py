import time
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
    speed = _finite(velocidade, 'velocidade', 0.05, 10.0)
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


def converter_imagem_capa_1080x1920(caminho_imagem: str, caminho_saida: Optional[str] = None) -> str:
    from PIL import Image, ImageOps
    if not os.path.isfile(caminho_imagem):
        raise ValueError(f'Imagem de capa nao encontrada: {caminho_imagem}')
    if not caminho_saida:
        diretorio = os.path.dirname(caminho_imagem)
        nome, _ = os.path.splitext(os.path.basename(caminho_imagem))
        caminho_saida = os.path.join(diretorio, f'{nome}_1080x1920.png')
    with Image.open(caminho_imagem) as img:
        img_rgb = img.convert('RGB')
        encaixada = ImageOps.fit(img_rgb, (1080, 1920), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        # Higienizacao forense: cria imagem pura do zero sem transferir info, exif, gps ou chunks de software
        pura = Image.new('RGB', (1080, 1920))
        pura.paste(encaixada)
        pura.save(caminho_saida, format='PNG')
    try:
        now = time.time()
        os.utime(caminho_saida, (now, now))
    except Exception:
        pass
    return caminho_saida


def _claros_escuros_faixa(faixa):
    claros = escuros = 0
    img_rgb = faixa.convert('RGB')
    w_f, h_f = img_rgb.size
    pixels = [img_rgb.getpixel((x, y)) for y in range(h_f) for x in range(w_f)]
    for r, g, b in pixels:
        mx, mn = max(r, g, b), min(r, g, b)
        if mn >= 200 and mx - mn <= 35:
            claros += 1
        elif mx <= 55:
            escuros += 1
    n = max(1, len(pixels))
    return claros / n, escuros / n


def detectar_fundo_da_imagem(img) -> str:
    im = img.convert('RGB')
    w, h = im.size
    m = max(2, round(w * 0.025))
    lados = [_claros_escuros_faixa(im.crop(cx).resize((4, 96))) for cx in ((0, 0, m, h), (w - m, 0, w, h))]
    if all(e >= 0.90 for _, e in lados):
        return 'preto'
    claros, escuros = _claros_escuros_faixa(im.crop((0, 0, w, max(4, round(h * 0.14)))).resize((96, 24)))
    if claros >= 0.55:
        return 'branco'
    if escuros >= 0.55:
        return 'preto'
    claros_b, escuros_b = _claros_escuros_faixa(im.crop((0, max(0, h - round(h * 0.14)), w, h)).resize((96, 24)))
    if claros_b >= 0.55:
        return 'branco'
    if escuros_b >= 0.55:
        return 'preto'
    return 'preto'


def detectar_cor_fundo_video(video_path: str, timestamp_sec: float = 0.5) -> str:
    try:
        from io import BytesIO
        from PIL import Image
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-ss', str(max(0.1, timestamp_sec)), '-i', video_path,
               '-frames:v', '1', '-vf', 'scale=480:-2', '-f', 'image2', '-vcodec', 'mjpeg', 'pipe:1']
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
        if p.stdout:
            with Image.open(BytesIO(p.stdout)) as img:
                tipo = detectar_fundo_da_imagem(img)
                return '#ffffff' if tipo == 'branco' else '#000000'
        cmd2 = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-i', video_path, '-frames:v', '1', '-vf', 'scale=480:-2',
                '-f', 'image2', '-vcodec', 'mjpeg', 'pipe:1']
        p2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
        if p2.stdout:
            with Image.open(BytesIO(p2.stdout)) as img:
                tipo = detectar_fundo_da_imagem(img)
                return '#ffffff' if tipo == 'branco' else '#000000'
    except Exception:
        pass
    return '#000000'

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
    if not re.fullmatch(r'auto|detectar|[a-zA-Z]+|#[0-9a-fA-F]{6}|0x[0-9a-fA-F]{6}', bg_color):
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
    cancel_check: Optional[Callable[[], bool]] = None,
    **kwargs
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
    if str(bg_color).lower() in ('auto', 'detectar', 'auto_detect'):
        bg_color = detectar_cor_fundo_video(input_path)
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
            audio_args = ['-map', '[outa]', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2']
    profile_args = ['-profile:v', 'high', '-level:v', '4.1'] if crf > 0 else []
    cmd += ['-filter_complex', filters, '-map', map_video, *audio_args,
            '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), *profile_args, '-pix_fmt', 'yuv420p']
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
    # UUID e tags Android camera/device: simulam video gerado e gravado nativamente em Android
    if not enabled:
        return []
    uid = uuid.uuid4()
    now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())
    return [
        '-metadata', f'content_identifier={uid}',
        '-metadata', f'android.version=14',
        '-metadata', f'creation_time={now_str}',
        '-metadata:s:v:0', f'creation_time={now_str}',
        '-metadata:s:a:0', f'creation_time={now_str}'
    ]


def metadata_removal_args(output_path):
    args = ['-map_metadata', '-1', '-map_metadata:s', '-1', '-map_chapters', '-1',
            '-metadata', 'encoder=', '-metadata:s', 'encoder=', '-fflags', '+bitexact']
    if os.path.splitext(output_path)[1].lower() in ('.mp4', '.mov'):
        args += ['-write_tmcd', '0']
    return args


def clean_metadata(input_path, output_path, progress_callback=None, cancel_check=None, identidade_unica=False, **kwargs):
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
    ext = os.path.splitext(output_path)[1]
    temp_output = os.path.join(os.path.dirname(output_path), f'.fnk_tmp_{uuid.uuid4().hex[:12]}{ext}')
    if os.path.exists(temp_output):
        try:
            os.remove(temp_output)
        except OSError:
            pass
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
        try:
            os.replace(temp_output, output_path)
        except OSError:
            time.sleep(0.1)
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
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
