"""
WhatZeFact — Video Assembler
Assembles the final video from voiceover, stock clips, subtitles, and branding.
"""

import random
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from moviepy import (
    VideoFileClip,
    AudioFileClip,
    ImageClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
    concatenate_audioclips,
    vfx,
)

from config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_FPS,
    LOGO_PATH,
    LOGO_SIZE,
    LOGO_POSITION,
    LOGO_OPACITY,
    MUSIC_DIR,
    MUSIC_VOLUME_DB,
    OUTPUT_DIR,
    TEMP_DIR,
    OUTRO_PATH,
    OUTRO_FADE_DURATION,
    INTRO_VIDEO_PATH,
    INTRO_DURATION,
    INTRO_BG_GRADIENT_TOP,
    INTRO_BG_GRADIENT_BOTTOM,
    INTRO_LOGO_SIZE,
    INTRO_TITLE_FONT_SIZE,
    INTRO_TITLE_COLOR,
    INTRO_ACCENT_COLOR,
)
from assembler.subtitle_engine import build_subtitle_clip, estimate_word_timestamps


def _resize_clip_to_portrait(clip: VideoFileClip) -> VideoFileClip:
    """
    Resize and crop a video clip to fit 1080x1920 (9:16 portrait).
    Handles both landscape and portrait source videos.
    """
    target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT  # 0.5625
    clip_ratio = clip.w / clip.h
    
    if clip_ratio > target_ratio:
        # Source is wider → scale by height, crop width
        new_height = VIDEO_HEIGHT
        new_width = int(clip.w * (VIDEO_HEIGHT / clip.h))
        clip = clip.resized(height=new_height)
        # Center crop
        x_center = new_width // 2
        x1 = x_center - VIDEO_WIDTH // 2
        clip = clip.cropped(x1=x1, y1=0, x2=x1 + VIDEO_WIDTH, y2=VIDEO_HEIGHT)
    else:
        # Source is taller or same ratio → scale by width, crop height
        new_width = VIDEO_WIDTH
        new_height = int(clip.h * (VIDEO_WIDTH / clip.w))
        clip = clip.resized(width=new_width)
        # Center crop
        y_center = new_height // 2
        y1 = y_center - VIDEO_HEIGHT // 2
        clip = clip.cropped(x1=0, y1=y1, x2=VIDEO_WIDTH, y2=y1 + VIDEO_HEIGHT)
    
    return clip


def _create_logo_overlay(duration: float) -> ImageClip:
    """Create a logo overlay clip."""
    if not LOGO_PATH.exists():
        print("  ⚠️  Logo non trouvé, pas d'overlay logo")
        return None
    
    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo = logo.resize(LOGO_SIZE, Image.Resampling.LANCZOS)
    
    # Apply opacity
    logo_array = np.array(logo)
    logo_array[:, :, 3] = (logo_array[:, :, 3] * LOGO_OPACITY).astype(np.uint8)
    
    logo_clip = (
        ImageClip(logo_array)
        .with_duration(duration)
        .with_position(LOGO_POSITION)
    )
    
    return logo_clip


def _pick_random_music() -> Optional[Path]:
    """Pick a random music file from the music directory."""
    if not MUSIC_DIR.exists():
        return None
    
    music_files = list(MUSIC_DIR.glob("*.mp3")) + list(MUSIC_DIR.glob("*.wav"))
    if not music_files:
        return None
    
    return random.choice(music_files)


def _find_font(bold: bool = True) -> str:
    """Find a suitable system font for the intro title."""
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
    return None


