from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from .agent import DEFAULT_MODEL, build_agent, resolve_model


def message_text(message: Any) -> str:
    """Return the text content of a LangChain message."""
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

    prompt = " ".join(args.prompt).strip()
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        parser.error("provide a task, e.g. minicode \"fix the failing test\"")

    try:
        model_name = resolve_model(args.model)
        provider_keys = {
            "anthropic:": "ANTHROPIC_API_KEY",
            "deepseek:": "DEEPSEEK_API_KEY",
            "openai:": "OPENAI_API_KEY",
        }
        for prefix, env_name in provider_keys.items():
            if model_name.startswith(prefix) and not os.getenv(env_name):
                print(
                    f"minicode: {env_name} is not set. "
                    f"Export it, or pass --model for another provider.",
                    file=sys.stderr,
                )
                return 1

        agent = build_agent(model=model_name, root=args.root, debug=args.debug)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": prompt}]}
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        if args.debug:
            raise
        print(f"minicode: {exc}", file=sys.stderr)
        return 1

    messages = result.get("messages", [])
    if messages:
        print(message_text(messages[-1]))
    return 0
