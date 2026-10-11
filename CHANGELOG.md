# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0b9] - 2026-10-11

### Added
- Per-cluster retrieval: `get_raw_logs(cluster_id=N)` returns the raw lines behind one cluster, backed by a per-template line-index map persisted in the tee cache.
- Cluster retrieval for the Docker, container and journald log tools.
- `get_logs` output ends with a shared retrieval trailer and a cluster hint, so an agent knows how to drill into a cluster.

### Security
- cryptography 50.0.1 and joserfc 1.7.5 (transitive), clearing 4 high-severity advisories; plus routine updates to mcp, starlette, pyjwt, urllib3, anyio, gitpython, pillow, pydantic-settings and python-multipart.

### Changed
- The repository moved to the Apsion organization: https://github.com/Apsion/log-essence. Old URLs redirect.
- CI runs on self-hosted runners.

## [0.1.0b8] - 2026-04-29

### Fixed
- `ui` under uvx: detect the uvx persistent tool install path.

## [0.1.0b7] - 2026-04-28

### Changed
- Replaced the drain3 dependency with a vendored minimal Drain implementation.

## [0.1.0b6] - 2026-04-28

### Fixed
- `ui` auto-bootstraps streamlit when run via uvx.

## [0.1.0b5] - 2026-04-13

### Fixed
- Severity and timestamp extraction guard `json.loads` results that are not objects.

## [0.1.0b4] - 2026-03-13

### Added
- Subcommands: `analytics`, `discover` and `init`.

### Fixed
- Compatibility with the FastMCP API change (removed `.fn` accessor in tests); `StrEnum` instead of `str` + `Enum`.

## [0.1.0b3] - 2025-12-27

### Changed
- README no longer states specific compression percentages.

## [0.1.0b2] - 2025-12-27

### Added
- Automated PyPI publishing, with the version taken from the git tag.

## [0.1.0b1] - 2025-12-27

Initial beta release of log-essence.

### Added

#### Core Analysis
- MCP server with `get_logs` tool using FastMCP framework
- Drain3 template extraction for log pattern recognition
- FastEmbed semantic clustering with k-means algorithm
- Auto-detection of log formats: JSON, syslog, Apache, nginx, Docker, Kubernetes
- Markdown output with configurable token budget enforcement
- Severity filtering (ERROR, WARNING, INFO, DEBUG)
- Time filtering with `--since` flag (durations like `1h`, `30m` or ISO dates)
- Glob pattern support for analyzing multiple files

#### Multi-Source Support
- `get_docker_logs` - analyze Docker Compose service logs with auto-discovery
- `get_container_logs` - analyze standalone Docker container logs
- `list_containers` - list running Docker containers
- `get_journald_logs` - analyze systemd journal logs
- `list_docker_services` - list Docker Compose services

#### Causality & Intelligence
- `get_error_chain` - trace error root causes with temporal proximity analysis
- `search_logs` - semantic search using AI embeddings
- Stack trace extraction for Python, Java, JavaScript, Go, and Rust
- Exception type extraction and "Caused by:" pattern detection

#### Security
- Correlation-preserving secret/PII redaction before LLM analysis
- Redacts: emails, IPs (v4/v6), credit cards (Luhn validated), SSNs, phones
- Redacts: AWS keys, GitHub tokens, Stripe keys, JWTs, Bearer tokens
- Redacts: private keys, connection strings, URL credentials
- Three redaction modes: `strict`, `moderate` (default), `minimal`
- Consistent hashing enables debugging without exposing values
- Output format: `[TYPE:length?:hash4]` (e.g., `[EMAIL:a7f2]`)

#### CLI
- Standalone CLI mode: `log-essence /path/to/logs`
- MCP server mode: `log-essence --serve`
- Config file support with YAML and named profiles
- JSON output format: `-o json`
- Watch mode for continuous monitoring: `-w`

#### Web UI
- Streamlit-based web interface: `log-essence ui`
- Paste-and-copy workflow for quick analysis
- Real-time processing stats (time, tokens, redaction count, savings %)
- Copy to clipboard and download as markdown
- Configurable settings sidebar
- Optional dependency: `pip install log-essence[ui]`

#### Demo Generation
- Automated demo creation with Playwright
- OpenAI-compatible TTS for narration
- YAML-based demo scripts with Pydantic validation
- Optional dependency: `pip install log-essence[demo]`

#### Infrastructure
- GitHub Actions CI workflow (Python 3.11, 3.12, 3.13)
- PyPI publish workflow with trusted publishing
- Comprehensive test suite (140 tests)
- MIT license

### Technical Details

- **Token compression**: Significant reduction in log volume
- **Supported Python**: 3.11+
- **Dependencies**: fastmcp, drain3, fastembed, numpy, tiktoken, pyyaml

[0.1.0b9]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b9
[0.1.0b8]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b8
[0.1.0b7]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b7
[0.1.0b6]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b6
[0.1.0b5]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b5
[0.1.0b4]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b4
[0.1.0b3]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b3
[0.1.0b2]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b2
[0.1.0b1]: https://github.com/Apsion/log-essence/releases/tag/v0.1.0b1
