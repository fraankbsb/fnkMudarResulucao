import math
import os
import subprocess
from .converter import (build_filter_complex, cover_filter, ensure_even_dimensions, detectar_cor_fundo_video,
                        get_edit_timeline, get_video_metadata)


def generate_preview_frame(
    video_path: str, output_image_path: str, timestamp_sec: float = 1.0,
    mode: str = 'blur', target_resolution: tuple = (1080, 1350),
    blur_strength: int = 35, bg_color: str = 'black', sharpen_strength: float = 0.0,
    espelhar: bool = False, capa_path: str = None, capa_segundos: float = 0.1,
    capa_ajuste: str = 'preencher', corte_inicio: float = 0.0,
    corte_fim: float = 0.0, velocidade: float = 1.0, metadata=None
) -> str:
    """timestamp_sec representa a linha de tempo do resultado, incluindo a capa."""
    metadata = metadata or get_video_metadata(video_path)
    if str(bg_color).lower() in ('auto', 'detectar', 'auto_detect'):
        bg_color = detectar_cor_fundo_video(video_path)
    w, h = ensure_even_dimensions(*target_resolution)
    start, duration, speed, cover_duration, fps = get_edit_timeline(
        metadata, corte_inicio, corte_fim, velocidade, capa_path, capa_segundos)
    timestamp = float(timestamp_sec)
    if not math.isfinite(timestamp):
        raise ValueError('Tempo de previa invalido.')
    timestamp = max(0.0, timestamp)
    cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y']
    if capa_path and timestamp < cover_duration:
        cmd += ['-i', capa_path, '-vf', cover_filter(w, h, capa_ajuste)]
    else:
        body_time = max(0, timestamp - cover_duration)
        source_time = start + min(body_time * speed, max(0, duration - 1 / fps))
        filters = build_filter_complex(metadata.width, metadata.height, w, h,
                                       mode, blur_strength, bg_color, sharpen_strength)
        if espelhar:
            filters = filters.replace('[outv]', ',hflip[outv]')
        cmd += ['-ss', str(source_time), '-i', video_path,
                '-filter_complex', filters, '-map', '[outv]']
    cmd += ['-frames:v', '1', '-update', '1', output_image_path]
    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
    if result.returncode or not os.path.isfile(output_image_path):
        raise RuntimeError(f'Falha ao gerar previa: {result.stderr[-3000:]}')
    return output_image_path
