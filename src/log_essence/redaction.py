"""Correlation-preserving secret and PII redaction for log analysis.

Redacts sensitive data before sending logs to external LLMs while preserving
correlation and debugging info through consistent hashing.

Output format: [TYPE:length?:hash4]
- TYPE: EMAIL, IPV4, IPV6, CC, SSN, PHONE, SECRET, API_KEY, JWT, etc.
- length: included for variable-length secrets (helps debugging)
- hash: 4-char consistent hash (correlatable, not reversible)
"""

from __future__ import annotations

import hashlib
import re
from enum import Enum


class RedactionMode(Enum):
    """Redaction strictness levels."""

    DISABLED = "disabled"
    MINIMAL = "minimal"  # Only obvious secrets (bearer tokens, API keys)
    MODERATE = "moderate"  # Default: emails, IPs, CC, SSN, phones + obvious secrets
    STRICT = "strict"  # All of the above + high-entropy strings in key=value context


def _compute_hash(value: str) -> str:
    """Compute a 4-character consistent hash for correlation.

    Uses MD5 (fast, collision-resistant enough for 4 chars) truncated to 4 hex chars.
    Same input always produces same output for correlation without reversibility.
    """
    return hashlib.md5(value.encode()).hexdigest()[:4]


def is_valid_credit_card(number: str) -> bool:
    """Validate credit card number using Luhn algorithm.

    Args:
        number: Credit card number (digits only, no spaces/dashes)

    Returns:
        True if the number passes Luhn validation and has valid length (13-19 digits)
    """
    # Must be numeric
    if not number.isdigit():
        return False

    # Valid CC lengths: 13-19 digits
    if not (13 <= len(number) <= 19):
        return False

    # Luhn algorithm
    digits = [int(d) for d in number]
    checksum = 0

    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit

    return checksum % 10 == 0


# Pre-compiled patterns for performance
# Order matters - more specific patterns should come before generic ones

# JWT: base64url encoded segments separated by dots
JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

# AWS Access Key ID: AKIA... (20 chars)
AWS_KEY_PATTERN = re.compile(r"AKIA[0-9A-Z]{16}")

# AWS Secret Key: 40 chars of base64-ish in secret context
AWS_SECRET_PATTERN = re.compile(
    r"(?:aws_secret_access_key|secret_access_key|aws_secret)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?",
    re.IGNORECASE,
)

# GitHub tokens (classic and fine-grained)
GITHUB_TOKEN_PATTERN = re.compile(r"gh[ps]_[A-Za-z0-9]{36,}")

# Stripe API keys
STRIPE_KEY_PATTERN = re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{24,}")

# Bearer tokens
BEARER_PATTERN = re.compile(r"Bearer\s+([A-Za-z0-9_\-./+=]{10,})", re.IGNORECASE)

# Private key headers
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN\s+(?:RSA\s+)?(?:EC\s+)?(?:DSA\s+)?(?:OPENSSH\s+)?PRIVATE\s+KEY-----"
)

# Connection strings with credentials
CONN_STRING_PATTERN = re.compile(
    r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:]+:([^@]+)@[^\s]+",
    re.IGNORECASE,
)

# URL with embedded credentials
URL_CREDS_PATTERN = re.compile(r"https?://([^:]+):([^@]+)@[^\s]+", re.IGNORECASE)

# Email addresses
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# IPv4 addresses
IPV4_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
)

# IPv6 addresses (simplified - catches most forms)
IPV6_PATTERN = re.compile(
    r"(?:(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|"
    r"(?:[0-9a-fA-F]{1,4}:){1,7}:|"
    r"::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}|"
    r"::)"
)

# Credit card patterns (with separators)
CC_PATTERN_SPACES = re.compile(r"\b(\d{4})\s+(\d{4})\s+(\d{4})\s+(\d{4})\b")
CC_PATTERN_DASHES = re.compile(r"\b(\d{4})-(\d{4})-(\d{4})-(\d{4})\b")
CC_PATTERN_CONTINUOUS = re.compile(r"\b(\d{13,19})\b")

# SSN (US format xxx-xx-xxxx)
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Phone numbers - require at least one separator or formatting to avoid
# matching random digit sequences like "1234567890123456"
PHONE_PATTERN = re.compile(
    r"(?:"
    r"\+?1[-.\s][0-9]{3}[-.\s][0-9]{3}[-.\s][0-9]{4}"  # +1-xxx-xxx-xxxx with separators
    r"|"
    r"\([0-9]{3}\)[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}"  # (xxx) xxx-xxxx with parens
    r"|"
    r"[0-9]{3}[-.\s][0-9]{3}[-.\s][0-9]{4}"  # xxx-xxx-xxxx with separators
    r")\b"
)

# Generic high-entropy secrets in key=value context
# Matches: key="value" or key=value where value is 8+ chars
# Use word boundary to avoid partial matches like "TOKEN" in "GITHUB_TOKEN"
SECRET_KEY_PATTERN = re.compile(
    r"\b(?:password|secret|api_?key|auth_?token|credential|private_?key)\s*[=:]\s*['\"]?([A-Za-z0-9!@#$%^&*()_+\-=\[\]{}|;:,.<>?/\\]{8,})['\"]?",
    re.IGNORECASE,
)

