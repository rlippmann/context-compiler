#!/usr/bin/env python3
"""
Run clean, stateless prompt lanes for selected SWE-bench tasks via LiteLLM.

Note:
`manual_compiled_prompt` is a handwritten, state-framed prompt used for
comparison/task curation. It is NOT produced by Context Compiler.
`compiled_state` is produced by Context Compiler from explicit directives.

Usage:
  python swe-bench.py --model anthropic/claude-sonnet-4-20250514
  python swe-bench.py --model openai/gpt-4o-mini
  python swe-bench.py --model ollama/qwen2.5:14b-instruct --api-base http://127.0.0.1:11434

Optional:
  --manifest manifest.json
  --tasks-dir tasks
  --temperature 0
  --max-tokens 1600
  --output-path results.json
  --api-key-env OPENAI_API_KEY
"""

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from litellm import completion  # type: ignore[import-not-found]

from context_compiler import create_engine


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    baseline_prompt: str
    manual_compiled_prompt: str
    directives: list[str] | None = None
    task_prompt: str | None = None
    repo: str | None = None
    topology: str | None = None
    issue_title: str | None = None


@dataclass(frozen=True)
class RunConfig:
    model: str
    temperature: float | None
    reasoning_effort: str | None
    max_tokens: int
    output_path: Path
    sleep_between_calls: float
    api_base: str | None
    api_key_env: str | None
    manifest: Path
    tasks_dir: Path | None
    task_id: str | None
    limit: int | None


def parse_args() -> RunConfig:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Run SWE-bench baseline/manual-compiled/compiler prompt lanes via LiteLLM"
    )
    parser.add_argument(
        "--model",
        default=os.getenv("MODEL")
        or os.getenv("ANTHROPIC_MODEL", "anthropic/claude-sonnet-4-20250514"),
        help="Model name for LiteLLM, e.g. anthropic/..., openai/..., ollama/...",
    )
    parser.add_argument(
        "--manifest",
        default=os.getenv("MANIFEST", str(script_dir / "manifest.json")),
        help="Path to manifest.json listing task files",
    )
    parser.add_argument(
        "--tasks-dir",
        default=os.getenv("TASKS_DIR"),
        help="Optional base directory for task files listed in the manifest",
    )
    parser.add_argument(
        "--task-id",
        default=os.getenv("TASK_ID"),
        help="Optional single task_id to run from the manifest set",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ["LIMIT"]) if "LIMIT" in os.environ else None,
        help="Optional max number of tasks to run from the manifest order",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=(
            float(os.environ["TEMPERATURE"])
            if "TEMPERATURE" in os.environ
            else (
                float(os.environ["ANTHROPIC_TEMPERATURE"])
                if "ANTHROPIC_TEMPERATURE" in os.environ
                else None
            )
        ),
        help="Optional sampling temperature. If omitted, no temperature parameter is sent.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.getenv("MAX_TOKENS", os.getenv("ANTHROPIC_MAX_TOKENS", "1600"))),
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.getenv("REASONING_EFFORT"),
        help="Optional reasoning effort (e.g., none, low, medium, high).",
    )
    parser.add_argument(
        "--output-path",
        default=os.getenv("OUTPUT_PATH", "ab_results.json"),
        help="Output JSON path",
    )
    parser.add_argument(
        "--sleep-between-calls",
        type=float,
        default=float(os.getenv("SLEEP_BETWEEN_CALLS", "1.0")),
    )
    parser.add_argument(
        "--api-base",
        default=os.getenv("API_BASE"),
        help="Optional API base URL (e.g. http://127.0.0.1:11434 for Ollama)",
    )
    parser.add_argument(
        "--api-key-env",
        default=os.getenv("API_KEY_ENV"),
        help="Optional env var name to read API key from (e.g. OPENAI_API_KEY)",
    )
    args = parser.parse_args()

    return RunConfig(
        model=args.model,
        temperature=args.temperature,
        reasoning_effort=args.reasoning_effort,
        max_tokens=args.max_tokens,
        output_path=Path(args.output_path),
        sleep_between_calls=args.sleep_between_calls,
        api_base=args.api_base,
        api_key_env=args.api_key_env,
        manifest=Path(args.manifest),
        tasks_dir=Path(args.tasks_dir) if args.tasks_dir else None,
        task_id=args.task_id,
        limit=args.limit,
    )


