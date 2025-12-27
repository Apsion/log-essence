"""Demo generation module for log-essence.

This module provides automated demo video generation for log-essence.
It uses Playwright for browser automation and supports TTS narration
with Whisper-based word timing for synchronized subtitles.

Install with: pip install log-essence[demo]

Usage:
    log-essence demo generate demos/compare-logs.yaml
    log-essence demo generate demos/compare-logs.yaml --word-overlay --use-hosted-ffmpeg
    log-essence demo record demos/compare-logs.yaml  # video only, no TTS

Environment variables (for hosted services):
    LOG_ESSENCE_TTS_BASE_URL - Kokoro TTS endpoint
    LOG_ESSENCE_WHISPER_BASE_URL - WhisperX endpoint
    LOG_ESSENCE_FFMPEG_BASE_URL - FFmpeg API endpoint
"""

__all__ = [
    "Action",
    "DemoComposer",
    "DemoRunner",
    "DemoScript",
    "FFmpegClient",
    "Scene",
    "TTSClient",
    "WhisperClient",
]


def __getattr__(name: str) -> object:
    """Lazy import to avoid loading Playwright unless needed."""
    if name in ("DemoScript", "Scene", "Action"):
        from log_essence.demo.schema import Action, DemoScript, Scene

        return {"DemoScript": DemoScript, "Scene": Scene, "Action": Action}[name]
    elif name == "DemoRunner":
        from log_essence.demo.runner import DemoRunner

        return DemoRunner
    elif name == "TTSClient":
        from log_essence.demo.tts import TTSClient

        return TTSClient
    elif name == "WhisperClient":
        from log_essence.demo.tts import WhisperClient

        return WhisperClient
    elif name == "FFmpegClient":
        from log_essence.demo.tts import FFmpegClient

        return FFmpegClient
    elif name == "DemoComposer":
        from log_essence.demo.compose import DemoComposer

        return DemoComposer
    raise AttributeError(f"module 'log_essence.demo' has no attribute {name!r}")
