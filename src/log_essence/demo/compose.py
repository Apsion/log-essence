"""Video composition using ffmpeg (local or hosted API)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from log_essence.demo.runner import DemoRecording
from log_essence.demo.tts import AudioSegment, FFmpegClient, WordTiming


@dataclass
class ComposedDemo:
    """Final composed demo output."""

    mp4_path: Path
    gif_path: Path | None = None
    audio_path: Path | None = None
    srt_path: Path | None = None  # Subtitle file


@dataclass
class SceneAudio:
    """Audio segment with timing info for a scene."""

    scene_id: str
    segment: AudioSegment
    video_start_ms: int  # When this scene starts in the video
    video_end_ms: int  # When this scene ends in the video


@dataclass
class ComposerConfig:
    """Configuration for demo composition."""

    use_hosted_ffmpeg: bool = False  # Use hosted FFmpeg API instead of local
    add_subtitles: bool = True  # Generate SRT subtitles
    add_word_overlay: bool = False  # Add karaoke-style word overlays
    subtitle_position: str = "bottom"  # top, center, bottom
    font_size: int = 32
    font_color: str = "white"


class DemoComposer:
    """Composes video and audio into final demo output."""

    def __init__(
        self,
        output_dir: Path | None = None,
        config: ComposerConfig | None = None,
    ) -> None:
        self.output_dir = output_dir or Path("demos/output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or ComposerConfig()
        self._ffmpeg_client: FFmpegClient | None = None

    @property
    def ffmpeg(self) -> FFmpegClient:
        """Get or create FFmpeg client for hosted API."""
        if self._ffmpeg_client is None:
            self._ffmpeg_client = FFmpegClient()
        return self._ffmpeg_client

    def compose(
        self,
        recording: DemoRecording,
        audio_segments: list[AudioSegment],
        output_name: str = "demo",
    ) -> ComposedDemo:
        """Compose video and audio into final output.

        Pipeline:
        1. Match audio segments to scenes (using recording timing)
        2. Generate SRT subtitles from word timings (if enabled)
        3. Concatenate audio segments
        4. Combine video + audio
        5. Add text overlays (if enabled)
        6. Generate GIF
        """
        if not recording.video_path or not recording.video_path.exists():
            raise ValueError("No video recording found")

        # Match audio to scene timings
        scene_audio = self._match_audio_to_scenes(recording, audio_segments)

        # Generate subtitles from word timings
        srt_path = None
        if self.config.add_subtitles and audio_segments:
            srt_path = self._generate_subtitles(scene_audio, output_name)

        # Concatenate audio segments
        audio_path = self._concat_audio(audio_segments, output_name)

        # Combine video and audio
        mp4_path = self._combine_video_audio(recording.video_path, audio_path, output_name)

        # Add word overlays if enabled (uses hosted FFmpeg API)
        if self.config.add_word_overlay and self.config.use_hosted_ffmpeg:
            mp4_path = self._add_word_overlays(mp4_path, scene_audio, output_name)

        # Generate GIF
        gif_path = self._generate_gif(mp4_path, output_name)

        return ComposedDemo(
            mp4_path=mp4_path,
            gif_path=gif_path,
            audio_path=audio_path,
            srt_path=srt_path,
        )

    def _match_audio_to_scenes(
        self,
        recording: DemoRecording,
        audio_segments: list[AudioSegment],
    ) -> list[SceneAudio]:
        """Match audio segments to scene timing from video recording."""
        result = []
        for scene, segment in zip(recording.scenes, audio_segments, strict=False):
            result.append(
                SceneAudio(
                    scene_id=scene.scene_id,
                    segment=segment,
                    video_start_ms=scene.start_ms,
                    video_end_ms=scene.end_ms,
                )
            )
        return result

    def _generate_subtitles(
        self,
        scene_audio: list[SceneAudio],
        output_name: str,
    ) -> Path:
        """Generate SRT subtitle file from word timings."""
        srt_path = self.output_dir / f"{output_name}.srt"
        subtitle_index = 1

        with open(srt_path, "w") as f:
            for sa in scene_audio:
                # If we have word timings, create word-level subtitles
                if sa.segment.word_timings:
                    # Group words into subtitle chunks (roughly 5-7 words each)
                    words = sa.segment.word_timings
                    chunk_size = 6
                    for i in range(0, len(words), chunk_size):
                        chunk = words[i : i + chunk_size]
                        if not chunk:
                            continue

                        # Calculate timing relative to video
                        start_ms = sa.video_start_ms + chunk[0].start_ms
                        end_ms = sa.video_start_ms + chunk[-1].end_ms
                        text = " ".join(w.word for w in chunk)

                        start_time = self._ms_to_srt_time(start_ms)
                        end_time = self._ms_to_srt_time(end_ms)
                        f.write(f"{subtitle_index}\n")
                        f.write(f"{start_time} --> {end_time}\n")
                        f.write(f"{text}\n\n")
                        subtitle_index += 1
                else:
                    # Fall back to scene-level subtitles
                    start_time = self._ms_to_srt_time(sa.video_start_ms)
                    end_time = self._ms_to_srt_time(sa.video_end_ms)
                    f.write(f"{subtitle_index}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{sa.segment.text}\n\n")
                    subtitle_index += 1

        return srt_path

    def _ms_to_srt_time(self, ms: int) -> str:
        """Convert milliseconds to SRT timestamp format (HH:MM:SS,mmm)."""
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        millis = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    def _add_word_overlays(
        self,
        video_path: Path,
        scene_audio: list[SceneAudio],
        output_name: str,
    ) -> Path:
        """Add karaoke-style word overlays using hosted FFmpeg API."""
        # Collect all word timings with absolute video timestamps
        all_timings: list[WordTiming] = []
        for sa in scene_audio:
            for wt in sa.segment.word_timings:
                all_timings.append(
                    WordTiming(
                        word=wt.word,
                        start_ms=sa.video_start_ms + wt.start_ms,
                        end_ms=sa.video_start_ms + wt.end_ms,
                    )
                )

        if not all_timings:
            return video_path

        # Upload and process via FFmpeg API
        video_id = self.ffmpeg.upload(video_path)
        result_id = self.ffmpeg.add_word_overlays(
            video_id,
            all_timings,
            font_size=self.config.font_size,
            font_color=self.config.font_color,
            position=self.config.subtitle_position,
        )

        # Download result
        output_path = self.output_dir / f"{output_name}_overlay.mp4"
        self.ffmpeg.download(result_id, output_path)

        # Cleanup uploaded files
        self.ffmpeg.delete(video_id)
        self.ffmpeg.delete(result_id)

        return output_path

    def _concat_audio(self, segments: list[AudioSegment], output_name: str) -> Path:
        """Concatenate audio segments into a single file."""
        if not segments:
            # Create silence if no audio
            output_path = self.output_dir / f"{output_name}_audio.mp3"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=stereo",
                    "-t",
                    "1",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
            )
            return output_path

        if len(segments) == 1:
            return segments[0].path

        # Create a concat file
        concat_file = self.output_dir / f"{output_name}_concat.txt"
        with open(concat_file, "w") as f:
            for segment in segments:
                f.write(f"file '{segment.path.absolute()}'\n")

        output_path = self.output_dir / f"{output_name}_audio.mp3"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )

        # Clean up concat file
        concat_file.unlink()

        return output_path

    def _combine_video_audio(self, video_path: Path, audio_path: Path, output_name: str) -> Path:
        """Combine video and audio into MP4."""
        output_path = self.output_dir / f"{output_name}.mp4"

        # Get durations
        video_duration = self._get_duration(video_path)
        audio_duration = self._get_duration(audio_path)

        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
        ]

        # If audio is longer, extend video by freezing last frame
        if audio_duration > video_duration:
            # Use tpad filter to extend video with last frame
            pad_duration = audio_duration - video_duration
            cmd.extend(["-vf", f"tpad=stop_mode=clone:stop_duration={pad_duration}"])

        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-t",
                str(audio_duration),
                str(output_path),
            ]
        )

        subprocess.run(cmd, check=True, capture_output=True)

        return output_path

    def _generate_gif(self, mp4_path: Path, output_name: str) -> Path:
        """Generate a GIF from the video."""
        output_path = self.output_dir / f"{output_name}.gif"

        # Generate palette for better quality GIF
        palette_path = self.output_dir / f"{output_name}_palette.png"

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp4_path),
                "-vf",
                "fps=10,scale=640:-1:flags=lanczos,palettegen",
                str(palette_path),
            ],
            check=True,
            capture_output=True,
        )

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp4_path),
                "-i",
                str(palette_path),
                "-lavfi",
                "fps=10,scale=640:-1:flags=lanczos[x];[x][1:v]paletteuse",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )

        # Clean up palette
        palette_path.unlink()

        return output_path

    def _get_duration(self, path: Path) -> float:
        """Get duration of a media file in seconds."""
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())


def compose_demo(
    recording: DemoRecording,
    audio_segments: list[AudioSegment],
    output_name: str = "demo",
    output_dir: Path | None = None,
) -> ComposedDemo:
    """Convenience function to compose a demo."""
    composer = DemoComposer(output_dir=output_dir)
    return composer.compose(recording, audio_segments, output_name)
