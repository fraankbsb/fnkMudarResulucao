import json
import math
import os
import re
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

def get_video_metadata(video_path: str) -> VideoMetadata:
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        video_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
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
        aspect_ratio=ratio
    )

def calculate_target_dimensions(width: int, height: int, target_w: int = 1080, target_h: int = 1350) -> tuple:
    if target_w % 2 != 0:
        target_w += 1
    if target_h % 2 != 0:
        target_h += 1
    return target_w, target_h

def build_filter_complex(mode: str, target_w: int, target_h: int, blur_strength: int = 35, bg_color: str = 'black') -> str:
    if mode == 'blur':
        filter_str = (
            f'[0:v]split=2[fg_in][bg_in];'
            f'[bg_in]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,'
            f'crop={target_w}:{target_h},'
            f'boxblur={blur_strength}:5,'
            f'eq=brightness=-0.08:saturation=1.1[bg];'
            f'[fg_in]scale=-2:{target_h}[fg];'
            f'[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]'
        )
    elif mode == 'pillarbox':
        filter_str = (
            f'[0:v]scale=-2:{target_h}[fg];'
            f'[fg]pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color={bg_color}[outv]'
        )
    elif mode == 'crop':
        filter_str = (
            f'[0:v]scale={target_w}:-2,'
            f'crop={target_w}:{target_h}:(iw-ow)/2:(ih-oh)/2[outv]'
        )
    else:
        raise ValueError(f'Modo desconhecido: {mode}')

    return filter_str

def convert_video(
    input_path: str,
    output_path: str,
    mode: str = 'blur',
    target_resolution: tuple = (1080, 1350),
    blur_strength: int = 35,
    bg_color: str = 'black',
    crf: int = 18,
    preset: str = 'fast',
    progress_callback: Optional[Callable[[float, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> bool:
    metadata = get_video_metadata(input_path)
    target_w, target_h = calculate_target_dimensions(*target_resolution)
    filter_str = build_filter_complex(mode, target_w, target_h, blur_strength, bg_color)

    cmd = [
        'ffmpeg',
        '-y',
        '-i', input_path,
        '-filter_complex', filter_str,
        '-map', '[outv]',
        '-map', '0:a?',
        '-c:v', 'libx264',
        '-preset', preset,
        '-crf', str(crf),
        '-c:a', 'copy',
        '-movflags', '+faststart',
        '-progress', 'pipe:1',
        '-nostats',
        output_path
    ]

    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        universal_newlines=True,
        startupinfo=startupinfo
    )

    total_duration = metadata.duration if metadata.duration > 0 else 1.0
    time_pattern = re.compile(r'out_time_ms=(\d+)')

    while True:
        if cancel_check and cancel_check():
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            return False

        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break

        if line:
            match = time_pattern.search(line)
            if match and progress_callback:
                current_ms = int(match.group(1))
                current_sec = current_ms / 1_000_000.0
                progress = min(0.99, current_sec / total_duration)
                progress_callback(progress, f'{int(progress * 100)}%')

    process.wait()
    if process.returncode != 0:
        raise RuntimeError('Erro ao converter video com FFmpeg.')

    if progress_callback:
        progress_callback(1.0, '100%')

    return True