from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from dotenv import dotenv_values, find_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape

from .agent import (
    DEFAULT_MODEL,
    build_agent,
    close_checkpointer,
    resolve_model,
    resolve_root,
)

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


def print_update(update: Any, console: Console) -> Any:
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
                    console.print(
                        f"[bold cyan]->[/] [bold]{escape(str(name))}[/] "
                        f"[dim]{escape(short_json(args))}[/]"
                    )
            elif getattr(message, "type", None) == "tool":
                name = getattr(message, "name", "tool")
                text = message_text(message).strip().replace("\n", " ")
                console.print(
                    f"[green]<-[/] [bold]{escape(str(name))}[/] "
                    f"[dim]{escape(text[:200])}[/]"
                )
            elif getattr(message, "type", None) == "ai":
                final = message
    return final


def print_final(message: Any, output: Console) -> None:
    """Print the final answer as Markdown only on an interactive terminal."""
    text = message_text(message)
    if output.is_terminal:
        output.print(Markdown(text))
    else:
        output.print(text, markup=False, highlight=False, soft_wrap=True)


def print_error(console: Console, exc: Exception) -> None:
    text = str(exc).lower()
    if (
        "api key" in text
        or "api_key" in text
        or "authentication" in text
        or "unauthorized" in text
    ):
        console.print(
            "[red]minicode:[/] provider API key is missing or invalid. "
            "Set it for the selected model, or pass --model for another provider."
        )
    else:
        console.print(f"[red]minicode:[/] {escape(str(exc))}")


def run_turn(
    agent: Any,
    prompt: str,
    progress: Console,
    config: dict[str, Any],
) -> Any:
    """Run one user turn and return the final AI message."""
    final_message = None
    for update in agent.stream(
        {"messages": [{"role": "user", "content": prompt}]},
        config=config,
        stream_mode="updates",
    ):
        message = print_update(update, progress)
        if message is not None:
            final_message = message
    return final_message


def make_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def reset_thread(config: dict[str, Any], agent: Any) -> None:
    """Clear the current conversation while keeping its thread id."""
    thread_id = config["configurable"]["thread_id"]
    checkpointer = getattr(agent, "checkpointer", None)
    if checkpointer is not None:
        checkpointer.delete_thread(thread_id)


def interactive_loop(
    agent: Any,
    progress: Console,
    output: Console,
    config: dict[str, Any],
    debug: bool,
) -> int:
    """Run a simple REPL until EOF or /exit."""
    output.print(
        "[bold]Interactive mode[/] [dim]Type /help for commands, /exit to quit.[/]"
    )

    while True:
        try:
            prompt = output.input("[bold cyan]minicode>[/] ")
        except (EOFError, KeyboardInterrupt):
            output.print()
            return 0

        prompt = prompt.strip()
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return 0
        if prompt == "/help":
            output.print("[dim]Commands: /help, /reset, /exit, /quit[/]")
            continue
        if prompt == "/reset":
            reset_thread(config, agent)
            output.print("[dim]Context cleared.[/]")
            continue

        try:
            final_message = run_turn(agent, prompt, progress, config)
        except KeyboardInterrupt:
            reset_thread(config, agent)
            progress.print("[yellow]Interrupted. Context reset.[/]")
            continue
        except Exception as exc:
            if debug:
                raise
            reset_thread(config, agent)
            print_error(progress, exc)
            progress.print("[yellow]Context reset after the failed turn.[/]")
            continue

        if final_message is not None:
            print_final(final_message, output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minicode",
        description="Run a minimal Deep Agents coding agent in a workspace.",
        epilog="Task evals: minicode eval --help",
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
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="start an interactive REPL",
    )
    parser.add_argument(
        "--thread",
        default=None,
        help=(
            "conversation id for the SQLite checkpointer "
            "(default: default; use a unique value for parallel sessions)"
        ),
    )
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "SQLite checkpoint path, file only "
            "(default: <root>/.minicode/checkpoints.sqlite)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "eval":
        from .evals.cli import main as eval_main

        return eval_main(argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)
    env_path = load_env()
    progress = Console(stderr=True, soft_wrap=True)
    output = Console(soft_wrap=True)
    if args.debug and env_path:
        progress.print(f"[dim]loaded env from[/] {escape(env_path)}")

    prompt = " ".join(args.prompt).strip()
    if prompt and args.interactive:
        parser.error("--interactive cannot be combined with a prompt")
    if not prompt and not args.interactive and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if prompt and (args.db or args.thread):
        parser.error("--db and --thread require interactive mode")
    if not prompt and not args.interactive and not sys.stdin.isatty():
        parser.error("provide a task, e.g. minicode \"fix the failing test\"")

    agent = None
    try:
        thread_id = (args.thread or "default").strip() or "default"
        if args.debug:
            model_name = resolve_model(args.model)
            root_path = resolve_root(args.root)
            progress.print(f"[dim]workspace[/] {escape(str(root_path))}")
            progress.print(f"[dim]model[/] {escape(model_name)}")
            progress.print(f"[dim]thread[/] {escape(thread_id)}")

        agent = build_agent(
            model=args.model,
            root=args.root,
            debug=args.debug,
            checkpoint=not bool(prompt),
            db_path=args.db,
        )
        config = make_config(thread_id)

        if prompt:
            final_message = run_turn(agent, prompt, progress, config)
            if final_message is not None:
                print_final(final_message, output)
            return 0

        return interactive_loop(agent, progress, output, config, args.debug)
    except KeyboardInterrupt:
        progress.print("\n[yellow]Interrupted.[/]")
        return 130
    except Exception as exc:
        if args.debug:
            raise
        print_error(progress, exc)
        return 1
    finally:
        if agent is not None:
            close_checkpointer(agent)
