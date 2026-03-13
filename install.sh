#!/bin/sh
# log-essence installer
# Usage: curl -fsSL https://raw.githubusercontent.com/petebytes/log-essence/main/install.sh | sh
set -e

PACKAGE="log-essence"
MIN_PYTHON_VERSION="3.11"

echo "Installing $PACKAGE..."

# Check Python version
check_python() {
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

PYTHON=$(check_python) || {
    echo "Error: Python >= $MIN_PYTHON_VERSION is required but not found."
    echo "Install Python from https://www.python.org/downloads/"
    exit 1
}

echo "Found Python: $PYTHON ($($PYTHON --version))"

# Try uvx first (fastest, isolated)
if command -v uvx >/dev/null 2>&1; then
    echo "Installing with uvx..."
    uvx install "$PACKAGE"
    echo "Done! Verify with: log-essence --version"
    exit 0
fi

# Try pipx (isolated environment)
if command -v pipx >/dev/null 2>&1; then
    echo "Installing with pipx..."
    pipx install "$PACKAGE"
    echo "Done! Verify with: log-essence --version"
    exit 0
fi

# Fall back to pip
echo "Neither uvx nor pipx found. Installing with pip..."
echo "Consider installing uv (https://docs.astral.sh/uv/) for better package management."
$PYTHON -m pip install --user "$PACKAGE"

echo ""
echo "Done! Verify with: log-essence --version"
echo ""
echo "Quick start:"
echo "  log-essence /var/log/system.log     # Analyze logs"
echo "  log-essence serve                   # Run as MCP server"
echo "  log-essence init                    # Configure AI tools"
echo "  log-essence stats                   # View analytics"
