#!/usr/bin/env python3
"""
WhatZeFact — Pipeline CLI
Generate educational & funny short videos automatically.

Usage:
    python main.py "Pourquoi les chats ont peur des concombres ?"
    python main.py --batch topics.txt
    python main.py "Un fait sur le café" --voice fr-FR-RemyMultilingualNeural
    python main.py --list-voices
"""

import argparse
import json
import sys
import time
import datetime
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from config import validate_config, DEFAULT_VOICE, OUTPUT_DIR, TEMP_DIR
from generators.script_generator import generate_script, print_script, script_to_full_text
from generators.voice_generator import generate_voice_per_segment, list_french_voices
from generators.video_searcher import search_and_download_for_segments
from assembler.video_assembler import assemble_video


def generate_video(
    topic: str,
    voice: str = DEFAULT_VOICE,
    music_path: Path = None,
    no_subtitles: bool = False,
    no_logo: bool = False,
    no_intro: bool = False,
    no_outro: bool = False,
    output_name: str = None,
    skip_confirm: bool = False,
    publish_to: str = None,
    schedule_at: datetime.datetime = None,
) -> Path:
    """
    Full pipeline: topic → finished video.
    
    Returns:
        Path to the generated video file
    """
    start_time = time.time()
    
    print(f"\n{'='*60}")
    print(f"🎬 WhatZeFact — Génération Automatique")
    print(f"{'='*60}")
    print(f"📌 Sujet : {topic}")
    print(f"🎙️ Voix  : {voice}")
    print(f"{'='*60}\n")
    
    # ─── Step 1: Generate Script ─────────────────────────
    print("📝 Étape 1/5 — Génération du script (Gemini Flash)...")
    script = generate_script(topic)
    print_script(script)
    
    # Optional: let user review script
    if not skip_confirm:
        print("👆 Vérifie le script ci-dessus.")
        response = input("   Continuer ? (o/n/modifier) : ").strip().lower()
        if response == "n":
            print("❌ Génération annulée.")
            return None
        elif response == "modifier":
            print("💡 Tu peux modifier le script dans l'interface web (python -m web.app)")
            return None
    
    # ─── Step 2: Generate Voice ──────────────────────────
    print("\n🎙️ Étape 2/5 — Génération de la voix off (Kokoro TTS)...")
    
    # Create a clean temp dir for this video
    video_temp = TEMP_DIR / output_name if output_name else TEMP_DIR / f"video_{int(time.time())}"
    video_temp.mkdir(parents=True, exist_ok=True)
    
    audio_parts = generate_voice_per_segment(
        segments=script["segments"],
        hook=script["hook"],
        loop_bridge=script.get("loop_bridge", script.get("outro_text", "")),
        voice=voice,
        output_dir=video_temp / "audio",
    )
    
    total_audio_duration = sum(p["duration"] for p in audio_parts)
    print(f"  ⏱️  Durée totale voix off : {total_audio_duration:.1f}s")
    
    # ─── Step 3: Search & Download Videos ────────────────
    print("\n🎥 Étape 3/5 — Recherche de vidéos (Pexels)...")
    stock_videos = search_and_download_for_segments(
        segments=script["segments"],
        output_dir=video_temp / "videos",
    )
    
    # ─── Step 4: Assemble Video ──────────────────────────
    print("\n🎬 Étape 4/5 — Assemblage de la vidéo...")
    music = Path(music_path) if music_path else None
    
    output_path = assemble_video(
        script=script,
        audio_parts=audio_parts,
        stock_videos=stock_videos,
        output_name=output_name,
        music_path=music,
        include_logo=not no_logo,
        include_subtitles=not no_subtitles,
        include_intro=not no_intro,
        include_outro=not no_outro,
    )
    
    # ─── Step 5: Summary ─────────────────────────────────
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"✅ VIDÉO GÉNÉRÉE AVEC SUCCÈS !")
    print(f"{'='*60}")
    print(f"📁 Fichier : {output_path}")
    print(f"⏱️  Temps total : {elapsed:.0f}s")
    print(f"#️⃣  Hashtags : {' '.join(script.get('hashtags', []))}")
    print(f"{'='*60}\n")
    
    # Save script as JSON for reference
    script_path = OUTPUT_DIR / f"{output_path.stem}_script.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)
    print(f"📄 Script sauvegardé : {script_path}")
    
    # ─── Step 6: Publish (optional) ───────────────────
    if publish_to == "youtube":
        print("\n📤 Étape 6/6 — Publication YouTube...")
        try:
            from publishers.youtube_publisher import upload_to_youtube
            result = upload_to_youtube(
                video_path=output_path,
                script=script,
                scheduled_at=schedule_at,
            )
            print(f"  ✅ Vidéo uploadée : {result['url']}")
        except Exception as e:
            print(f"  ❌ Erreur upload YouTube : {e}")
    elif schedule_at is not None:
        # Schedule for later without immediate publish
        print("\n📅 Planification de la publication...")
        from publishers.publish_scheduler import add_to_schedule
        add_to_schedule(
            video_path=output_path,
            script=script,
            publish_at=schedule_at,
            platform=publish_to or "youtube",
        )
    
    return output_path


