"""Optional NeMo Relay observability for MiniCode runs.

NeMo Relay records model and tool calls as one event stream. It is opt-in and
runs its plugin host on a background asyncio loop while the sync MiniCode CLI
keeps the main thread.
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Iterator

DEFAULT_EVENTS_DIR = Path(".minicode") / "relay"
DEFAULT_EVENTS_FILENAME = "events.jsonl"
START_TIMEOUT_SECONDS = 60.0
STOP_TIMEOUT_SECONDS = 30.0


class RelayError(RuntimeError):
    """Raised when the NeMo Relay plugin host cannot start or stop."""


class RelaySession:
    """Own one NeMo Relay plugin host for a MiniCode process."""

    def __init__(self, root: str | Path, plugins: str | Path | None = None) -> None:
        self.root = Path(root).expanduser().resolve()
        self.plugins = Path(plugins).expanduser() if plugins else None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._error: BaseException | None = None
        self._thread: threading.Thread | None = None
        self._started = False

    def config(self) -> dict[str, Any]:
        """Return the inline observability config used when no file is given."""
        output_directory = self.root / DEFAULT_EVENTS_DIR
        return {
            "version": 1,
            "components": [
                {
                    "kind": "observability",
                    "enabled": True,
                    "config": {
                        "version": 4,
                        "enable_full_payloads": False,
                        "atof": {
                            "enabled": True,
                            "sinks": [
                                {
                                    "type": "file",
                                    "output_directory": str(output_directory),
                                    "filename": DEFAULT_EVENTS_FILENAME,
                                    "mode": "append",
                                }
                            ],
                        },
                    },
                }
            ],
        }

    def start(self) -> RelaySession:
        """Start the plugin host and wait until it is active."""
        if self._started:
            return self
        try:
            import nemo_relay  # noqa: F401
        except ImportError as exc:
            raise RelayError(
                "NeMo Relay support is not installed; run `uv sync` or "
                "`uv add nemo-relay[deepagents]`."
            ) from exc

        output_directory = self.root / DEFAULT_EVENTS_DIR
        output_directory.mkdir(parents=True, exist_ok=True)

        self._thread = threading.Thread(
            target=self._run_host,
            name="minicode-relay",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=START_TIMEOUT_SECONDS):
            raise RelayError(f"NeMo Relay did not start within {START_TIMEOUT_SECONDS:.0f} seconds")
        if self._error is not None:
            raise RelayError(f"could not start NeMo Relay: {self._error}") from self._error
        self._started = True
        return self

    def _run_host(self) -> None:
        try:
            asyncio.run(self._host())
        except BaseException as exc:  # noqa: BLE001 - reported to the CLI thread
            self._error = exc
            self._ready.set()

    async def _host(self) -> None:
        import nemo_relay

        plugins = str(self.plugins) if self.plugins is not None else None
        # A user-supplied file owns the component list; the inline config would
        # otherwise override its observability settings.
        config = {} if self.plugins is not None else self.config()
        async with nemo_relay.plugin.activate(config, plugins):
            self._ready.set()
            await asyncio.to_thread(self._stop.wait)

    def attach(self, config: dict[str, Any]) -> dict[str, Any]:
        """Return a LangGraph config that includes the Relay callback handler."""
        from nemo_relay.integrations.deepagents import NemoRelayDeepAgentsCallbackHandler

        callbacks = list(config.get("callbacks") or [])
        callbacks.append(NemoRelayDeepAgentsCallbackHandler())
        return {**config, "callbacks": callbacks}

    @contextmanager
    def turn(self, name: str = "minicode-turn") -> Iterator[None]:
        """Wrap one user turn in a NeMo Relay agent scope."""
        import nemo_relay

        with nemo_relay.scope.scope(name, nemo_relay.ScopeType.Agent):
            yield

    def close(self) -> None:
        """Flush pending events, then stop and join the plugin host."""
        if not self._started:
            return
        flush_error: BaseException | None = None
        try:
            import nemo_relay

            nemo_relay.subscribers.flush()
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            flush_error = exc
        finally:
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=STOP_TIMEOUT_SECONDS)
            self._started = False
        if flush_error is not None:
            raise RelayError(f"could not flush NeMo Relay events: {flush_error}") from flush_error

    def __enter__(self) -> RelaySession:
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            self.close()
        except RelayError:
            if exc_type is None:
                raise

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()
