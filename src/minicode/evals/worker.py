"""Run a single evaluation task against one baseline."""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain.chat_models import init_chat_model
from langgraph.types import Command

from minicode.agent import build_agent, close_checkpointer, resolve_model, shell_env

from .approval import decide
from .baselines import WORKER_BASELINE_CHOICES, Baseline, resolve_baseline
from .trace import Trace


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


def _call_id(call: dict[str, Any]) -> str:
    raw = call.get("id")
    if raw:
        return str(raw)
    name = str(call.get("name", "tool"))
    args = json.dumps(call.get("args", {}), ensure_ascii=False, sort_keys=True, default=str)
    return f"{name}:{args}"


def _approval_decision(
    action: dict[str, Any],
    *,
    approval_policy: str | None,
    trace: Trace,
) -> dict[str, str]:
    if approval_policy is None:
        decision, reason = "reject", "no approval policy configured"
    else:
        decision, reason = decide(action, policy=approval_policy)
    trace.record(
        "approval",
        tool=str(action.get("name", "")),
        args=action.get("args") or {},
        decision=decision,
        reason=reason,
    )
    if decision == "approve":
        return {"type": "approve"}
    return {"type": "reject", "message": f"User rejected this action: {reason}"}


def run_agent_stream(
    agent: Any,
    prompt: str,
    *,
    max_tool_calls: int,
    trace: Trace,
    approval_policy: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Run one agent turn, including scripted HITL resumes."""
    started = time.perf_counter()
    final = None
    tool_calls = 0
    usage_totals: dict[str, int] = {}
    seen_calls: set[str] = set()
    stream_input: Any = {"messages": [{"role": "user", "content": prompt}]}
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None

    while True:
        pending: list[Any] = []
        stream = (
            agent.stream(stream_input, config=config, stream_mode="updates")
            if config is not None
            else agent.stream(stream_input, stream_mode="updates")
        )
        for update in stream:
            if not isinstance(update, dict):
                continue
            if "__interrupt__" in update:
                pending.extend(update["__interrupt__"])
                continue
            for node_update in update.values():
                if not isinstance(node_update, dict):
                    continue
                messages = node_update.get("messages")
                if not isinstance(messages, list):
                    continue
                for message in messages:
                    message_type = getattr(message, "type", None)
                    if message_type == "tool":
                        trace.record(
                            "tool_result",
                            name=str(getattr(message, "name", "tool")),
                            content=message_text(message)[:2000],
                        )
                        continue
                    if message_type != "ai":
                        continue
                    for key, value in usage(message).items():
                        usage_totals[key] = usage_totals.get(key, 0) + value
                    calls = getattr(message, "tool_calls", None) or []
                    for call in calls:
                        if not isinstance(call, dict):
                            continue
                        call_id = _call_id(call)
                        if call_id in seen_calls:
                            continue
                        seen_calls.add(call_id)
                        tool_calls += 1
                        trace.record(
                            "tool_call",
                            id=call_id,
                            name=str(call.get("name", "tool")),
                            args=call.get("args") or {},
                        )
                        if tool_calls > max_tool_calls:
                            raise RuntimeError(f"tool call limit exceeded: {max_tool_calls}")
                    if not calls:
                        final = message

        if not pending:
            break

        pending_decisions: dict[str, dict[str, list[dict[str, str]]]] = {}
        for interrupt in pending:
            trace.record("interrupt", id=str(getattr(interrupt, "id", "")))
            interrupt_value = getattr(interrupt, "value", {})
            actions: list[Any] = (
                interrupt_value.get("action_requests", [])
                if isinstance(interrupt_value, dict)
                else []
            )
            decisions = [
                _approval_decision(
                    action,
                    approval_policy=approval_policy,
                    trace=trace,
                )
                for action in actions
                if isinstance(action, dict)
            ]
            pending_decisions[str(interrupt.id)] = {"decisions": decisions}

        if len(pending) == 1:
            stream_input = Command(resume=next(iter(pending_decisions.values())))
        else:
            stream_input = Command(resume=pending_decisions)
        trace.record("resume", count=len(pending))

    return {
        "final": message_text(final) if final is not None else "",
        "tool_calls": tool_calls,
        "usage": usage_totals,
        "duration_s": time.perf_counter() - started,
    }


def run_minicode(
    prompt: str,
    root: Path,
    model: str | None,
    max_tool_calls: int,
    *,
    baseline: Baseline,
    trace_path: str | Path | None = None,
    checkpoint_db: str | Path | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Run MiniCode with the policy, prompt, and checkpointer from a baseline."""
    trace = Trace(trace_path)
    agent = None
    try:
        agent = build_agent(
            model=model,
            root=root,
            checkpoint=baseline.checkpoint,
            db_path=checkpoint_db,
            permission_mode=baseline.permission_mode or "yolo",
            trace_sink=trace.sink,
        )
        result = run_agent_stream(
            agent,
            prompt,
            max_tool_calls=max_tool_calls,
            trace=trace,
            approval_policy=baseline.approval_policy,
            thread_id=(thread_id or "default") if baseline.checkpoint else None,
        )
        result["trace_summary"] = trace.summary()
        return result
    finally:
        if agent is not None:
            close_checkpointer(agent)
        trace.close()


def run_deepagents_default(
    prompt: str,
    root: Path,
    model: str | None,
    max_tool_calls: int,
    *,
    trace_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run the native Deep Agents stack without MiniCode policy or HITL."""
    trace = Trace(trace_path)
    try:
        backend = LocalShellBackend(
            root_dir=root,
            env=shell_env(),
            inherit_env=False,
        )
        agent = create_deep_agent(
            model=resolve_model(model),
            backend=backend,
            name="deepagents-default",
        )
        result = run_agent_stream(
            agent,
            prompt,
            max_tool_calls=max_tool_calls,
            trace=trace,
        )
        result["trace_summary"] = trace.summary()
        return result
    finally:
        trace.close()


def run_full(
    prompt: str,
    root: Path,
    model: str | None,
    max_tool_calls: int,
    *,
    trace_path: str | Path | None = None,
    checkpoint_db: str | Path | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Compatibility wrapper for the original full baseline."""
    return run_minicode(
        prompt,
        root,
        model,
        max_tool_calls,
        baseline=resolve_baseline("full"),
        trace_path=trace_path,
        checkpoint_db=checkpoint_db,
        thread_id=thread_id,
    )


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
    parser.add_argument("--baseline", choices=WORKER_BASELINE_CHOICES, default="full")
    parser.add_argument("--max-tool-calls", type=int, default=30)
    parser.add_argument("--trace-file", default=None)
    parser.add_argument("--checkpoint-db", default=None)
    parser.add_argument("--thread", default=None)
    args = parser.parse_args(argv)

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    baseline = resolve_baseline(args.baseline)
    result: dict[str, Any]
    try:
        if args.baseline == "bare":
            result = run_bare(prompt, args.model)
        elif baseline.kind == "deepagents":
            result = run_deepagents_default(
                prompt,
                Path(args.root),
                args.model,
                args.max_tool_calls,
                trace_path=args.trace_file,
            )
        elif args.baseline == "full":
            result = run_full(
                prompt,
                Path(args.root),
                args.model,
                args.max_tool_calls,
                trace_path=args.trace_file,
                checkpoint_db=args.checkpoint_db,
                thread_id=args.thread,
            )
        else:
            result = run_minicode(
                prompt,
                Path(args.root),
                args.model,
                args.max_tool_calls,
                baseline=baseline,
                trace_path=args.trace_file,
                checkpoint_db=args.checkpoint_db,
                thread_id=args.thread,
            )
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
            "trace_summary": {},
        }

    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
