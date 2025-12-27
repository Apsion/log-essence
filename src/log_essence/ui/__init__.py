"""Streamlit-based paste-and-copy UI for log-essence.

This module provides a web interface for analyzing logs.
Requires the 'ui' optional dependency: pip install log-essence[ui]
"""

from __future__ import annotations


def launch_ui(*, open_browser: bool = True, port: int = 8501) -> None:
    """Launch the Streamlit UI.

    Args:
        open_browser: Whether to auto-open browser
        port: Port to run on

    Raises:
        ImportError: If streamlit is not installed
    """
    try:
        import streamlit.web.cli as stcli
    except ImportError as e:
        raise ImportError(
            "Streamlit not installed. Install with: pip install log-essence[ui]"
        ) from e

    import sys
    from pathlib import Path

    app_path = Path(__file__).parent / "app.py"

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        f"--server.port={port}",
        f"--server.headless={not open_browser}",
        "--browser.gatherUsageStats=false",
    ]

    if open_browser:
        sys.argv.append("--server.runOnSave=false")

    sys.exit(stcli.main())
