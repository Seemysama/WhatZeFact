"""
WhatZeFact — Subtitle Engine
Generates dynamic word-by-word subtitles (TikTok style) using Pillow.
"""

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy import VideoClip

from config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_FONT_COLOR,
    SUBTITLE_HIGHLIGHT_COLOR,
    SUBTITLE_STROKE_COLOR,
    SUBTITLE_STROKE_WIDTH,
    SUBTITLE_MAX_WORDS,
)


def _find_system_font(bold: bool = True) -> str:
    """Find a suitable system font for subtitles."""
    # macOS font paths
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    
    for font_path in font_candidates:
        if Path(font_path).exists():
            return font_path
    
    # Fallback to default
    return None


def _render_subtitle_frame(
    words: list[str],
    highlight_index: int,
    width: int = VIDEO_WIDTH,
    font_size: int = SUBTITLE_FONT_SIZE,
    font_color: str = SUBTITLE_FONT_COLOR,
    highlight_color: str = SUBTITLE_HIGHLIGHT_COLOR,
    stroke_color: str = SUBTITLE_STROKE_COLOR,
    stroke_width: int = SUBTITLE_STROKE_WIDTH,
) -> np.ndarray:
    """
    Render a single subtitle frame with one word highlighted.
    
    Returns:
        RGBA numpy array of the subtitle overlay
    """
    # Create transparent image
    img = Image.new("RGBA", (width, font_size * 3), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Convert words to uppercase
    words = [w.upper() for w in words]
    
    # Load font
    font_path = _find_system_font()
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    
    # Calculate total text width
    text = " ".join(words)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    
    # Center horizontally
    x_start = (width - text_width) // 2
    y = font_size // 2  # Vertical padding
    
    # Draw each word
    current_x = x_start
    for i, word in enumerate(words):
        color = highlight_color if i == highlight_index else font_color
        
        # Draw stroke (outline) for readability
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((current_x + dx, y + dy), word, font=font, fill=stroke_color)
        
        # Draw the word
        draw.text((current_x, y), word, font=font, fill=color)
        
        # Advance x position
        word_bbox = draw.textbbox((0, 0), word + " ", font=font)
        current_x += word_bbox[2] - word_bbox[0]
    
    return np.array(img)


def estimate_word_timestamps(text: str, duration: float, start_time: float = 0.0) -> list[dict]:
    """
    Estimate word-level timestamps for a sentence given its total duration.
    Distributes duration based on word length (character count), with pauses for punctuation.
    """
    words = text.split()
    if not words:
        return []
        
    # Calculate word weights (character counts)
    adjusted_weights = []
    for w in words:
        weight = len(w)
        # Extra weights for punctuation pauses
        if w.endswith(('.', '?', '!', ';', ':')):
            weight += 3
        elif w.endswith(','):
            weight += 1.5
        adjusted_weights.append(max(weight, 1.0))
        
    total_adjusted = sum(adjusted_weights)
    word_timestamps = []
    current_time = start_time
    
    for i, word in enumerate(words):
        # Calculate portion of duration
        word_duration = (adjusted_weights[i] / total_adjusted) * duration
        
        word_timestamps.append({
            "text": word,
            "start": current_time,
            "end": current_time + word_duration
        })
        current_time += word_duration
        
    return word_timestamps


def create_subtitle_clips(
    word_timestamps: list[dict],
    max_words: int = SUBTITLE_MAX_WORDS,
    font_size: int = SUBTITLE_FONT_SIZE,
) -> list[dict]:
    """
    Create subtitle display groups from word timestamps.
    
    Groups words into chunks of max_words, with each word highlighted in sequence.
    
    Args:
        word_timestamps: List of {text, start, end} dicts from Edge TTS
        max_words: Maximum words to display at once
        
    Returns:
        List of subtitle event dicts with timing and rendering info
    """
    if not word_timestamps:
        return []
    
    events = []
    
    # Group words into display chunks
    chunks = []
    for i in range(0, len(word_timestamps), max_words):
        chunk_words = word_timestamps[i:i + max_words]
        chunks.append(chunk_words)
    
    for chunk in chunks:
        words_text = [w["text"] for w in chunk]
        chunk_start = chunk[0]["start"]
        chunk_end = chunk[-1]["end"]
        
        # Create an event for each word highlight within the chunk
        for j, word_data in enumerate(chunk):
            events.append({
                "words": words_text,
                "highlight_index": j,
                "start": word_data["start"],
                "end": word_data["end"],
                "chunk_start": chunk_start,
                "chunk_end": chunk_end,
            })
    
    return events


def build_subtitle_clip(
    word_timestamps: list[dict],
    total_duration: float,
    max_words: int = SUBTITLE_MAX_WORDS,
    font_size: int = SUBTITLE_FONT_SIZE,
    position_y_ratio: float = 0.78,
) -> VideoClip:
    """
    Build a MoviePy VideoClip overlay with animated word-by-word subtitles.
    
    Args:
        word_timestamps: Word-level timestamps from Edge TTS
        total_duration: Total video duration in seconds
        max_words: Max words shown at once
        font_size: Font size for subtitles
        position_y_ratio: Vertical position (0.0 = top, 1.0 = bottom)
        
    Returns:
        A MoviePy VideoClip to composite over the main video
    """
    events = create_subtitle_clips(word_timestamps, max_words, font_size)
    
    if not events:
        # Return empty transparent clip
        def empty_frame(t):
            return np.zeros((1, VIDEO_WIDTH, 4), dtype=np.uint8)
        return VideoClip(empty_frame, duration=total_duration).with_fps(30)
    
    # Pre-render all unique frames for performance
    frame_cache = {}
    
    def make_frame(t):
        """Generate the subtitle frame for time t."""
        # Find the active event at time t
        active_event = None
        for event in events:
            if event["start"] <= t < event["end"]:
                active_event = event
                break
        
        if active_event is None:
            # No subtitle at this time — transparent frame
            return np.zeros((font_size * 3, VIDEO_WIDTH, 4), dtype=np.uint8)
        
        # Create cache key
        cache_key = (tuple(active_event["words"]), active_event["highlight_index"])
        
        if cache_key not in frame_cache:
            frame_cache[cache_key] = _render_subtitle_frame(
                active_event["words"],
                active_event["highlight_index"],
                width=VIDEO_WIDTH,
                font_size=font_size,
            )
        
        return frame_cache[cache_key]
    
    clip = VideoClip(make_frame, duration=total_duration)
    clip = clip.with_fps(30)
    
    return clip


if __name__ == "__main__":
    # Quick visual test — render a single frame
    test_words = ["Savais-tu", "que", "les", "flamants"]
    frame = _render_subtitle_frame(test_words, highlight_index=2)
    
    img = Image.fromarray(frame)
    test_path = Path(__file__).parent.parent / "output" / "subtitle_test.png"
    img.save(test_path)
    print(f"✅ Test frame sauvegardé : {test_path}")