def detect_provider(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return "unknown"


def _resolve_task_path(task_ref: str, manifest_path: Path, tasks_dir: Path | None) -> Path:
    task_path = Path(task_ref)
    if task_path.is_absolute():
        return task_path
    if tasks_dir is not None:
        return tasks_dir / task_path
    return manifest_path.parent / task_path


def _required_str_field(data: dict[str, Any], field: str, task_path: Path) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Task file {task_path} missing required string field: {field}")
    return value


def _optional_str_field(data: dict[str, Any], field: str, task_path: Path) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Task file {task_path} has non-string optional field: {field}")
    return value


def _optional_directives_field(data: dict[str, Any], task_path: Path) -> list[str] | None:
    value = data.get("directives")
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"Task file {task_path} has non-list optional field: directives")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"Task file {task_path} has non-string directive entries")
    return value


def load_tasks(manifest_path: Path, tasks_dir: Path | None) -> list[TaskSpec]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"Manifest must be a JSON object: {manifest_path}")

    task_files = manifest.get("task_files")
    if not isinstance(task_files, list) or not task_files:
        raise ValueError(f"Manifest must include non-empty task_files array: {manifest_path}")

    tasks: list[TaskSpec] = []
    seen_ids: set[str] = set()

    for task_ref in task_files:
        if not isinstance(task_ref, str) or not task_ref:
            raise ValueError(f"Manifest {manifest_path} has invalid task file entry: {task_ref!r}")

        task_path = _resolve_task_path(task_ref, manifest_path, tasks_dir)
        if not task_path.exists():
            raise FileNotFoundError(f"Task file not found: {task_path}")

        raw = json.loads(task_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Task file must be a JSON object: {task_path}")

        task_id = _required_str_field(raw, "task_id", task_path)
        baseline_prompt = _required_str_field(raw, "baseline_prompt", task_path)
        manual_compiled_prompt = _required_str_field(raw, "manual_compiled_prompt", task_path)

        if task_id in seen_ids:
            raise ValueError(f"Duplicate task_id in manifest set: {task_id}")
        seen_ids.add(task_id)

        tasks.append(
            TaskSpec(
                task_id=task_id,
                baseline_prompt=baseline_prompt,
                manual_compiled_prompt=manual_compiled_prompt,
                directives=_optional_directives_field(raw, task_path),
                task_prompt=_optional_str_field(raw, "task_prompt", task_path),
                repo=_optional_str_field(raw, "repo", task_path),
                topology=_optional_str_field(raw, "topology", task_path),
                issue_title=_optional_str_field(raw, "issue_title", task_path),
            )
        )

    return tasks


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
                continue
            if not isinstance(item, dict):
                continue
            for key in ("text", "content"):
                value = item.get(key)
                if isinstance(value, str):
                    text = value.strip()
                    if text:
                        parts.append(text)
                if key == "content":
                    nested = _extract_text_from_content(value)
                    if nested:
                        parts.append(nested)
            output_text = item.get("output_text")
            if isinstance(output_text, str):
                text = output_text.strip()
                if text:
                    parts.append(text)
            if isinstance(item.get("text"), dict):
                nested = item["text"].get("value")
                if isinstance(nested, str):
                    text = nested.strip()
                    if text:
                        parts.append(text)
        return "\n".join(parts).strip()

    if isinstance(content, dict):
        for key in ("text", "content", "output_text"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def _extract_text_from_response_dump(obj: Any) -> str:
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        for key in ("output_text", "text", "content"):
            value = node.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    parts.append(text)
            elif key == "content":
                nested = _extract_text_from_content(value)
                if nested:
                    parts.append(nested)
                walk(value)

        for key in ("output", "choices", "message", "messages"):
            if key in node:
                walk(node[key])

    walk(obj)
    return "\n".join(p for p in parts if p).strip()


def _extract_response_text(resp: Any) -> str:
    try:
        choice = resp.choices[0]
    except Exception:
        return ""

    message = getattr(choice, "message", None)
    if message is not None:
        text = _extract_text_from_content(getattr(message, "content", None))
        if text:
            return text
        model_extra = getattr(message, "model_extra", None)
        if isinstance(model_extra, dict):
            text = _extract_text_from_content(model_extra.get("content"))
            if text:
                return text

    text = _extract_text_from_content(getattr(choice, "content", None))
    if text:
        return text
    choice_extra = getattr(choice, "model_extra", None)
    if isinstance(choice_extra, dict):
        text = _extract_text_from_content(choice_extra.get("content"))
        if text:
            return text
    resp_extra = getattr(resp, "model_extra", None)
    if isinstance(resp_extra, dict):
        for key in ("output_text", "content", "output"):
            text = _extract_text_from_content(resp_extra.get(key))
            if text:
                return text

    dump: dict[str, Any] | None = None
    if hasattr(resp, "model_dump"):
        maybe = resp.model_dump()
        if isinstance(maybe, dict):
            dump = maybe
    elif hasattr(resp, "json"):
        try:
            maybe = json.loads(resp.json())
            if isinstance(maybe, dict):
                dump = maybe
        except Exception:
            dump = None
    if dump is not None:
        text = _extract_text_from_response_dump(dump)
        if text:
            return text
    return ""


def _is_litellm_unsupported_param_error(exc: Exception) -> bool:
    try:
        litellm_module = import_module("litellm")
    except ModuleNotFoundError:
        return False
    unsupported_error_type = getattr(litellm_module, "UnsupportedParamsError", None)
    if not isinstance(unsupported_error_type, type):
        return False
    return isinstance(exc, unsupported_error_type)


@contextmanager
def _temporary_litellm_drop_params(enabled: bool) -> Any:
    if not enabled:
        yield
        return

    litellm_module = import_module("litellm")
    litellm_any = cast(Any, litellm_module)
    had_attr = hasattr(litellm_module, "drop_params")
    previous_value = getattr(litellm_module, "drop_params", None)
    litellm_any.drop_params = True
    try:
        yield
    finally:
        if had_attr:
            litellm_any.drop_params = previous_value
        else:
            delattr(litellm_module, "drop_params")


def call_model(prompt: str, cfg: RunConfig) -> str:
    provider = detect_provider(cfg.model)
    kwargs: dict[str, Any] = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": cfg.max_tokens,
    }
    if cfg.temperature is not None:
        kwargs["temperature"] = cfg.temperature
    if cfg.reasoning_effort is not None:
        kwargs["reasoning_effort"] = cfg.reasoning_effort

    if provider == "ollama" and not cfg.api_base:
        kwargs["api_base"] = "http://127.0.0.1:11434"
    elif cfg.api_base:
        kwargs["api_base"] = cfg.api_base

    if cfg.api_key_env:
        api_key = os.getenv(cfg.api_key_env)
        if not api_key:
            print(f"Missing required environment variable: {cfg.api_key_env}", file=sys.stderr)
            sys.exit(1)
        kwargs["api_key"] = api_key

    try:
        with _temporary_litellm_drop_params(False):
            resp = completion(**kwargs)
    except Exception as first_exc:
        if not _is_litellm_unsupported_param_error(first_exc):
            raise
        print(
            "Retrying once with litellm.drop_params=True due to unsupported params",
            file=sys.stderr,
        )
        with _temporary_litellm_drop_params(True):
            resp = completion(**kwargs)

    text = _extract_response_text(resp)

    if not text:
        debug_path = Path(f"/private/tmp/litellm_empty_response_{int(time.time())}.json")
        debug_payload: dict[str, Any] = {"model": cfg.model}
        if hasattr(resp, "model_dump"):
            with suppress(Exception):
                dump = resp.model_dump()
                if isinstance(dump, dict):
                    debug_payload["model_dump"] = dump
        if "model_dump" not in debug_payload and hasattr(resp, "json"):
            with suppress(Exception):
                debug_payload["json"] = resp.json()
        if "model_dump" not in debug_payload and "json" not in debug_payload:
            debug_payload["repr"] = repr(resp)
        try:
            debug_path.write_text(
                json.dumps(debug_payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            debug_path = Path("<failed to write debug payload>")
        raise RuntimeError(
            f"Empty text extracted from model response for model={cfg.model}. "
            f"This likely indicates an unsupported response shape. Debug payload: {debug_path}"
        )
    return text


def _render_compiler_prompt(compiled_state: Any, task_prompt: str) -> str:
    state_obj = compiled_state if isinstance(compiled_state, dict) else {}
    premise = state_obj.get("premise")
    policies_obj = state_obj.get("policies")
    policies = policies_obj if isinstance(policies_obj, dict) else {}
    use_items = sorted(key for key, value in policies.items() if value == "use")
    prohibit_items = sorted(key for key, value in policies.items() if value == "prohibit")

    lines = [
        "You are a grounded assistant.",
        "",
        "Authoritative state (compiled by Context Compiler):",
        f"Premise: {premise if premise is not None else '(none)'}",
        "",
        "Policies:",
        "use:",
    ]
    if use_items:
        lines.extend(f"- {item}" for item in use_items)
    else:
        lines.append("- (none)")
    lines.append("prohibit:")
    if prohibit_items:
        lines.extend(f"- {item}" for item in prohibit_items)
    else:
        lines.append("- (none)")
    lines.extend(["", "Task:", task_prompt])
    return "\n".join(lines)


def main() -> None:
    cfg = parse_args()
    provider = detect_provider(cfg.model)
    tasks = load_tasks(cfg.manifest, cfg.tasks_dir)
    if cfg.task_id is not None:
        tasks = [task for task in tasks if task.task_id == cfg.task_id]
        if not tasks:
            raise ValueError(f"task_id not found in manifest task set: {cfg.task_id}")
    if cfg.limit is not None:
        if cfg.limit < 1:
            raise ValueError("--limit must be >= 1 when provided")
        tasks = tasks[: cfg.limit]

    results: dict[str, Any] = {
        "meta": {
            "model": cfg.model,
            "provider": provider,
            "api_base": cfg.api_base
            if cfg.api_base
            else ("http://127.0.0.1:11434" if provider == "ollama" else None),
            "api_key_env": cfg.api_key_env,
            "max_tokens": cfg.max_tokens,
            "temperature": cfg.temperature,
            "reasoning_effort": cfg.reasoning_effort,
            "prompt_style": "assertions_policies",
            "lanes": ["baseline", "manual_compiled", "compiler"],
            "tasks": [task.task_id for task in tasks],
            "stateless": True,
        },
        "results": {},
    }

    for task in tasks:
        print(f"[1/3] Baseline: {task.task_id}", file=sys.stderr)
        baseline_text = call_model(task.baseline_prompt, cfg)
        time.sleep(cfg.sleep_between_calls)

        print(f"[2/3] Manual compiled: {task.task_id}", file=sys.stderr)
        manual_compiled_text = call_model(task.manual_compiled_prompt, cfg)
        time.sleep(cfg.sleep_between_calls)

        task_result: dict[str, Any] = {
            "baseline_prompt": task.baseline_prompt,
            "manual_compiled_prompt": task.manual_compiled_prompt,
            "baseline_output": baseline_text,
            "manual_compiled_output": manual_compiled_text,
            "compiled_state": None,
            "rendered_compiler_prompt": None,
            "compiler_result": None,
        }
        if task.directives is not None:
            print(f"[3/3] Compiler: {task.task_id}", file=sys.stderr)
            engine = create_engine()
            clarify_error: dict[str, Any] | None = None
            for index, directive in enumerate(task.directives):
                decision = engine.step(directive)
                if str(decision["kind"]) == "clarify":
                    clarify_error = {
                        "error": "compiler_lane_clarify",
                        "directive_index": index,
                        "directive": directive,
                        "prompt_to_user": decision.get("prompt_to_user"),
                    }
                    break

            if clarify_error is not None:
                task_result["compiler_result"] = clarify_error
            else:
                compiled_state = engine.state
                task_prompt = (
                    task.task_prompt if task.task_prompt is not None else task.baseline_prompt
                )
                rendered_compiler_prompt = _render_compiler_prompt(compiled_state, task_prompt)
                compiler_result = call_model(rendered_compiler_prompt, cfg)
                time.sleep(cfg.sleep_between_calls)
                task_result["compiled_state"] = compiled_state
                task_result["rendered_compiler_prompt"] = rendered_compiler_prompt
                task_result["compiler_result"] = compiler_result

        if task.repo is not None:
            task_result["repo"] = task.repo
        if task.topology is not None:
            task_result["topology"] = task.topology
        if task.issue_title is not None:
            task_result["issue_title"] = task.issue_title

        results["results"][task.task_id] = task_result

        cfg.output_path.write_text(
            json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Saved {task.task_id} to {cfg.output_path}", file=sys.stderr)

    print(f"Done. Results written to {cfg.output_path}")


if __name__ == "__main__":
    main()
