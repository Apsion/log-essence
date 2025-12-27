# Demo Video Generation System

A reusable 3-stage pipeline for creating narrated product demos with synchronized audio, video, and subtitles.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     DEMO GENERATION PIPELINE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Stage 1: Audio Generation                                       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │  Narration  │───▶│  Kokoro TTS │───▶│ AudioSegment + MP3  │  │
│  │    Text     │    │   (OpenAI   │    │                     │  │
│  │             │    │ compatible) │    │                     │  │
│  └─────────────┘    └──────┬──────┘    └─────────────────────┘  │
│                            │                                     │
│                            ▼                                     │
│                    ┌─────────────┐    ┌─────────────────────┐   │
│                    │   Whisper   │───▶│    Word Timings     │   │
│                    │  (WhisperX) │    │ (start_ms, end_ms)  │   │
│                    └─────────────┘    └─────────────────────┘   │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Stage 2: Video Recording                                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ Demo Script │───▶│  Playwright │───▶│   WebM Video +      │  │
│  │   (YAML)    │    │  Recording  │    │   Scene Timings     │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Stage 3: Composition                                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ Video +     │───▶│   FFmpeg    │───▶│  MP4 + SRT + GIF    │  │
│  │ Audio +     │    │  (local or  │    │                     │  │
│  │ Timings     │    │   hosted)   │    │                     │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Kokoro TTS (Text-to-Speech)

**Purpose**: Convert narration text to audio files.

**API**: OpenAI-compatible speech endpoint.

```python
# Request
POST {base_url}/audio/speech
{
    "model": "tts-1",
    "input": "Your narration text here",
    "voice": "af_sky",
    "response_format": "mp3"
}

# Response: Binary MP3 data
```

**Voice Options**:
- Female: `af_sky`, `af_bella`, `af_heart`, `af_nova`, `af_sarah`
- Male: `am_adam`, `am_michael`, `am_eric`

**Integration Pattern**:
```python
class TTSClient:
    def __init__(self, base_url: str, voice: str = "af_sky"):
        self.base_url = base_url
        self.voice = voice

    def generate(self, text: str, output_path: Path) -> Path:
        response = httpx.post(
            f"{self.base_url}/audio/speech",
            json={
                "model": "tts-1",
                "input": text,
                "voice": self.voice,
                "response_format": "mp3"
            },
            timeout=60.0
        )
        output_path.write_bytes(response.content)
        return output_path
```

### 2. Whisper (Word-Level Timing Extraction)

**Purpose**: Extract precise word timings from generated audio for subtitle synchronization.

**Note**: Uses WhisperX API (not OpenAI Whisper) for word-level timestamps.

**API**:
```python
# Request
POST {base_url}/transcribe
# Form data with audio file

# Response
{
    "segments": [
        {
            "words": [
                {"word": "log", "start": 0.12, "end": 0.45},
                {"word": "essence", "start": 0.46, "end": 0.89}
            ]
        }
    ]
}
```

**Integration Pattern**:
```python
@dataclass
class WordTiming:
    word: str
    start_ms: int
    end_ms: int

class WhisperClient:
    def transcribe(self, audio_path: Path) -> tuple[int, list[WordTiming]]:
        with open(audio_path, "rb") as f:
            response = httpx.post(
                f"{self.base_url}/transcribe",
                files={"file": f},
                timeout=120.0
            )

        data = response.json()
        word_timings = []
        for segment in data.get("segments", []):
            for word_data in segment.get("words", []):
                word_timings.append(WordTiming(
                    word=word_data["word"],
                    start_ms=int(word_data["start"] * 1000),
                    end_ms=int(word_data["end"] * 1000)
                ))

        duration_ms = word_timings[-1].end_ms if word_timings else 0
        return duration_ms, word_timings
```

### 3. FFmpeg (Audio/Video Composition)

**Purpose**: Combine video and audio, generate subtitles, create GIFs.

Supports both local `ffmpeg` binary and hosted API.

#### Local FFmpeg Operations

