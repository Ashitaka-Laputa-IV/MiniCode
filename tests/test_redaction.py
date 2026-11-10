from pathlib import Path

import pytest

from minicode.redaction import display_args, redact_text, redact_value, summarize_args


@pytest.mark.parametrize(
    "text",
    [
        "key=sk-abcdefghijklmnopqrstuvwxyz",
        "token=ghp_abcdefghijklmnopqrstuvwxyz012345",
        "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz",
        "slack=xoxb-1234567890-abcdefghij",
        "aws=AKIAIOSFODNN7EXAMPLE",
        "google=AIzaSyA1234567890abcdefghijklmnopqrstu",
    ],
)
def test_known_token_formats_are_redacted(text: str) -> None:
    assert "***" in redact_text(text)
    assert "abcdefghij" not in redact_text(text)


def test_env_assignment_is_redacted() -> None:
    redacted = redact_text("DEEPSEEK_API_KEY=sk-live-secret")

    assert redacted == "DEEPSEEK_API_KEY=***"


def test_authorization_header_is_redacted() -> None:
    redacted = redact_text("curl -H 'Authorization: Bearer abcdefghijklmnop'")

    assert "abcdefghijklmnop" not in redacted
    assert "***" in redacted


def test_authorization_basic_scheme_is_redacted() -> None:
    redacted = redact_text("Authorization: Basic dXNlcjpwYXNzd29yZA==")

    assert "dXNlcjpwYXNzd29yZA" not in redacted
    assert redacted == "Authorization: ***"


def test_quoted_assignment_with_spaces_is_redacted() -> None:
    redacted = redact_text('password="my secret phrase"')

    assert "my secret phrase" not in redacted
    assert redacted == 'password="***"'


@pytest.mark.parametrize(
    "text",
    [
        '{"token": "SECRETVALUE123"}',
        "{'password': 'SECRETVALUE123'}",
        '{"api_key": "SECRETVALUE123"}',
    ],
)
def test_quoted_json_keys_are_redacted(text: str) -> None:
    redacted = redact_text(text)

    assert "SECRETVALUE123" not in redacted
    assert redacted.count("***") == 1


def test_url_password_is_redacted() -> None:
    redacted = redact_text("https://user:supersecret@example.com/repo")

    assert "supersecret" not in redacted
    assert redacted == "https://user:***@example.com/repo"


def test_cli_secret_argument_is_redacted() -> None:
    redacted = redact_text("tool --api-key abc123 --token=xyz")

    assert "abc123" not in redacted
    assert "xyz" not in redacted


def test_redact_value_recurses() -> None:
    value = {
        "command": "curl -H 'Authorization: Bearer abcdefghijklmnop'",
        "items": ["sk-abcdefghijklmnopqrstuvwxyz"],
        "ok": True,
        "count": 3,
    }

    redacted = redact_value(value)

    assert "abcdefghijklmnop" not in str(redacted)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in str(redacted)
    assert redacted["ok"] is True
    assert redacted["count"] == 3


def test_summarize_execute_redacts_command() -> None:
    summary = summarize_args(
        "execute",
        {"command": "curl -H 'Authorization: Bearer abcdefghijklmnop'"},
    )

    assert "abcdefghijklmnop" not in summary["command"]
    assert "***" in summary["command"]


def test_summarize_write_omits_content() -> None:
    content = "sk-abcdefghijklmnopqrstuvwxyz"
    summary = summarize_args(
        "write_file",
        {"file_path": "/src/parser.py", "content": content},
    )

    assert summary["file_path"] == "/src/parser.py"
    assert summary["content_bytes"] == len(content)
    assert "content" not in summary
    assert "abcdefghij" not in str(summary)


def test_summarize_write_counts_utf8_bytes() -> None:
    summary = summarize_args("write_file", {"file_path": "/notes.txt", "content": "你好"})

    assert summary["content_bytes"] == 6


def test_summarize_edit_omits_strings() -> None:
    summary = summarize_args(
        "edit_file",
        {
            "file_path": "/src/parser.py",
            "old_string": "old",
            "new_string": "new",
            "replace_all": True,
        },
    )

    assert summary == {
        "file_path": "/src/parser.py",
        "old_bytes": 3,
        "new_bytes": 3,
        "replace_all": True,
    }


def test_display_args_adds_redacted_preview() -> None:
    display = display_args(
        "write_file",
        {"file_path": "/notes.txt", "content": "sk-abcdefghijklmnopqrstuvwxyz\nmore"},
    )

    assert display["content_preview"].startswith("***")
    assert "abcdefghij" not in display["content_preview"]


def test_display_args_truncates_preview() -> None:
    display = display_args("write_file", {"file_path": "/notes.txt", "content": "x" * 300})

    assert display["content_preview"].endswith("...")
    assert len(display["content_preview"]) == 203


def test_display_args_preview_is_redacted_before_truncating() -> None:
    display = display_args(
        "write_file",
        {"file_path": "/notes.txt", "content": "prefix sk-abcdefghijklmnopqrstuvwxyz suffix"},
    )

    assert "prefix *** suffix" == display["content_preview"]


def test_display_args_redacts_secret_across_preview_boundary() -> None:
    content = "x" * 195 + "sk-abcdefghijklmnopqrstuvwxyz"
    display = display_args("write_file", {"file_path": "/notes.txt", "content": content})

    assert "sk-" not in display["content_preview"]
    assert "***" in display["content_preview"]


def test_summarize_unknown_tool_redacts_and_truncates() -> None:
    payload = "x" * 195 + "sk-abcdefghijklmnopqrstuvwxyz"
    summary = summarize_args("custom_tool", {"payload": payload})

    assert "sk-" not in summary["payload"]
    assert len(summary["payload"]) <= 200


def test_summarize_unknown_tool_respects_non_string_values() -> None:
    summary = summarize_args(
        "custom_tool",
        {"count": 3, "flag": True, "nested": {"token": "SECRETVALUE123"}},
    )

    assert summary["count"] == 3
    assert summary["flag"] is True
    assert "SECRETVALUE123" not in str(summary["nested"])


def test_summarize_unknown_tool_redacts_sensitive_keys() -> None:
    summary = summarize_args(
        "custom_tool",
        {"token": "SECRETVALUE123", "password": None, "note": "ok"},
    )

    assert summary["token"] == "***"
    assert summary["password"] is None
    assert summary["note"] == "ok"


def test_summarize_unknown_tool_truncates_nested_values() -> None:
    summary = summarize_args(
        "custom_tool",
        {"nested": {"values": ["x" * 300]}},
    )

    assert len(summary["nested"]["values"][0]) == 200


def test_normal_paths_are_not_mistaken_for_secrets() -> None:
    assert redact_text("cat docs/--output.md") == "cat docs/--output.md"
    assert redact_text(str(Path("src") / "minicode" / "cli.py")) == str(
        Path("src") / "minicode" / "cli.py"
    )
