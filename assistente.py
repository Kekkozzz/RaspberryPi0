import os
import re
import time
import json
import socket
import threading
import subprocess
import pvporcupine
import pyaudio
import struct
import wave
import numpy as np
import requests
from datetime import datetime
from google import genai
from groq import Groq
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
SECONDI_REGISTRAZIONE_MAX = 20  # limite massimo di sicurezza
SOGLIA_SILENZIO = 200           # RMS energy: sotto = silenzio (regola se il mic è rumoroso)
SECONDI_SILENZIO_STOP = 0.8     # secondi di silenzio consecutivi per fermare la registrazione
SECONDI_MIN_REGISTRAZIONE = 0.5 # registra almeno questa durata prima di controllare il silenzio
CITTA_METEO = "Roma"
MPV_SOCKET = "/tmp/mpvsocket"
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
groq_client = Groq(api_key=os.environ['GROQ_API_KEY'])
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

WHISPER_PROMPT = (
    "Raspy, Modà, Måneskin, Spotify, YouTube, playlist, "
    "Ed Sheeran, Coldplay, Adele, Drake, Taylor Swift, "
    "Ultimo, Blanco, Annalisa, Elodie, Geolier, Sfera Ebbasta, Shiva "
    "timer, meteo, volume, stop, pausa, riprendi, basta, ferma"
)

def trascrivi(filepath='/tmp/input.wav'):
    with open(filepath, 'rb') as f:
        transcription = groq_client.audio.transcriptions.create(
            file=(filepath, f),
            model="whisper-large-v3-turbo",
            language="it",
            response_format="text",
            prompt=WHISPER_PROMPT
        )
    return transcription.strip()

def parla(testo):
    from gtts import gTTS
    tts = gTTS(text=testo, lang='it', slow=False)
    tts.save('/tmp/risposta.mp3')
    subprocess.run(['mpg123', '-q', '/tmp/risposta.mp3'], capture_output=True)
    os.remove('/tmp/risposta.mp3')

def get_orario():
    now = datetime.now()
    giorni = ["lunedì","martedì","mercoledì","giovedì","venerdì","sabato","domenica"]
    mesi = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
            "luglio","agosto","settembre","ottobre","novembre","dicembre"]
    return (f"Sono le {now.hour} e {now.minute}. "
            f"Oggi è {giorni[now.weekday()]} {now.day} {mesi[now.month-1]} {now.year}.")

_WMO = {
    0:"cielo sereno", 1:"poco nuvoloso", 2:"parzialmente nuvoloso", 3:"nuvoloso",
    45:"nebbia", 48:"nebbia gelata",
    51:"pioggerella", 61:"pioggia leggera", 63:"pioggia moderata", 65:"pioggia forte",
    71:"neve leggera", 73:"neve moderata", 75:"neve forte",
    80:"rovesci", 81:"rovesci moderati", 82:"rovesci forti",
    95:"temporale", 96:"temporale con grandine", 99:"temporale forte"
}

def get_meteo(citta=CITTA_METEO):
    geo = requests.get(
        f"https://geocoding-api.open-meteo.com/v1/search?name={citta}&count=1&language=it",
        timeout=5).json()
    lat = geo['results'][0]['latitude']
    lon = geo['results'][0]['longitude']
    w = requests.get(
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weathercode,windspeed_10m&timezone=Europe/Rome",
        timeout=5).json()['current']
    desc = _WMO.get(w['weathercode'], "condizioni variabili")
    return (f"A {citta} ci sono {w['temperature_2m']}°C, {desc}. "
            f"Vento a {w['windspeed_10m']} km/h.")

def parse_timer(testo):
    for pattern, mult in [(r'(\d+)\s*or[ae]', 3600),
                          (r'(\d+)\s*minut[oi]', 60),
                          (r'(\d+)\s*second[oi]', 1)]:
        m = re.search(pattern, testo.lower())
        if m:
            return int(m.group(1)) * mult
    return None

def avvia_timer(secondi):
    def _run():
        time.sleep(secondi)
        parla("Il timer è scaduto!")
    threading.Thread(target=_run, daemon=True).start()

_mpv_proc = None

def _mpv_command(cmd):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(MPV_SOCKET)
        s.send(json.dumps({"command": cmd}).encode() + b'\n')
        s.close()
    except:
        pass

def musica_in_riproduzione():
    return _mpv_proc is not None and _mpv_proc.poll() is None

def musica_play(query):
    global _mpv_proc
    musica_stop()
    _mpv_proc = subprocess.Popen(
        ['mpv', '--no-video', '--really-quiet',
         f'--input-ipc-server={MPV_SOCKET}',
         f'ytdl://ytsearch1:{query}'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

def musica_pausa():
    _mpv_command(["cycle", "pause"])

def musica_stop():
    global _mpv_proc
    if _mpv_proc:
        _mpv_proc.terminate()
        _mpv_proc = None
    try:
        os.remove(MPV_SOCKET)
    except:
        pass

def musica_volume(direzione):
    delta = 10 if direzione == "su" else -10
    _mpv_command(["add", "volume", delta])

def gestisci_comando(testo):
    tl = testo.lower()
    if any(w in tl for w in ["che ore", "che giorno", "orario", "data di oggi"]):
        return get_orario()
    if any(w in tl for w in ["meteo", "che tempo", "temperatura", "previsioni"]):
        m = re.search(r'\ba\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)', testo)
        citta = m.group(1) if m else CITTA_METEO
        return get_meteo(citta)
    if "timer" in tl:
        secondi = parse_timer(testo)
        if secondi:
            avvia_timer(secondi)
            m, s = divmod(secondi, 60)
            parti = []
            if m: parti.append(f"{m} minut{'o' if m==1 else 'i'}")
            if s: parti.append(f"{s} second{'o' if s==1 else 'i'}")
            return f"Timer avviato per {' e '.join(parti)}!"
    # ── Musica ──
    m = re.search(r'(?:metti|riproduci|suona|fammi sentire)\s+(.+)', tl)
    if m:
        query = m.group(1)
        musica_play(query)
        return f"Cerco e riproduco: {query}"
    if any(w in tl for w in ["pausa", "metti in pausa"]):
        musica_pausa()
        return "Musica in pausa."
    if any(w in tl for w in ["riprendi", "continua"]):
        musica_pausa()
        return "Riprendo la musica."
    if any(w in tl for w in ["stop musica", "ferma musica", "basta musica", "spegni musica",
                              "stop", "basta", "ferma", "fermati", "smetti"]):
        musica_stop()
        return "Musica fermata."
    if any(w in tl for w in ["volume su", "alza volume", "più forte"]):
        musica_volume("su")
        return "Volume alzato."
    if any(w in tl for w in ["volume giù", "abbassa volume", "più piano"]):
        musica_volume("giù")
        return "Volume abbassato."
    return None

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

            # Pausa musica durante interazione
            musica_era_attiva = musica_in_riproduzione()
            if musica_era_attiva:
                musica_pausa()

            stream.stop_stream()
            stream.close()

            parla("Dimmi!")

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
                risposta = gestisci_comando(testo) or chiedi_gemini(testo)
                print(f"💬 {NOME_ASSISTENTE}: {risposta}\n")
                display.set_stato("RISPOSTA", risposta)
                parla(risposta)

            # Riprendi musica se era in riproduzione e non è stata fermata
            if musica_era_attiva and musica_in_riproduzione():
                musica_pausa()

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
