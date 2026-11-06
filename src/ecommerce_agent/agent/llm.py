from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


class LLMClient(Protocol):
    def complete(self, prompt: str) -> dict[str, Any]: ...


@dataclass
class FakeLLMClient:
    responses: list[dict[str, Any]]

    def complete(self, prompt: str) -> dict[str, Any]:
        if not self.responses:
            raise LLMResponseError("FakeLLMClient has no response queued")
        return self.responses.pop(0)


Runner = Callable[..., subprocess.CompletedProcess[str]]


class CliLLMClient:
    def __init__(
        self,
        *,
        command: tuple[str, ...] = ("codex", "exec", "--ephemeral", "--json", "-"),
        timeout_seconds: float = 120,
        runner: Runner = subprocess.run,
    ):
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.runner = runner

    def complete(self, prompt: str) -> dict[str, Any]:
        try:
            result = self.runner(
                self.command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LLMTimeoutError(f"LLM CLI timed out after {self.timeout_seconds}s") from exc
        if result.returncode != 0:
            stderr = result.stderr.strip()[-500:]
            raise LLMError(f"LLM CLI exited {result.returncode}: {stderr}")
        return self._parse_jsonl(result.stdout)

    @staticmethod
    def _parse_jsonl(output: str) -> dict[str, Any]:
        final_text: str | None = None
        for line in output.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LLMResponseError("LLM CLI emitted non-JSON output") from exc
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                final_text = item.get("text")
        if final_text is None:
            raise LLMResponseError("LLM CLI did not emit a final agent message")
        try:
            parsed = json.loads(final_text)
        except json.JSONDecodeError as exc:
            raise LLMResponseError("final agent message is not a JSON object") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseError("final agent message must be a JSON object")
        return parsed