**Audio Concatenation**:
```bash
# Create concat list file
echo "file 'audio1.mp3'
file 'audio2.mp3'" > concat.txt

# Concatenate
ffmpeg -f concat -safe 0 -i concat.txt -c copy output.mp3
```

**Video + Audio Merge** (with duration extension):
```bash
# If audio is longer than video, extend video with frozen last frame
ffmpeg -i video.webm -i audio.mp3 \
    -vf "tpad=stop_mode=clone:stop_duration=2.5" \
    -c:v libx264 -c:a aac \
    output.mp4
```

**GIF Generation** (two-pass for quality):
```bash
# Pass 1: Generate palette
ffmpeg -i video.mp4 \
    -vf "fps=10,scale=640:-1:flags=lanczos,palettegen" \
    palette.png

# Pass 2: Apply palette
ffmpeg -i video.mp4 -i palette.png \
    -lavfi "fps=10,scale=640:-1:flags=lanczos[x];[x][1:v]paletteuse" \
    output.gif
```

**Duration Probe**:
```bash
ffprobe -v error -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 file.mp3
```

#### Hosted FFmpeg API

Alternative to local binary for serverless environments.

```python
class FFmpegClient:
    def upload(self, file_path: Path) -> str:
        """Upload file, returns file_id"""

    def download(self, file_id: str, output_path: Path) -> Path:
        """Download processed file"""

    def concat(self, file_ids: list[str]) -> str:
        """Concatenate videos, returns new file_id"""

    def to_gif(self, file_id: str) -> str:
        """Convert to GIF, returns new file_id"""

    def add_text_overlay(self, file_id: str, text: str, ...) -> str:
        """Add text overlay using drawtext filter"""
```

### 4. Playwright (Browser Recording)

**Purpose**: Automate browser interactions and record video.

```python
async def record_demo(script: DemoScript) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir="recordings/",
            record_video_size={"width": 1280, "height": 720}
        )
        page = await context.new_page()

        for scene in script.scenes:
            for action in scene.actions:
                await execute_action(page, action)
                if scene.target_duration_ms:
                    # Wait until audio duration reached
                    await wait_for_duration(scene.target_duration_ms)

        await context.close()
        return Path(await page.video.path())
```

## Demo Script Format (YAML)

```yaml
title: "Product Demo"
viewport: [1280, 720]
typing_speed: 50  # ms per character
output_dir: "demos/output"

scenes:
  - id: intro
    narration: "Welcome to our product demo."
    actions:
      - type: navigate
        url: "https://example.com"
      - type: wait
        duration: 1000

  - id: feature-demo
    narration: "Let me show you our key feature."
    actions:
      - type: type
        selector: "#search"
        text: "example query"
      - type: click
        selector: "#submit"
      - type: screenshot
        name: "result"

  - id: outro
    narration: "Thanks for watching!"
    actions:
      - type: execute
        script: "document.body.classList.add('highlight')"
```

**Action Types**:
| Type | Parameters | Description |
|------|------------|-------------|
| `navigate` | `url` | Navigate to URL |
| `type` | `selector`, `text` | Type text into element |
| `click` | `selector` | Click element |
| `wait` | `duration` | Wait milliseconds |
| `screenshot` | `name` | Capture screenshot |
| `execute` | `script` | Run JavaScript |
| `clear` | `selector` | Clear input field |

## Output Files

```
output/
├── demo.mp4           # Final video with audio
├── demo.srt           # Subtitles (word-level sync)
├── demo.gif           # Animated GIF preview
├── demo_audio.mp3     # Concatenated audio
└── audio/
    ├── intro.mp3      # Per-scene audio
    ├── feature.mp3
    └── outro.mp3
```

## Configuration

### Environment Variables

```bash
# TTS (Kokoro)
LOG_ESSENCE_TTS_BASE_URL=
LOG_ESSENCE_TTS_VOICE=af_sky

# Whisper (word timing)
LOG_ESSENCE_WHISPER_BASE_URL=

# FFmpeg (optional hosted API)
LOG_ESSENCE_FFMPEG_BASE_URL=https://ffmpeg.h.lanxcape.com
```