# High entropy string detection for strict mode
# Matches standalone or prefixed secret keywords with 16+ char values
HIGH_ENTROPY_PATTERN = re.compile(
    r"\b(?:\w*[_-]?)?(?:key|secret|token|password|auth|credential)\s*[=:]\s*['\"]?([A-Za-z0-9_\-./+=]{16,})['\"]?",
    re.IGNORECASE,
)


class PatternMatcher:
    """Pattern matching with consistent replacement."""

    def __init__(self) -> None:
        self.hash_cache: dict[str, str] = {}
        self.redaction_count: int = 0

    def get_hash(self, value: str) -> str:
        """Get or compute hash for a value, caching for consistency."""
        if value not in self.hash_cache:
            self.hash_cache[value] = _compute_hash(value)
        return self.hash_cache[value]

    def replace_with_placeholder(
        self, match: re.Match[str], ptype: str, include_length: bool = False
    ) -> str:
        """Create placeholder for matched value."""
        self.redaction_count += 1
        value = match.group(0)
        h = self.get_hash(value)
        if include_length:
            return f"[{ptype}:{len(value)}:{h}]"
        return f"[{ptype}:{h}]"

    def redact_jwt(self, text: str) -> str:
        """Redact JWT tokens."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "JWT", include_length=True)

        return JWT_PATTERN.sub(replace, text)

    def redact_aws_key(self, text: str) -> str:
        """Redact AWS access key IDs."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "AWS_KEY", include_length=True)

        return AWS_KEY_PATTERN.sub(replace, text)

    def redact_aws_secret(self, text: str) -> str:
        """Redact AWS secret access keys."""

        def replace(m: re.Match[str]) -> str:
            self.redaction_count += 1
            secret = m.group(1)
            h = self.get_hash(secret)
            prefix = m.group(0)[: m.start(1) - m.start(0)]
            return f"{prefix}[SECRET:{len(secret)}:{h}]"

        return AWS_SECRET_PATTERN.sub(replace, text)

    def redact_github_token(self, text: str) -> str:
        """Redact GitHub tokens."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "GITHUB_TOKEN", include_length=True)

        return GITHUB_TOKEN_PATTERN.sub(replace, text)

    def redact_stripe_key(self, text: str) -> str:
        """Redact Stripe API keys."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "STRIPE_KEY", include_length=True)

        return STRIPE_KEY_PATTERN.sub(replace, text)

    def redact_bearer(self, text: str) -> str:
        """Redact Bearer tokens."""

        def replace(m: re.Match[str]) -> str:
            self.redaction_count += 1
            token = m.group(1)
            h = self.get_hash(token)
            return f"Bearer [BEARER:{len(token)}:{h}]"

        return BEARER_PATTERN.sub(replace, text)

    def redact_private_key(self, text: str) -> str:
        """Redact private key headers."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "PRIVATE_KEY", include_length=False)

        return PRIVATE_KEY_PATTERN.sub(replace, text)

    def redact_connection_string(self, text: str) -> str:
        """Redact connection strings with credentials."""

        def replace(m: re.Match[str]) -> str:
            self.redaction_count += 1
            password = m.group(1)
            h = self.get_hash(password)
            full_match = m.group(0)
            # Replace just the password portion
            return full_match.replace(f":{password}@", f":[CONN_STRING:{len(password)}:{h}]@")

        return CONN_STRING_PATTERN.sub(replace, text)

    def redact_url_creds(self, text: str) -> str:
        """Redact credentials in URLs."""

        def replace(m: re.Match[str]) -> str:
            self.redaction_count += 1
            user = m.group(1)
            password = m.group(2)
            full_match = m.group(0)
            h = self.get_hash(password)
            # Replace user:pass with redacted version
            return full_match.replace(
                f"{user}:{password}@", f"[REDACTED_USER]:[SECRET:{len(password)}:{h}]@"
            )

        return URL_CREDS_PATTERN.sub(replace, text)

    def redact_email(self, text: str) -> str:
        """Redact email addresses."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "EMAIL", include_length=False)

        return EMAIL_PATTERN.sub(replace, text)

    def redact_ipv4(self, text: str) -> str:
        """Redact IPv4 addresses."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "IPV4", include_length=False)

        return IPV4_PATTERN.sub(replace, text)

    def redact_ipv6(self, text: str) -> str:
        """Redact IPv6 addresses."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "IPV6", include_length=False)

        return IPV6_PATTERN.sub(replace, text)

    def redact_credit_card(self, text: str) -> str:
        """Redact credit card numbers (with Luhn validation)."""

        def replace_with_validation(m: re.Match[str], separator: str = "") -> str:
            groups = m.groups()
            number = "".join(groups)
            if is_valid_credit_card(number):
                self.redaction_count += 1
                h = self.get_hash(number)
                return f"[CC:{len(number)}:{h}]"
            return m.group(0)

        # Try each pattern
        text = CC_PATTERN_SPACES.sub(lambda m: replace_with_validation(m), text)
        text = CC_PATTERN_DASHES.sub(lambda m: replace_with_validation(m), text)

        # For continuous digits, need to validate
        def replace_continuous(m: re.Match[str]) -> str:
            number = m.group(1)
            if is_valid_credit_card(number):
                self.redaction_count += 1
                h = self.get_hash(number)
                return f"[CC:{len(number)}:{h}]"
            return m.group(0)

        text = CC_PATTERN_CONTINUOUS.sub(replace_continuous, text)
        return text

    def redact_ssn(self, text: str) -> str:
        """Redact Social Security Numbers."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "SSN", include_length=False)

        return SSN_PATTERN.sub(replace, text)

    def redact_phone(self, text: str) -> str:
        """Redact phone numbers."""

        def replace(m: re.Match[str]) -> str:
            return self.replace_with_placeholder(m, "PHONE", include_length=False)

        return PHONE_PATTERN.sub(replace, text)

    def redact_secret_key_value(self, text: str) -> str:
        """Redact secrets in key=value patterns."""

        def replace(m: re.Match[str]) -> str:
            self.redaction_count += 1
            secret = m.group(1)
            h = self.get_hash(secret)
            prefix = m.group(0)[: m.start(1) - m.start(0)]
            return f"{prefix}[SECRET:{len(secret)}:{h}]"

        return SECRET_KEY_PATTERN.sub(replace, text)

    def redact_high_entropy(self, text: str) -> str:
        """Redact high-entropy strings in key=value context (strict mode)."""

        def replace(m: re.Match[str]) -> str:
            self.redaction_count += 1
            secret = m.group(1)
            h = self.get_hash(secret)
            prefix = m.group(0)[: m.start(1) - m.start(0)]
            return f"{prefix}[SECRET:{len(secret)}:{h}]"

        return HIGH_ENTROPY_PATTERN.sub(replace, text)


def redact_line(line: str, mode: RedactionMode = RedactionMode.MODERATE) -> str:
    """Redact sensitive data from a single log line.

    Args:
        line: The log line to redact
        mode: Redaction strictness level

    Returns:
        The line with sensitive data replaced by [TYPE:length?:hash4] placeholders
    """
    if not line or mode == RedactionMode.DISABLED:
        return line

    matcher = PatternMatcher()

    # Always redact these (obvious secrets) - MINIMAL mode and up
    line = matcher.redact_jwt(line)
    line = matcher.redact_aws_key(line)
    line = matcher.redact_aws_secret(line)
    line = matcher.redact_github_token(line)
    line = matcher.redact_stripe_key(line)
    line = matcher.redact_bearer(line)
    line = matcher.redact_private_key(line)
    line = matcher.redact_connection_string(line)
    line = matcher.redact_url_creds(line)

    if mode in (RedactionMode.MODERATE, RedactionMode.STRICT):
        # PII patterns
        line = matcher.redact_email(line)
        line = matcher.redact_ipv4(line)
        line = matcher.redact_ipv6(line)
        line = matcher.redact_credit_card(line)
        line = matcher.redact_ssn(line)
        line = matcher.redact_phone(line)
        line = matcher.redact_secret_key_value(line)

    if mode == RedactionMode.STRICT:
        # High entropy strings
        line = matcher.redact_high_entropy(line)

    return line


def redact_lines(
    lines: list[str], mode: RedactionMode = RedactionMode.MODERATE
) -> tuple[list[str], int]:
    """Redact sensitive data from multiple log lines with consistent hashing.

    Uses a shared PatternMatcher to ensure the same value gets the same hash
    across all lines (correlation preservation).

    Args:
        lines: List of log lines to redact
        mode: Redaction strictness level

    Returns:
        Tuple of (redacted lines, redaction count)
    """
    if mode == RedactionMode.DISABLED:
        return lines, 0

    # Shared matcher for consistent hashing across lines
    matcher = PatternMatcher()
    result: list[str] = []

    for line in lines:
        if not line:
            result.append(line)
            continue

        # Always redact these (obvious secrets) - MINIMAL mode and up
        line = matcher.redact_jwt(line)
        line = matcher.redact_aws_key(line)
        line = matcher.redact_aws_secret(line)
        line = matcher.redact_github_token(line)
        line = matcher.redact_stripe_key(line)
        line = matcher.redact_bearer(line)
        line = matcher.redact_private_key(line)
        line = matcher.redact_connection_string(line)
        line = matcher.redact_url_creds(line)

        if mode in (RedactionMode.MODERATE, RedactionMode.STRICT):
            # PII patterns
            line = matcher.redact_email(line)
            line = matcher.redact_ipv4(line)
            line = matcher.redact_ipv6(line)
            line = matcher.redact_credit_card(line)
            line = matcher.redact_ssn(line)
            line = matcher.redact_phone(line)
            line = matcher.redact_secret_key_value(line)

        if mode == RedactionMode.STRICT:
            # High entropy strings
            line = matcher.redact_high_entropy(line)

        result.append(line)

    return result, matcher.redaction_count
