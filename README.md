# Jarvis

Linux voice assistant. Say **Hey Jarvis**, then a command. The wake word runs locally. One Gemini Live session hears you, speaks the reply, and can search the web or control music. Playback goes through a headless `mpv`.

Jarvis answers in the language you speak: English or Hungarian.

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

From the project directory, with the virtualenv activated:

```bash
source .venv/bin/activate
python3 main.py
```

`python3 -m jarvis` does the same thing.

When the terminal prints `listening`, the microphone is open. Say **Hey Jarvis**, wait for the beep, then speak. Examples:

- “Play Get Lucky by Daft Punk”
- “Pause” / “Resume” / “Stop” / “Play another version”
- “What’s the weather in London?”
- “Milyen az idő Londonban?”

Jarvis ducks music to 15% while you talk, speaks the reply, then restores volume to 100%. Press `Ctrl+C` to quit. `mpv` shuts down with it.

## Commands

After **Hey Jarvis**:

| You say | What happens |
|---|---|
| play [song] | search for the official studio track and stream it |
| another version | next official match for the current song |
| pause / resume | hold or continue the current track |
| stop | end the song |
| a factual question | Google Search, then a spoken answer under 20 seconds |

The same commands work in Hungarian. `mpv` stays running in the background so you can wake Jarvis again during a song.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | unset | Gemini API key |
| `GEMINI_API_KEY` | unset | fallback key name |
| `GEMINI_MODEL` | `gemini-3.8-live` | live session: speech in, speech out, search, music tool |

`.env` is loaded automatically and is gitignored.

## Layout

```
main.py                 entry
jarvis/config.py        constants and env
jarvis/runtime.py       wake loop
jarvis/audio/           mic, wake word, speaker, mpv
jarvis/media/           YouTube resolver
jarvis/intent/          music tool
jarvis/llm/             Gemini Live session
```
