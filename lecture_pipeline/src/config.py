"""Configuration management for math-video-generator"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Global configuration manager"""
    
    # Default paths
    ROOT_DIR = Path(__file__).parent.parent
    CACHE_DIR = ROOT_DIR / "media" / "cache"
    OUTPUT_DIR = ROOT_DIR / "media" / "output"
    EXAMPLES_DIR = ROOT_DIR / "examples"
    
    # Video settings
    VIDEO_QUALITY = "1080p"
    FPS = 30
    BACKGROUND_COLOR = "#000000"
    
    # Encoding settings
    ENCODING_QUALITY_MODE = "balanced"  # fast, balanced, quality
    ENCODING_PRESET = "medium"  # ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
    ENCODING_CRF = 20  # Constant Rate Factor (0-51, lower = better quality)
    ENCODING_PIXEL_FORMAT = "yuv420p"  # yuv420p (compatible), yuv444p (higher quality)
    
    # TTS settings
    TTS_APPID = os.getenv("DOUBAO_APPID", "")
    TTS_TOKEN = os.getenv("DOUBAO_TOKEN", "")
    TTS_CLUSTER = os.getenv("DOUBAO_CLUSTER", "seed-tts-2.0")
    TTS_DEFAULT_VOICE = os.getenv("DOUBAO_VOICE", "zh_male_taocheng_uranus_bigtts")
    TTS_API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    TTS_CACHE_ENABLED = True
    
    @classmethod
    def load_from_file(cls, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist"""
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (cls.CACHE_DIR / "tts").mkdir(exist_ok=True)
        (cls.CACHE_DIR / "beamer").mkdir(exist_ok=True)
    
    @classmethod
    def get_resolution(cls) -> tuple:
        """Get video resolution based on quality setting"""
        resolutions = {
            "720p": (1280, 720),
            "1080p": (1920, 1080),
            "4k": (3840, 2160),
        }
        return resolutions.get(cls.VIDEO_QUALITY, (1920, 1080))
    
    @classmethod
    def get_encoding_profile(cls):
        """Get video encoding profile based on current settings"""
        from src.video_encoder import VideoEncoder
        return VideoEncoder.get_profile(
            resolution=cls.VIDEO_QUALITY,
            fps=cls.FPS,
            quality_mode=cls.ENCODING_QUALITY_MODE
        )
    
    @classmethod
    def get_ffmpeg_config(cls) -> Dict[str, str]:
        """Get FFmpeg encoding configuration"""
        profile = cls.get_encoding_profile()
        from src.video_encoder import VideoEncoder
        return VideoEncoder.get_ffmpeg_args(profile)


# Initialize directories on import
Config.ensure_directories()
