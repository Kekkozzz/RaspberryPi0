import os
import time
import pvporcupine
import pyaudio
import struct
import wave
import numpy as np
from google import genai
import ctypes
from display import RaspyDisplay

# Sopprimi warning ALSA/JACK
ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
def py_error_handler(filename, line, function, err, fmt): pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
try:
    asound = ctypes.cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except:
    pass

# ─── CONFIGURAZIONE ───────────────────────────────────────
NOME_ASSISTENTE = "Raspy"
LINGUA = "it"
MODELLO_GEMINI = "gemini-2.5-flash"
SECONDI_REGISTRAZIONE_MAX = 30  # limite massimo di sicurezza
SOGLIA_SILENZIO = 500           # RMS energy: sotto = silenzio (regola se il mic è rumoroso)
SECONDI_SILENZIO_STOP = 0.8     # secondi di silenzio consecutivi per fermare la registrazione
SECONDI_MIN_REGISTRAZIONE = 0.5 # registra almeno questa durata prima di controllare il silenzio
PPn_PATH = os.path.expanduser("~/assistente/raspi_it_raspberry-pi_v4_0_0.ppn")
MODEL_PATH = os.path.expanduser("~/assistente/porcupine_params_it.pv")

SYSTEM_PROMPT = f"""Sei {NOME_ASSISTENTE}, un assistente vocale intelligente e amichevole
che gira su un Raspberry Pi 5. Sei stato creato da Francesco, uno sviluppatore italiano.
Rispondi sempre in italiano, in modo breve, naturale e conversazionale.
Evita elenchi e formattazione — parla come in una conversazione normale.
Ricordi il contesto della conversazione e puoi fare riferimento a cose dette in precedenza."""

# ─── INIZIALIZZAZIONE ─────────────────────────────────────
display = RaspyDisplay(NOME_ASSISTENTE)
display.set_stato("CARICAMENTO")
display.start()

client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
cronologia = []
print(f"✅ {NOME_ASSISTENTE} è pronta!")

# ─── FUNZIONI ─────────────────────────────────────────────
def registra_audio(pa, filepath='/tmp/input.wav'):
    CHUNK = 1024
    RATE = 44100
    frames_max = int(RATE / CHUNK * SECONDI_REGISTRAZIONE_MAX)
    frames_min = int(RATE / CHUNK * SECONDI_MIN_REGISTRAZIONE)
    frames_silenzio = int(RATE / CHUNK * SECONDI_SILENZIO_STOP)

    s = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=RATE,
        input=True,
        input_device_index=1,
        frames_per_buffer=CHUNK
    )
    frames = []
    silent_count = 0
    for i in range(frames_max):
        data = s.read(CHUNK, exception_on_overflow=False)
        frames.append(data)
        if i >= frames_min:
            rms = np.sqrt(np.mean(np.frombuffer(data, dtype=np.int16).astype(np.float32) ** 2))
            if rms < SOGLIA_SILENZIO:
                silent_count += 1
                if silent_count >= frames_silenzio:
                    break
            else:
                silent_count = 0
    s.stop_stream()
    s.close()
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

def trascrivi(filepath='/tmp/input.wav'):
    from google.genai import types
    with open(filepath, 'rb') as f:
        audio_bytes = f.read()
    response = client.models.generate_content(
        model=MODELLO_GEMINI,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type='audio/wav'),
            "Trascrivi esattamente quello che viene detto in questo audio in italiano. "
            "Rispondi solo con la trascrizione, senza aggiungere altro.",
        ]
    )
    return response.text.strip()

def parla(testo):
    from gtts import gTTS
    import subprocess
    tts = gTTS(text=testo, lang='it', slow=False)
    tts.save('/tmp/risposta.mp3')
    subprocess.run(['mpg123', '-q', '/tmp/risposta.mp3'], capture_output=True)
    os.remove('/tmp/risposta.mp3')