def _create_branded_intro(title: str) -> VideoFileClip:
    """
    Create a branded intro clip.
    
    If Intro.mp4 exists in Charte Graphique, uses that file.
    Otherwise, generates a dynamic intro with:
    - Dark gradient background
    - WhatZeFact logo (centered, animated fade-in)
    - Video title text below logo
    """
    # Option B: Use intro video file if it exists
    if INTRO_VIDEO_PATH.exists():
        print("  🎬 Intro depuis fichier Intro.mp4")
        try:
            intro = VideoFileClip(str(INTRO_VIDEO_PATH))
            intro = _resize_clip_to_portrait(intro)
            return intro
        except Exception as e:
            print(f"  ⚠️  Erreur chargement Intro.mp4: {e}, génération dynamique...")
    
    # Option A: Generate dynamic intro
    print("  🎬 Génération de l'intro dynamique...")
    
    from PIL import ImageDraw, ImageFont
    
    duration = INTRO_DURATION
    logo_img = None
    
    # Load logo if available
    if LOGO_PATH.exists():
        logo_img = Image.open(LOGO_PATH).convert("RGBA")
        logo_img = logo_img.resize(INTRO_LOGO_SIZE, Image.Resampling.LANCZOS)
    
    # Load font
    font_path = _find_font()
    try:
        title_font = ImageFont.truetype(font_path, INTRO_TITLE_FONT_SIZE) if font_path else ImageFont.load_default()
        brand_font = ImageFont.truetype(font_path, 36) if font_path else ImageFont.load_default()
    except Exception:
        title_font = ImageFont.load_default()
        brand_font = ImageFont.load_default()
    
    # Wrap title text to fit screen width
    max_chars_per_line = 25
    words = title.split()
    title_lines = []
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 > max_chars_per_line:
            title_lines.append(current_line.strip())
            current_line = word
        else:
            current_line += " " + word
    if current_line.strip():
        title_lines.append(current_line.strip())
    
    def make_intro_frame(t):
        """Render a single frame of the branded intro."""
        # Create gradient background
        frame = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
        top = np.array(INTRO_BG_GRADIENT_TOP)
        bottom = np.array(INTRO_BG_GRADIENT_BOTTOM)
        for y in range(VIDEO_HEIGHT):
            ratio = y / VIDEO_HEIGHT
            color = (top * (1 - ratio) + bottom * ratio).astype(np.uint8)
            frame[y, :] = color
        
        # Convert to PIL for text/logo rendering
        pil_img = Image.fromarray(frame).convert("RGBA")
        overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Fade-in factor (0→1 over first 0.6s)
        fade = min(1.0, t / 0.6)
        alpha = int(255 * fade)
        
        # Center Y calculation
        center_y = VIDEO_HEIGHT // 2 - 100
        
        # Draw logo if available
        if logo_img is not None:
            logo_with_alpha = logo_img.copy()
            logo_arr = np.array(logo_with_alpha)
            logo_arr[:, :, 3] = (logo_arr[:, :, 3] * fade).astype(np.uint8)
            logo_faded = Image.fromarray(logo_arr)
            logo_x = (VIDEO_WIDTH - INTRO_LOGO_SIZE[0]) // 2
            logo_y = center_y - INTRO_LOGO_SIZE[1] // 2 - 30
            overlay.paste(logo_faded, (logo_x, logo_y), logo_faded)
            text_start_y = logo_y + INTRO_LOGO_SIZE[1] + 30
        else:
            text_start_y = center_y
        
        # Draw title lines
        for i, line in enumerate(title_lines):
            text_bbox = draw.textbbox((0, 0), line, font=title_font)
            text_w = text_bbox[2] - text_bbox[0]
            text_x = (VIDEO_WIDTH - text_w) // 2
            text_y = text_start_y + i * (INTRO_TITLE_FONT_SIZE + 15)
            
            # Text shadow
            draw.text((text_x + 2, text_y + 2), line, font=title_font, fill=(0, 0, 0, alpha))
            # Main text
            draw.text((text_x, text_y), line, font=title_font, fill=(255, 255, 255, alpha))
        
        # Draw "WhatZeFact" brand text at bottom
        brand_text = "WhatZeFact"
        brand_bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
        brand_w = brand_bbox[2] - brand_bbox[0]
        brand_x = (VIDEO_WIDTH - brand_w) // 2
        brand_y = text_start_y + len(title_lines) * (INTRO_TITLE_FONT_SIZE + 15) + 40
        draw.text((brand_x, brand_y), brand_text, font=brand_font, fill=(255, 193, 7, alpha))  # Yellow
        
        # Composite
        result = Image.alpha_composite(pil_img, overlay)
        return np.array(result.convert("RGB"))
    
    from moviepy import VideoClip
    intro_clip = VideoClip(make_intro_frame, duration=duration).with_fps(VIDEO_FPS)
    
    return intro_clip


def _load_outro_clip() -> Optional[VideoFileClip]:
    """
    Load the Outro.mp4 from Charte Graphique and resize to portrait.
    Returns None if the file doesn't exist.
    """
    if not OUTRO_PATH.exists():
        print("  ⚠️  Outro.mp4 non trouvé, pas d'outro")
        return None
    
    try:
        outro = VideoFileClip(str(OUTRO_PATH))
        outro = _resize_clip_to_portrait(outro)
        print(f"  🎬 Outro chargé ({outro.duration:.1f}s)")
        return outro
    except Exception as e:
        print(f"  ⚠️  Erreur chargement Outro.mp4: {e}")
        return None


def _prepare_background_music(music_path: Path, duration: float) -> AudioFileClip:
    """Load and prepare background music (loop if needed, reduce volume)."""
    music = AudioFileClip(str(music_path))
    
    # Loop if music is shorter than video
    if music.duration < duration:
        loops_needed = int(duration / music.duration) + 1
        music_clips = [music] * loops_needed
        music = concatenate_audioclips(music_clips)
    
    # Trim to video duration
    music = music.subclipped(0, duration)
    
    # Reduce volume
    volume_factor = 10 ** (MUSIC_VOLUME_DB / 20)  # Convert dB to factor
    music = music.with_volume_scaled(volume_factor)
    
    return music


