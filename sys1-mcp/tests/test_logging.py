"""Call logging, caller identity, the relevance wording, the workflow-tool
setting and the access-log filter. No model is loaded here."""

from __future__ import annotations

import asyncio
import json
import os
import logging
import sys
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastmcp import Client
from mcp import types as mcp_types

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# The server builds its backend at import. Tests never reach this endpoint:
# they patch `BACKEND` or the HTTP client.
os.environ.setdefault("SYS1_ENDPOINT", "http://127.0.0.1:9/v1/systemone")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sys1_mcp import daemon, server  # noqa: E402
from test_backends import FakeBackend  # noqa: E402
from test_workflows import request_for  # noqa: E402


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(record.getMessage()))


class LoggingCase(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = FakeBackend()
        self.handler = ListHandler()
        call_log = logging.getLogger(f"sys1_mcp.calls.test.{id(self)}")
        call_log.setLevel(logging.INFO)
        call_log.propagate = False
        call_log.addHandler(self.handler)
        for patcher in (
            patch.object(server, "BACKEND", self.backend),
            patch.object(server, "_call_logger", lambda: call_log),
            patch.dict("os.environ", {"SYS1_DAEMON_URL": ""}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def records(self) -> list[dict[str, Any]]:
        self.assertTrue(server.flush_call_log(5.0))
        return self.handler.lines


class TestCallLog(LoggingCase):
    def test_the_call_returns_before_redaction_scoring(self) -> None:
        release = threading.Event()
        scored: list[list[str]] = []

        def slow_scores(texts: list[str]) -> list[float]:
            release.wait(5.0)
            scored.append(texts)
            return [0.9, 0.1]

        with patch.object(server, "_sensitive_scores", slow_scores):
            result = server._dispatch("sys1_relevant", {"task": "fix it", "context": "token=abc"})
            # Answered while the scorer is still blocked.
            self.assertIn("relevant", result["answers"])
            self.assertEqual(self.handler.lines, [])
            release.set()
            records = self.records()
        self.assertEqual(scored, [["fix it", "token=abc"]])
        self.assertEqual(records[0]["arguments"]["task"]["redacted"], True)
        self.assertEqual(records[0]["arguments"]["context"], "token=abc")
        self.assertEqual(records[0]["route"], "mcp")

    def test_failed_scoring_withholds_the_text(self) -> None:
        def broken(texts: list[str]) -> list[float]:
            raise RuntimeError("model down")

        with patch.object(server, "_sensitive_scores", broken), self.assertLogs("sys1_mcp", "ERROR"):
            server._dispatch("sys1_ask", {"state": "secret", "questions": {"x": {"type": "noul", "instructions": "q"}}, "model": None})
            record = self.records()[0]
        self.assertEqual(record["arguments"]["state"], {"redacted": True, "reason": "not scored: redaction scoring failed", "chars": 6})

    def test_a_full_queue_writes_at_once_without_scoring(self) -> None:
        with (
            patch.object(server._log_queue, "put_nowait", side_effect=server.queue.Full),
            patch.object(server, "_sensitive_scores", side_effect=AssertionError("scored")),
        ):
            server._log_call("sys1_relevant", {"task": "t", "context": "c"}, {"answers": {}}, 1.0, "mcp")
        record = self.handler.lines[0]
        self.assertEqual(record["arguments"]["task"]["reason"], "not scored: the log queue was full")

    def test_screen_reuses_its_own_score(self) -> None:
        with patch.object(server, "_sensitive_scores", side_effect=AssertionError("scored")):
            server._dispatch("sys1_screen", {"text": "hello"})
            record = self.records()[0]
        # FakeBackend answers every noul with 0.9.
        self.assertEqual(record["arguments"]["text"]["sensitive_data_noul"], 0.9)


class TestCaller(LoggingCase):
    def test_mcp_calls_log_the_client_and_session(self) -> None:
        info = mcp_types.Implementation(name="test-agent", version="9.1")

        async def call() -> None:
            async with Client(server.app, client_info=info) as client:
                await client.call_tool("sys1_relevant", {"task": "t", "context": "c"})

        asyncio.run(call())
        caller = self.records()[0]["caller"]
        self.assertEqual(caller["client"], {"name": "test-agent", "version": "9.1"})
        self.assertTrue(caller["session"])
        # The in-memory client starts no transport, so `transport` is checked live.

    def test_predict_logs_the_forwarded_caller(self) -> None:
        payload = {
            "tool": "sys1_relevant", "arguments": {"task": "t", "context": "c"},
            "caller": {"client": {"name": "Claude Desktop", "version": "1"}, "session": "s1", "transport": "stdio", "extra": "dropped"},
        }
        with patch.object(daemon, "_ready", True), patch.object(daemon, "_log_call") as logged:
            asyncio.run(daemon.predict(request_for("/predict", payload)))
        tool, _args, _result, _ms, route, caller = logged.call_args.args
        self.assertEqual((tool, route), ("sys1_relevant", "predict"))
        self.assertEqual(caller, {"client": {"name": "Claude Desktop", "version": "1"}, "session": "s1", "transport": "stdio"})

    def test_systemone_route_is_named(self) -> None:
        body = {"state": "s", "questions": {"x": {"type": "noul", "instructions": "q"}}}
        with patch.object(daemon, "_ready", True), patch.object(daemon, "_log_call") as logged:
            asyncio.run(daemon.systemone(request_for("/v1/systemone", body)))
        self.assertEqual(logged.call_args.args[4], "systemone")

    def test_a_daemon_served_call_is_logged_by_the_daemon_only(self) -> None:
        class Response:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {"answers": {}}

            def raise_for_status(self) -> None:
                pass

        with (
            patch.dict("os.environ", {"SYS1_DAEMON_URL": "http://daemon.test"}),
            patch.object(server.httpx, "post", return_value=Response()) as posted,
            patch.object(server, "_log_call") as logged,
        ):
            server._dispatch("sys1_health", {})
        self.assertIn("caller", posted.call_args.kwargs["json"])
        logged.assert_not_called()


class TestRelevanceWording(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(server, "BACKEND", FakeBackend())
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_choice_wording_answers_in_the_noul_shape(self) -> None:
        with patch.object(server, "RELEVANCE_QUESTIONS", server.RELEVANCE_WORDINGS["choice"]):
            result = server.relevant_locally("fix it", "the bug is here")
        # FakeBackend gives the first label, "A", 0.7.
        self.assertEqual(result["answers"]["relevant"]["type"], "noul")
        self.assertEqual(result["answers"]["relevant"]["noul"], 0.7)
        self.assertEqual(result["question"]["relevant"]["type"], "choice")

    def test_the_noul_wording_is_returned_unchanged(self) -> None:
        with patch.object(server, "RELEVANCE_QUESTIONS", server.RELEVANCE_WORDINGS["noul"]):
            result = server.relevant_locally("fix it", "the bug is here")
        self.assertEqual(result["answers"]["relevant"]["noul"], 0.9)


class TestWorkflowSetting(unittest.TestCase):
    def test_the_listed_tools_follow_the_setting(self) -> None:
        async def names() -> set[str]:
            async with Client(server.app) as client:
                return {tool.name for tool in await client.list_tools()}

        listed = asyncio.run(names())
        core = {"sys1_ask", "sys1_classify", "sys1_screen", "sys1_health", "sys1_relevant"}
        self.assertEqual(set(server.TOOL_SURFACE), listed)
        if server.WORKFLOW_TOOLS_ENABLED:
            self.assertEqual(listed, core | set(server.WORKFLOW_TOOLS))
        else:
            self.assertEqual(listed, core)
            with self.assertRaisesRegex(ValueError, "SYS1_WORKFLOW_TOOLS=1"):
                server.run_tool_locally("sys1_select_tests", {})


class TestQuietAccessLog(unittest.TestCase):
    def check(self, method: str, path: str, status: int) -> bool:
        record = logging.LogRecord(
            "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:1", method, path, "1.1", status), None,
        )
        return daemon._QuietAccessLog().filter(record)

    def test_probes_and_stale_sessions_are_dropped(self) -> None:
        self.assertFalse(self.check("GET", "/.well-known/oauth-protected-resource/mcp", 404))
        self.assertFalse(self.check("GET", "/mcp/.well-known/openid-configuration", 404))
        self.assertFalse(self.check("GET", "/mcp", 400))
        self.assertFalse(self.check("GET", "/mcp", 404))
        self.assertFalse(self.check("DELETE", "/mcp", 404))

    def test_real_traffic_and_errors_are_kept(self) -> None:
        self.assertTrue(self.check("POST", "/mcp", 200))
        self.assertTrue(self.check("POST", "/mcp", 400))
        self.assertTrue(self.check("POST", "/predict", 400))
        self.assertTrue(self.check("GET", "/health", 503))


if __name__ == "__main__":
    unittest.main()
