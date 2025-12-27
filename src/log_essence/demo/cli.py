"""CLI for demo generation."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Load .env file if present (for TTS/Whisper/FFmpeg API configuration)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use environment variables directly


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for demo CLI."""
    parser = argparse.ArgumentParser(
        prog="log-essence demo",
        description="Generate demo videos for log-essence",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate command
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate a demo from a script",
    )
    gen_parser.add_argument(
        "script",
        type=str,
        help="Path to the demo script YAML file",
    )
    gen_parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="demos/output",
        help="Output directory (default: demos/output)",
    )
    gen_parser.add_argument(
        "-n",
        "--name",
        type=str,
        default=None,
        help="Output filename (default: script name)",
    )
    gen_parser.add_argument(
        "--no-tts",
        action="store_true",
        help="Skip TTS generation (video only)",
    )
    gen_parser.add_argument(
        "--no-gif",
        action="store_true",
        help="Skip GIF generation",
    )
    gen_parser.add_argument(
        "--subtitles",
        action="store_true",
        default=True,
        help="Generate SRT subtitle file (default: enabled)",
    )
    gen_parser.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Disable subtitle generation",
    )
    gen_parser.add_argument(
        "--word-overlay",
        action="store_true",
        help="Add karaoke-style word overlays (requires hosted FFmpeg)",
    )
    gen_parser.add_argument(
        "--use-hosted-ffmpeg",
        action="store_true",
        help="Use hosted FFmpeg API instead of local ffmpeg",
    )

    # record command (just record, no TTS)
    rec_parser = subparsers.add_parser(
        "record",
        help="Record a demo (video only, no audio)",
    )
    rec_parser.add_argument(
        "script",
        type=str,
        help="Path to the demo script YAML file",
    )
    rec_parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="demos/output",
        help="Output directory (default: demos/output)",
    )

    return parser


async def run_generate(args: argparse.Namespace) -> int:
    """Run the generate command."""
    from log_essence.demo.compose import ComposerConfig, DemoComposer
    from log_essence.demo.runner import DemoRunner
    from log_essence.demo.schema import DemoScript
    from log_essence.demo.tts import TTSClient

    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Script not found: {script_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output)
    output_name = args.name or script_path.stem

    print(f"Loading script: {script_path}")
    script = DemoScript.from_yaml(str(script_path))

    # Step 1: Generate audio first to get actual durations (with Whisper timing)
    audio_segments = []
    scene_durations: dict[str, int] = {}

    if not args.no_tts:
        print("Generating narration audio...")
        with TTSClient(use_whisper=True) as tts:
            scenes = [(s.id, s.narration) for s in script.scenes]
            audio_segments = tts.generate_for_scenes(scenes, output_dir / "audio")
            for seg, scene in zip(audio_segments, script.scenes, strict=True):
                scene_durations[scene.id] = seg.duration_ms
                word_count = len(seg.word_timings)
                print(f"  {scene.id}: {seg.duration_ms}ms ({word_count} words) - {seg.path.name}")

    # Step 2: Record video synced to audio durations
    print(f"Recording demo: {script.title}")
    runner = DemoRunner(output_dir=output_dir)
    durations = scene_durations if scene_durations else None
    recording = await runner.run(script, scene_durations=durations)
    print(f"  Video: {recording.video_path}")
    print(f"  Total duration: {recording.total_duration_ms}ms")

    # Print scene timing info
    for scene in recording.scenes:
        timing = f"{scene.start_ms}ms - {scene.end_ms}ms ({scene.duration_ms}ms)"
        print(f"  Scene '{scene.scene_id}': {timing}")

    # Step 3: Compose video + audio with subtitles
    print("Composing final output...")
    config = ComposerConfig(
        use_hosted_ffmpeg=getattr(args, "use_hosted_ffmpeg", False),
        add_subtitles=not getattr(args, "no_subtitles", False),
        add_word_overlay=getattr(args, "word_overlay", False),
    )
    composer = DemoComposer(output_dir=output_dir, config=config)
    composed = composer.compose(recording, audio_segments, output_name)

    print(f"  MP4: {composed.mp4_path}")
    if composed.srt_path:
        print(f"  SRT: {composed.srt_path}")
    if composed.gif_path:
        print(f"  GIF: {composed.gif_path}")

    print("Done!")
    return 0


async def run_record(args: argparse.Namespace) -> int:
    """Run the record command."""
    from log_essence.demo.runner import DemoRunner
    from log_essence.demo.schema import DemoScript

    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Script not found: {script_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output)

    print(f"Loading script: {script_path}")
    script = DemoScript.from_yaml(str(script_path))

    print(f"Recording demo: {script.title}")
    runner = DemoRunner(output_dir=output_dir)
    recording = await runner.run(script)

    print(f"Video saved: {recording.video_path}")
    for scene in recording.scenes:
        print(f"  Scene '{scene.scene_id}': {scene.duration_ms}ms")
        for screenshot in scene.screenshots:
            print(f"    Screenshot: {screenshot}")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for demo CLI."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        return asyncio.run(run_generate(args))
    elif args.command == "record":
        return asyncio.run(run_record(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