def assemble_video(
    script: dict,
    audio_parts: list[dict],
    stock_videos: list[dict],
    output_name: Optional[str] = None,
    music_path: Optional[Path] = None,
    include_logo: bool = True,
    include_subtitles: bool = True,
    include_intro: bool = True,
    include_outro: bool = True,
) -> Path:
    """
    Assemble the final WhatZeFact video.
    
    Args:
        script: The structured script dict
        audio_parts: Voice parts from voice_generator (hook + segments + outro)
        stock_videos: Downloaded stock video paths from video_searcher
        output_name: Output filename (without extension)
        music_path: Path to background music file (auto-picked if None)
        include_logo: Whether to overlay the WhatZeFact logo
        include_subtitles: Whether to add word-by-word subtitles
        include_intro: Whether to add branded intro at the start
        include_outro: Whether to add Outro.mp4 at the end
        
    Returns:
        Path to the final video file
    """
    if output_name is None:
        # Clean title for filename
        title = script.get("title", "whatzefact_video")
        output_name = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
        output_name = output_name.strip().replace(" ", "_")[:50]
    
    output_path = OUTPUT_DIR / f"{output_name}.mp4"
    
    print(f"\n🎬 Assemblage de la vidéo finale...")
    print(f"   📁 Sortie : {output_path}")
    
    # ─── 1. Build video segments ─────────────────────────
    video_segments = []
    all_word_timestamps = []
    cumulative_time = 0.0
    
    # audio_parts = [hook, segment_0, segment_1, ..., outro]
    # stock_videos = [segment_0_video, segment_1_video, ...]
    # Hook and outro use stock_videos[0] and last as fallback
    
    for part_idx, part in enumerate(audio_parts):
        speech_duration = part["duration"]
        pause = part.get("pause", 0.0)
        duration = speech_duration + pause
        
        # Find matching stock video
        stock_video_path = None
        if part["label"] == "hook":
            # Use first segment's video for hook
            if stock_videos and stock_videos[0].get("video_path"):
                stock_video_path = stock_videos[0]["video_path"]
        elif part["label"] in ("loop_bridge", "outro"):
            # Use last segment's video for loop_bridge / outro
            if stock_videos and stock_videos[-1].get("video_path"):
                stock_video_path = stock_videos[-1]["video_path"]
        else:
            # Match segment index
            seg_idx = int(part["label"].split("_")[1]) if "_" in part["label"] else 0
            if seg_idx < len(stock_videos) and stock_videos[seg_idx].get("video_path"):
                stock_video_path = stock_videos[seg_idx]["video_path"]
        
        # Create video clip for this segment
        if stock_video_path and Path(stock_video_path).exists():
            try:
                clip = VideoFileClip(str(stock_video_path))
                clip = _resize_clip_to_portrait(clip)
                
                # Loop or trim to match audio duration
                if clip.duration < duration:
                    loops = int(duration / clip.duration) + 1
                    clip = concatenate_videoclips([clip] * loops)
                clip = clip.subclipped(0, duration)
                clip = clip.without_audio()  # Remove stock audio
                
            except Exception as e:
                print(f"  ⚠️  Erreur vidéo {stock_video_path}: {e}")
                clip = _create_color_clip(duration)
        else:
            # Fallback: dark gradient background
            clip = _create_color_clip(duration)
        
        video_segments.append(clip)
        
        # Get or estimate word timestamps
        wts = part.get("word_timestamps", [])
        if not wts:
            wts = estimate_word_timestamps(part["text"], speech_duration)
            
        # Offset word timestamps for this part
        for wt in wts:
            all_word_timestamps.append({
                "text": wt["text"],
                "start": wt["start"] + cumulative_time,
                "end": wt["end"] + cumulative_time,
            })
        
        cumulative_time += duration
    
    # ─── 2. Add branded intro ────────────────────────────
    intro_clip = None
    intro_duration = 0.0
    if include_intro:
        title = script.get("title", "WhatZeFact")
        intro_clip = _create_branded_intro(title)
        if intro_clip is not None:
            intro_duration = intro_clip.duration
            video_segments.insert(0, intro_clip)
            # Offset all word timestamps by intro duration
            for wt in all_word_timestamps:
                wt["start"] += intro_duration
                wt["end"] += intro_duration
            cumulative_time += intro_duration
            print(f"  🎬 Intro ajoutée ({intro_duration:.1f}s)")
    
    # ─── 3. Add outro clip ───────────────────────────────
    outro_clip = None
    if include_outro:
        outro_clip = _load_outro_clip()
        if outro_clip is not None:
            # Remove audio from outro (we'll use our own audio track)
            outro_no_audio = outro_clip.without_audio()
            video_segments.append(outro_no_audio)
            cumulative_time += outro_clip.duration
    
    # ─── 4. Concatenate all video segments ───────────────
    print("  📼 Concaténation des segments vidéo...")
    final_video = concatenate_videoclips(video_segments, method="compose")
    total_duration = final_video.duration
    
    # ─── 5. Build audio track ────────────────────────────
    print("  🔊 Construction de la piste audio...")
    audio_clips = []
    for part in audio_parts:
        speech_clip = AudioFileClip(str(part["audio_path"]))
        pause = part.get("pause", 0.0)
        if pause > 0.0:
            # Create silent audio clip to fill pause
            from moviepy import AudioClip
            import numpy as np
            silence_clip = AudioClip(lambda t: np.zeros(2), duration=pause, fps=44100)
            combined_audio = concatenate_audioclips([speech_clip, silence_clip])
            audio_clips.append(combined_audio)
        else:
            audio_clips.append(speech_clip)
    
    voiceover = concatenate_audioclips(audio_clips)
    
    # Pad voiceover with silence for intro and outro
    from moviepy import AudioClip
    if intro_duration > 0:
        intro_silence = AudioClip(lambda t: np.zeros(2), duration=intro_duration, fps=44100)
        voiceover = concatenate_audioclips([intro_silence, voiceover])
    if outro_clip is not None:
        outro_silence = AudioClip(lambda t: np.zeros(2), duration=outro_clip.duration, fps=44100)
        voiceover = concatenate_audioclips([voiceover, outro_silence])
        # If outro has its own audio, mix it in
        if outro_clip.audio is not None:
            outro_audio = outro_clip.audio
            # Pad outro audio to start at the right time
            outro_start = total_duration - outro_clip.duration
            outro_audio = outro_audio.with_start(outro_start)
            voiceover = CompositeAudioClip([voiceover, outro_audio])
    
    # Add background music if available
    if music_path is None:
        music_path = _pick_random_music()
    
    if music_path and music_path.exists():
        print(f"  🎵 Musique de fond : {music_path.name}")
        bg_music = _prepare_background_music(music_path, total_duration)
        final_audio = CompositeAudioClip([voiceover, bg_music])
    else:
        print("  🎵 Pas de musique de fond")
        final_audio = voiceover
    
    final_video = final_video.with_audio(final_audio)
    
    # ─── 6. Add overlays ─────────────────────────────────
    layers = [final_video]
    
    # Logo overlay
    if include_logo:
        logo_clip = _create_logo_overlay(total_duration)
        if logo_clip is not None:
            layers.append(logo_clip)
            print("  🏷️  Logo ajouté")
    
    # Subtitle overlay
    if include_subtitles and all_word_timestamps:
        print("  📝 Génération des sous-titres dynamiques...")
        subtitle_clip = build_subtitle_clip(
            all_word_timestamps,
            total_duration,
        )
        # Position subtitles in lower third
        y_position = int(VIDEO_HEIGHT * 0.75)
        subtitle_clip = subtitle_clip.with_position(("center", y_position))
        layers.append(subtitle_clip)
        print(f"  ✅ {len(all_word_timestamps)} mots sous-titrés")
    
    # ─── 7. Composite and export ─────────────────────────
    print("  🎞️  Rendu final...")
    final = CompositeVideoClip(layers, size=(VIDEO_WIDTH, VIDEO_HEIGHT))
    
    final.write_videofile(
        str(output_path),
        fps=VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger="bar",
    )
    
    # Clean up
    for clip in video_segments:
        clip.close()
    final.close()
    
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"\n  🎉 Vidéo générée : {output_path}")
    print(f"  📏 Durée : {total_duration:.1f}s | Taille : {size_mb:.1f} MB")
    
    return output_path


def _create_color_clip(duration: float) -> VideoFileClip:
    """Create a dark gradient background clip as fallback."""
    def make_frame(t):
        # Dark blue-to-black gradient
        frame = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 3), dtype=np.uint8)
        for y in range(VIDEO_HEIGHT):
            ratio = y / VIDEO_HEIGHT
            r = int(10 * (1 - ratio))
            g = int(15 * (1 - ratio))
            b = int(30 * (1 - ratio))
            frame[y, :] = [r, g, b]
        return frame
    
    return VideoClip(make_frame, duration=duration).with_fps(VIDEO_FPS)


if __name__ == "__main__":
    print("Video assembler module — import and use assemble_video()")
