import os
import subprocess
from .converter import build_filter_complex, calculate_target_dimensions

def generate_preview_frame(
    video_path: str,
    output_image_path: str,
    timestamp_sec: float = 1.0,
    mode: str = 'blur',
    target_resolution: tuple = (1080, 1350),
    blur_strength: int = 35,
    bg_color: str = 'black'
) -> str:
    target_w, target_h = calculate_target_dimensions(*target_resolution)
    filter_str = build_filter_complex(mode, target_w, target_h, blur_strength, bg_color)

    cmd = [
        'ffmpeg',
        '-y',
        '-ss', str(timestamp_sec),
        '-i', video_path,
        '-filter_complex', filter_str,
        '-map', '[outv]',
        '-vframes', '1',
        output_image_path
    ]

    startupinfo = None
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, startupinfo=startupinfo)
    if res.returncode != 0:
        raise RuntimeError(f'Falha ao gerar preview: {res.stderr}')

    return output_image_path