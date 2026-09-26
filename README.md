# Jarvis

Linux voice assistant. Say **Hey Jarvis**, then a command. Wake word runs locally. Speech goes to Gemini. Music plays through `mpv`.

## Requirements

- Ubuntu (or similar)
- Python 3.12
- Microphone and speakers
- `mpv`, PortAudio, ffmpeg

```bash
sudo apt install portaudio19-dev mpv ffmpeg python3-venv python3-dev
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey):

```
GOOGLE_API_KEY=your-key
```

`GEMINI_API_KEY` is an alternative to `GOOGLE_API_KEY`. Only one is required.

## Run

```bash
source .venv/bin/activate
python3 main.py
```

Or `python3 -m jarvis`.

## Commands

After **Hey Jarvis**:

| You say | What happens |
|---|---|
| play [song] | search YouTube and stream audio |
| another version | next YouTube result |
| add [song] to my [list] | store title and link in memory |
| pause / resume / stop | control the current track |
| jump 21 seconds | seek forward (or back with a negative number) |

Music ducks while you speak, then volume returns. Playback stays in the background so you can wake Jarvis again during a song.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | unset | Gemini API key |
| `GEMINI_API_KEY` | unset | fallback key name |
| `GEMINI_MODEL` | `gemini-3.1-flash-live-preview` | live microphone session |
| `JSON_MODEL` | `gemini-2.5-flash` | intent JSON (`play_music`, pause, seek, …) |

`.env` is loaded automatically and is gitignored.

## Layout

```
main.py                 entry
jarvis/config.py        constants and env
jarvis/runtime.py       wake loop
jarvis/audio/           mic, wake word, TTS, mpv
jarvis/media/           YouTube, playlists
jarvis/intent/          parse and execute actions
jarvis/llm/             live session and text routing
```
