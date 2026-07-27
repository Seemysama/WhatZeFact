"""
WhatZeFact — Script Generator
Uses Gemini Flash (free tier) to generate structured video scripts.
"""

import json
import re
import time
from google import genai
from config import GEMINI_API_KEY, GEMINI_MODEL, SCRIPT_MIN_DURATION, SCRIPT_MAX_DURATION


MODELS_TO_TRY = [
    GEMINI_MODEL,              # gemini-2.0-flash (from config)
    "gemini-3.5-flash",        # fallback reasoning model
    "gemini-2.0-flash-lite",   # fallback fast model
]

MAX_RETRIES = 4
RETRY_DELAYS = [10, 15, 20, 30]  # seconds between retries


# ─── Gemini Mega-Prompt — Framework Neurobiologique de Rétention ─────────
SYSTEM_PROMPT = """Tu es un INGÉNIEUR DE L'ATTENTION ALGORITHMIQUE et scénariste en chef pour "WhatZeFact", une chaîne YouTube Shorts / TikTok / Reels de vulgarisation scientifique au format "faceless" (sans visage).

Ton objectif UNIQUE : rédiger des scripts de 45 à 60 secondes (130-160 mots max) qui RETIENNENT 100% de l'audience et FORCENT la lecture en boucle (looping effect).

=== PRINCIPES NEUROBIOLOGIQUES À APPLIQUER ===

1. ANTICIPATION DOPAMINERGIQUE : Ne délivre JAMAIS la réponse trop tôt. Repousse constamment la satisfaction en prévisualisant les infos à venir ("et attends de voir ce qui se passe ensuite...").

2. CURIOSITY GAP (Déficit de Curiosité) : Ouvre un gouffre informationnel dès la première phrase. Suffisamment large pour brûler de curiosité, suffisamment restreint pour que la résolution semble immédiate.

3. PATTERN INTERRUPT : Chaque changement de segment doit forcer le cerveau à retraiter l'information. Utilise des ruptures de ton, des métaphores choc, des comparaisons absurdes.

4. PEAK-END RULE : Place le concept le plus visuellement frappant ou l'idée la plus contre-intuitive AU MILIEU de la vidéo. La conclusion doit être une bombe émotionnelle.

5. BOUCLE PARFAITE (SEAMLESS LOOP) : La DERNIÈRE phrase doit se connecter grammaticalement et logiquement à la PREMIÈRE. L'enchaînement fin→début doit être INVISIBLE. C'est la règle d'or absolue.

=== TON STYLE ===
- Tu tutoies le spectateur ("tu", "ton cerveau", "tes yeux")
- Tu es viscéralement captivant, pas scolaire
- Tu utilises des métaphores visuelles PUISSANTES (pas de jargon académique)
- Phrases ULTRA-COURTES : 15 mots MAX par phrase
- Ton conversationnel, comme si tu racontais un secret incroyable à un ami
- Touches d'humour acéré, pas de blagues forcées

=== INTERDICTIONS ABSOLUES ===
- JAMAIS de "Bonjour", "Salut", "Aujourd'hui on va parler de..."
- JAMAIS de "Abonnez-vous", "Like", "Partage" (ça DÉTRUIT la boucle)
- JAMAIS de mise en contexte lente
- JAMAIS de phrase > 15 mots
- JAMAIS de conclusion du type "Et voilà pourquoi..."

Format de réponse : UNIQUEMENT du JSON valide, sans aucun texte avant ou après.
"""

