"""Streamlit application for log-essence paste-and-copy UI."""

from __future__ import annotations

from datetime import UTC, datetime

from log_essence.server import analyze_log_lines, count_tokens
from log_essence.ui.models import (
    AnalysisResult,
    AnalysisStats,
    JSONOutput,
    MetadataOutput,
    UIConfig,
)


def analyze_logs_from_text(logs: str, config: UIConfig) -> AnalysisResult:
    """Analyze logs from pasted text.

    Args:
        logs: Raw log text (newline separated)
        config: Analysis configuration

    Returns:
        AnalysisResult with markdown and statistics
    """
    if not logs.strip():
        return AnalysisResult(
            markdown="Error: No log content provided",
            stats=AnalysisStats(
                processing_time_ms=0,
                redaction_count=0,
                original_tokens=0,
                output_tokens=0,
            ),
        )

    lines = logs.splitlines()

    # Convert redaction mode
    redact: bool | str = False if config.redaction_mode == "disabled" else config.redaction_mode

    return analyze_log_lines(
        all_lines=lines,
        token_budget=config.token_budget,
        num_clusters=config.num_clusters,
        severity_filter=list(config.severity_filter) if config.severity_filter else None,
        redact=redact,
    )


def main() -> None:
    """Main Streamlit application."""
    try:
        import streamlit as st
    except ImportError as e:
        raise ImportError(
            "Streamlit not installed. Install with: pip install log-essence[ui]"
        ) from e

    st.set_page_config(
        page_title="log-essence",
        page_icon="",
        layout="wide",
    )

    # Custom CSS for cleaner look and smaller metrics
    st.markdown(
        """
        <style>
        .stTextArea textarea { font-family: monospace; font-size: 12px; }
        .block-container { padding-top: 2rem; }
        /* Smaller metrics */
        [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.8rem !important; }
        [data-testid="stMetricDelta"] { font-size: 0.7rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("log-essence")
    st.caption("Paste logs, get LLM-ready analysis with automatic secret redaction")

    # Sidebar controls
    with st.sidebar:
        st.header("Settings")

        token_budget = st.slider(
            "Token Budget",
            min_value=1000,
            max_value=32000,
            value=8000,
            step=1000,
            help="Maximum tokens in output",
        )

        num_clusters = st.slider(
            "Cluster Count",
            min_value=1,
            max_value=50,
            value=10,
            help="Number of semantic clusters",
        )

        redaction_mode = st.selectbox(
            "Redaction Mode",
            options=["moderate", "strict", "minimal", "disabled"],
            index=0,
            help="How aggressively to redact secrets/PII",
        )

        severity_options = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        severity_filter = st.multiselect(
            "Severity Filter",
            options=severity_options,
            default=[],
            help="Leave empty to include all severities",
        )

    # Main content area - input smaller, output larger
    col1, col2 = st.columns([2, 3])

    with col1:
        st.subheader("Input")
        logs_input = st.text_area(
            "Log content",
            height=500,
            placeholder="Paste your log content here...",
            label_visibility="collapsed",
        )

        # Show line count
        line_count = len(logs_input.splitlines()) if logs_input.strip() else 0
        st.caption(f"{line_count:,} lines")

        analyze_button = st.button("Analyze", type="primary", use_container_width=True)

    with col2:
        st.subheader("Output")

        if analyze_button and logs_input:
            config = UIConfig(
                token_budget=token_budget,
                num_clusters=num_clusters,
                redaction_mode=redaction_mode,
                severity_filter=severity_filter if severity_filter else None,
            )

            with st.spinner("Analyzing..."):
                result = analyze_logs_from_text(logs_input, config)

            st.session_state["analysis_result"] = result

        if "analysis_result" in st.session_state:
            result = st.session_state["analysis_result"]
            stats = result.stats

            # Generate JSON output first so we can count tokens
            json_output = JSONOutput(
                metadata=MetadataOutput(
                    source="pasted-logs",
                    lines_processed=result.lines_processed,
                    log_format=result.log_format,
                    timestamp=datetime.now(UTC),
                ),
                stats=result.stats.model_dump(),
                severity_distribution=result.severity_distribution,
                clusters=[c.model_dump() for c in (result.clusters_data or [])],
            )
            json_str = json_output.model_dump_json(indent=2)
            json_tokens = count_tokens(json_str)

            # Stats row
            stat_cols = st.columns(5)
            with stat_cols[0]:
                if stats.processing_time_ms < 1000:
                    time_str = f"{stats.processing_time_ms:.0f}ms"
                else:
                    time_str = f"{stats.processing_time_ms / 1000:.1f}s"
                st.metric("Time", time_str)
            with stat_cols[1]:
                st.metric("Redactions", f"{stats.redaction_count:,}")
            with stat_cols[2]:
                st.metric("Input", f"{stats.original_tokens:,} tokens")
            with stat_cols[3]:
                # Show change vs input: positive = more tokens (bad), negative = fewer (good)
                md_change = (
                    (stats.output_tokens / stats.original_tokens - 1) * 100
                    if stats.original_tokens > 0
                    else 0
                )
                md_delta = f"{md_change:+.0f}%" if md_change != 0 else None
                st.metric(
                    "MD Output",
                    f"{stats.output_tokens:,} tokens",
                    delta=md_delta,
                    delta_color="inverse",
                )
            with stat_cols[4]:
                # Show change vs input: positive = more tokens (bad), negative = fewer (good)
                json_change = (
                    (json_tokens / stats.original_tokens - 1) * 100
                    if stats.original_tokens > 0
                    else 0
                )
                json_delta = f"{json_change:+.0f}%" if json_change != 0 else None
                st.metric(
                    "JSON Output",
                    f"{json_tokens:,} tokens",
                    delta=json_delta,
                    delta_color="inverse",
                )

            # Compact action buttons - single row using only Streamlit buttons
            btn_cols = st.columns(3)
            with btn_cols[0]:
                st.download_button(
                    "Save MD",
                    data=result.markdown,
                    file_name="log-analysis.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with btn_cols[1]:
                st.download_button(
                    "Save JSON",
                    data=json_str,
                    file_name="log-analysis.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with btn_cols[2]:
                if st.button("Clear", use_container_width=True):
                    del st.session_state["analysis_result"]
                    st.rerun()

            # Show markdown in code block with built-in copy button
            st.code(result.markdown, language="markdown")
        else:
            st.info("Paste logs and click **Analyze** to see results")


if __name__ == "__main__":
    main()
