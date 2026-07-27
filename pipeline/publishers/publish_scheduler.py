"""
WhatZeFact — Publish Scheduler
Local queue system for scheduling video publications.

Stores a JSON file with pending publications and their target dates.
Can be used with cron or a background process to auto-publish.
"""

import json
import datetime
from pathlib import Path
from typing import Optional

from config import OUTPUT_DIR

SCHEDULE_FILE = OUTPUT_DIR / ".publish_schedule.json"


def _load_schedule() -> list[dict]:
    """Load the publish schedule from disk."""
    if not SCHEDULE_FILE.exists():
        return []
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_schedule(schedule: list[dict]):
    """Save the publish schedule to disk."""
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2, default=str)


def add_to_schedule(
    video_path: Path,
    script: dict,
    publish_at: datetime.datetime,
    platform: str = "youtube",
    privacy: str = "public",
) -> dict:
    """
    Add a video to the publish schedule.
    
    Args:
        video_path: Path to the video file
        script: The script dict for metadata generation
        publish_at: When to publish (UTC)
        platform: Target platform ("youtube")
        privacy: Privacy setting for the published video
    
    Returns:
        The schedule entry dict
    """
    schedule = _load_schedule()
    
    entry = {
        "id": len(schedule) + 1,
        "video_path": str(video_path),
        "script_path": str(video_path.with_name(f"{video_path.stem}_script.json")),
        "title": script.get("title", video_path.stem),
        "platform": platform,
        "privacy": privacy,
        "publish_at": publish_at.isoformat(),
        "status": "pending",  # pending, published, failed
        "created_at": datetime.datetime.now().isoformat(),
        "result": None,
    }
    
    schedule.append(entry)
    _save_schedule(schedule)
    
    print(f"  📅 Ajouté au planning : {entry['title']}")
    print(f"     Publication : {publish_at.strftime('%d/%m/%Y à %Hh%M')} ({platform})")
    
    return entry


def list_schedule(status: Optional[str] = None) -> list[dict]:
    """
    List all scheduled publications.
    
    Args:
        status: Filter by status ("pending", "published", "failed") or None for all
    
    Returns:
        List of schedule entries
    """
    schedule = _load_schedule()
    if status:
        schedule = [e for e in schedule if e.get("status") == status]
    return schedule


def get_pending_publications() -> list[dict]:
    """Get publications that are due (publish_at <= now and status == pending)."""
    now = datetime.datetime.now()
    schedule = _load_schedule()
    
    due = []
    for entry in schedule:
        if entry.get("status") != "pending":
            continue
        publish_at = datetime.datetime.fromisoformat(entry["publish_at"])
        if publish_at <= now:
            due.append(entry)
    
    return due


def mark_published(entry_id: int, result: dict):
    """Mark a schedule entry as published with its result."""
    schedule = _load_schedule()
    for entry in schedule:
        if entry.get("id") == entry_id:
            entry["status"] = "published"
            entry["result"] = result
            entry["published_at"] = datetime.datetime.now().isoformat()
            break
    _save_schedule(schedule)


def mark_failed(entry_id: int, error: str):
    """Mark a schedule entry as failed."""
    schedule = _load_schedule()
    for entry in schedule:
        if entry.get("id") == entry_id:
            entry["status"] = "failed"
            entry["result"] = {"error": error}
            break
    _save_schedule(schedule)


def process_pending():
    """
    Process all pending publications that are due.
    
    This is the main function to call from a cron job or background process.
    """
    from publishers.youtube_publisher import upload_to_youtube
    
    due = get_pending_publications()
    if not due:
        print("📅 Aucune publication en attente")
        return
    
    print(f"\n📅 {len(due)} publication(s) en attente\n")
    
    for entry in due:
        video_path = Path(entry["video_path"])
        
        if not video_path.exists():
            print(f"  ❌ Vidéo introuvable : {video_path}")
            mark_failed(entry["id"], f"Fichier introuvable: {video_path}")
            continue
        
        # Load script
        script = {}
        script_path = Path(entry.get("script_path", ""))
        if script_path.exists():
            with open(script_path, "r", encoding="utf-8") as f:
                script = json.load(f)
        
        try:
            if entry.get("platform") == "youtube":
                result = upload_to_youtube(
                    video_path=video_path,
                    script=script,
                    privacy=entry.get("privacy", "public"),
                )
                mark_published(entry["id"], result)
                print(f"  ✅ Publié : {entry['title']}")
            else:
                mark_failed(entry["id"], f"Plateforme non supportée: {entry['platform']}")
        
        except Exception as e:
            print(f"  ❌ Erreur : {e}")
            mark_failed(entry["id"], str(e))


def print_schedule():
    """Print the current schedule in a readable format."""
    schedule = _load_schedule()
    
    if not schedule:
        print("\n📅 Aucune publication planifiée\n")
        return
    
    print(f"\n📅 Planning de publication ({len(schedule)} entrées)")
    print(f"{'='*60}")
    
    status_icons = {"pending": "⏳", "published": "✅", "failed": "❌"}
    
    for entry in schedule:
        icon = status_icons.get(entry.get("status", ""), "❓")
        title = entry.get("title", "Sans titre")[:40]
        publish_at = entry.get("publish_at", "?")
        try:
            dt = datetime.datetime.fromisoformat(publish_at)
            publish_str = dt.strftime("%d/%m/%Y %Hh%M")
        except (ValueError, TypeError):
            publish_str = publish_at
        
        platform = entry.get("platform", "?")
        print(f"  {icon} [{platform}] {title}")
        print(f"     📅 {publish_str} | Status: {entry.get('status', '?')}")
        
        if entry.get("result") and entry.get("status") == "published":
            url = entry["result"].get("url", "")
            if url:
                print(f"     🔗 {url}")
        elif entry.get("result") and entry.get("status") == "failed":
            error = entry["result"].get("error", "")
            if error:
                print(f"     ❌ {error[:60]}")
    
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "process":
        process_pending()
    else:
        print_schedule()
