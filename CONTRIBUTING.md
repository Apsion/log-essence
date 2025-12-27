# Contributing to log-essence

Thanks for your interest in contributing! This document covers the development workflow and guidelines.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/petebytes/log-essence
cd log-essence

# Install dependencies (requires uv)
uv sync --all-groups

# Verify setup
uv run pytest
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feat/your-feature-name
```

### 2. Write Tests First (TDD)

We follow test-driven development. Write a failing test before implementing:

```bash
# Run tests in watch mode during development
uv run pytest tests/test_server.py -v --tb=short
```

### 3. Implement Your Changes

Key directories:
- `src/log_essence/` - Main source code
- `src/log_essence/server.py` - MCP tools and core analysis
- `src/log_essence/redaction.py` - Secret/PII redaction
- `src/log_essence/cli.py` - Command-line interface
- `src/log_essence/ui/` - Streamlit web interface
- `tests/` - Test suite

### 4. Run Quality Checks

```bash
# Run all tests
uv run pytest

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

### 5. Commit Your Changes

We use [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: add support for nginx error logs"
git commit -m "fix: handle empty log files gracefully"
git commit -m "test: add coverage for IPv6 redaction"
git commit -m "refactor: extract timestamp parsing logic"
git commit -m "docs: update MCP server configuration"
```

Commit types:
- `feat:` - New feature
- `fix:` - Bug fix
- `test:` - Adding or updating tests
- `refactor:` - Code change that neither fixes a bug nor adds a feature
- `docs:` - Documentation only
- `chore:` - Maintenance tasks

### 6. Submit a Pull Request

Push your branch and open a PR against `main`.

## Code Style

### Python

- **Type hints required** - Use strict typing, avoid `Any`
- **Pydantic for models** - Use Pydantic v2 for data validation
- **Early returns** - Prefer early returns over nested conditionals
- **Options objects** - Use dataclasses/Pydantic for function parameters when >3 args

### Example

```python
# Good
def analyze_logs(
    lines: list[str],
    *,
    token_budget: int = 8000,
    redact: bool = True,
) -> AnalysisResult:
    if not lines:
        return AnalysisResult(markdown="No logs found", stats=empty_stats())

    # ... implementation
    return result

# Avoid
def analyze_logs(lines, token_budget=8000, redact=True):  # No types
    if lines:  # Nested instead of early return
        # ... deep nesting
        pass
    return None
```

## Testing Guidelines

### Test Structure

```python
class TestFeatureName:
    """Group related tests in classes."""

    def test_basic_case(self) -> None:
        """Test the happy path."""
        result = my_function(valid_input)
        assert result.status == "success"

    def test_edge_case(self) -> None:
        """Test boundary conditions."""
        result = my_function(empty_input)
        assert result.status == "empty"

    def test_error_handling(self) -> None:
        """Test error conditions."""
        with pytest.raises(ValueError, match="invalid"):
            my_function(invalid_input)
```

### What to Test

- **Redaction**: Any new pattern must have tests for detection and correlation
- **Log formats**: New format support needs detection and parsing tests
- **MCP tools**: Integration tests that verify tool behavior end-to-end
- **CLI**: Argument parsing and output format tests

## Adding New Features

### New Log Format

1. Add regex pattern to `LOG_PATTERNS` in `server.py`
2. Add format detection test in `test_server.py`
3. Update README if user-facing

### New Redaction Pattern

1. Add pattern to appropriate category in `redaction.py`
2. Add tests for:
   - Basic detection
   - Correlation preservation (same value → same hash)
   - Edge cases (partial matches, false positives)
3. Update README redaction section

### New MCP Tool

1. Add function with `@mcp.tool()` decorator in `server.py`
2. Include comprehensive docstring (used for tool description)
3. Add integration tests
4. Update README with usage example

## Questions?

Open an issue for questions or discussion before starting large changes.
