import json
import re
from pathlib import Path
from typing import Optional
import time
import soundfile as sf

from config import (
    DEFAULT_VOICE,
    TEMP_DIR,
)

# Initialize Kokoro globally so it's loaded only once per process
_KOKORO_INSTANCE = None

def get_kokoro():
    global _KOKORO_INSTANCE
    if _KOKORO_INSTANCE is None:
        from kokoro_onnx import Kokoro
        print("Chargement de Kokoro TTS (Apple Silicon / ONNX)...")
        # Ensure these paths match where the models actually are in the project
        _KOKORO_INSTANCE = Kokoro("kokoro_models/kokoro-v1.0.onnx", "kokoro_models/voices-v1.0.bin")
    return _KOKORO_INSTANCE

# ─── Emotion Profiles with Speed and Pause ───────────
EMOTION_PROFILES = {
    "dramatic": {"speed": 0.85, "pause": 0.5},
    "tense": {"speed": 0.9, "pause": 0.4},
    "curious": {"speed": 1.05, "pause": 0.3},
    "surprised": {"speed": 1.15, "pause": 0.2},
    "funny": {"speed": 1.1, "pause": 0.3},
    "informative": {"speed": 1.0, "pause": 0.3},
}

def _approximate_timestamps(text: str, duration: float) -> list[dict]:
    """
    Since Kokoro doesn't provide word-level timestamps natively in the python port,
    we approximate them based on character length. This works surprisingly well
    for short segments.
    """
    # Split keeping words but filtering out empty strings
    words = [w for w in re.split(r'(\s+)', text) if w.strip()]
    if not words:
        return []
        
    total_chars = sum(len(w) for w in words)
    char_time = duration / max(total_chars, 1)
    
    word_timestamps = []
    current_time = 0.0
    for word in words:
        word_dur = len(word) * char_time
        word_timestamps.append({
            "text": word,
            "start": current_time,
            "end": current_time + word_dur
        })
        current_time += word_dur
        
    return word_timestamps

def generate_voice(
    text: str,
    output_name: str = "voiceover",
    voice: str = "ff_siwis",  # Default Kokoro French voice
    rate: str = "1.0",        # Ignored, using profile speeds
    pitch: str = "0",         # Ignored
    output_dir: Optional[Path] = None,
    emotion: str = "informative",
) -> tuple[Path, Path, list[dict]]:
    """
    Generate voiceover audio from text using Kokoro TTS.
    """
    if output_dir is None:
        output_dir = TEMP_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save as .wav because Kokoro outputs raw audio arrays (soundfile writes wav easily)
    audio_path = output_dir / f"{output_name}.wav"
    timestamps_path = output_dir / f"{output_name}_timestamps.json"
    
    profile = EMOTION_PROFILES.get(emotion, EMOTION_PROFILES["informative"])
    speed = profile["speed"]
    
    print(f"🎙️ Génération Kokoro ({voice}, emotion={emotion}, speed={speed})...")
    print(f"   📝 Texte : {text[:80]}...")
    
    kokoro = get_kokoro()
    audio, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="fr-fr")
    
    # Write audio
    sf.write(audio_path, audio, sample_rate)
    duration = len(audio) / sample_rate
    
    # Timestamps approximation
    word_timestamps = _approximate_timestamps(text, duration)
    
    with open(timestamps_path, "w", encoding="utf-8") as f:
        json.dump(word_timestamps, f, ensure_ascii=False, indent=2)
    
    print(f"   ✅ Audio sauvegardé : {audio_path}")
    print(f"   ✅ Timestamps : {len(word_timestamps)} mots approximés")
    
    return audio_path, timestamps_path, word_timestamps

def list_french_voices() -> list[dict]:
    """List all available French voices in Kokoro (approximation for API compatibility)."""
    # Kokoro has specific voices bundled. For v1.0 usually:
    return [
        {"Name": "ff_siwis", "Gender": "Female", "Locale": "fr-FR"},
        {"Name": "mf_...", "Gender": "Male", "Locale": "fr-FR"}, # Add others if you know them
    ]

def generate_voice_per_segment(
    segments: list[dict],
    hook: str,
    loop_bridge: str,
    voice: str = "ff_siwis",
    rate: str = "1.0",
    output_dir: Optional[Path] = None,
    hook_emotion: str = "dramatic",
    bridge_emotion: str = "tense",
) -> list[dict]:
    """
    Generate separate audio files for each segment using Kokoro TTS.
    Each segment gets custom speed based on its emotion tag.
    """
    if output_dir is None:
        output_dir = TEMP_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    all_parts = []
    
    text_parts = [{"text": hook, "label": "hook", "emotion": hook_emotion}]
    for i, seg in enumerate(segments):
        emotion = seg.get("emotion", "informative")
        text_parts.append({"text": seg["text"], "label": f"segment_{i}", "emotion": emotion})
    text_parts.append({"text": loop_bridge, "label": "loop_bridge", "emotion": bridge_emotion})
    
    kokoro = get_kokoro()
    
    for part in text_parts:
        audio_path = output_dir / f"{part['label']}.wav"
        ts_path = output_dir / f"{part['label']}_timestamps.json"
        
        emotion_emoji = {
            "dramatic": "🎭", "tense": "😰", "curious": "🤔",
            "surprised": "😲", "funny": "😂", "informative": "📚",
        }.get(part["emotion"], "🎵")
        
        profile = EMOTION_PROFILES.get(part["emotion"], EMOTION_PROFILES["informative"])
        pause = profile.get("pause", 0.3)
        if part["label"] == "loop_bridge":
            pause = 0.0  # Seamless loop!
            
        speed = profile["speed"]
        print(f"  🎙️ [{part['label']}] {emotion_emoji} {part['emotion']} (speed={speed}) — {part['text'][:50]}...")
        
        # Generate with Kokoro
        audio, sample_rate = kokoro.create(part["text"], voice=voice, speed=speed, lang="fr-fr")
        sf.write(audio_path, audio, sample_rate)
        duration = len(audio) / sample_rate
        
        # Approximate timestamps
        word_timestamps = _approximate_timestamps(part["text"], duration)
        with open(ts_path, "w", encoding="utf-8") as f:
            json.dump(word_timestamps, f, ensure_ascii=False, indent=2)
        
        all_parts.append({
            "label": part["label"],
            "text": part["text"],
            "audio_path": audio_path,
            "timestamps_path": ts_path,
            "word_timestamps": word_timestamps,
            "duration": duration,
            "pause": pause,
            "emotion": part["emotion"],
        })
    
    total_speech = sum(p["duration"] for p in all_parts)
    total_pauses = sum(p["pause"] for p in all_parts)
    total_total = total_speech + total_pauses
    print(f"\n  ✅ Voix off complète : {total_speech:.1f}s (+ {total_pauses:.1f}s pauses = {total_total:.1f}s total)")
    
    return all_parts

if __name__ == "__main__":
    # Quick test
    test_text = "Ton cerveau te ment. Chaque nuit, il fabrique des souvenirs."
    audio, ts, words = generate_voice(test_text, "test_kokoro", emotion="dramatic")
    print(f"\nAudio : {audio}")
