"""Playwright-based demo runner for recording terminal sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page

from log_essence.demo.schema import (
    Action,
    ClearAction,
    ClickAction,
    DemoScript,
    ExecuteAction,
    FillAction,
    NavigateAction,
    Scene,
    ScreenshotAction,
    TypeAction,
    WaitAction,
)


@dataclass
class ActionTiming:
    """Timing data for a single action."""

    action_type: str
    start_ms: int
    end_ms: int
    details: dict = field(default_factory=dict)  # Action-specific data (text, url, etc.)


@dataclass
class SceneRecording:
    """Recording data for a single scene."""

    scene_id: str
    narration: str
    start_ms: int = 0  # When this scene started (relative to video start)
    end_ms: int = 0  # When this scene ended
    screenshots: list[Path] = field(default_factory=list)
    action_timings: list[ActionTiming] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        """Duration of this scene in milliseconds."""
        return self.end_ms - self.start_ms


@dataclass
class DemoRecording:
    """Complete recording data for a demo."""

    title: str
    scenes: list[SceneRecording] = field(default_factory=list)
    video_path: Path | None = None
    output_dir: Path = field(default_factory=lambda: Path("demos/output"))
    total_duration_ms: int = 0

    def get_scene_at_time(self, time_ms: int) -> SceneRecording | None:
        """Get the scene that's active at a given time."""
        for scene in self.scenes:
            if scene.start_ms <= time_ms < scene.end_ms:
                return scene
        return None

    def get_all_action_timings(self) -> list[tuple[str, ActionTiming]]:
        """Get all action timings with their scene IDs."""
        result = []
        for scene in self.scenes:
            for timing in scene.action_timings:
                result.append((scene.scene_id, timing))
        return result


class DemoRunner:
    """Runs demo scripts using Playwright and records the output."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self.output_dir = output_dir or Path("demos/output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._recording_start_time: float = 0  # Track when recording started

    async def run(
        self,
        script: DemoScript,
        scene_durations: dict[str, int] | None = None,
    ) -> DemoRecording:
        """Execute a demo script and return the recording.

        Args:
            script: The demo script to execute
            scene_durations: Optional dict mapping scene_id to target duration in ms.
                            If provided, each scene will wait until its audio duration
                            is reached before moving to the next scene.
        """
        from playwright.async_api import async_playwright

        recording = DemoRecording(
            title=script.title,
            output_dir=self.output_dir,
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(
                viewport={"width": script.viewport[0], "height": script.viewport[1]},
                record_video_dir=str(self.output_dir),
                record_video_size={
                    "width": script.viewport[0],
                    "height": script.viewport[1],
                },
            )
            page = await context.new_page()

            # Mark when video recording starts
            self._recording_start_time = asyncio.get_event_loop().time()

            for scene in script.scenes:
                target_duration = None
                if scene_durations and scene.id in scene_durations:
                    target_duration = scene_durations[scene.id]
                scene_recording = await self._run_scene(
                    page, scene, script.typing_speed, target_duration
                )
                recording.scenes.append(scene_recording)

            # Calculate total duration
            final_time = asyncio.get_event_loop().time()
            recording.total_duration_ms = int((final_time - self._recording_start_time) * 1000)

            await context.close()
            await browser.close()

            # Get the video path
            video = page.video
            if video:
                video_path = await video.path()
                recording.video_path = Path(video_path)

        return recording

    def _get_elapsed_ms(self) -> int:
        """Get milliseconds elapsed since recording started."""
        return int((asyncio.get_event_loop().time() - self._recording_start_time) * 1000)

    async def _run_scene(
        self,
        page: Page,
        scene: Scene,
        default_typing_speed: int,
        target_duration_ms: int | None = None,
    ) -> SceneRecording:
        """Run a single scene and record it.

        Args:
            page: Playwright page
            scene: Scene to execute
            default_typing_speed: Default delay between keystrokes
            target_duration_ms: If provided, wait until this duration is reached
                               after executing all actions (syncs with audio)
        """
        scene_recording = SceneRecording(
            scene_id=scene.id,
            narration=scene.narration,
            start_ms=self._get_elapsed_ms(),
        )

        for action in scene.actions:
            await self._execute_action(page, action, scene_recording, default_typing_speed)

        elapsed_ms = self._get_elapsed_ms() - scene_recording.start_ms

        # If we have a target duration and haven't reached it, wait
        if target_duration_ms and elapsed_ms < target_duration_ms:
            remaining_ms = target_duration_ms - elapsed_ms + 200  # 200ms buffer
            await asyncio.sleep(remaining_ms / 1000)

        scene_recording.end_ms = self._get_elapsed_ms()

        return scene_recording

    async def _execute_action(
        self,
        page: Page,
        action: Action,
        scene_recording: SceneRecording,
        default_typing_speed: int,
    ) -> None:
        """Execute a single action and record its timing."""
        start_ms = self._get_elapsed_ms()
        details: dict = {}

        match action:
            case NavigateAction():
                url = action.url
                if url.startswith("file://"):
                    # Convert relative file path to absolute
                    file_path = Path(url.replace("file://", ""))
                    if not file_path.is_absolute():
                        file_path = Path.cwd() / file_path
                    url = f"file://{file_path.absolute()}"
                await page.goto(url)
                await page.wait_for_load_state("domcontentloaded")
                details = {"url": action.url}

            case TypeAction():
                delay = action.delay or default_typing_speed
                # Use the terminal API for typing if available
                has_api = await page.evaluate("typeof window.terminalAPI !== 'undefined'")
                if has_api:
                    text_escaped = action.text.replace("\\", "\\\\").replace("'", "\\'")
                    await page.evaluate(f"window.terminalAPI.type('{text_escaped}', {delay})")
                else:
                    await page.type(action.selector, action.text, delay=delay)
                details = {"text": action.text, "selector": action.selector}

            case WaitAction():
                await asyncio.sleep(action.duration / 1000)
                details = {"duration": action.duration}

            case ScreenshotAction():
                screenshot_count = len(scene_recording.screenshots)
                name = action.name or f"{scene_recording.scene_id}_{screenshot_count}"
                screenshot_path = self.output_dir / f"{name}.png"
                await page.screenshot(path=str(screenshot_path))
                scene_recording.screenshots.append(screenshot_path)
                details = {"name": name, "path": str(screenshot_path)}

            case ExecuteAction():
                has_api = await page.evaluate("typeof window.terminalAPI !== 'undefined'")
                if has_api:
                    await page.evaluate("window.terminalAPI.execute()")
                else:
                    await page.keyboard.press("Enter")

            case ClearAction():
                has_api = await page.evaluate("typeof window.terminalAPI !== 'undefined'")
                if has_api:
                    await page.evaluate("window.terminalAPI.clear()")

            case ClickAction():
                if action.text:
                    # Use getByText for text-based matching
                    await page.get_by_text(action.text, exact=True).click()
                else:
                    await page.click(action.selector)
                details = {"selector": action.selector, "text": action.text}

            case FillAction():
                await page.fill(action.selector, action.text)
                details = {"selector": action.selector, "text": action.text[:50] + "..."}

        # Record the action timing
        end_ms = self._get_elapsed_ms()
        action_timing = ActionTiming(
            action_type=action.type,
            start_ms=start_ms,
            end_ms=end_ms,
            details=details,
        )
        scene_recording.action_timings.append(action_timing)


async def run_demo(script_path: str, output_dir: str | None = None) -> DemoRecording:
    """Convenience function to run a demo script."""
    script = DemoScript.from_yaml(script_path)
    runner = DemoRunner(output_dir=Path(output_dir) if output_dir else None)
    return await runner.run(script)