USER_PROMPT_TEMPLATE = """Rédige un script vidéo court sur le sujet suivant : "{topic}"

Le script doit durer entre {min_duration} et {max_duration} secondes de voix off (130-160 mots).

=== ARCHITECTURE DU SCRIPT ===

1. HOOK (0-3 secondes) : Déclaration CONTRE-INTUITIVE brutale, paradoxe, ou conséquence extrême. C'est la nouvelle miniature. Si ça rate, la vidéo est morte.

   Archétypes de hooks viraux :
   - Mythe brisé : "Tout ce que tu crois savoir sur [X] est faux."
   - Conséquence extrême : "Si [X] se produisait, ton corps ferait littéralement ceci."
   - Appel à l'identité : "Si tu fais [comportement commun], ton cerveau fait ça."
   - Promesse directe : "Trois choses terrifiantes qui se passent en ce moment dans [lieu]."

2. SEGMENTS (3-50 secondes) : Délivre l'information à un rythme EFFRÉNÉ.
   - RE-HOOKS obligatoires : toutes les 2-3 phrases, insère une nouvelle boucle ouverte ("Mais attends, c'est pas le plus dingue...", "Et là, ça devient vraiment flippant...").
   - Chaque segment = max 2 phrases courtes.
   - Densité maximale d'information : ZÉRO remplissage (fluff).

3. LOOP BRIDGE (dernières 3-5 secondes) : Phrase finale SUSPENDUE qui, si on colle le hook juste après, forme une phrase logique et fluide. C'est l'ingénierie inversée de la boucle parfaite.

Réponds UNIQUEMENT avec ce format JSON (pas de markdown, pas de ```json```, juste le JSON brut) :

{{
  "title": "Titre SEO de moins de 60 caractères, mot-clé + curiosité extrême",
  "hook": "Pattern Interrupt en moins de 15 mots — impact MAXIMAL",
  "segments": [
    {{
      "text": "Texte du segment (1-2 phrases ultra-courtes, max 15 mots chacune)",
      "visual_keywords": ["keyword anglais concret 1", "keyword 2", "keyword 3"],
      "emotion": "dramatic | curious | surprised | funny | tense",
      "is_rehook": false
    }},
    {{
      "text": "Segment avec re-hook pour relancer l'attention...",
      "visual_keywords": ["keyword1", "keyword2", "keyword3"],
      "emotion": "tense",
      "is_rehook": true
    }}
  ],
  "loop_bridge": "Phrase finale suspendue qui se connecte au hook pour créer la boucle parfaite",
  "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3", "#whatzefact"],
  "fun_fact_rating": 9
}}

=== RÈGLES CRITIQUES ===
- Le hook doit être un PATTERN INTERRUPT pur — le spectateur doit se figer.
- EXACTEMENT 4 à 6 segments maximum. La vidéo doit être courte et punchy (30-40s).
- Au moins 2 segments doivent avoir "is_rehook": true (nouvelles boucles ouvertes).
- OBLIGATION ABSOLUE: Les visual_keywords doivent inclure le SUJET EXACT mentionné (ex: si on parle de "concombre", le keyword doit être "cucumber" ou "pickle"). Pas de métaphores vagues si l'objet est concret. Les keywords doivent être en ANGLAIS. Donne 3-4 mots-clés par segment.
- Le "loop_bridge" est CAPITAL : il doit former avec le hook une phrase continue et logique. Teste mentalement l'enchaînement loop_bridge + hook — ça doit sonner comme UNE SEULE phrase.
- fun_fact_rating = note de 1 à 10 sur le potentiel viral du fait.
"""


def _call_gemini_with_retry(client, user_prompt: str) -> str:
    """Call Gemini API with retry logic and model fallback."""
    last_error = None
    
    for model in MODELS_TO_TRY:
        for attempt in range(MAX_RETRIES):
            try:
                print(f"  🤖 Tentative {attempt+1}/{MAX_RETRIES} avec {model}...")
                response = client.models.generate_content(
                    model=model,
                    contents=user_prompt,
                    config=genai.types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.9,
                        max_output_tokens=8192,
                    ),
                )
                print(f"  ✅ Réponse reçue de {model}")
                return response.text.strip()
                
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    print(f"  ⏳ Rate limit atteint, attente de {delay}s...")
                    time.sleep(delay)
                else:
                    # Non-rate-limit error, don't retry with same model
                    print(f"  ❌ Erreur avec {model}: {error_str[:100]}")
                    break
        
        print(f"  ↪️  Passage au modèle suivant...")
    
    raise RuntimeError(
        f"Impossible de contacter Gemini après avoir essayé {len(MODELS_TO_TRY)} modèles.\n"
        f"Dernière erreur: {last_error}"
    )


