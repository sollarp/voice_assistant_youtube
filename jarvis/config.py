import os
import tempfile

from dotenv import load_dotenv
import pyaudio

load_dotenv()

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1280

WAKE_MODEL = "hey_jarvis"
WAKE_THRESHOLD = 0.5
PCM_MIME = "audio/pcm;rate=16000"

SILENCE_RMS_THRESHOLD = 450.0
MIN_SPEECH_CHUNKS = int(0.35 * RATE / CHUNK)
SILENCE_CHUNKS = int(0.85 * RATE / CHUNK)
MAX_UTTERANCE_CHUNKS = int(8 * RATE / CHUNK)
NO_SPEECH_CHUNKS = int(1.6 * RATE / CHUNK)
TRANSCRIPT_TIMEOUT = 5.0

LIVE_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-live-preview")
JSON_MODEL = os.environ.get("JSON_MODEL", "gemini-2.5-flash")
LIVE_MODELS = [
    LIVE_MODEL,
    "gemini-3.1-flash-live-preview",
    "gemini-2.5-flash-native-audio-preview-12-2025",
]

MPV_IPC_PATH = os.path.join(tempfile.gettempdir(), "jarvis-mpv.sock")
MUSIC_VOLUME_NORMAL = 100
MUSIC_VOLUME_DUCKED = 12
SEEK_SECONDS_DEFAULT = 21

MUSIC_CONTROL_ACTIONS = frozenset({
    "pause_music",
    "resume_music",
    "stop_music",
    "seek_music",
})
