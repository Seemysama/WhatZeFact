"""
WhatZeFact Pipeline - Configuration
Loads environment variables and defines project paths.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent / ".env")

# ─── API Keys ────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgq5GQZ71dB8")  # Default Rachel/Antoni or similar

# ─── Paths ───────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
WHATZEFACT_ROOT = PROJECT_ROOT.parent  # WhatZeFact/

# Existing assets
CHARTE_DIR = WHATZEFACT_ROOT / "Charte Graphique"
LOGO_PATH = CHARTE_DIR / "Logo.png"
OUTRO_PATH = CHARTE_DIR / "Outro.mp4"
INTRO_VIDEO_PATH = CHARTE_DIR / "Intro.mp4"  # Optional: if exists, used instead of dynamic intro

# Pipeline directories
OUTPUT_DIR = PROJECT_ROOT / "output"
MUSIC_DIR = PROJECT_ROOT / "music"
TEMP_DIR = PROJECT_ROOT / ".temp"  # Temporary files during generation

# Ensure directories exist
OUTPUT_DIR.mkdir(exist_ok=True)
MUSIC_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# ─── Video Settings ──────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_FORMAT = "mp4"
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

# ─── Voice Settings ──────────────────────────────────────────
# French voices available in Kokoro TTS:
# - ff_siwis (female, natural, default)
DEFAULT_VOICE = "ff_siwis"
VOICE_RATE = "1.0"
VOICE_PITCH = "0"

# ─── Subtitle Settings ───────────────────────────────────────
SUBTITLE_FONT_SIZE = 75
SUBTITLE_FONT_COLOR = "white"
SUBTITLE_HIGHLIGHT_COLOR = "#FFC107"  # WhatZeFact yellow!
SUBTITLE_STROKE_COLOR = "black"
SUBTITLE_STROKE_WIDTH = 5
SUBTITLE_POSITION = ("center", 0.75)  # 75% from top
SUBTITLE_MAX_WORDS = 3  # Max 3 words shown at once for fast reading

# ─── Music Settings ──────────────────────────────────────────
MUSIC_VOLUME_DB = -20  # Background music volume reduction

# ─── Logo Settings ───────────────────────────────────────────
LOGO_SIZE = (120, 120)  # Logo overlay size in pixels
LOGO_POSITION = (30, 30)  # Top-left corner with padding
LOGO_OPACITY = 0.7

# ─── Intro Settings ──────────────────────────────────────────
# Dynamic intro: title text + logo over gradient background
INTRO_DURATION = 2.5  # seconds
INTRO_BG_GRADIENT_TOP = (15, 15, 40)  # Dark blue-purple
INTRO_BG_GRADIENT_BOTTOM = (5, 5, 15)  # Near-black
INTRO_LOGO_SIZE = (200, 200)
INTRO_TITLE_FONT_SIZE = 55
INTRO_TITLE_COLOR = "white"
INTRO_ACCENT_COLOR = "#FFC107"  # WhatZeFact yellow

# ─── Outro Settings ──────────────────────────────────────────
OUTRO_FADE_DURATION = 0.5  # Cross-fade duration in seconds

# ─── YouTube Publisher Settings ──────────────────────────────
YOUTUBE_CLIENT_SECRETS_PATH = PROJECT_ROOT / "client_secrets.json"
YOUTUBE_TOKEN_PATH = PROJECT_ROOT / ".youtube_token.json"
YOUTUBE_DEFAULT_CATEGORY = "27"  # Education
YOUTUBE_DEFAULT_PRIVACY = "private"  # private, unlisted, public
YOUTUBE_DEFAULT_LANGUAGE = "fr"

# ─── Gemini Settings ─────────────────────────────────────────
GEMINI_MODEL = "gemini-2.0-flash"  # Stable, fast, and does not hit reasoning token limits
SCRIPT_MIN_DURATION = 30  # seconds
SCRIPT_MAX_DURATION = 40  # seconds


def validate_config():
    """Check that required API keys are set."""
    errors = []
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
        errors.append(
            "❌ GEMINI_API_KEY non configurée. "
            "Va sur https://aistudio.google.com/apikey (gratuit)"
        )
    if not PEXELS_API_KEY or PEXELS_API_KEY == "your_pexels_api_key_here":
        errors.append(
            "❌ PEXELS_API_KEY non configurée. "
            "Va sur https://www.pexels.com/api/ (gratuit)"
        )
    return errors
