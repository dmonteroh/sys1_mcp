"""Safety and compatibility checks for the additive agent workflows."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# The server builds its backend at import. Tests never reach this endpoint:
# they patch `BACKEND` or the HTTP client.
os.environ.setdefault("SYS1_ENDPOINT", "http://127.0.0.1:9/v1/systemone")

from sys1_mcp import workflows  # noqa: E402
from sys1_mcp import daemon  # noqa: E402
from sys1_mcp.server import TOOL_SURFACE  # noqa: E402


def classify_with(scores: dict[str, float], truncated: bool = False):
    def classify(items: list[Any], questions: dict[str, Any]) -> dict[str, Any]:
        key = next(iter(questions))
        return {
            "items": [
                {
                    "id": item["id"],
                    "answers": {key: {"noul": scores.get(item["id"], 0.0)}},
                    "truncated": [key] if truncated else [],
                }
                for item in items
            ],
            "truncation": {"truncated_items": [item["id"] for item in items] if truncated else [], "prefix_truncated": False},
            "model": "test-model",
            "checkpoint": "test-checkpoint",
        }

    return classify


def choice_result(choice: str = "A", cut: bool = False) -> dict[str, Any]:
    return {
        "answers": {
            "outcome": {"choice": choice, "probabilities": {"A": 0.8, "B": 0.1, "C": 0.05, "D": 0.05}},
            "fit": {"choice": choice, "probabilities": {"A": 0.8, "B": 0.1, "C": 0.1}},
            "novel": {"noul": 0.2},
        },
        "truncation": {"truncated": cut, "prefix_truncated": False},
        "model": "test-model",
        "checkpoint": "test-checkpoint",
    }


class TestSelection(unittest.TestCase):
    def setUp(self) -> None:
        self.tests = [
            {"id": "billing", "path": "tests/billing.spec.ts", "title": "billing flow"},
            {"id": "search", "path": "tests/search.spec.ts", "title": "search flow"},
        ]

    def test_changed_spec_runs_even_when_model_scores_it_low(self) -> None:
        result = workflows.select_tests(
            ["change checkout billing"], self.tests, ["tests/billing.spec.ts"], 0.7,
            classify_with({"billing": 0.01, "search": 0.9}),
        )
        self.assertEqual(result["mode"], "selected")
        self.assertEqual(result["run_ids"], ["billing", "search"])
        self.assertEqual(result["directly_changed_ids"], ["billing"])
        self.assertEqual(result["threshold"], 0.7)

    def test_uncalibrated_and_truncated_selections_run_full_suite(self) -> None:
        observed = workflows.select_tests(["change"], self.tests, [], None, classify_with({"billing": 0.9}))
        cut = workflows.select_tests(["change"], self.tests, [], 0.7, classify_with({}, truncated=True))
        self.assertEqual(observed["run_ids"], ["billing", "search"])
        self.assertEqual(cut["mode"], "full_suite")
        self.assertEqual(cut["run_ids"], ["billing", "search"])

    def test_model_failure_runs_full_suite(self) -> None:
        def fail(*_: Any) -> dict[str, Any]:
            raise RuntimeError("model unavailable")

        result = workflows.select_tests(["change"], self.tests, [], 0.7, fail)
        self.assertEqual(result["mode"], "full_suite")
        self.assertEqual(result["run_ids"], ["billing", "search"])


def request_for(path: str, payload: dict[str, Any]) -> Request:
    body = json.dumps(payload).encode()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": path, "headers": []}, receive)


class TestSurface(unittest.TestCase):
    def test_tool_arguments(self) -> None:
        expected = {
            "sys1_ask": ["state", "questions", "model"],
            "sys1_classify": ["items", "questions", "model"],
            "sys1_screen": ["text"],
            "sys1_health": [],
            "sys1_relevant": ["task", "context"],
        }
        for tool, arguments in expected.items():
            with self.subTest(tool=tool):
                self.assertEqual(TOOL_SURFACE[tool]["arguments"], arguments)

    def test_every_tool_runs_locally(self) -> None:
        for tool, spec in TOOL_SURFACE.items():
            with self.subTest(tool=tool):
                self.assertTrue(callable(spec["local"]))

    def test_predict_dispatches_tool_payloads(self) -> None:
        with (
            patch.object(daemon, "_ready", True),
            patch.object(daemon, "run_tool_locally", return_value={"mode": "full_suite"}) as dispatched,
            patch.object(daemon, "_log_call"),
        ):
            ok = asyncio.run(daemon.predict(request_for("/predict", {"tool": "sys1_select_tests", "arguments": {"diff_chunks": []}})))
            bad = asyncio.run(daemon.predict(request_for("/predict", {"text": "state", "schema": {}})))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(json.loads(ok.body)["mode"], "full_suite")
        self.assertEqual(bad.status_code, 400)
        dispatched.assert_called_once_with("sys1_select_tests", {"diff_chunks": []})

    def test_systemone_route_asks_with_the_wire_contract(self) -> None:
        with (
            patch.object(daemon, "_ready", True),
            patch.object(daemon, "run_tool_locally", return_value={"model": "m", "answers": {"x": {"noul": 0.7}}}) as dispatched,
            patch.object(daemon, "_log_call"),
        ):
            ok = asyncio.run(daemon.systemone(request_for("/v1/systemone", {"state": "s", "questions": {"x": {}}, "model": "m"})))
            bad = asyncio.run(daemon.systemone(request_for("/v1/systemone", {"state": "s"})))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(json.loads(ok.body)["answers"]["x"]["noul"], 0.7)
        self.assertEqual(bad.status_code, 400)
        dispatched.assert_called_once_with("sys1_ask", {"state": "s", "questions": {"x": {}}, "model": "m"})


class TestOutcome(unittest.TestCase):
    def test_exact_failure_and_missing_evidence_never_claim_completion(self) -> None:
        def fail(*_: Any) -> dict[str, Any]:
            raise AssertionError("model should not run")

        failed = workflows.verify_outcome("report exists", "HTTP 200", "report found", [{"name": "file exists", "passed": False}], fail)
        missing = workflows.verify_outcome("report exists", "HTTP 200", "", [], fail)
        self.assertEqual(failed["status"], "contradicted")
        self.assertEqual(missing["status"], "needs_evidence")

    def test_model_support_is_observation(self) -> None:
        result = workflows.verify_outcome("report exists", "job queued", "report file now exists", [], lambda *_: choice_result())
        self.assertEqual(result["status"], "observation")
        self.assertEqual(result["suggested"], "supported")


class TestCache(unittest.TestCase):
    def test_scope_and_expiry_checks_precede_model(self) -> None:
        def fail(*_: Any) -> dict[str, Any]:
            raise AssertionError("model should not run")

        args = ("new", "old", "answer")
        different = workflows.cache_fit(*args, {"tenant": "b"}, {"tenant": "a"}, "2099-01-01T00:00:00Z", 0.7, fail)
        expired = workflows.cache_fit(*args, {"tenant": "a"}, {"tenant": "a"}, "2000-01-01T00:00:00Z", 0.7, fail)
        self.assertEqual(different["action"], "recompute")
        self.assertEqual(expired["action"], "recompute")
        self.assertFalse(different["model_called"])

    def test_reuse_requires_caller_threshold_and_full_input(self) -> None:
        args = ("new", "old", "answer", {"tenant": "a"}, {"tenant": "a"}, "2099-01-01T00:00:00Z")
        observed = workflows.cache_fit(*args, None, lambda *_: choice_result())
        reuse = workflows.cache_fit(*args, 0.7, lambda *_: choice_result())
        cut = workflows.cache_fit(*args, 0.7, lambda *_: choice_result(cut=True))
        self.assertEqual(observed["action"], "recompute")
        self.assertEqual(reuse["action"], "reuse")
        self.assertEqual(cut["action"], "recompute")


class TestContext(unittest.TestCase):
    def test_novelty_changes_order_without_dropping_pins(self) -> None:
        candidates = [
            {"id": "rule", "text": "Keep API stable", "tokens": 2},
            {"id": "repeat", "text": "The API must stay stable", "tokens": 4},
            {"id": "trace", "text": "Cursor points to the wrong row", "tokens": 4},
        ]

        def classify(items: list[Any], questions: dict[str, Any]) -> dict[str, Any]:
            key = next(iter(questions))
            scores = {"relevant": {"repeat": 0.9, "trace": 0.8}, "novel": {"repeat": 0.1, "trace": 0.9}}
            return classify_with(scores[key])(items, questions)

        result = workflows.pack_context(
            "Fix cursor", candidates, ["rule"], 6, None,
            classify, lambda *_: choice_result(),
        )
        self.assertEqual(result["selected_ids"], ["rule", "trace"])
        self.assertGreater(result["scores"][0]["priority"], result["scores"][1]["priority"])

    def test_pins_survive_and_budget_is_hard(self) -> None:
        candidates = [
            {"id": "rule", "text": "Never delete user data", "tokens": 5},
            {"id": "repeat", "text": "Never delete user data", "tokens": 5},
            {"id": "trace", "text": "The failing cursor trace", "tokens": 4},
            {"id": "extra", "text": "Unrelated notes", "tokens": 4},
        ]
        result = workflows.pack_context(
            "Fix cursor", candidates, ["rule"], 9, None,
            classify_with({"trace": 0.9, "extra": 0.1}),
            lambda *_: choice_result(),
        )
        self.assertEqual(result["selected_ids"], ["rule", "trace"])
        self.assertEqual(result["used_tokens"], 9)
        self.assertTrue(any(row["reason"] == "exact duplicate" for row in result["skipped"]))

    def test_pins_cannot_be_silently_dropped(self) -> None:
        with self.assertRaisesRegex(ValueError, "pinned context exceeds"):
            workflows.pack_context(
                "Fix cursor", [{"id": "rule", "text": "Required constraint", "tokens": 10}],
                ["rule"], 9, None, classify_with({}), lambda *_: choice_result(),
            )

    def test_failed_relevance_keeps_source_order_and_ignores_novelty_gate(self) -> None:
        def fail(*_: Any) -> dict[str, Any]:
            raise RuntimeError("classifier unavailable")

        result = workflows.pack_context(
            "Fix cursor",
            [{"id": "first", "text": "Trace one", "tokens": 4},
             {"id": "second", "text": "Trace two", "tokens": 4}],
            [], 4, 0.9, fail, lambda *_: choice_result(),
        )
        self.assertEqual(result["selected_ids"], ["first"])
        self.assertIn("relevance ranking failed", result["warning"])


if __name__ == "__main__":
    unittest.main()
