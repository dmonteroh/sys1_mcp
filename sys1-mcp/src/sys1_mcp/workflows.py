"""Bounded agent workflows built from System One typed decisions.

The caller supplies the predictor and batch classifier, already bound to the
model that answers (the server binds its `trace` role). Keeping orchestration
separate from the transport and the backend lets every surface share it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

Predict = Callable[[str, dict[str, Any]], dict[str, Any]]
Classify = Callable[[list[Any], dict[str, Any]], dict[str, Any]]

TEST_QUESTION = {
    "affected": {
        "type": "noul",
        "instructions": "Could this code change affect the behavior or setup of this test?",
    }
}
OUTCOME_QUESTION = {
    "outcome": {
        "type": "choice",
        "instructions": "What does the independent evidence say about the requested outcome?",
        "criteria": {
            "A": "supported: evidence shows the requested outcome happened",
            "B": "pending: work started but the outcome has not happened yet",
            "C": "contradicted: evidence shows the outcome failed or did not happen",
            "D": "unknown: the evidence cannot establish the outcome",
        },
    }
}
CACHE_QUESTION = {
    "fit": {
        "type": "choice",
        "instructions": "Does the cached answer address the new request with the same intent and qualifiers?",
        "criteria": {
            "A": "same: the answer covers the new request and every qualifier",
            "B": "different: the answer misses or conflicts with an intent or qualifier",
            "C": "uncertain: the relationship cannot be established from this text",
        },
    }
}
RELEVANCE_QUESTION = {
    "relevant": {
        "type": "noul",
        "instructions": "Given the task, is this context needed to do it or understand it?",
    }
}
NOVELTY_QUESTION = {
    "novel": {
        "type": "noul",
        "instructions": "Does the candidate add useful task information absent from the retained context?",
    }
}


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{name}` must be a non-empty string")
    return value


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"`{name}` must be a number from 0 to 1")
    return float(value)


def _cut(result: dict[str, Any]) -> bool:
    truncation = result.get("truncation") or {}
    return bool(truncation.get("truncated") or truncation.get("prefix_truncated"))


def _provenance(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result[key] for key in ("backend", "model", "checkpoint", "limits", "model_reason") if key in result}


def select_tests(
    diff_chunks: list[str],
    tests: list[dict[str, Any]],
    changed_files: list[str],
    threshold: float | None,
    classify: Classify,
) -> dict[str, Any]:
    """Rank discovered tests; skip only with a caller-calibrated threshold."""
    if not isinstance(diff_chunks, list) or not diff_chunks:
        raise ValueError("`diff_chunks` must be a non-empty list")
    if not isinstance(tests, list) or not tests:
        raise ValueError("`tests` must be a non-empty list")
    if not isinstance(changed_files, list) or any(not isinstance(path, str) for path in changed_files):
        raise ValueError("`changed_files` must be a list of paths")
    if threshold is not None:
        threshold = _probability(threshold, "threshold")
    ids: list[str] = []
    for index, test in enumerate(tests):
        if not isinstance(test, dict):
            raise ValueError(f"tests[{index}] must be an object")
        ids.append(_text(test.get("id"), f"tests[{index}].id"))
        _text(test.get("path"), f"tests[{index}].path")
        _text(test.get("title"), f"tests[{index}].title")
    if len(set(ids)) != len(ids):
        raise ValueError("test ids must be unique")
    all_ids = list(ids)
    changed = {path.removeprefix("./") for path in changed_files}
    direct = [test["id"] for test in tests if test["path"].removeprefix("./") in changed]

    def full_suite(reason: str, scores: dict[str, float] | None = None) -> dict[str, Any]:
        return {
            "mode": "full_suite",
            "reason": reason,
            "run_ids": all_ids,
            "directly_changed_ids": direct,
            "scores": scores or {},
            "threshold": threshold,
        }

    if len(diff_chunks) > 8 or len(tests) > 128:
        return full_suite("input exceeds 8 diff chunks or 128 tests; split the selection request")
    for index, chunk in enumerate(diff_chunks):
        _text(chunk, f"diff_chunks[{index}]")
    scores = {item_id: 0.0 for item_id in ids}
    provenance: dict[str, Any] = {}
    for chunk in diff_chunks:
        items = [
            {
                "id": test["id"],
                "text": (
                    f"Code change:\n{chunk}\n\nTest path: {test['path']}\n"
                    f"Test title: {test['title']}\nTest detail: {test.get('description', '')}"
                ),
            }
            for test in tests
        ]
        try:
            result = classify(items, TEST_QUESTION)
            provenance = _provenance(result)
            if result.get("truncation", {}).get("prefix_truncated") or result.get("truncation", {}).get("truncated_items"):
                return {**full_suite("model input was truncated", scores), **provenance}
            rows = result["items"]
            if len(rows) != len(tests):
                raise ValueError("classifier returned a different number of tests")
            for expected_id, row in zip(ids, rows):
                if row["id"] != expected_id or row.get("truncated"):
                    raise ValueError("classifier returned a missing, reordered, or truncated test")
                scores[expected_id] = max(scores[expected_id], float(row["answers"]["affected"]["noul"]))
        except Exception as exc:
            return {**full_suite(f"classification failed: {type(exc).__name__}", scores), **provenance}
    ranked = sorted(ids, key=lambda item_id: (-scores[item_id], ids.index(item_id)))
    if threshold is None:
        return {
            **full_suite("observation mode; no calibrated threshold was supplied", scores),
            "ranked_ids": ranked,
            **provenance,
        }
    selected = [item_id for item_id in ids if item_id in direct or scores[item_id] >= threshold]
    if not selected:
        return {**full_suite("no tests selected", scores), "ranked_ids": ranked, **provenance}
    return {
        "mode": "selected",
        "reason": "caller-supplied threshold",
        "run_ids": selected,
        "skipped_ids": [item_id for item_id in ids if item_id not in selected],
        "directly_changed_ids": direct,
        "scores": scores,
        "threshold": threshold,
        "ranked_ids": ranked,
        **provenance,
    }


def verify_outcome(
    goal: str,
    tool_result: str,
    evidence: str,
    checks: list[dict[str, Any]],
    predict: Predict,
) -> dict[str, Any]:
    """Compare a claimed outcome with independent evidence and exact checks."""
    _text(goal, "goal")
    _text(tool_result, "tool_result")
    if not isinstance(evidence, str):
        raise ValueError("`evidence` must be a string")
    if not isinstance(checks, list):
        raise ValueError("`checks` must be a list")
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or not isinstance(check.get("passed"), bool):
            raise ValueError(f"checks[{index}] needs a boolean `passed` field")
        _text(check.get("name"), f"checks[{index}].name")
    failed = [check["name"] for check in checks if not check["passed"]]
    if failed:
        return {"status": "contradicted", "reason": "deterministic checks failed", "failed_checks": failed}
    if not evidence.strip():
        return {"status": "needs_evidence", "reason": "no independent evidence was supplied"}
    state = f"Requested outcome:\n{goal}\n\nTool result or claim:\n{tool_result}\n\nIndependent evidence:\n{evidence}"
    try:
        result = predict(state, OUTCOME_QUESTION)
        if _cut(result):
            return {"status": "inconclusive", "reason": "model input was truncated", **_provenance(result)}
        answer = result["answers"]["outcome"]
        labels = {"A": "supported", "B": "pending", "C": "contradicted", "D": "unknown"}
        return {
            "status": "observation",
            "suggested": labels[answer["choice"]],
            "probabilities": {labels[key]: value for key, value in answer["probabilities"].items()},
            "checks_passed": [check["name"] for check in checks],
            **_provenance(result),
        }
    except Exception as exc:
        return {"status": "inconclusive", "reason": f"prediction failed: {type(exc).__name__}"}


def cache_fit(
    new_request: str,
    cached_request: str,
    cached_answer: str,
    new_scope: dict[str, Any],
    cached_scope: dict[str, Any],
    expires_at: str,
    reuse_threshold: float | None,
    predict: Predict,
) -> dict[str, Any]:
    """Reject stale or differently scoped cache entries before semantic scoring."""
    for name, value in (("new_request", new_request), ("cached_request", cached_request), ("cached_answer", cached_answer)):
        _text(value, name)
    if not isinstance(new_scope, dict) or not new_scope or not isinstance(cached_scope, dict) or not cached_scope:
        raise ValueError("both scope objects must be non-empty")
    if reuse_threshold is not None:
        reuse_threshold = _probability(reuse_threshold, "reuse_threshold")
    if new_scope != cached_scope:
        return {"action": "recompute", "reason": "exact scope differs", "model_called": False}
    try:
        expiry = datetime.fromisoformat(_text(expires_at, "expires_at"))
    except ValueError as exc:
        raise ValueError("`expires_at` must be an ISO 8601 timestamp") from exc
    if expiry.tzinfo is None:
        raise ValueError("`expires_at` must include a timezone")
    if expiry <= datetime.now(timezone.utc):
        return {"action": "recompute", "reason": "cached evidence expired", "model_called": False}
    state = f"New request:\n{new_request}\n\nCached request:\n{cached_request}\n\nCached answer:\n{cached_answer}"
    try:
        result = predict(state, CACHE_QUESTION)
        if _cut(result):
            return {"action": "recompute", "reason": "model input was truncated", "model_called": True, **_provenance(result)}
        answer = result["answers"]["fit"]
        probabilities = answer["probabilities"]
        action = "reuse" if reuse_threshold is not None and answer["choice"] == "A" and probabilities["A"] >= reuse_threshold else "recompute"
        reason = "caller-supplied threshold met" if action == "reuse" else "semantic fit is uncalibrated or below threshold"
        if action == "reuse" and expiry <= datetime.now(timezone.utc):
            action = "recompute"
            reason = "cached evidence expired during the decision"
        return {
            "action": action,
            "reason": reason,
            "model_called": True,
            "fit_probabilities": {"same": probabilities["A"], "different": probabilities["B"], "uncertain": probabilities["C"]},
            "reuse_threshold": reuse_threshold,
            **_provenance(result),
        }
    except Exception as exc:
        return {"action": "recompute", "reason": f"prediction failed: {type(exc).__name__}", "model_called": True}


def pack_context(
    task: str,
    candidates: list[dict[str, Any]],
    pinned_ids: list[str],
    budget_tokens: int,
    novelty_threshold: float | None,
    classify: Classify,
    predict: Predict,
) -> dict[str, Any]:
    """Pin obligations, then fill a caller-counted token budget with context."""
    _text(task, "task")
    if not isinstance(candidates, list) or not candidates or len(candidates) > 32:
        raise ValueError("`candidates` must contain 1 to 32 items")
    if not isinstance(budget_tokens, int) or isinstance(budget_tokens, bool) or budget_tokens < 1:
        raise ValueError("`budget_tokens` must be a positive integer")
    if not isinstance(pinned_ids, list) or any(not isinstance(item_id, str) for item_id in pinned_ids):
        raise ValueError("`pinned_ids` must be a list of ids")
    if novelty_threshold is not None:
        novelty_threshold = _probability(novelty_threshold, "novelty_threshold")
    by_id: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        item_id = _text(candidate.get("id"), f"candidates[{index}].id")
        _text(candidate.get("text"), f"candidates[{index}].text")
        tokens = candidate.get("tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 1:
            raise ValueError(f"candidates[{index}].tokens must be a positive integer")
        if item_id in by_id:
            raise ValueError("candidate ids must be unique")
        by_id[item_id] = candidate
    if len(set(pinned_ids)) != len(pinned_ids) or any(item_id not in by_id for item_id in pinned_ids):
        raise ValueError("pinned ids must be unique and name supplied candidates")
    pinned = [by_id[item_id] for item_id in pinned_ids]
    used = sum(item["tokens"] for item in pinned)
    if used > budget_tokens:
        raise ValueError("pinned context exceeds the token budget; increase the budget or shorten it explicitly")
    remaining = [item for item in candidates if item["id"] not in pinned_ids]
    selected = list(pinned)
    ranked: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    provenance: dict[str, Any] = {}
    ranking_failed = False
    if remaining:
        items = [{"id": item["id"], "text": f"Task:\n{task}\n\nCandidate context:\n{item['text']}"} for item in remaining]
        try:
            result = classify(items, RELEVANCE_QUESTION)
            provenance = _provenance(result)
            if result.get("truncation", {}).get("prefix_truncated") or len(result["items"]) != len(remaining):
                raise ValueError("relevance batch was truncated or incomplete")
            for candidate, row in zip(remaining, result["items"]):
                if row["id"] != candidate["id"]:
                    raise ValueError("relevance batch was reordered")
                score = None if row.get("truncated") else float(row["answers"]["relevant"]["noul"])
                ranked.append({"id": candidate["id"], "relevance": score})
        except Exception as exc:
            ranked = [{"id": item["id"], "relevance": None} for item in remaining]
            provenance["warning"] = f"relevance ranking failed: {type(exc).__name__}; using source order"
            ranking_failed = True
    if not ranking_failed:
        ranked.sort(key=lambda item: -(item["relevance"] if item["relevance"] is not None else 1.0))
    # One batched novelty pass affects ordering without treating an uncalibrated
    # score as a reason to discard context. With no pinned text, the highest
    # relevance item that fits becomes the comparison anchor for the rest.
    anchor = None if pinned else next(
        (row["id"] for row in ranked if by_id[row["id"]]["tokens"] <= budget_tokens), None
    )
    comparison = "\n\n".join(item["text"] for item in pinned)
    if anchor is not None:
        comparison = by_id[anchor]["text"]
    to_compare = [row for row in ranked if row["id"] != anchor]
    if comparison and to_compare and not ranking_failed:
        novelty_items = [
            {
                "id": row["id"],
                "text": (
                    f"Task:\n{task}\n\nRetained context:\n{comparison}\n\n"
                    f"Candidate context:\n{by_id[row['id']]['text']}"
                ),
            }
            for row in to_compare
        ]
        try:
            novelty_result = classify(novelty_items, NOVELTY_QUESTION)
            if novelty_result.get("truncation", {}).get("prefix_truncated") or len(novelty_result["items"]) != len(to_compare):
                raise ValueError("novelty batch was truncated or incomplete")
            for row, answer in zip(to_compare, novelty_result["items"]):
                if row["id"] != answer["id"]:
                    raise ValueError("novelty batch was reordered")
                row["initial_novelty"] = (
                    None if answer.get("truncated")
                    else float(answer["answers"]["novel"]["noul"])
                )
        except Exception as exc:
            provenance["novelty_warning"] = f"initial novelty ranking failed: {type(exc).__name__}"
    for row in ranked:
        if row["id"] == anchor:
            row["initial_novelty"] = 1.0
        novelty = row.get("initial_novelty")
        relevance = row["relevance"] if row["relevance"] is not None else 1.0
        row["priority"] = relevance * (0.5 + 0.5 * (novelty if novelty is not None else 1.0))
    if not ranking_failed:
        ranked.sort(key=lambda item: -item["priority"])
    seen = {item["text"].strip() for item in selected}
    for row in ranked:
        candidate = by_id[row["id"]]
        if candidate["text"].strip() in seen:
            skipped.append({"id": row["id"], "reason": "exact duplicate"})
            continue
        if used + candidate["tokens"] > budget_tokens:
            skipped.append({"id": row["id"], "reason": "token budget"})
            continue
        novelty: float | None = 1.0
        if selected:
            retained = "\n\n".join(item["text"] for item in selected)
            state = f"Task:\n{task}\n\nRetained context:\n{retained}\n\nCandidate context:\n{candidate['text']}"
            try:
                result = predict(state, NOVELTY_QUESTION)
                if _cut(result):
                    novelty = None
                else:
                    novelty = float(result["answers"]["novel"]["noul"])
            except Exception:
                novelty = None
        row["novelty"] = novelty
        if (
            novelty_threshold is not None and not ranking_failed
            and row["relevance"] is not None and novelty is not None
            and novelty < novelty_threshold
        ):
            skipped.append({"id": row["id"], "reason": "below caller-supplied novelty threshold"})
            continue
        selected.append(candidate)
        seen.add(candidate["text"].strip())
        used += candidate["tokens"]
    return {
        "selected": [{"id": item["id"], "text": item["text"], "tokens": item["tokens"]} for item in selected],
        "selected_ids": [item["id"] for item in selected],
        "pinned_ids": pinned_ids,
        "skipped": skipped,
        "scores": ranked,
        "used_tokens": used,
        "budget_tokens": budget_tokens,
        "count_basis": "caller-supplied token counts",
        "novelty_threshold": novelty_threshold,
        **provenance,
    }
