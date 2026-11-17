import pytest

from minicode.evals.classify import classify_failure, failure_counts, pass_at_k


def result(**overrides):
    base = {
        "passed": False,
        "worker_ok": True,
        "verify_ok": False,
        "error": None,
        "verify_output": "",
    }
    base.update(overrides)
    return base


def test_passed() -> None:
    assert classify_failure({"passed": True}) == "passed"


def test_timeout_from_worker_and_verify() -> None:
    assert classify_failure(result(error="task timed out after 10s")) == "timeout"
    assert classify_failure(result(verify_output="verification timed out")) == "timeout"


def test_verify_output_does_not_spoof_timeout_or_context_overflow() -> None:
    assert (
        classify_failure(result(verify_output="pytest failed: timed out waiting for server"))
        == "verification_failed"
    )
    assert (
        classify_failure(result(verify_output="assert context length exceeded"))
        == "verification_failed"
    )


def test_tool_limit() -> None:
    assert classify_failure(result(error="tool call limit exceeded: 30")) == "tool_limit"


def test_context_overflow() -> None:
    assert classify_failure(result(error="context window overflow")) == "context_overflow"


@pytest.mark.parametrize(
    "error",
    [
        "BadRequestError: This model's maximum context length is 65536 tokens",
        "context_length_exceeded",
        "prompt is too long for this model",
        "Input tokens exceed the context window",
    ],
)
def test_common_provider_context_errors(error: str) -> None:
    assert classify_failure(result(error=error)) == "context_overflow"


def test_worker_error() -> None:
    assert classify_failure(result(worker_ok=False, error="boom")) == "agent_error"


def test_permission_denied() -> None:
    assert classify_failure(result(), {"blocked": 1}) == "permission_denied"
    assert classify_failure(result(), {"rejections": 1}) == "permission_denied"


def test_loop() -> None:
    assert classify_failure(result(), {"repeated_tool_calls": True}) == "loop"


def test_no_tests_run() -> None:
    assert classify_failure(result(), {"ran_tests": False}) == "no_tests_run"


def test_verification_failed() -> None:
    assert classify_failure(result(), {"ran_tests": True}) == "verification_failed"


def test_failure_counts_and_pass_at_k() -> None:
    results = [
        {"id": "a", "passed": True, "failure_reason": "passed"},
        {"id": "a", "passed": False, "failure_reason": "loop"},
        {"id": "a", "passed": False, "failure_reason": "loop"},
        {"id": "b", "passed": False, "failure_reason": "timeout"},
    ]

    assert failure_counts(results) == {"loop": 2, "timeout": 1}
    assert pass_at_k(results, 3) == (0.5, 0.5)
