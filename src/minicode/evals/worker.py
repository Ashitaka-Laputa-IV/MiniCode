"""Run a single evaluation task against one baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import traceback
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain.chat_models import init_chat_model
from langgraph.types import Command

from minicode.agent import (
    build_agent,
    close_checkpointer,
    resolve_db_path,
    resolve_model,
    shell_env,
)

from .approval import decide
from .baselines import WORKER_BASELINE_CHOICES, Baseline, resolve_baseline
from .trace import Trace, read_trace, summarize_events


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


def _message_key(message: Any) -> str:
    message_id = getattr(message, "id", None)
    if message_id:
        return f"id:{message_id}"
    calls = getattr(message, "tool_calls", None) or []
    payload = f"{message_text(message)}\0{json.dumps(calls, sort_keys=True, default=str)}"
    return f"hash:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


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


def _interrupt_actions(interrupt: Any) -> tuple[str, list[dict[str, Any]]]:
    """Return the interrupt id and its pending action requests."""
    interrupt_id = str(getattr(interrupt, "id", ""))
    value = getattr(interrupt, "value", {})
    actions: list[Any] = value.get("action_requests", []) if isinstance(value, dict) else []
    return interrupt_id, [action for action in actions if isinstance(action, dict)]


def run_agent_stream(
    agent: Any,
    prompt: str,
    *,
    max_tool_calls: int,
    trace: Trace,
    approval_policy: str | None = None,
    thread_id: str | None = None,
    pause_on_interrupt: bool = False,
    resume_decisions: Any = None,
) -> dict[str, Any]:
    """Run one agent turn, including scripted HITL resumes.

    ``resume_decisions`` starts the stream with ``Command(resume=...)`` instead
    of a new user message. When ``pause_on_interrupt`` is true the first
    interrupt ends the stream without an automatic resume, leaving the
    checkpoint available for a later process.
    """
    started = time.perf_counter()
    final = None
    tool_calls = 0
    usage_totals: dict[str, int] = {}
    seen_calls: set[str] = set()
    seen_messages: set[str] = set()
    interrupt_ids: list[str] = []
    pending_actions: list[dict[str, Any]] = []
    interrupted = False
    if resume_decisions is not None:
        stream_input: Any = (
            resume_decisions
            if isinstance(resume_decisions, Command)
            else Command(resume=resume_decisions)
        )
        trace.record("resume_input", decisions=resume_decisions)
    else:
        stream_input = {"messages": [{"role": "user", "content": prompt}]}
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None

    while True:
        pending: list[Any] = []
        paused = False
        stream = (
            agent.stream(stream_input, config=config, stream_mode="updates")
            if config is not None
            else agent.stream(stream_input, stream_mode="updates")
        )
        for update in stream:
            if not isinstance(update, dict):
                continue
            if "__interrupt__" in update:
                interrupts = update["__interrupt__"]
                if not isinstance(interrupts, (list, tuple)):
                    interrupts = [interrupts]
                for interrupt in interrupts:
                    interrupt_id, actions = _interrupt_actions(interrupt)
                    trace.record("interrupt", id=interrupt_id, actions=actions)
                    if interrupt_id:
                        interrupt_ids.append(interrupt_id)
                    pending_actions.extend(actions)
                if pause_on_interrupt:
                    interrupted = True
                    paused = True
                    trace.record(
                        "pause",
                        interrupt_id=interrupt_ids[0] if interrupt_ids else "",
                        count=len(interrupts),
                    )
                    break
                pending.extend(interrupts)
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
                    key = _message_key(message)
                    if key not in seen_messages:
                        seen_messages.add(key)
                        message_usage = usage(message)
                        if message_usage:
                            trace.record("usage", **message_usage)
                        for field, value in message_usage.items():
                            usage_totals[field] = usage_totals.get(field, 0) + value
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

        if paused:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
            break
        if not pending:
            break

        pending_decisions: dict[str, dict[str, list[dict[str, str]]]] = {}
        for interrupt in pending:
            interrupt_value = getattr(interrupt, "value", {})
            requested_actions: list[Any] = (
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
                for action in requested_actions
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
        "interrupted": interrupted,
        "interrupt_id": interrupt_ids[0] if interrupt_ids else None,
        "interrupt_ids": interrupt_ids,
        "pending_actions": pending_actions,
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
    pause_on_interrupt: bool = False,
    resume_decisions: Any = None,
    disable_checkpoint: bool = False,
) -> dict[str, Any]:
    """Run MiniCode with the policy, prompt, and checkpointer from a baseline."""
    trace = Trace(trace_path)
    agent = None
    checkpoint_enabled = bool(baseline.checkpoint) and not disable_checkpoint
    permission_mode = baseline.permission_mode or "yolo"
    effective_thread_id = (thread_id or "default") if checkpoint_enabled else None
    # ``ask`` mode always needs an in-process checkpointer for HITL. When the
    # persistent checkpointer is disabled the config id is process-local and is
    # not reported as a persistent thread.
    config_thread_id = (
        (thread_id or "default") if checkpoint_enabled or permission_mode == "ask" else None
    )
    effective_db: Path | None = None
    try:
        if checkpoint_enabled:
            effective_db = resolve_db_path(root, checkpoint_db)
        agent = build_agent(
            model=model,
            root=root,
            checkpoint=checkpoint_enabled,
            db_path=None if disable_checkpoint else checkpoint_db,
            permission_mode=permission_mode,
            subagents=baseline.subagents,
            trace_sink=trace.sink,
        )
        result = run_agent_stream(
            agent,
            prompt,
            max_tool_calls=max_tool_calls,
            trace=trace,
            approval_policy=baseline.approval_policy,
            thread_id=config_thread_id,
            pause_on_interrupt=pause_on_interrupt,
            resume_decisions=resume_decisions,
        )
        result["thread_id"] = effective_thread_id
        result["checkpoint_db"] = str(effective_db) if effective_db is not None else None
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
    pause_on_interrupt: bool = False,
    resume_decisions: Any = None,
    disable_checkpoint: bool = False,
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
        pause_on_interrupt=pause_on_interrupt,
        resume_decisions=resume_decisions,
        disable_checkpoint=disable_checkpoint,
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
    parser.add_argument(
        "--pause-on-interrupt",
        action="store_true",
        help="stop at the first HITL interrupt instead of auto-resuming",
    )
    parser.add_argument(
        "--resume-approve",
        action="store_true",
        help="start with Command(resume=...) approving the pending HITL action",
    )
    parser.add_argument(
        "--disable-checkpoint",
        action="store_true",
        help="force no persistent checkpointer/thread (recovery control)",
    )
    args = parser.parse_args(argv)

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    baseline = resolve_baseline(args.baseline)
    resume_decisions = {"decisions": [{"type": "approve"}]} if args.resume_approve else None
    result: dict[str, Any]
    started = time.perf_counter()
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
                pause_on_interrupt=args.pause_on_interrupt,
                resume_decisions=resume_decisions,
                disable_checkpoint=args.disable_checkpoint,
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
                pause_on_interrupt=args.pause_on_interrupt,
                resume_decisions=resume_decisions,
                disable_checkpoint=args.disable_checkpoint,
            )
        result.update({"ok": True, "baseline": args.baseline, "error": None})
    except Exception as exc:
        events = read_trace(args.trace_file) if args.trace_file else []
        trace_summary = summarize_events(events)
        result = {
            "ok": False,
            "baseline": args.baseline,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=8),
            "final": "",
            "tool_calls": trace_summary.get("tool_calls", 0),
            "usage": trace_summary.get("usage", {}),
            "duration_s": round(time.perf_counter() - started, 3),
            "trace_summary": trace_summary,
        }

    result.setdefault("interrupted", False)
    result.setdefault("interrupt_id", None)
    result.setdefault("pending_actions", [])
    result.setdefault("thread_id", None if args.disable_checkpoint else args.thread)
    result.setdefault("checkpoint_db", None if args.disable_checkpoint else args.checkpoint_db)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
