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

When the terminal prints `listening`, the microphone is open. Say **Hey Jarvis**, wait for the beep, then speak. Music ducks while you talk, then returns to the volume you set. Press `Ctrl+C` to quit. `mpv` shuts down with it.

## Commands

Say **Hey Jarvis**, then a command in English or Hungarian.

| English | Hungarian | What happens |
|---|---|---|
| Play [song] | Játszd le [dal] | Plays a saved song if it is in history or a playlist. Otherwise searches YouTube once and remembers it. |
| Another version | Másik verzió | Plays the next official recording of the current song. |
| Pause | Szünet | Holds the song. |
| Resume | Folytasd | Continues the song. |
| Stop | Állj | Ends the song and clears a queued playlist. |
| Create a playlist called [name] | Készíts egy [név] lejátszási listát | Creates an empty named playlist. |
| Add this song to my playlist [name] | Add hozzá ezt a dalt a [név] listához | Saves the song that is playing. |
| Play my playlist [name] | Játszd le a [név] listámat | Asks whether to play in order or at random. |
| Play my playlist [name] in order | Játszd le a [név] listámat sorban | Plays that playlist from first to last. |
| Play my playlist [name] in random | Játszd le a [név] listámat keverve | Plays that playlist in random order. |
| Volume up | Hangerő fel | Raises the volume by 2 steps. |
| Volume down | Hangerő le | Lowers the volume by 2 steps. |
| Set volume to [1–10] | Hangerő [1–10] | Sets the volume. 10 is the loudest. |
| Delete this song | Töröld ezt a dalt | Removes the playing song from history and every playlist. |
| Delete the playlist called [name] | Töröld a [név] lejátszási listát | Deletes that playlist. |
| What playlists do you have? | Milyen lejátszási listáid vannak? | Says the saved playlist names. |
| What’s the weather in London? | Milyen az idő Londonban? | Looks up the fact and answers in under 20 seconds. |

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
