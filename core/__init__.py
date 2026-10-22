from .converter import (
    convert_video,
    get_video_metadata,
    ensure_even_dimensions,
    build_filter_complex,
    VideoMetadata,
    PRESET_RATIOS
)
from .preview import generate_preview_frame

# Alias de retrocompatibilidade
calculate_target_dimensions = ensure_even_dimensions

__all__ = [
    'convert_video',
    'get_video_metadata',
    'ensure_even_dimensions',
    'calculate_target_dimensions',
    'build_filter_complex',
    'VideoMetadata',
    'PRESET_RATIOS',
    'generate_preview_frame'
]