def batch_generate(topics_file: Path, voice: str = DEFAULT_VOICE, **kwargs):
    """Generate videos for multiple topics from a text file (one topic per line)."""
    if not topics_file.exists():
        print(f"❌ Fichier non trouvé : {topics_file}")
        return
    
    with open(topics_file, "r", encoding="utf-8") as f:
        topics = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    print(f"\n🎯 Batch : {len(topics)} vidéos à générer")
    print(f"{'='*60}\n")
    
    results = []
    for i, topic in enumerate(topics, 1):
        print(f"\n📌 [{i}/{len(topics)}] {topic}")
        print(f"{'-'*60}")
        try:
            path = generate_video(
                topic, voice=voice, skip_confirm=True,
                output_name=f"batch_{i:03d}", **kwargs,
            )
            results.append({"topic": topic, "status": "✅", "path": str(path)})
        except Exception as e:
            print(f"  ❌ Erreur : {e}")
            results.append({"topic": topic, "status": "❌", "error": str(e)})
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 RÉSUMÉ BATCH")
    print(f"{'='*60}")
    success = sum(1 for r in results if r["status"] == "✅")
    print(f"  ✅ Réussies : {success}/{len(topics)}")
    for r in results:
        print(f"  {r['status']} {r['topic'][:50]}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="🎬 WhatZeFact — Générateur automatique de vidéos courtes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python main.py "Pourquoi les chats ont peur des concombres ?"
  python main.py --batch topics.txt
  python main.py "Le café" --voice fr-FR-RemyMultilingualNeural --no-music
  python main.py --list-voices
        """,
    )
    
    parser.add_argument(
        "topic",
        nargs="?",
        help="Le sujet/thème de la vidéo",
    )
    parser.add_argument(
        "--batch",
        type=Path,
        help="Fichier texte avec un sujet par ligne",
    )
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help=f"Voix Kokoro TTS (défaut: {DEFAULT_VOICE})",
    )
    parser.add_argument(
        "--music",
        type=Path,
        help="Chemin vers un fichier musique de fond",
    )
    parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Désactiver les sous-titres dynamiques",
    )
    parser.add_argument(
        "--no-logo",
        action="store_true",
        help="Ne pas afficher le logo WhatZeFact",
    )
    parser.add_argument(
        "--no-music",
        action="store_true",
        help="Pas de musique de fond",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Nom du fichier de sortie (sans extension)",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip la confirmation du script",
    )
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Lister les voix françaises disponibles",
    )
    parser.add_argument(
        "--no-intro",
        action="store_true",
        help="Ne pas ajouter l'intro brandée",
    )
    parser.add_argument(
        "--no-outro",
        action="store_true",
        help="Ne pas ajouter l'outro WhatZeFact",
    )
    parser.add_argument(
        "--publish",
        choices=["youtube"],
        help="Publier la vid\u00e9o apr\u00e8s g\u00e9n\u00e9ration (ex: --publish youtube)",
    )
    parser.add_argument(
        "--schedule",
        type=str,
        help="Planifier la publication (format: 'JJ/MM/AAAA HHhMM', ex: '25/07/2026 18h00')",
    )
    parser.add_argument(
        "--publish-pending",
        action="store_true",
        help="Traiter les publications planifi\u00e9es en attente",
    )
    parser.add_argument(
        "--show-schedule",
        action="store_true",
        help="Afficher le planning de publication",
    )
    
    args = parser.parse_args()
    
    # List voices mode
    if args.list_voices:
        print("\n🎙️ Voix françaises disponibles :\n")
        voices = list_french_voices()
        for v in voices:
            gender = "👩" if v.get("Gender") == "Female" else "👨"
            print(f"  {gender} {v['ShortName']}")
            print(f"     {v.get('FriendlyName', '')}")
        return
    
    # Show schedule mode
    if args.show_schedule:
        from publishers.publish_scheduler import print_schedule
        print_schedule()
        return
    
    # Process pending publications
    if args.publish_pending:
        from publishers.publish_scheduler import process_pending
        process_pending()
        return
    
    # Validate config
    errors = validate_config()
    if errors:
        print("\n⚠️  Configuration incomplète :\n")
        for error in errors:
            print(f"  {error}")
        print("\n💡 Édite le fichier .env dans le dossier pipeline/")
        sys.exit(1)
    
    # Batch mode
    if args.batch:
        batch_generate(
            args.batch,
            voice=args.voice,
            music_path=None if args.no_music else args.music,
            no_subtitles=args.no_subtitles,
            no_logo=args.no_logo,
            no_intro=args.no_intro,
            no_outro=args.no_outro,
        )
        return
    
    # Single video mode
    if not args.topic:
        parser.print_help()
        print("\n💡 Exemple : python main.py \"Pourquoi le ciel est bleu ?\"")
        sys.exit(1)
    
    # Parse schedule datetime if provided
    schedule_at = None
    if args.schedule:
        try:
            schedule_at = datetime.datetime.strptime(args.schedule, "%d/%m/%Y %Hh%M")
            print(f"📅 Publication planifiée : {schedule_at.strftime('%d/%m/%Y à %Hh%M')}")
        except ValueError:
            print(f"❌ Format de date invalide : '{args.schedule}'")
            print("💡 Format attendu : 'JJ/MM/AAAA HHhMM' (ex: '25/07/2026 18h00')")
            sys.exit(1)
    
    generate_video(
        topic=args.topic,
        voice=args.voice,
        music_path=None if args.no_music else args.music,
        no_subtitles=args.no_subtitles,
        no_logo=args.no_logo,
        no_intro=args.no_intro,
        no_outro=args.no_outro,
        output_name=args.output,
        skip_confirm=args.yes,
        publish_to=args.publish,
        schedule_at=schedule_at,
    )


if __name__ == "__main__":
    main()
