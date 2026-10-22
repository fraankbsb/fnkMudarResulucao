"""Compatibilidade para consumidores da previa em memoria, sem exigir OpenCV."""
import os
import tempfile
from PIL import Image
from .preview import generate_preview_frame


def get_preview_frame_cv2(video_path, target_resolution=(1080, 1350),
                          timestamp_sec=0.0, **options):
    fd, path = tempfile.mkstemp(suffix='.png', prefix='preview_fnk_')
    os.close(fd)
    try:
        generate_preview_frame(video_path, path, timestamp_sec=timestamp_sec,
                               target_resolution=target_resolution, **options)
        with Image.open(path) as image:
            return image.convert('RGB')
    finally:
        if os.path.exists(path):
            os.remove(path)
