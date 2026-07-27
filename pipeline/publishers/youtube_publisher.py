"""
WhatZeFact — YouTube Publisher
Upload videos to YouTube with auto-generated metadata from scripts.

Requirements:
    pip install google-auth-oauthlib google-api-python-client

Setup:
    1. Go to https://console.cloud.google.com
    2. Create a project (or use existing)
    3. Enable "YouTube Data API v3"
    4. Create OAuth2 credentials (Desktop App)
    5. Download client_secrets.json → place in pipeline/
    6. First run will open a browser for auth (tokens are saved)
"""

import json
import datetime
from pathlib import Path
from typing import Optional

from config import (
    YOUTUBE_CLIENT_SECRETS_PATH,
    YOUTUBE_TOKEN_PATH,
    YOUTUBE_DEFAULT_CATEGORY,
    YOUTUBE_DEFAULT_PRIVACY,
    YOUTUBE_DEFAULT_LANGUAGE,
    OUTPUT_DIR,
)


# YouTube API scopes
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_authenticated_service():
    """
    Authenticate with YouTube API using OAuth2.
    First run opens a browser, subsequent runs use saved tokens.
    
    Returns:
        googleapiclient.discovery.Resource: YouTube API service object
    """
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None

    # Load existing tokens
    if YOUTUBE_TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    # Refresh or get new tokens
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not YOUTUBE_CLIENT_SECRETS_PATH.exists():
                raise FileNotFoundError(
                    f"❌ client_secrets.json non trouvé !\n"
                    f"   Chemin attendu : {YOUTUBE_CLIENT_SECRETS_PATH}\n"
                    f"   Guide : https://console.cloud.google.com → APIs → Credentials\n"
                    f"   Crée des identifiants OAuth2 (type 'Application de bureau')\n"
                    f"   et télécharge le fichier JSON dans pipeline/"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(YOUTUBE_CLIENT_SECRETS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=8090)

        # Save tokens for next run
        with open(YOUTUBE_TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())
        print("  ✅ Tokens YouTube sauvegardés")

    return build("youtube", "v3", credentials=creds)


def _generate_description(script: dict) -> str:
    """
    Generate a YouTube description from the video script.
    
    Includes:
    - Hook text as intro
    - Segment summaries
    - Hashtags
    - Channel branding
    """
    lines = []
    
    # Hook as intro
    hook = script.get("hook", "")
    if hook:
        lines.append(hook)
        lines.append("")
    
    # Segment titles/summaries
    segments = script.get("segments", [])
    if segments:
        lines.append("📚 Dans cette vidéo :")
        for i, seg in enumerate(segments, 1):
            title = seg.get("title", seg.get("text", "")[:50])
            lines.append(f"  {i}. {title}")
        lines.append("")
    
    # Source/topic
    topic = script.get("topic", "")
    if topic:
        lines.append(f"🔍 Sujet : {topic}")
        lines.append("")
    
    # Branding
    lines.extend([
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🧠 WhatZeFact — Des faits incroyables, chaque jour !",
        "",
        "👆 Abonne-toi pour ne rien manquer !",
        "❤️ Like si tu as appris quelque chose !",
        "",
    ])
    
    # Hashtags
    hashtags = script.get("hashtags", [])
    if hashtags:
        lines.append(" ".join(hashtags))
    else:
        lines.append("#WhatZeFact #SaviezVous #Culture #Facts #Short")
    
    return "\n".join(lines)


def _generate_tags(script: dict) -> list[str]:
    """Generate YouTube tags from script metadata."""
    tags = ["WhatZeFact", "faits", "culture", "savoir", "éducation", "shorts"]
    
    # Extract hashtags as tags (remove #)
    hashtags = script.get("hashtags", [])
    for h in hashtags:
        tag = h.lstrip("#").strip()
        if tag and tag not in tags:
            tags.append(tag)
    
    # Add topic keywords
    topic = script.get("topic", "")
    if topic:
        for word in topic.split():
            word = word.strip("?!.,;:")
            if len(word) > 3 and word not in tags:
                tags.append(word)
    
    return tags[:30]  # YouTube limit: 500 chars total, ~30 tags max


def upload_to_youtube(
    video_path: Path,
    script: dict,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    category: str = YOUTUBE_DEFAULT_CATEGORY,
    privacy: str = YOUTUBE_DEFAULT_PRIVACY,
    scheduled_at: Optional[datetime.datetime] = None,
) -> dict:
    """
    Upload a video to YouTube.
    
    Args:
        video_path: Path to the MP4 video file
        script: The script dict (used to auto-generate title/description/tags)
        title: Custom title (auto-generated from script if None)
        description: Custom description (auto-generated if None)
        tags: Custom tags (auto-generated if None)
        category: YouTube category ID (default: 27 = Education)
        privacy: "private", "unlisted", or "public"
        scheduled_at: Schedule publication for this datetime (UTC).
                      If set, privacy is automatically set to "private" until publish time.
    
    Returns:
        dict with upload result: {video_id, url, status}
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Vidéo non trouvée : {video_path}")
    
    # Auto-generate metadata from script
    if title is None:
        title = script.get("title", video_path.stem)
        # YouTube title limit: 100 chars
        if len(title) > 100:
            title = title[:97] + "..."
    
    if description is None:
        description = _generate_description(script)
    
    if tags is None:
        tags = _generate_tags(script)
    
    print(f"\n📤 Upload YouTube...")
    print(f"   📹 Fichier : {video_path.name}")
    print(f"   📝 Titre   : {title}")
    print(f"   🔒 Visibilité : {privacy}")
    
    # Handle scheduled publishing
    publish_at = None
    if scheduled_at is not None:
        privacy = "private"  # Must be private for scheduling
        # Format as ISO 8601 with timezone
        publish_at = scheduled_at.isoformat()
        print(f"   📅 Publication planifiée : {scheduled_at.strftime('%d/%m/%Y à %Hh%M')}")
    
    # Build request body
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category,
            "defaultLanguage": YOUTUBE_DEFAULT_LANGUAGE,
            "defaultAudioLanguage": YOUTUBE_DEFAULT_LANGUAGE,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    
    if publish_at:
        body["status"]["publishAt"] = publish_at
    
    # Authenticate and upload
    youtube = _get_authenticated_service()
    
    from googleapiclient.http import MediaFileUpload
    
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )
    
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )
    
    # Execute with progress
    response = None
    print("   ⏳ Upload en cours...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            print(f"   📊 {progress}%", end="\r")
    
    video_id = response["id"]
    video_url = f"https://youtu.be/{video_id}"
    
    print(f"\n   ✅ Upload réussi !")
    print(f"   🔗 URL : {video_url}")
    print(f"   🆔 ID  : {video_id}")
    
    result = {
        "video_id": video_id,
        "url": video_url,
        "title": title,
        "privacy": privacy,
        "scheduled_at": str(scheduled_at) if scheduled_at else None,
        "status": "uploaded",
    }
    
    # Save upload result
    result_path = video_path.with_suffix(".youtube.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"   📄 Résultat sauvegardé : {result_path.name}")
    
    return result


def check_youtube_auth() -> dict:
    """
    Check if YouTube authentication is configured and valid.
    
    Returns:
        dict with status info
    """
    result = {
        "client_secrets_exists": YOUTUBE_CLIENT_SECRETS_PATH.exists(),
        "token_exists": YOUTUBE_TOKEN_PATH.exists(),
        "authenticated": False,
        "error": None,
    }
    
    if not result["client_secrets_exists"]:
        result["error"] = (
            "client_secrets.json manquant. "
            "Crée des identifiants OAuth2 sur console.cloud.google.com"
        )
        return result
    
    try:
        _get_authenticated_service()
        result["authenticated"] = True
    except Exception as e:
        result["error"] = str(e)
    
    return result


if __name__ == "__main__":
    print("\n🔍 Vérification de l'authentification YouTube...\n")
    status = check_youtube_auth()
    
    if status["authenticated"]:
        print("✅ Authentification YouTube OK !")
    else:
        print(f"❌ {status['error']}")
        if not status["client_secrets_exists"]:
            print("\n💡 Guide de configuration :")
            print("   1. Va sur https://console.cloud.google.com")
            print("   2. Crée un projet (ou utilise un existant)")
            print("   3. Active 'YouTube Data API v3'")
            print("   4. Crée des identifiants OAuth2 (type 'Application de bureau')")
            print("   5. Télécharge le JSON → renomme en 'client_secrets.json'")
            print(f"   6. Place-le dans : {YOUTUBE_CLIENT_SECRETS_PATH.parent}/")
