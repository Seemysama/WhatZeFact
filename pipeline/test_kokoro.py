import soundfile as sf
from kokoro_onnx import Kokoro
import time
import os

print("Chargement de Kokoro TTS...")
model_path = "kokoro_models/kokoro-v1.0.onnx"
voices_path = "kokoro_models/voices-v1.0.bin"

start = time.time()
kokoro = Kokoro(model_path, voices_path)
print(f"Modèle chargé en {time.time() - start:.2f}s")

print("Génération de l'audio...")
# La voix française s'appelle ff_siwis
text = "Salut tout le monde. Ceci est un test de la nouvelle voix française avec Kokoro T T S."
audio, sample_rate = kokoro.create(text, voice="ff_siwis", speed=1.0, lang="fr-fr")

sf.write("test_kokoro.wav", audio, sample_rate)
print(f"✅ Audio généré ! test_kokoro.wav ({len(audio)/sample_rate:.1f}s d'audio)")
