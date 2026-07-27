"""
WhatZeFact — Video Searcher
Uses the free Pexels API to find and download stock video clips.
"""

import os
import time
from pathlib import Path
from typing import Optional

import requests

from config import PEXELS_API_KEY, TEMP_DIR, VIDEO_WIDTH, VIDEO_HEIGHT


PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"


def search_videos(
    query: str,
    per_page: int = 5,
    orientation: str = "portrait",
    min_duration: int = 3,
    max_duration: int = 30,
) -> list[dict]:
    """
    Search for videos on Pexels.
    
    Args:
        query: Search keywords (in English)
        per_page: Number of results to fetch
        orientation: "portrait", "landscape", or "square"
        min_duration: Minimum video duration in seconds
        max_duration: Maximum video duration in seconds
        
    Returns:
        List of video metadata dicts
    """
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": orientation,
    }
    
    response = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params)
    response.raise_for_status()
    
    data = response.json()
    videos = []
    
    for video in data.get("videos", []):
        duration = video.get("duration", 0)
        if min_duration <= duration <= max_duration:
            # Find best video file (prefer HD portrait)
            best_file = _pick_best_file(video.get("video_files", []))
            if best_file:
                videos.append({
                    "id": video["id"],
                    "width": best_file.get("width", 0),
                    "height": best_file.get("height", 0),
                    "duration": duration,
                    "url": best_file["link"],
                    "quality": best_file.get("quality", "unknown"),
                    "file_type": best_file.get("file_type", "video/mp4"),
                })
    
    return videos


def _pick_best_file(video_files: list[dict]) -> Optional[dict]:
    """Pick the best video file from Pexels options (prefer HD, mp4)."""
    # Filter mp4 files
    mp4_files = [f for f in video_files if f.get("file_type") == "video/mp4"]
    if not mp4_files:
        mp4_files = video_files
    
    if not mp4_files:
        return None
    
    # Sort by resolution (prefer closest to our target without being too small)
    def score(f):
        w = f.get("width", 0)
        h = f.get("height", 0)
        # Prefer files with height >= 720 but not too huge
        if h >= 720 and h <= 1920:
            return h  # Higher is better in this range
        elif h > 1920:
            return 1920 - (h - 1920)  # Penalize too large
        else:
            return h  # Small files scored lower
    
    mp4_files.sort(key=score, reverse=True)
    return mp4_files[0]


def download_video(
    url: str,
    output_path: Path,
    timeout: int = 30,
) -> Path:
    """Download a video file from URL."""
    print(f"   ⬇️  Téléchargement : {output_path.name}")
    
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"   ✅ Téléchargé : {output_path.name} ({size_mb:.1f} MB)")
    
    return output_path


def search_and_download_for_segments(
    segments: list[dict],
    output_dir: Optional[Path] = None,
) -> list[dict]:
    """
    For each script segment, search Pexels and download the best matching video.
    
    Args:
        segments: List of script segments (each with 'visual_keywords')
        output_dir: Directory to save downloaded videos
        
    Returns:
        List of dicts with segment info + downloaded video path
    """
    if output_dir is None:
        output_dir = TEMP_DIR / "stock_videos"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    
    for i, segment in enumerate(segments):
        keywords = segment.get("visual_keywords", [])
        video_path = None
        
        print(f"\n  🔍 Segment {i+1}: recherche de vidéos...")
        
        # Try each keyword until we find a video
        for keyword in keywords:
            print(f"     🔎 Recherche : '{keyword}'")
            try:
                videos = search_videos(keyword, per_page=3)
                if videos:
                    # Pick the first (best) result
                    video = videos[0]
                    video_path = output_dir / f"segment_{i}_{keyword.replace(' ', '_')}.mp4"
                    download_video(video["url"], video_path)
                    break
            except Exception as e:
                print(f"     ⚠️  Erreur avec '{keyword}': {e}")
                continue
            
            # Rate limiting: Pexels allows 200 requests/hour
            time.sleep(0.5)
        
        if video_path is None:
            # Fallback: try a generic search
            print(f"     ⚠️  Aucun résultat, recherche générique...")
            try:
                videos = search_videos("abstract background", per_page=3)
                if videos:
                    video_path = output_dir / f"segment_{i}_fallback.mp4"
                    download_video(videos[0]["url"], video_path)
            except Exception as e:
                print(f"     ❌ Impossible de trouver une vidéo : {e}")
        
        results.append({
            "segment_index": i,
            "text": segment.get("text", ""),
            "keywords_tried": keywords,
            "video_path": video_path,
        })
        
        # Rate limiting between segments
        time.sleep(0.3)
    
    found = sum(1 for r in results if r["video_path"] is not None)
    print(f"\n  ✅ Vidéos trouvées : {found}/{len(segments)} segments")
    
    return results


if __name__ == "__main__":
    # Quick test
    test_segments = [
        {"visual_keywords": ["cat scared", "cat jump", "funny cat"]},
        {"visual_keywords": ["cucumber", "green vegetable", "garden"]},
        {"visual_keywords": ["brain science", "neuroscience", "brain scan"]},
    ]
    results = search_and_download_for_segments(test_segments)
    for r in results:
        print(f"  Segment {r['segment_index']}: {r['video_path']}")
