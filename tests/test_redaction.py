"""Tests for the correlation-preserving redaction module."""

from pathlib import Path

from log_essence.redaction import (
    RedactionMode,
    is_valid_credit_card,
    redact_line,
    redact_lines,
)
from log_essence.server import get_logs


class TestLuhnValidation:
    """Tests for credit card Luhn algorithm validation."""

    def test_valid_visa(self) -> None:
        assert is_valid_credit_card("4111111111111111") is True

    def test_valid_mastercard(self) -> None:
        assert is_valid_credit_card("5500000000000004") is True

    def test_valid_amex(self) -> None:
        assert is_valid_credit_card("378282246310005") is True

    def test_invalid_checksum(self) -> None:
        assert is_valid_credit_card("4111111111111112") is False

    def test_too_short(self) -> None:
        assert is_valid_credit_card("411111111111") is False

    def test_non_numeric(self) -> None:
        assert is_valid_credit_card("4111-1111-1111") is False


class TestEmailRedaction:
    """Tests for email address redaction."""

    def test_basic_email(self) -> None:
        result = redact_line("user@example.com logged in")
        assert "user@example.com" not in result
        assert "[EMAIL:" in result
        assert "] logged in" in result

    def test_multiple_emails_same_hash(self) -> None:
        result = redact_line("user@acme.com sent to user@acme.com")
        # Same email should produce same hash
        parts = result.split("[EMAIL:")
        assert len(parts) == 3
        hash1 = parts[1].split("]")[0]
        hash2 = parts[2].split("]")[0]
        assert hash1 == hash2

    def test_different_emails_different_hashes(self) -> None:
        result = redact_line("alice@acme.com to bob@acme.com")
        parts = result.split("[EMAIL:")
        hash1 = parts[1].split("]")[0]
        hash2 = parts[2].split("]")[0]
        assert hash1 != hash2

    def test_complex_email(self) -> None:
        result = redact_line("Contact user.name+tag@sub.example.co.uk")
        assert "[EMAIL:" in result


class TestIPv4Redaction:
    """Tests for IPv4 address redaction."""

    def test_basic_ipv4(self) -> None:
        result = redact_line("Connection from 192.168.1.50")
        assert "192.168.1.50" not in result
        assert "[IPV4:" in result

    def test_preserves_correlation(self) -> None:
        result = redact_line("192.168.1.50 pinged 192.168.1.50")
        parts = result.split("[IPV4:")
        hash1 = parts[1].split("]")[0]
        hash2 = parts[2].split("]")[0]
        assert hash1 == hash2

    def test_different_ips_different_hashes(self) -> None:
        result = redact_line("192.168.1.1 to 10.0.0.1")
        parts = result.split("[IPV4:")
        hash1 = parts[1].split("]")[0]
        hash2 = parts[2].split("]")[0]
        assert hash1 != hash2


