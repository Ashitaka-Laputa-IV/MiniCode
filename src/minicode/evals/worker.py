"""Run a single evaluation task against one baseline."""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path
from typing import Any

from langchain.chat_models import init_chat_model

from minicode.agent import build_agent, resolve_model


def message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text", "")) if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def usage(message: Any) -> dict[str, int]:
    raw = getattr(message, "usage_metadata", None)
    if isinstance(raw, dict):
        result = {
            key: int(value)
            for key, value in raw.items()
            if key in {"input_tokens", "output_tokens", "total_tokens"}
            and isinstance(value, (int, float))
        }
        details = raw.get("input_token_details")
        if isinstance(details, dict):
            cached = details.get("cache_read") or details.get("cached_tokens")
            if isinstance(cached, (int, float)):
                result["cached_input_tokens"] = int(cached)
        return result
    response = getattr(message, "response_metadata", None)
    if isinstance(response, dict):
        raw = response.get("token_usage") or response.get("usage")
        if isinstance(raw, dict):
            mapping = {
                "prompt_tokens": "input_tokens",
                "completion_tokens": "output_tokens",
                "total_tokens": "total_tokens",
            }
            result = {
                mapping[key]: int(value)
                for key, value in raw.items()
                if key in mapping and isinstance(value, (int, float))
            }
            cached = raw.get("prompt_cache_hit_tokens")
            if isinstance(cached, (int, float)):
                result["cached_input_tokens"] = int(cached)
            return result
    return {}


def run_full(prompt: str, root: Path, model: str | None, max_tool_calls: int) -> dict[str, Any]:
    agent = build_agent(
        model=model,
        root=root,
        checkpoint=False,
        permission_mode="yolo",
    )
    started = time.perf_counter()
    final = None
    tool_calls = 0
    usage_totals: dict[str, int] = {}

    for update in agent.stream(
        {"messages": [{"role": "user", "content": prompt}]},
        stream_mode="updates",
    ):
        if not isinstance(update, dict):
            continue
        for node_update in update.values():
            if not isinstance(node_update, dict):
                continue
            messages = node_update.get("messages")
            if not isinstance(messages, list):
                continue
            for message in messages:
                if getattr(message, "type", None) != "ai":
                    continue
                for key, value in usage(message).items():
                    usage_totals[key] = usage_totals.get(key, 0) + value
                calls = getattr(message, "tool_calls", None) or []
                tool_calls += len(calls)
                if tool_calls > max_tool_calls:
                    raise RuntimeError(f"tool call limit exceeded: {max_tool_calls}")
                if not calls:
                    final = message

    return {
        "final": message_text(final) if final is not None else "",
        "tool_calls": tool_calls,
        "usage": usage_totals,
        "duration_s": time.perf_counter() - started,
    }


def run_bare(prompt: str, model: str | None) -> dict[str, Any]:
    model_name = resolve_model(model)
    started = time.perf_counter()
    response = init_chat_model(model_name).invoke(prompt)
    return {
        "final": message_text(response),
        "tool_calls": 0,
        "usage": usage(response),
        "duration_s": time.perf_counter() - started,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one MiniCode eval baseline.")
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--baseline", choices=["full", "bare"], default="full")
    parser.add_argument("--max-tool-calls", type=int, default=30)
    args = parser.parse_args(argv)

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    result: dict[str, Any]
    try:
        if args.baseline == "bare":
            result = run_bare(prompt, args.model)
        else:
            result = run_full(prompt, Path(args.root), args.model, args.max_tool_calls)
        result.update({"ok": True, "baseline": args.baseline, "error": None})
    except Exception as exc:
        result = {
            "ok": False,
            "baseline": args.baseline,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=8),
            "final": "",
            "tool_calls": 0,
            "usage": {},
            "duration_s": 0.0,
        }

    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
