"""OpenAI-compatible TTS and Whisper clients for demo generation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import httpx


@dataclass
class WordTiming:
    """A word with its timing information."""

    word: str
    start_ms: int
    end_ms: int


@dataclass
class AudioSegment:
    """An audio segment with metadata."""

    path: Path
    duration_ms: int
    text: str
    word_timings: list[WordTiming] = field(default_factory=list)


class TTSClient:
    """OpenAI-compatible TTS client."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        voice: str | None = None,
        model: str = "tts-1",
        use_whisper: bool = True,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("LOG_ESSENCE_TTS_BASE_URL") or "https://api.openai.com/v1"
        )
        self.api_key = api_key or os.environ.get("LOG_ESSENCE_TTS_API_KEY") or ""
        self.voice = voice or os.environ.get("LOG_ESSENCE_TTS_VOICE") or "alloy"
        self.model = model
        self.use_whisper = use_whisper
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=60.0,
            )
        return self._client

    def generate(self, text: str, output_path: Path) -> AudioSegment:
        """Generate audio for text and save to file."""
        response = self.client.post(
            "/audio/speech",
            json={
                "model": self.model,
                "input": text,
                "voice": self.voice,
                "response_format": "mp3",
            },
        )
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)

        # Get duration and word timings (uses Whisper if enabled, falls back to ffprobe)
        duration_ms, word_timings = get_audio_timing(output_path, use_whisper=self.use_whisper)

        if duration_ms == 0:
            # Fall back to estimation if all methods fail
            word_count = len(text.split())
            duration_ms = int((word_count / 150) * 60 * 1000)

        return AudioSegment(
            path=output_path,
            duration_ms=duration_ms,
            text=text,
            word_timings=word_timings,
        )

    def generate_for_scenes(
        self, scenes: list[tuple[str, str]], output_dir: Path
    ) -> list[AudioSegment]:
        """Generate audio for multiple scenes.

        Args:
            scenes: List of (scene_id, narration_text) tuples
            output_dir: Directory to save audio files

        Returns:
            List of AudioSegment objects
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        segments = []

        for scene_id, text in scenes:
            output_path = output_dir / f"{scene_id}.mp3"
            segment = self.generate(text, output_path)
            segments.append(segment)

        return segments

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> TTSClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class WhisperClient:
    """Whisper client for audio transcription and timing extraction.

    Supports both WhisperX API (custom /transcribe endpoint) and
    OpenAI-compatible API (/v1/audio/transcriptions).
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("LOG_ESSENCE_WHISPER_BASE_URL")
            or "https://whisper.h.lanxcape.com"
        )
        self.api_key = api_key or os.environ.get("LOG_ESSENCE_WHISPER_API_KEY") or ""
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None:
            headers: dict[str, str] = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=120.0,  # Transcription can take longer
            )
        return self._client

    def transcribe(self, audio_path: Path) -> tuple[int, list[WordTiming]]:
        """Transcribe audio file and extract word-level timings.

        Args:
            audio_path: Path to the audio file

        Returns:
            Tuple of (duration_ms, list of WordTiming)
        """
        with open(audio_path, "rb") as f:
            # Use WhisperX /transcribe endpoint
            response = self.client.post(
                "/transcribe",
                files={"file": (audio_path.name, f, "audio/mpeg")},
            )
        response.raise_for_status()

        data = response.json()

        # Parse WhisperX response format
        # Response contains: segments, word_srt, segment_srt, text
        word_timings: list[WordTiming] = []
        duration_ms = 0

        # Extract word timings from segments
        for segment in data.get("segments", []):
            for word_data in segment.get("words", []):
                start_ms = int(word_data.get("start", 0) * 1000)
                end_ms = int(word_data.get("end", 0) * 1000)
                word_timings.append(
                    WordTiming(
                        word=word_data.get("word", "").strip(),
                        start_ms=start_ms,
                        end_ms=end_ms,
                    )
                )
                # Track max end time as duration
                if end_ms > duration_ms:
                    duration_ms = end_ms

        return duration_ms, word_timings

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> WhisperClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class FFmpegClient:
    """FFmpeg API client for video processing and text overlays."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("LOG_ESSENCE_FFMPEG_BASE_URL")
            or "https://ffmpeg.h.lanxcape.com"
        )
        self.api_key = api_key or os.environ.get("LOG_ESSENCE_FFMPEG_API_KEY") or ""
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTP client."""
        if self._client is None:
            headers: dict[str, str] = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=300.0,  # Video processing can take a while
            )
        return self._client

    def upload(self, file_path: Path) -> str:
        """Upload a file and return its file_id."""
        with open(file_path, "rb") as f:
            response = self.client.post(
                "/api/upload",
                files={"file": (file_path.name, f)},
            )
        response.raise_for_status()
        return response.json()["file_id"]

    def download(self, file_id: str, output_path: Path) -> Path:
        """Download a processed file."""
        response = self.client.get(f"/api/file/{file_id}")
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        return output_path

    def probe(self, file_id: str) -> dict:
        """Get file metadata."""
        response = self.client.get(f"/api/probe/{file_id}")
        response.raise_for_status()
        return response.json()

    def add_text_overlay(
        self,
        video_file_id: str,
        text: str,
        start_time: float = 0,
        duration: float | None = None,
        font_size: int = 48,
        font_color: str = "white",
        position: str = "center",
        output_format: str = "mp4",
    ) -> str:
        """Add text overlay to video using drawtext filter.

        Args:
            video_file_id: ID of uploaded video file
            text: Text to overlay
            start_time: When to show text (seconds)
            duration: How long to show text (seconds), None = until end
            font_size: Font size in pixels
            font_color: Font color (white, yellow, etc.)
            position: center, top, bottom, or x:y coordinates
            output_format: Output format (mp4, webm, etc.)

        Returns:
            file_id of processed video
        """
        # Build position coordinates
        if position == "center":
            x, y = "(w-text_w)/2", "(h-text_h)/2"
        elif position == "top":
            x, y = "(w-text_w)/2", "50"
        elif position == "bottom":
            x, y = "(w-text_w)/2", "h-text_h-50"
        else:
            x, y = position.split(":")

        # Build enable expression for timing
        enable = f"gte(t,{start_time})"
        if duration is not None:
            enable = f"between(t,{start_time},{start_time + duration})"

        # Escape text for FFmpeg
        escaped_text = text.replace("'", "'\\''").replace(":", "\\:")

        # Build drawtext filter
        drawtext = (
            f"drawtext=text='{escaped_text}':"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}:"
            f"x={x}:y={y}:"
            f"enable='{enable}'"
        )

        response = self.client.post(
            "/api/custom",
            json={
                "file_id": video_file_id,
                "command": f'-vf "{drawtext}"',
                "output_format": output_format,
            },
        )
        response.raise_for_status()
        return response.json()["file_id"]

    def add_word_overlays(
        self,
        video_file_id: str,
        word_timings: list[WordTiming],
        font_size: int = 48,
        font_color: str = "white",
        position: str = "bottom",
        output_format: str = "mp4",
    ) -> str:
        """Add karaoke-style word overlays synced with audio.

        Args:
            video_file_id: ID of uploaded video file
            word_timings: List of WordTiming with word, start_ms, end_ms
            font_size: Font size in pixels
            font_color: Font color
            position: Text position
            output_format: Output format

        Returns:
            file_id of processed video
        """
        if not word_timings:
            return video_file_id

        # Build position coordinates
        if position == "center":
            x, y = "(w-text_w)/2", "(h-text_h)/2"
        elif position == "top":
            x, y = "(w-text_w)/2", "50"
        elif position == "bottom":
            x, y = "(w-text_w)/2", "h-text_h-50"
        else:
            x, y = position.split(":")

        # Build chained drawtext filters for each word
        filters = []
        for wt in word_timings:
            start_sec = wt.start_ms / 1000
            end_sec = wt.end_ms / 1000
            escaped_word = wt.word.replace("'", "'\\''").replace(":", "\\:")

            filters.append(
                f"drawtext=text='{escaped_word}':"
                f"fontsize={font_size}:"
                f"fontcolor={font_color}:"
                f"x={x}:y={y}:"
                f"enable='between(t,{start_sec:.3f},{end_sec:.3f})'"
            )

        filter_chain = ",".join(filters)

        response = self.client.post(
            "/api/custom",
            json={
                "file_id": video_file_id,
                "command": f'-vf "{filter_chain}"',
                "output_format": output_format,
            },
        )
        response.raise_for_status()
        return response.json()["file_id"]

    def concat(self, file_ids: list[str], output_format: str = "mp4") -> str:
        """Concatenate multiple video files.

        Args:
            file_ids: List of file IDs to concatenate
            output_format: Output format

        Returns:
            file_id of concatenated video
        """
        response = self.client.post(
            "/api/concat",
            json={
                "file_ids": file_ids,
                "output_format": output_format,
            },
        )
        response.raise_for_status()
        return response.json()["file_id"]

    def to_gif(
        self,
        file_id: str,
        fps: int = 10,
        width: int = 640,
    ) -> str:
        """Convert video to GIF.

        Args:
            file_id: ID of video file
            fps: Frames per second
            width: Output width (height auto-calculated)

        Returns:
            file_id of GIF
        """
        response = self.client.post(
            "/api/gif",
            json={
                "file_id": file_id,
                "fps": fps,
                "width": width,
            },
        )
        response.raise_for_status()
        return response.json()["file_id"]

    def delete(self, file_id: str) -> None:
        """Delete a file from storage."""
        self.client.delete(f"/api/file/{file_id}")

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> FFmpegClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def get_audio_duration_ms(audio_path: Path) -> int:
    """Get the actual duration of an audio file using ffprobe."""
    import subprocess

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration_seconds = float(result.stdout.strip())
        return int(duration_seconds * 1000)
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        # Fall back to estimation if ffprobe fails
        return 0


def get_audio_timing(audio_path: Path, use_whisper: bool = True) -> tuple[int, list[WordTiming]]:
    """Get audio duration and optionally word-level timings.

    Args:
        audio_path: Path to the audio file
        use_whisper: If True, use Whisper for word-level timing extraction

    Returns:
        Tuple of (duration_ms, list of WordTiming)
    """
    if use_whisper:
        try:
            whisper = WhisperClient()
            duration_ms, word_timings = whisper.transcribe(audio_path)
            whisper.close()
            if duration_ms > 0:
                return duration_ms, word_timings
        except Exception:
            pass  # Fall back to ffprobe

    # Fallback to ffprobe (no word timings)
    duration_ms = get_audio_duration_ms(audio_path)
    return duration_ms, []