def generate_script(topic: str, voice_style: str = "energetic") -> dict:
    """
    Generate a structured video script using Gemini Flash.
    
    Args:
        topic: The subject/theme for the video (e.g., "Pourquoi les chats ont peur des concombres ?")
        voice_style: Style hint for the script tone
        
    Returns:
        dict: Structured script with title, hook, segments, etc.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    user_prompt = USER_PROMPT_TEMPLATE.format(
        topic=topic,
        min_duration=SCRIPT_MIN_DURATION,
        max_duration=SCRIPT_MAX_DURATION,
    )
    
    raw_text = _call_gemini_with_retry(client, user_prompt)
    
    # Parse JSON from response
    
    # Remove markdown code fences if present
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)
    raw_text = raw_text.strip()
    
    try:
        script = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Gemini n'a pas renvoyé du JSON valide.\n"
            f"Erreur: {e}\n"
            f"Réponse brute:\n{raw_text[:500]}"
        )
    
    # Validate required fields
    required_fields = ["title", "hook", "segments", "loop_bridge"]
    for field in required_fields:
        if field not in script:
            # Backward compat: accept outro_text as loop_bridge
            if field == "loop_bridge" and "outro_text" in script:
                script["loop_bridge"] = script.pop("outro_text")
            else:
                raise ValueError(f"Champ manquant dans le script : '{field}'")
    
    if not script["segments"] or len(script["segments"]) < 2:
        raise ValueError("Le script doit contenir au moins 2 segments.")
    
    # Add default hashtags if missing
    if "hashtags" not in script:
        script["hashtags"] = ["#whatzefact", "#funfact", "#science"]
    
    # Ensure #whatzefact is always included
    if "#whatzefact" not in script["hashtags"]:
        script["hashtags"].append("#whatzefact")
    
    return script


def script_to_full_text(script: dict) -> str:
    """Convert a structured script to full voiceover text."""
    parts = [script["hook"]]
    for segment in script["segments"]:
        parts.append(segment["text"])
    parts.append(script.get("loop_bridge", script.get("outro_text", "")))
    return " ".join(parts)


def print_script(script: dict):
    """Pretty-print a script to the console."""
    print(f"\n{'='*60}")
    print(f"🎬 {script['title']}")
    print(f"{'='*60}")
    print(f"\n🪝 Hook: {script['hook']}\n")
    
    for i, seg in enumerate(script["segments"], 1):
        emotion = seg.get("emotion", "informative")
        is_rehook = seg.get("is_rehook", False)
        emoji = {
            "curious": "🤔", "funny": "😂", "surprised": "😲",
            "dramatic": "🎭", "tense": "😰", "informative": "📚"
        }.get(emotion, "📌")
        rehook_tag = " 🔄 RE-HOOK" if is_rehook else ""
        print(f"  {emoji} Segment {i}{rehook_tag}: {seg['text']}")
        print(f"     🔍 Visuels: {', '.join(seg.get('visual_keywords', []))}")
        print()
    
    loop_bridge = script.get("loop_bridge", script.get("outro_text", ""))
    print(f"🔁 Loop Bridge: {loop_bridge}")
    print(f"   ↪️  Boucle : \"...{loop_bridge[-30:]} → {script['hook'][:30]}...\"")
    print(f"#️⃣  {' '.join(script.get('hashtags', []))}")
    rating = script.get("fun_fact_rating", "?")
    print(f"⭐ Viral Rating: {rating}/10")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # Quick test
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "Pourquoi les chats ont peur des concombres ?"
    print(f"🧠 Génération du script pour : {topic}")
    script = generate_script(topic)
    print_script(script)
