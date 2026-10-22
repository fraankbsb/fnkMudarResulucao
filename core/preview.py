import os
import subprocess
from .converter import build_filter_complex, ensure_even_dimensions, get_video_metadata

def generate_preview_frame(
    video_path: str,
    output_image_path: str,
    timestamp_sec: float = 1.0,
    mode: str = 'blur',
    target_resolution: tuple = (1080, 1350),
    blur_strength: int = 35,
    bg_color: str = 'black'
) -> str:
    metadata = get_video_metadata(video_path)
    target_w, target_h = ensure_even_dimensions(*target_resolution)
    filter_str = build_filter_complex(
        input_w=metadata.width,
        input_h=metadata.height,
        target_w=target_w,
        target_h=target_h,
        mode=mode,
        blur_strength=blur_strength,
        bg_color=bg_color
    )

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
