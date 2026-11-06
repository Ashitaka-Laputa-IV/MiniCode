from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from dotenv import dotenv_values, find_dotenv

from .agent import DEFAULT_MODEL, build_agent

ENV_ALLOWLIST = {
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "FIREWORKS_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "MINICODE_MODEL",
    "MISTRAL_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY",
}


def load_env() -> str | None:
    """Load safe values from the nearest .env without overriding the shell."""
    path = find_dotenv(usecwd=True)
    if not path:
        return None
    for key, value in dotenv_values(path).items():
        if value and value.strip() and key in ENV_ALLOWLIST:
            os.environ.setdefault(key, value.strip())
    return path


def message_text(message: Any) -> str:
    """Return the text content of a LangChain message."""
    if isinstance(message, dict):
        content = message.get("content", message)
    else:
        content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return str(content)


def short_json(value: Any, limit: int = 160) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def print_update(update: Any) -> Any:
    """Print tool activity from one stream update; return the last AI message."""
    if not isinstance(update, dict):
        return None

    final = None
    for node_update in update.values():
        if not isinstance(node_update, dict):
            continue
        messages = node_update.get("messages")
        if not isinstance(messages, list):
            continue

        for message in messages:
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                for call in tool_calls:
                    name = call.get("name", "tool") if isinstance(call, dict) else "tool"
                    args = call.get("args", {}) if isinstance(call, dict) else {}
                    print(f"-> {name} {short_json(args)}", file=sys.stderr, flush=True)
            elif getattr(message, "type", None) == "tool":
                name = getattr(message, "name", "tool")
                text = message_text(message).strip().replace("\n", " ")
                print(f"<- {name}: {text[:200]}", file=sys.stderr, flush=True)
            elif getattr(message, "type", None) == "ai":
                final = message
    return final


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minicode",
        description="Run a minimal Deep Agents coding agent in a workspace.",
    )
    parser.add_argument("prompt", nargs="*", help="task for the agent")
    parser.add_argument(
        "--model",
        default=None,
        help=f"LangChain model, e.g. deepseek:deepseek-chat (default: $MINICODE_MODEL or {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="workspace root (default: current directory)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable Deep Agents debug logging",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env_path = load_env()
    if args.debug and env_path:
        print(f"minicode: loaded env from {env_path}", file=sys.stderr)

    prompt = " ".join(args.prompt).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        parser.error("provide a task, e.g. minicode \"fix the failing test\"")

    try:
        agent = build_agent(model=args.model, root=args.root, debug=args.debug)
        final_message = None
        for update in agent.stream(
            {"messages": [{"role": "user", "content": prompt}]},
            stream_mode="updates",
        ):
            message = print_update(update)
            if message is not None:
                final_message = message
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        if args.debug:
            raise
        text = str(exc).lower()
        if (
            "api key" in text
            or "api_key" in text
            or "authentication" in text
            or "unauthorized" in text
        ):
            print(
                "minicode: provider API key is missing or invalid. "
                "Set it for the selected model, or pass --model for another provider.",
                file=sys.stderr,
            )
        else:
            print(f"minicode: {exc}", file=sys.stderr)
        return 1

    if final_message is not None:
        print(message_text(final_message))
    return 0
