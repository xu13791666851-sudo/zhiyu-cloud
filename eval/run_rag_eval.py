"""Run a lightweight RAG evaluation against the ZhiYu API."""

from __future__ import annotations

import argparse
import csv
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "rag_testset.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "runs"
DEFAULT_NEGATIVE_ANSWER_TERMS = [
    "未提及",
    "未明确",
    "并未明确",
    "没有足够证据",
    "未讨论",
    "并未讨论",
    "没有明确讨论",
    "文献没有明确讨论",
    "文献未明确讨论",
    "not enough evidence",
    "not explicitly discussed",
]


class ResponseReadError(RuntimeError):
    """Raised when the API response body is truncated or unreadable."""


RETRYABLE_API_ERRORS = (
    ResponseReadError,
    UnicodeDecodeError,
    urllib.error.URLError,
    http.client.RemoteDisconnected,
    ConnectionResetError,
    TimeoutError,
    json.JSONDecodeError,
)


def load_dataset(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            case = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
        if not case.get("id") or not case.get("question"):
            raise ValueError(f"{path}:{line_number} must contain id and question")
        cases.append(case)
    return cases


def read_response_bytes(response) -> bytes:
    try:
        return response.read()
    except http.client.IncompleteRead as exc:
        raise ResponseReadError(
            f"incomplete response body: received {len(exc.partial)} bytes"
        ) from exc


def post_json(
    api_base: str,
    path: str,
    payload: dict[str, Any],
    timeout: int,
    retries: int = 3,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        request = urllib.request.Request(
            f"{api_base.rstrip('/')}{path}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_body = read_response_bytes(response).decode("utf-8")
            return json.loads(response_body)
        except urllib.error.HTTPError:
            raise
        except RETRYABLE_API_ERRORS as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(min(attempt, 3))

    assert last_error is not None
    raise last_error


def joined_chunk_text(chunks: list[dict[str, Any]]) -> str:
    values: list[str] = []
    for chunk in chunks:
        values.extend(
            str(chunk.get(key) or "")
            for key in ("doc", "section_title", "content", "source_type", "provider")
        )
    return "\n".join(values)


def contains_any(text: str, terms: list[str]) -> bool:
    if not terms:
        return True
    return any(term and term in text for term in terms)


def count_hits(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term and term in text)


def evaluate_answer(case: dict[str, Any], answer_text: str) -> dict[str, Any]:
    expected_answer_points = case.get("expected_answer_points") or []
    acceptable_answer_terms = case.get("acceptable_answer_terms") or []
    negative_case = bool(case.get("negative_case"))
    min_answer_hits = case.get("min_answer_hits")

    if negative_case:
        negative_terms = acceptable_answer_terms or expected_answer_points or DEFAULT_NEGATIVE_ANSWER_TERMS
        negative_hit = contains_any(answer_text, negative_terms)
        return {
            "answer_point_hits": int(negative_hit),
            "answer_point_total": 1,
            "answer_pass": negative_hit,
            "answer_eval_mode": "negative",
        }

    total_points = len(expected_answer_points) if expected_answer_points else len(acceptable_answer_terms)
    expected_hits = count_hits(answer_text, expected_answer_points)
    acceptable_hits = count_hits(answer_text, acceptable_answer_terms)
    answer_hits = min(total_points, expected_hits + acceptable_hits) if total_points else 0
    required_hits = min_answer_hits if isinstance(min_answer_hits, int) and min_answer_hits > 0 else total_points
    return {
        "answer_point_hits": answer_hits,
        "answer_point_total": total_points,
        "answer_pass": answer_hits >= required_hits if total_points else None,
        "required_answer_hits": required_hits if total_points else 0,
        "answer_eval_mode": "positive",
    }


def summarize_case(
    case: dict[str, Any],
    chunks: list[dict[str, Any]],
    answer: str | None,
    latency_ms: int,
    error: str | None = None,
) -> dict[str, Any]:
    expected_sources = case.get("expected_sources") or []
    must_retrieve_terms = case.get("must_retrieve_terms") or []
    chunk_text = joined_chunk_text(chunks)
    answer_text = answer or ""
    top_chunk = chunks[0] if chunks else {}
    answer_eval = evaluate_answer(case, answer_text)

    return {
        "id": case["id"],
        "question": case["question"],
        "top_k": case.get("top_k"),
        "ok": error is None,
        "error": error,
        "retrieved_count": len(chunks),
        "provider": top_chunk.get("provider") if top_chunk else None,
        "top_similarity": top_chunk.get("similarity") if top_chunk else None,
        "source_hit": contains_any(chunk_text, expected_sources),
        "term_hit": contains_any(chunk_text, must_retrieve_terms),
        "answer_point_hits": answer_eval["answer_point_hits"],
        "answer_point_total": answer_eval["answer_point_total"],
        "answer_pass": answer_eval["answer_pass"],
        "required_answer_hits": answer_eval.get("required_answer_hits", answer_eval["answer_point_total"]),
        "answer_eval_mode": answer_eval["answer_eval_mode"],
        "negative_case": bool(case.get("negative_case")),
        "latency_ms": latency_ms,
        "answer": answer,
        "chunks": chunks,
        "human_score": None,
        "human_notes": "",
    }


def case_status(item: dict[str, Any]) -> str:
    if not item["ok"]:
        return "error"
    if item["answer_pass"] is False:
        return "fail"
    if not item["source_hit"] or not item["term_hit"]:
        return "review"
    if item["answer_pass"] is True:
        return "pass"
    return "review"


def failure_reasons(item: dict[str, Any]) -> str:
    if case_status(item) == "pass":
        return ""
    reasons: list[str] = []
    if not item["ok"]:
        reasons.append("request_error")
    if not item["source_hit"]:
        reasons.append("source_miss")
    if not item["term_hit"]:
        reasons.append("term_miss")
    if item["answer_pass"] is False:
        reasons.append("answer_fail")
    if not reasons:
        reasons.append("needs_review")
    return ",".join(reasons)


def top_source_label(item: dict[str, Any]) -> str:
    chunks = item.get("chunks") or []
    if not chunks:
        return ""
    top_chunk = chunks[0]
    return str(top_chunk.get("doc") or "Unknown source")


def render_summary_markdown(results: list[dict[str, Any]], *, api_base: str, with_chat: bool) -> str:
    status_counts = {
        "pass": sum(1 for item in results if case_status(item) == "pass"),
        "review": sum(1 for item in results if case_status(item) == "review"),
        "fail": sum(1 for item in results if case_status(item) == "fail"),
        "error": sum(1 for item in results if case_status(item) == "error"),
    }
    lines = [
        "# ZhiYu RAG Evaluation Summary",
        "",
        f"- API: `{api_base}`",
        f"- Mode: `{'retrieve + chat' if with_chat else 'retrieve only'}`",
        f"- Pass: `{status_counts['pass']}`",
        f"- Review: `{status_counts['review']}`",
        f"- Fail: `{status_counts['fail']}`",
        f"- Error: `{status_counts['error']}`",
        "",
        "## Overview",
        "",
        "| id | status | source | answer | similarity | latency_ms |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for item in results:
        lines.append(
            f"| {item['id']} | {case_status(item)} | "
            f"{'Y' if item['source_hit'] else 'N'} | "
            f"{item['answer_point_hits']}/{item['required_answer_hits']} | "
            f"{item['top_similarity']} | {item['latency_ms']} |"
        )

    failures = [item for item in results if case_status(item) in {"fail", "error", "review"}]
    if failures:
        lines.extend(["", "## Needs Attention", ""])
        for item in failures:
            lines.extend(
                [
                    f"### {item['id']}",
                    "",
                    f"- Status: `{case_status(item)}`",
                    f"- Reasons: `{failure_reasons(item)}`",
                    f"- Question: {item['question']}",
                    f"- Source hit: `{item['source_hit']}`",
                    f"- Term hit: `{item['term_hit']}`",
                    f"- Answer: `{item['answer_point_hits']}/{item['answer_point_total']}` with threshold `{item['required_answer_hits']}`",
                    f"- Top source: `{top_source_label(item)}`",
                    "",
                ]
            )

    return "\n".join(lines)


def write_summary_csv(path: Path, results: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "status",
                "question",
                "source_hit",
                "term_hit",
                "answer_pass",
                "answer_point_hits",
                "answer_point_total",
                "required_answer_hits",
                "top_similarity",
                "provider",
                "retrieved_count",
                "latency_ms",
                "negative_case",
                "failure_reasons",
                "top_source",
                "error",
            ],
        )
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "id": item["id"],
                    "status": case_status(item),
                    "question": item["question"],
                    "source_hit": item["source_hit"],
                    "term_hit": item["term_hit"],
                    "answer_pass": item["answer_pass"],
                    "answer_point_hits": item["answer_point_hits"],
                    "answer_point_total": item["answer_point_total"],
                    "required_answer_hits": item["required_answer_hits"],
                    "top_similarity": item["top_similarity"],
                    "provider": item["provider"],
                    "retrieved_count": item["retrieved_count"],
                    "latency_ms": item["latency_ms"],
                    "negative_case": item["negative_case"],
                    "failure_reasons": failure_reasons(item),
                    "top_source": top_source_label(item),
                    "error": item["error"],
                }
            )


def render_markdown(results: list[dict[str, Any]], *, api_base: str, with_chat: bool) -> str:
    total = len(results)
    ok_count = sum(1 for item in results if item["ok"])
    source_hits = sum(1 for item in results if item["source_hit"])
    term_hits = sum(1 for item in results if item["term_hit"])
    answer_cases = sum(1 for item in results if item["answer_point_total"] > 0)
    answer_passes = sum(1 for item in results if item["answer_pass"] is True)
    negative_cases = sum(1 for item in results if item["negative_case"])
    negative_passes = sum(1 for item in results if item["negative_case"] and item["answer_pass"] is True)
    lines = [
        "# ZhiYu RAG Evaluation Report",
        "",
        f"- API: `{api_base}`",
        f"- Mode: `{'retrieve + chat' if with_chat else 'retrieve only'}`",
        f"- Cases: `{total}`",
        f"- Successful requests: `{ok_count}/{total}`",
        f"- Source hits: `{source_hits}/{total}`",
        f"- Term hits: `{term_hits}/{total}`",
        f"- Answer passes: `{answer_passes}/{answer_cases}`",
        f"- Negative cases passed: `{negative_passes}/{negative_cases}`" if negative_cases else "- Negative cases passed: `0/0`",
        "",
        "## Cases",
        "",
    ]

    for item in results:
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"Question: {item['question']}",
                "",
                f"- Retrieved: `{item['retrieved_count']}`",
                f"- Provider: `{item['provider'] or 'none'}`",
                f"- Top similarity: `{item['top_similarity']}`",
                f"- Source hit: `{item['source_hit']}`",
                f"- Term hit: `{item['term_hit']}`",
                f"- Answer point hits: `{item['answer_point_hits']}/{item['answer_point_total']}`",
                f"- Required answer hits: `{item['required_answer_hits']}`",
                f"- Answer pass: `{item['answer_pass']}`",
                f"- Answer eval mode: `{item['answer_eval_mode']}`",
                f"- Latency: `{item['latency_ms']} ms`",
                "- Human score: `__ / 2`",
                "- Human notes:",
                "",
            ]
        )
        if item["error"]:
            lines.extend(["Error:", "", f"```text\n{item['error']}\n```", ""])
        if item["answer"]:
            lines.extend(["Answer:", "", item["answer"], ""])

        lines.append("Top sources:")
        for index, chunk in enumerate(item["chunks"][:5], start=1):
            page = ""
            if chunk.get("page_start"):
                page = f", p. {chunk['page_start']}"
            lines.append(
                f"- [{index}] {chunk.get('doc') or 'Unknown source'}"
                f"{page}, score={chunk.get('similarity')}, chunk={chunk.get('chunk_index')}"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ZhiYu RAG evaluation cases.")
    parser.add_argument("--api-base", default=os.getenv("ZHIYU_API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-k", type=int, default=None, help="Override top_k for every case.")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--with-chat", action="store_true", help="Call /api/chat after /api/retrieve.")
    args = parser.parse_args()

    cases = load_dataset(args.dataset)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    results: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        question = case["question"]
        top_k = args.top_k or int(case.get("top_k") or 5)
        print(f"[{index}/{len(cases)}] {case['id']}: {question}")
        started = time.perf_counter()
        answer = None
        chunks: list[dict[str, Any]] = []
        error = None

        try:
            retrieve_data = post_json(
                args.api_base,
                "/api/retrieve",
                {"query": question, "top_k": top_k},
                args.timeout,
            )
            chunks = retrieve_data.get("chunks") or []
            if args.with_chat:
                chat_data = post_json(
                    args.api_base,
                    "/api/chat",
                    {
                        "query": question,
                        "top_k": top_k,
                        "session_id": f"eval-{run_id}",
                    },
                    args.timeout,
                )
                answer = chat_data.get("answer")
                chunks = chat_data.get("chunks") or chunks
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            error = f"HTTP {exc.code}: {error_body}"
        except RETRYABLE_API_ERRORS as exc:
            error = str(exc)

        latency_ms = int((time.perf_counter() - started) * 1000)
        results.append(summarize_case(case, chunks, answer, latency_ms, error))

    json_path = args.output_dir / f"rag_eval_{run_id}.json"
    md_path = args.output_dir / f"rag_eval_{run_id}.md"
    summary_md_path = args.output_dir / f"rag_eval_{run_id}_summary.md"
    summary_csv_path = args.output_dir / f"rag_eval_{run_id}_summary.csv"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    md_path.write_text(
        render_markdown(results, api_base=args.api_base, with_chat=args.with_chat),
        encoding="utf-8-sig",
    )
    summary_md_path.write_text(
        render_summary_markdown(results, api_base=args.api_base, with_chat=args.with_chat),
        encoding="utf-8-sig",
    )
    write_summary_csv(summary_csv_path, results)

    print(f"\nWrote JSON: {json_path}")
    print(f"Wrote report: {md_path}")
    print(f"Wrote summary: {summary_md_path}")
    print(f"Wrote CSV: {summary_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
