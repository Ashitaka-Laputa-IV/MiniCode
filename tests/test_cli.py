from minicode.cli import build_parser, message_text, short_json


def test_message_text_string() -> None:
    assert message_text("hello") == "hello"


def test_message_text_content_blocks() -> None:
    message = {
        "content": [
            {"type": "text", "text": "first"},
            {"type": "text", "text": "second"},
        ]
    }
    assert message_text(message) == "first\nsecond"


def test_short_json_truncates() -> None:
    assert short_json({"key": "value"}) == '{"key": "value"}'
    assert short_json("x" * 200, limit=10).endswith("...")


def test_parser_defaults() -> None:
    args = build_parser().parse_args(["fix", "the", "bug"])
    assert args.prompt == ["fix", "the", "bug"]
    assert args.model is None
    assert args.root == "."
    assert args.debug is False


def test_parser_root_and_model() -> None:
    args = build_parser().parse_args(
        ["--model", "deepseek:deepseek-chat", "--root", "workspace", "task"]
    )
    assert args.model == "deepseek:deepseek-chat"
    assert args.root == "workspace"