class TestIPv6Redaction:
    """Tests for IPv6 address redaction."""

    def test_full_ipv6(self) -> None:
        result = redact_line("From 2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        assert "[IPV6:" in result

    def test_compressed_ipv6(self) -> None:
        result = redact_line("From ::1 localhost")
        assert "[IPV6:" in result

    def test_ipv6_loopback(self) -> None:
        result = redact_line("Listening on ::1")
        assert "[IPV6:" in result


class TestCreditCardRedaction:
    """Tests for credit card number redaction."""

    def test_valid_cc_with_spaces(self) -> None:
        result = redact_line("Card: 4111 1111 1111 1111")
        assert "4111" not in result
        assert "[CC:" in result

    def test_valid_cc_with_dashes(self) -> None:
        result = redact_line("Card: 4111-1111-1111-1111")
        assert "[CC:" in result

    def test_valid_cc_continuous(self) -> None:
        result = redact_line("Payment for 4111111111111111")
        assert "[CC:" in result

    def test_invalid_cc_not_redacted(self) -> None:
        # Invalid Luhn checksum - should NOT be redacted
        result = redact_line("Number: 1234567890123456")
        # Should remain as-is since it fails Luhn check
        assert "1234567890123456" in result


class TestSSNRedaction:
    """Tests for Social Security Number redaction."""

    def test_ssn_format(self) -> None:
        result = redact_line("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert "[SSN:" in result

    def test_ssn_without_dashes_not_redacted(self) -> None:
        # Only match xxx-xx-xxxx format
        result = redact_line("ID: 123456789")
        # This is ambiguous - could be anything, so don't redact
        assert "[SSN:" not in result


class TestPhoneRedaction:
    """Tests for phone number redaction."""

    def test_us_phone_with_dashes(self) -> None:
        result = redact_line("Call 555-123-4567")
        assert "[PHONE:" in result

    def test_us_phone_with_parens(self) -> None:
        result = redact_line("Contact (555) 123-4567")
        assert "[PHONE:" in result

    def test_international_phone(self) -> None:
        result = redact_line("Dial +1-555-123-4567")
        assert "[PHONE:" in result


class TestJWTRedaction:
    """Tests for JWT token redaction."""

    def test_jwt_token(self) -> None:
        # A typical JWT structure (header.payload.signature)
        token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
            "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        )
        result = redact_line(f"Bearer {token}")
        assert "eyJ" not in result
        assert "[JWT:" in result


class TestAPIKeyRedaction:
    """Tests for API key redaction."""

    def test_aws_access_key(self) -> None:
        result = redact_line("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[AWS_KEY:" in result

    def test_aws_secret_key(self) -> None:
        result = redact_line("aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
        assert "[SECRET:" in result

    def test_github_token(self) -> None:
        # GitHub tokens: ghp_ (classic) or ghs_ (app) followed by 36+ alphanumerics
        result = redact_line("export GITHUB_TOKEN=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")
        assert "[GITHUB_TOKEN:" in result
        assert "ghp_" not in result

    def test_github_token_in_log_message(self) -> None:
        # GitHub token in a log line (common leak scenario)
        result = redact_line("Using token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij for auth")
        assert "[GITHUB_TOKEN:" in result
        assert "ghp_" not in result

    def test_stripe_key(self) -> None:
        # Construct key dynamically to avoid GitHub secret scanning
        key = "sk_" + "live_" + "0" * 24
        result = redact_line(f"stripe_key={key}")
        assert "[STRIPE_KEY:" in result

    def test_stripe_test_key(self) -> None:
        # Construct key dynamically to avoid GitHub secret scanning
        key = "sk_" + "test_" + "0" * 24
        result = redact_line(f"key={key}")
        assert "[STRIPE_KEY:" in result


class TestConnectionStringRedaction:
    """Tests for database connection string redaction."""

    def test_postgres_url(self) -> None:
        result = redact_line("DATABASE_URL=postgres://user:password@host:5432/db")
        assert "password" not in result
        assert "[CONN_STRING:" in result

    def test_mongodb_url(self) -> None:
        result = redact_line("MONGO=mongodb://admin:secret@localhost:27017")
        assert "secret" not in result
        assert "[CONN_STRING:" in result

    def test_redis_url(self) -> None:
        result = redact_line("REDIS_URL=redis://:mypassword@redis.example.com:6379")
        assert "mypassword" not in result


class TestBearerTokenRedaction:
    """Tests for Bearer token redaction."""

    def test_bearer_token(self) -> None:
        result = redact_line("Authorization: Bearer abc123def456ghi789")
        assert "abc123def456ghi789" not in result
        assert "[BEARER:" in result


class TestPrivateKeyRedaction:
    """Tests for private key redaction."""

    def test_rsa_key_header(self) -> None:
        result = redact_line("-----BEGIN RSA PRIVATE KEY-----")
        assert "[PRIVATE_KEY:" in result

    def test_generic_key_header(self) -> None:
        result = redact_line("-----BEGIN PRIVATE KEY-----")
        assert "[PRIVATE_KEY:" in result


class TestGenericSecretRedaction:
    """Tests for high-entropy generic secret detection."""

    def test_api_secret_in_key_value(self) -> None:
        line = "api_secret=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        result = redact_line(line, mode=RedactionMode.STRICT)
        assert "[SECRET:" in result

    def test_password_in_key_value(self) -> None:
        result = redact_line('password="SuperSecretP@ssw0rd123!"', mode=RedactionMode.STRICT)
        assert "[SECRET:" in result


class TestRedactionModes:
    """Tests for different redaction strictness levels."""

    def test_disabled_mode(self) -> None:
        line = "user@example.com from 192.168.1.1"
        result = redact_line(line, mode=RedactionMode.DISABLED)
        assert result == line

    def test_minimal_mode_only_obvious(self) -> None:
        # Minimal should only catch very obvious secrets
        # Bearer tokens require 10+ character token
        line = "Bearer abc123def456ghi789 and user@email.com"
        result = redact_line(line, mode=RedactionMode.MINIMAL)
        # Bearer tokens are obvious secrets
        assert "[BEARER:" in result
        # Emails are NOT caught in minimal mode
        assert "user@email.com" in result

    def test_moderate_mode_default(self) -> None:
        result = redact_line("user@email.com from 192.168.1.1")
        assert "[EMAIL:" in result
        assert "[IPV4:" in result

    def test_strict_mode_catches_more(self) -> None:
        # Strict mode should catch high-entropy strings
        result = redact_line("token=xK9mN2pL5qR8sT1vW4yZ", mode=RedactionMode.STRICT)
        assert "[SECRET:" in result


class TestRedactLines:
    """Tests for batch line redaction."""

    def test_preserves_correlation_across_lines(self) -> None:
        lines = [
            "user@acme.com logged in from 192.168.1.50",
            "Error processing payment for user@acme.com card 4111111111111111",
            "Request from 192.168.1.50 timed out",
        ]
        result, redaction_count = redact_lines(lines)

        # Same email should have same hash across lines
        email_hashes = []
        for line in result:
            if "[EMAIL:" in line:
                hash_part = line.split("[EMAIL:")[1].split("]")[0]
                email_hashes.append(hash_part)
        assert len(set(email_hashes)) == 1  # All same hash

        # Same IP should have same hash across lines
        ip_hashes = []
        for line in result:
            if "[IPV4:" in line:
                hash_part = line.split("[IPV4:")[1].split("]")[0]
                ip_hashes.append(hash_part)
        assert len(set(ip_hashes)) == 1  # All same hash

        # Should have counted the redactions (2 emails, 1 CC, 2 IPs = 5)
        assert redaction_count == 5

    def test_empty_lines_preserved(self) -> None:
        lines = ["line1", "", "line2"]
        result, redaction_count = redact_lines(lines)
        assert len(result) == 3
        assert result[1] == ""
        assert redaction_count == 0


class TestOutputFormat:
    """Tests for the redaction output format."""

    def test_email_format(self) -> None:
        result = redact_line("user@example.com")
        # Format: [EMAIL:hash4]
        import re

        assert re.search(r"\[EMAIL:[a-f0-9]{4}\]", result)

    def test_credit_card_format_includes_length(self) -> None:
        result = redact_line("Card: 4111111111111111")
        # Format: [CC:length:hash4]
        import re

        assert re.search(r"\[CC:\d+:[a-f0-9]{4}\]", result)

    def test_secret_format_includes_length(self) -> None:
        # GitHub tokens include length in format
        result = redact_line("ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij")
        # Secrets should include length for debugging
        import re

        assert re.search(r"\[GITHUB_TOKEN:\d+:[a-f0-9]{4}\]", result)


class TestHashConsistency:
    """Tests for hash consistency and properties."""

    def test_hash_is_4_chars(self) -> None:
        result = redact_line("user@test.com")
        hash_part = result.split("[EMAIL:")[1].split("]")[0]
        assert len(hash_part) == 4

    def test_hash_is_hex(self) -> None:
        result = redact_line("user@test.com")
        hash_part = result.split("[EMAIL:")[1].split("]")[0]
        assert all(c in "0123456789abcdef" for c in hash_part)

    def test_same_value_same_hash_different_calls(self) -> None:
        result1 = redact_line("user@test.com")
        result2 = redact_line("user@test.com")
        assert result1 == result2


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_string(self) -> None:
        assert redact_line("") == ""

    def test_no_sensitive_data(self) -> None:
        line = "INFO: Server started successfully"
        assert redact_line(line) == line

    def test_mixed_content(self) -> None:
        line = "2025-01-01T10:00:00Z INFO user@test.com connected from 192.168.1.1"
        result = redact_line(line)
        assert "2025-01-01T10:00:00Z INFO" in result
        assert "[EMAIL:" in result
        assert "[IPV4:" in result
        assert "connected from" in result

    def test_url_with_credentials(self) -> None:
        result = redact_line("Connecting to https://user:pass@api.example.com/endpoint")
        # Should redact the credentials
        assert "pass@" not in result


class TestIntegration:
    """Integration tests with the main get_logs function."""

    def test_get_logs_with_redaction_enabled(self, tmp_path: Path) -> None:
        log_file = tmp_path / "sensitive.log"
        log_file.write_text(
            """2025-01-01T10:00:00Z INFO user@acme.com logged in
2025-01-01T10:00:01Z INFO Request from 192.168.1.50
2025-01-01T10:00:02Z ERROR Payment failed for card 4111111111111111
"""
        )

        result = get_logs.fn(path=str(log_file), redact=True)
        assert "user@acme.com" not in result
        assert "192.168.1.50" not in result
        assert "4111111111111111" not in result
        assert "[EMAIL:" in result
        assert "[IPV4:" in result
        assert "[CC:" in result

    def test_get_logs_with_redaction_disabled(self, tmp_path: Path) -> None:
        log_file = tmp_path / "sensitive.log"
        log_file.write_text("2025-01-01T10:00:00Z INFO user@acme.com\n")

        result = get_logs.fn(path=str(log_file), redact=False)
        # Original email should be present
        assert "user@acme.com" in result

    def test_get_logs_strict_mode(self, tmp_path: Path) -> None:
        log_file = tmp_path / "secrets.log"
        log_file.write_text("2025-01-01T10:00:00Z token=xK9mN2pL5qR8sT1vW4yZ\n")

        result = get_logs.fn(path=str(log_file), redact="strict")
        assert "xK9mN2pL5qR8sT1vW4yZ" not in result

    def test_get_logs_minimal_mode(self, tmp_path: Path) -> None:
        log_file = tmp_path / "logs.log"
        # Bearer tokens need 10+ characters to be detected
        log_file.write_text("2025-01-01T10:00:00Z Authorization: Bearer secret12345678\n")

        result = get_logs.fn(path=str(log_file), redact="minimal")
        assert "[BEARER:" in result
