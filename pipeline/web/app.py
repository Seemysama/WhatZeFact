"""
WhatZeFact — Web Interface
Local Flask app for interactive video generation with live preview.
"""

import json
import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from flask_socketio import SocketIO, emit

from config import validate_config, DEFAULT_VOICE, OUTPUT_DIR, TEMP_DIR
from generators.script_generator import generate_script, script_to_full_text
from generators.voice_generator import generate_voice_per_segment, list_french_voices
from generators.video_searcher import search_and_download_for_segments
from assembler.video_assembler import assemble_video

app = Flask(__name__)
app.config["SECRET_KEY"] = "whatzefact-local-dev"
socketio = SocketIO(app, cors_allowed_origins="*")

# Track generation state
generation_state = {
    "is_generating": False,
    "current_step": "",
    "progress": 0,
    "script": None,
    "last_video_path": None,
}


def emit_progress(step: str, progress: int, message: str = ""):
    """Send progress update to the frontend."""
    generation_state["current_step"] = step
    generation_state["progress"] = progress
    socketio.emit("progress", {
        "step": step,
        "progress": progress,
        "message": message,
    })


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/voices")
def api_voices():
    """Get available French voices."""
    voices = list_french_voices()
    return jsonify([{
        "id": v["ShortName"],
        "name": v.get("FriendlyName", v["ShortName"]),
        "gender": v.get("Gender", "Unknown"),
    } for v in voices])


@app.route("/api/config-status")
def api_config_status():
    """Check if API keys are configured."""
    errors = validate_config()
    return jsonify({
        "configured": len(errors) == 0,
        "errors": errors,
    })


@app.route("/api/generate-script", methods=["POST"])
def api_generate_script():
    """Generate a script from a topic."""
    data = request.json
    topic = data.get("topic", "")
    
    if not topic:
        return jsonify({"error": "Le sujet est requis"}), 400
    
    errors = validate_config()
    if errors:
        return jsonify({"error": errors[0]}), 400
    
    try:
        script = generate_script(topic)
        generation_state["script"] = script
        return jsonify({"script": script})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-video", methods=["POST"])
def api_generate_video():
    """Start full video generation (async via WebSocket)."""
    if generation_state["is_generating"]:
        return jsonify({"error": "Une génération est déjà en cours"}), 409
    
    data = request.json
    script = data.get("script")
    voice = data.get("voice", DEFAULT_VOICE)
    include_subtitles = data.get("subtitles", True)
    include_logo = data.get("logo", True)
    include_intro = data.get("intro", True)
    include_outro = data.get("outro", True)
    
    if not script:
        return jsonify({"error": "Le script est requis"}), 400
    
    # Start generation in background thread
    thread = threading.Thread(
        target=_generate_video_worker,
        args=(script, voice, include_subtitles, include_logo, include_intro, include_outro),
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})


def _generate_video_worker(script, voice, include_subtitles, include_logo, include_intro, include_outro):
    """Background worker for video generation."""
    generation_state["is_generating"] = True
    
    try:
        video_id = f"video_{int(time.time())}"
        video_temp = TEMP_DIR / video_id
        video_temp.mkdir(parents=True, exist_ok=True)
        
        # Step 1: Voice generation
        emit_progress("voice", 10, "Génération de la voix off...")
        audio_parts = generate_voice_per_segment(
            segments=script["segments"],
            hook=script["hook"],
            loop_bridge=script.get("loop_bridge", script.get("outro_text", "")),
            voice=voice,
            output_dir=video_temp / "audio",
        )
        
        # Step 2: Video search
        emit_progress("search", 30, "Recherche de vidéos d'illustration...")
        stock_videos = search_and_download_for_segments(
            segments=script["segments"],
            output_dir=video_temp / "videos",
        )
        
        # Step 3: Assembly
        emit_progress("assemble", 60, "Montage de la vidéo...")
        output_path = assemble_video(
            script=script,
            audio_parts=audio_parts,
            stock_videos=stock_videos,
            output_name=video_id,
            include_logo=include_logo,
            include_subtitles=include_subtitles,
            include_intro=include_intro,
            include_outro=include_outro,
        )
        
        generation_state["last_video_path"] = str(output_path)
        
        # Save script
        script_path = OUTPUT_DIR / f"{video_id}_script.json"
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
        
        emit_progress("done", 100, "Vidéo générée avec succès !")
        socketio.emit("video_ready", {
            "path": str(output_path),
            "filename": output_path.name,
        })
        
    except Exception as e:
        emit_progress("error", 0, f"Erreur : {str(e)}")
        socketio.emit("error", {"message": str(e)})
    
    finally:
        generation_state["is_generating"] = False


@app.route("/api/download/<filename>")
def download_video(filename):
    """Download a generated video."""
    return send_from_directory(str(OUTPUT_DIR), filename, as_attachment=True)


@app.route("/api/preview/<filename>")
def preview_video(filename):
    """Stream a generated video for preview."""
    return send_from_directory(str(OUTPUT_DIR), filename)


@app.route("/api/videos")
def list_videos():
    """List all generated videos."""
    videos = []
    for f in sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        script_file = f.with_name(f"{f.stem}_script.json")
        script_data = None
        if script_file.exists():
            with open(script_file, encoding="utf-8") as sf:
                script_data = json.load(sf)
        
        videos.append({
            "filename": f.name,
            "size_mb": round(stat.st_size / (1024 * 1024), 1),
            "created": stat.st_mtime,
            "title": script_data.get("title", f.stem) if script_data else f.stem,
        })
    
    return jsonify(videos)


@app.route("/api/youtube/status")
def youtube_status():
    """Check YouTube authentication status."""
    try:
        from publishers.youtube_publisher import check_youtube_auth
        status = check_youtube_auth()
        return jsonify(status)
    except ImportError:
        return jsonify({"error": "Module YouTube non installé"}), 500


@app.route("/api/youtube/publish", methods=["POST"])
def youtube_publish():
    """Publish a video to YouTube."""
    data = request.json
    filename = data.get("filename")
    privacy = data.get("privacy", "private")
    
    if not filename:
        return jsonify({"error": "Le nom de fichier est requis"}), 400
    
    video_path = OUTPUT_DIR / filename
    if not video_path.exists():
        return jsonify({"error": f"Vidéo non trouvée: {filename}"}), 404
    
    # Load script
    script = {}
    script_file = video_path.with_name(f"{video_path.stem}_script.json")
    if script_file.exists():
        with open(script_file, encoding="utf-8") as f:
            script = json.load(f)
    
    try:
        from publishers.youtube_publisher import upload_to_youtube
        result = upload_to_youtube(
            video_path=video_path,
            script=script,
            privacy=privacy,
        )
        return jsonify(result)
    except FileNotFoundError as e:
        return jsonify({"error": str(e), "setup_required": True}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedule")
def get_schedule():
    """Get the publish schedule."""
    try:
        from publishers.publish_scheduler import list_schedule
        return jsonify(list_schedule())
    except ImportError:
        return jsonify([])



if __name__ == "__main__":
    print("\n🎬 WhatZeFact — Interface Web")
    print("   Ouvre http://localhost:5555 dans ton navigateur\n")
    socketio.run(app, host="0.0.0.0", port=5555, debug=True, allow_unsafe_werkzeug=True)