### Dependencies

```toml
[project.dependencies]
playwright = ">=1.40.0"
httpx = ">=0.27.0"
python-dotenv = ">=1.0.0"
pyyaml = ">=6.0"

[project.optional-dependencies]
# Local ffmpeg/ffprobe required OR use hosted API
```

## Subtitle Generation

Subtitles are generated from word timings with configurable grouping:

```python
def generate_srt(word_timings: list[WordTiming], words_per_chunk: int = 6) -> str:
    chunks = []
    for i in range(0, len(word_timings), words_per_chunk):
        chunk = word_timings[i:i + words_per_chunk]
        chunks.append(SrtEntry(
            start_ms=chunk[0].start_ms,
            end_ms=chunk[-1].end_ms,
            text=" ".join(w.word for w in chunk)
        ))
    return format_srt(chunks)
```

## Timing Synchronization

The key to smooth demos is synchronizing audio and video timing:

1. **Generate audio first** → Get exact duration from Whisper
2. **Pass duration to video recording** → Scene waits until duration reached
3. **Compose with matched timings** → Audio/video align perfectly

```python
# Stage 1: Audio with timing
audio_segments = []
for scene in script.scenes:
    segment = tts.generate(scene.narration)
    duration, word_timings = whisper.transcribe(segment.path)
    audio_segments.append(AudioSegment(
        path=segment.path,
        duration_ms=duration,
        word_timings=word_timings
    ))

# Stage 2: Video with duration targets
scene_durations = {s.id: seg.duration_ms for s, seg in zip(scenes, audio_segments)}
recording = runner.record(script, scene_durations=scene_durations)

# Stage 3: Compose
output = composer.compose(recording, audio_segments)
```

## Replication Checklist

To implement this system in another project:

- [ ] **TTS Integration**
  - [ ] Set up OpenAI-compatible TTS endpoint (Kokoro, OpenAI, etc.)
  - [ ] Implement TTSClient with generate() method
  - [ ] Configure voice selection

- [ ] **Whisper Integration**
  - [ ] Set up WhisperX API endpoint
  - [ ] Implement word timing extraction
  - [ ] Add fallback to ffprobe duration probe

- [ ] **Video Recording**
  - [ ] Set up Playwright with video recording
  - [ ] Implement action executors for your script format
  - [ ] Add duration-based waiting for audio sync

- [ ] **FFmpeg Composition**
  - [ ] Implement audio concatenation (concat demuxer)
  - [ ] Implement video+audio merge with tpad for extension
  - [ ] Implement two-pass GIF generation
  - [ ] (Optional) Set up hosted FFmpeg API client

- [ ] **Subtitle Generation**
  - [ ] Generate SRT from word timings
  - [ ] Configure words-per-chunk for readability

- [ ] **Configuration**
  - [ ] Environment variables for API endpoints
  - [ ] Graceful degradation (hosted → local → estimation)

## API Endpoints Summary

| Service | Endpoint | Purpose |
|---------|----------|---------|
| Kokoro TTS | `POST /v1/audio/speech` | Text-to-speech |
| WhisperX | `POST /transcribe` | Word-level timing |
| FFmpeg API | `POST /api/upload` | Upload file |
| FFmpeg API | `GET /api/file/{id}` | Download file |
| FFmpeg API | `POST /api/concat` | Concatenate videos |
| FFmpeg API | `POST /api/gif` | Generate GIF |
| FFmpeg API | `POST /api/custom` | Custom filter (drawtext) |

## Troubleshooting

**Audio longer than video**: FFmpeg automatically extends video with `tpad=stop_mode=clone`.

**Missing word timings**: Falls back to duration probe, then word count estimation (150 wpm).

**GIF too large**: Reduce fps (default 10) or scale (default 640px width).

**Subtitle sync off**: Check that Whisper timestamps match audio; may need to adjust chunk size.