def chiedi_gemini(testo):
    global cronologia
    cronologia.append(f"Utente: {testo}")
    contesto = "\n".join(cronologia[-10:])
    response = client.models.generate_content(
        model=MODELLO_GEMINI,
        contents=f"{SYSTEM_PROMPT}\n\nCronologia:\n{contesto}\n\nRispondi solo come {NOME_ASSISTENTE}:"
    )
    risposta = response.text.strip()
    cronologia.append(f"{NOME_ASSISTENTE}: {risposta}")
    return risposta

# ─── LOOP PRINCIPALE CON PORCUPINE ────────────────────────
porcupine = pvporcupine.create(
    access_key=os.environ['PORCUPINE_KEY'],
    keyword_paths=[PPn_PATH],
    model_path=MODEL_PATH
)

# Sopprimi stderr PortAudio/JACK durante init PyAudio
_devnull_fd = os.open(os.devnull, os.O_WRONLY)
_old_stderr = os.dup(2)
os.dup2(_devnull_fd, 2)
pa = pyaudio.PyAudio()
os.dup2(_old_stderr, 2)
os.close(_old_stderr)
os.close(_devnull_fd)

NATIVE_RATE = 44100
PORCUPINE_RATE = porcupine.sample_rate
FRAMES_NATIVE = int(porcupine.frame_length * NATIVE_RATE / PORCUPINE_RATE)

# Precomputa indici resampling (costanti)
resample_x = np.linspace(0, FRAMES_NATIVE, porcupine.frame_length)
resample_xp = np.arange(FRAMES_NATIVE)

stream = pa.open(
    rate=NATIVE_RATE,
    channels=1,
    format=pyaudio.paInt16,
    input=True,
    input_device_index=1,
    frames_per_buffer=FRAMES_NATIVE
)

print(f"\n👂 In ascolto... di' '{NOME_ASSISTENTE}' per attivare.")
print("   (CTRL+C per uscire)\n")
display.set_stato("ASCOLTO")

try:
    while True:
        pcm_raw = stream.read(FRAMES_NATIVE, exception_on_overflow=False)
        pcm_np = np.frombuffer(pcm_raw, dtype=np.int16).astype(np.float32)
        pcm_resampled = np.interp(resample_x, resample_xp, pcm_np).astype(np.int16)
        pcm = struct.unpack_from("h" * porcupine.frame_length, pcm_resampled.tobytes())

        if porcupine.process(pcm) >= 0:
            print(f"✅ Wake word rilevata!")
            print(f"🎙️  Parla ora (mi fermo quando smetti)...")
            display.set_stato("WAKE")

            stream.stop_stream()
            stream.close()

            display.set_stato("REGISTRAZIONE")
            registra_audio(pa)

            display.set_stato("TRASCRIZIONE")
            testo = trascrivi()

            if testo and len(testo) > 2:
                print(f"📝 Hai detto: {testo}")
                display.set_stato("HAI_DETTO", testo)
                time.sleep(1.5)

                print(f"🤖 {NOME_ASSISTENTE} sta pensando...")
                display.set_stato("PENSANDO")
                risposta = chiedi_gemini(testo)
                print(f"💬 {NOME_ASSISTENTE}: {risposta}\n")
                display.set_stato("RISPOSTA", risposta)
                parla(risposta)

            stream = pa.open(
                rate=NATIVE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                input_device_index=1,
                frames_per_buffer=FRAMES_NATIVE
            )
            print(f"👂 In ascolto... di' '{NOME_ASSISTENTE}' per attivare.")
            display.set_stato("ASCOLTO")

except KeyboardInterrupt:
    print(f"\n👋 {NOME_ASSISTENTE} spenta. Arrivederci!")
    display.set_stato("SPENTA")
    time.sleep(1.5)
finally:
    display.cleanup()
    stream.close()
    pa.terminate()
    porcupine.delete()
