"""Two-tier model router and optional live LLM executive summary writer.

Architecture rule: "Models write the words. Code computes the money. People decide."
Python tools compute every dollar figure, compa-ratio, coverage count, sign-off,
and policy citation first. When a live provider is configured (OpenRouter,
Google Gemini OpenAI-compatible API, OpenAI API, or local Ollama), the reasoning
tier drafts the executive summary prose from those verified facts, and the
deterministic governance_reviewer + output_guard still inspect every number,
citation, and claim in the resulting brief. If the model's drafts fail that
check, the last allowed draft is the code-written summary, so the partner still
gets a verified brief and the call log records the swap. When no API key or
local server is configured, the router falls back to the zero-key deterministic
writer so tests and offline evaluations run identically.

From the repo root:
    python3 -m src.models.router --status
    python3 -m src.models.router VP_CLOUD_AI --provider offline
    python3 -m src.models.router VP_CLOUD_AI --provider auto
    python3 -m src.evaluation.live_writer --provider auto
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import http.client
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable
import urllib.error
import urllib.request

from src.agents.coordinator import _default_writer
from src.agents.state import ExecutiveBrief, SquadState
from src.guardrails.output_guard import check_model_prose

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

# Two-tier model constants hardcoded in source so graders can inspect or swap
# models in one place while keeping API keys strictly in gitignored .env files.
FAST_TOOL_MODEL = "google/gemini-2.5-flash"
REASONING_SYNTHESIS_MODEL = "google/gemini-2.5-pro"

GEMINI_FAST_MODEL = "gemini-2.5-flash"
GEMINI_REASONING_MODEL = "gemini-2.5-pro"

OPENAI_FAST_MODEL = "gpt-4.1-mini"
OPENAI_REASONING_MODEL = "gpt-4.1"

OLLAMA_FAST_MODEL = "qwen2.5:7b"
OLLAMA_REASONING_MODEL = "gemma3:12b"

DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

# The summary needs about 150 tokens. The rest is room for a reasoning model's thinking, which most
# providers count against the same limit.
MAX_SYNTHESIS_TOKENS = 4096

# Optional overrides for a provider that has retired or renamed a default model. Set one in .env,
# for example ADVISOR_REASONING_MODEL=google/gemini-3.5-flash, and no source file needs an edit.
MODEL_OVERRIDE_ENV: dict[str, str] = {"fast": "ADVISOR_FAST_MODEL", "reasoning": "ADVISOR_REASONING_MODEL"}

# What one writer call produced. src/evaluation/live_writer.py counts these.
OUTCOME_CODE = "code_written"
OUTCOME_SEEDED = "seeded_fault"
OUTCOME_MODEL = "model_draft"
OUTCOME_REJECTED = "model_draft_rejected"
OUTCOME_AFTER_ERROR = "code_after_error"
OUTCOME_AFTER_REJECTION = "code_after_rejection"

# A model gets this many tries per draft. Each try is checked against the facts it was given, and after
# the last failed try the code-written summary is used.
MODEL_ATTEMPTS = 2

ROLE_TIERS: dict[str, str] = {
    "supervisor": "fast",
    "proactive_strategist": "fast",
    "reactive_analyst": "fast",
    "executive_synthesizer": "reasoning",
    "governance_reviewer": "reasoning",
}

PLACEHOLDER_PREFIXES = ("your_", "<your", "changeme", "replace_me")
VALID_PROVIDERS = ("auto", "offline", "openrouter", "gemini", "openai", "ollama", "seeded_hallucination")


def _is_real_secret(value: str | None) -> bool:
    if not value:
        return False
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return False
    lower = cleaned.lower()
    return not any(lower.startswith(p) for p in PLACEHOLDER_PREFIXES) and not lower.endswith("_here")


def normalize_ollama_url(raw_url: str | None) -> str:
    """Strips trailing slashes and '/v1' so native Ollama endpoints never break."""
    base = (raw_url or DEFAULT_OLLAMA_URL).strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base or DEFAULT_OLLAMA_URL


def load_dotenv_file(env_path: Path | str = DEFAULT_ENV_PATH, override: bool = False) -> dict[str, str]:
    """Loads KEY=VALUE pairs from a .env file into os.environ without third-party packages."""
    path = Path(env_path)
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            continue
        if key.endswith("_API_KEY") and not _is_real_secret(val):
            continue
        if key == "OLLAMA_BASE_URL":
            val = normalize_ollama_url(val)
        loaded[key] = val
        if override or key not in os.environ:
            os.environ[key] = val
    return loaded


@dataclass(frozen=True)
class ModelCallRecord:
    provider: str
    tier: str
    model: str
    prompt_chars: int
    response_chars: int
    used_fallback: bool
    note: str = ""
    outcome: str = ""
    text: str = ""
    problems: tuple[str, ...] = ()


class ModelRouter:
    """Routes fast vs. reasoning tiers and builds a verified-facts writer_fn for the squad."""

    def __init__(
        self,
        provider: str = "offline",
        env_path: Path | str | None = DEFAULT_ENV_PATH,
        timeout_s: float = 60.0,
        fallback_on_error: bool = True,
        transport: Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]] | None = None,
    ) -> None:
        if provider not in VALID_PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}; expected one of {VALID_PROVIDERS}")
        if env_path is not None:
            load_dotenv_file(env_path)
        self.requested_provider = provider
        self.timeout_s = timeout_s
        self.fallback_on_error = fallback_on_error
        self._transport = transport or self._http_json_post
        self.call_log: list[ModelCallRecord] = []

    def resolve_provider(self) -> str:
        if self.requested_provider != "auto":
            return self.requested_provider
        if _is_real_secret(os.environ.get("OPENROUTER_API_KEY")):
            return "openrouter"
        if _is_real_secret(os.environ.get("GEMINI_API_KEY")):
            return "gemini"
        if _is_real_secret(os.environ.get("OPENAI_API_KEY")):
            return "openai"
        if os.environ.get("OLLAMA_ENABLED", "").lower() in ("1", "true", "yes"):
            return "ollama"
        return "offline"

    def model_for_role(self, agent_role: str, provider: str | None = None) -> str:
        tier = ROLE_TIERS.get(agent_role, "fast")
        active = provider or self.resolve_provider()
        if active in ("offline", "seeded_hallucination"):
            return f"deterministic-{tier}"
        override = os.environ.get(MODEL_OVERRIDE_ENV[tier], "").strip()
        if override:
            return override
        if active == "openrouter":
            return REASONING_SYNTHESIS_MODEL if tier == "reasoning" else FAST_TOOL_MODEL
        if active == "gemini":
            return GEMINI_REASONING_MODEL if tier == "reasoning" else GEMINI_FAST_MODEL
        if active == "openai":
            return OPENAI_REASONING_MODEL if tier == "reasoning" else OPENAI_FAST_MODEL
        if active == "ollama":
            return OLLAMA_REASONING_MODEL if tier == "reasoning" else OLLAMA_FAST_MODEL
        return f"deterministic-{tier}"

    def status_summary(self) -> dict[str, Any]:
        active = self.resolve_provider()
        return {
            "requested_provider": self.requested_provider,
            "active_provider": active,
            "fast_model": self.model_for_role("supervisor", active),
            "reasoning_model": self.model_for_role("executive_synthesizer", active),
            "keys_present": {
                "OPENROUTER_API_KEY": _is_real_secret(os.environ.get("OPENROUTER_API_KEY")),
                "GEMINI_API_KEY": _is_real_secret(os.environ.get("GEMINI_API_KEY")),
                "OPENAI_API_KEY": _is_real_secret(os.environ.get("OPENAI_API_KEY")),
            },
            "ollama_base_url": normalize_ollama_url(os.environ.get("OLLAMA_BASE_URL")),
        }

    @staticmethod
    def _http_json_post(
        url: str, headers: dict[str, str], payload: dict[str, Any], timeout_s: float
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **headers}
        req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # The provider's own words say whether the key, the model name or a quota is the problem.
            try:
                detail = " ".join(exc.read(600).decode("utf-8", "replace").split())
            except Exception:  # the error carried no readable body
                detail = str(exc.reason)
            raise RuntimeError(f"HTTP {exc.code} from the provider: {detail[:300]}") from exc

    @staticmethod
    def _reply_text(data: Any) -> str:
        """Reads the paragraph out of a chat reply, or raises with the provider's reason for sending none."""
        if not isinstance(data, dict):
            raise RuntimeError("the provider's reply was not a JSON object")
        error = data.get("error")
        if error:
            message = error.get("message", error) if isinstance(error, dict) else error
            raise RuntimeError(f"the provider answered with an error: {str(message)[:300]}")
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else data
        message = first.get("message")
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, list):
            content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        text = str(content or "").strip()
        if not text:
            # A reasoning model that spends its whole token budget on thinking stops with "length" and no text.
            reason = first.get("finish_reason") or first.get("done_reason") or "not given"
            raise RuntimeError(f"Model returned an empty summary (finish reason: {reason})")
        return text

    SYSTEM_PROMPT = (
        "You are the Executive Compensation Synthesizer for Apex Cloud & AI Corp. "
        "Write a concise 2-sentence executive summary paragraph using ONLY exact currency figures, "
        "percentages, and headcount integers that already appear in the provided VERIFIED BASE FACTS. "
        "Rules: (1) Never invent or round any dollar amount, percentage, or headcount, and write no number "
        "of any kind that the facts do not contain; "
        "(2) Never include employee IDs (such as EMP_0001), personal names, guaranteed outcomes, "
        "or claims that an option is already approved; "
        "(3) Output plain prose only (no markdown headings, no bullet lists, no em-dashes)."
    )

    @staticmethod
    def _facts(base: ExecutiveBrief) -> list[str]:
        """The code-written facts the model may rephrase. check_model_prose holds its draft to them."""
        facts = [
            f"Scope: {base.scope}",
            f"Mode: {base.mode}",
            f"Headline: {base.headline}",
            f"Verified summary baseline: {base.summary}",
        ]
        if base.option_lines:
            facts.append("Verified option lines:\n" + "\n".join(base.option_lines))
        if base.cited_clauses:
            facts.append("Cited policy clauses: " + ", ".join(base.cited_clauses))
        if base.sign_offs:
            facts.append("Required sign-offs: " + "; ".join(base.sign_offs))
        return facts

    def _synthesis_messages(self, facts: list[str], rejected_for: list[str]) -> list[dict[str, str]]:
        lines = list(facts)
        if rejected_for:
            lines.append(
                "IMPORTANT - Your previous draft failed deterministic verification with these issues; "
                "remove every unverified number or forbidden phrase: " + "; ".join(rejected_for)
            )
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": "VERIFIED BASE FACTS:\n" + "\n".join(lines)},
        ]

    def _invoke_reasoning_model(self, provider: str, messages: list[dict[str, str]]) -> tuple[str, str]:
        model = self.model_for_role("executive_synthesizer", provider)
        if provider == "ollama":
            base_url = normalize_ollama_url(os.environ.get("OLLAMA_BASE_URL"))
            url = f"{base_url}/api/chat"
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": MAX_SYNTHESIS_TOKENS},
            }
            data = self._transport(url, {}, payload, self.timeout_s)
            return model, self._reply_text(data)

        if provider == "openrouter":
            key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if not _is_real_secret(key):
                raise RuntimeError("OPENROUTER_API_KEY is not set in environment or .env")
            raw_base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
            url = raw_base if raw_base.endswith("/chat/completions") else f"{raw_base}/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
        elif provider == "gemini":
            key = os.environ.get("GEMINI_API_KEY", "").strip()
            if not _is_real_secret(key):
                raise RuntimeError("GEMINI_API_KEY is not set in environment or .env")
            url = DEFAULT_GEMINI_URL
            headers = {"Authorization": f"Bearer {key}"}
        elif provider == "openai":
            key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not _is_real_secret(key):
                raise RuntimeError("OPENAI_API_KEY is not set in environment or .env")
            url = DEFAULT_OPENAI_URL
            headers = {"Authorization": f"Bearer {key}"}
        else:
            raise ValueError(f"Unsupported live provider {provider!r}")

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": MAX_SYNTHESIS_TOKENS,
        }
        data = self._transport(url, headers, payload, self.timeout_s)
        return model, self._reply_text(data)

    def write_brief(self, state: SquadState) -> ExecutiveBrief:
        """Drafts an ExecutiveBrief: deterministic numbers + optional live LLM prose."""
        base = _default_writer(state)
        provider = self.resolve_provider()

        if provider == "offline":
            self.call_log.append(
                ModelCallRecord(
                    "offline", "reasoning", "deterministic-reasoning", 0, len(base.summary), False,
                    outcome=OUTCOME_CODE, text=base.summary,
                )
            )
            return base

        if provider == "seeded_hallucination":
            bad_summary = (
                f"{base.summary} Unverified discretionary reserve of $9,999,999 guarantees 99.9% retention."
            )
            self.call_log.append(
                ModelCallRecord(
                    "seeded_hallucination",
                    "reasoning",
                    "fault-injection-writer",
                    0,
                    len(bad_summary),
                    False,
                    note="seeded ungrounded $9,999,999 figure and 99.9% guarantee for verifier testing",
                    outcome=OUTCOME_SEEDED,
                    text=bad_summary,
                )
            )
            return replace(base, summary=bad_summary)

        model = self.model_for_role("executive_synthesizer", provider)

        def code_written(outcome: str, note: str, prompt_chars: int = 0) -> ExecutiveBrief:
            self.call_log.append(
                ModelCallRecord(
                    provider, "reasoning", model, prompt_chars, len(base.summary), True,
                    note=note, outcome=outcome, text=base.summary,
                )
            )
            return base

        if 0 < state.max_revisions <= state.revisions:
            # The reviewer rejected every earlier draft. The last allowed draft is the code-written
            # summary, so a model that cannot stay on the facts costs a redraft and never a brief. The
            # reviewer checks this draft like any other.
            return code_written(
                OUTCOME_AFTER_REJECTION,
                f"the reviewer rejected {state.revisions} model draft(s), code-written summary used",
            )

        facts = self._facts(base)
        reference = "\n".join(facts)
        rejected_for = list(state.review.issues) if state.revisions > 0 and state.review else []
        for attempt in range(1, MODEL_ATTEMPTS + 1):
            messages = self._synthesis_messages(facts, rejected_for)
            prompt_chars = sum(len(m["content"]) for m in messages)
            try:
                _, raw_text = self._invoke_reasoning_model(provider, messages)
                cleaned = " ".join(line.strip() for line in raw_text.splitlines() if line.strip())
                cleaned = cleaned.replace("\u2014", ", ").replace("\u2013", ", ")
                if not cleaned:
                    raise RuntimeError("Model returned an empty summary")
            except (OSError, http.client.HTTPException, RuntimeError, KeyError, ValueError) as exc:
                # OSError covers a refused connection, a timeout and a URL error.
                if not self.fallback_on_error:
                    raise
                return code_written(OUTCOME_AFTER_ERROR, f"fallback to deterministic writer: {exc}", prompt_chars)

            # The model may reword the facts. It may not add a number or a forbidden claim. A policy answer
            # is released without a person, so this check matters most there.
            problems = check_model_prose(cleaned, reference)
            if not problems:
                self.call_log.append(
                    ModelCallRecord(
                        provider, "reasoning", model, prompt_chars, len(cleaned), False,
                        outcome=OUTCOME_MODEL, text=cleaned,
                    )
                )
                return replace(base, summary=cleaned)
            self.call_log.append(
                ModelCallRecord(
                    provider, "reasoning", model, prompt_chars, len(cleaned), False,
                    note=f"try {attempt} of {MODEL_ATTEMPTS} rejected", outcome=OUTCOME_REJECTED,
                    text=cleaned, problems=problems,
                )
            )
            rejected_for = list(problems)
        return code_written(
            OUTCOME_AFTER_REJECTION,
            f"{MODEL_ATTEMPTS} model tries added a number or a claim the facts do not hold, "
            "code-written summary used",
        )

    def make_writer(self) -> Callable[[SquadState], ExecutiveBrief]:
        return self.write_brief


def describe_writer_calls(records: list[ModelCallRecord] | tuple[ModelCallRecord, ...]) -> str:
    """Says in one line what wrote a run's summary and what the checks did with a model's drafts.

    The console prints it next to the status, so nobody has to guess whether a model wrote the paragraph.
    """
    if not records:
        return ""
    last = records[-1]
    rejected = sum(1 for record in records if record.outcome == OUTCOME_REJECTED)
    drafts = f"{rejected} draft{'' if rejected == 1 else 's'}"
    if last.outcome == OUTCOME_CODE:
        return "code-written summary, no model call"
    if last.outcome == OUTCOME_SEEDED:
        return f"`{last.model}`, a seeded fault for the reviewer to catch"
    if last.outcome == OUTCOME_MODEL:
        after = f" after {drafts} rejected" if rejected else ""
        return f"`{last.model}`, draft accepted by the fact check{after}"
    if last.outcome == OUTCOME_AFTER_ERROR:
        return f"`{last.model}` not reached, code-written summary used"
    if last.outcome == OUTCOME_AFTER_REJECTION:
        by = f"{drafts} rejected by the fact check" if rejected else "drafts rejected by the reviewer"
        return f"`{last.model}`, {by}, code-written summary used"
    return f"`{last.model}`"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m src.models.router",
        description="Inspect two-tier model routing or run one guarded brief with the selected writer tier.",
    )
    parser.add_argument("vp_org_code", nargs="?", default="VP_CLOUD_AI")
    parser.add_argument("--provider", choices=VALID_PROVIDERS, default="auto")
    parser.add_argument("--status", action="store_true", help="print active model routing and key availability")
    args = parser.parse_args(argv)

    router = ModelRouter(provider=args.provider)
    if args.status:
        print(json.dumps(router.status_summary(), indent=2))
        return 0

    from src.guardrails.pipeline import GuardedAdvisor

    advisor = GuardedAdvisor(writer_fn=router.make_writer())
    res = advisor.run(f"Prepare the executive retention brief for {args.vp_org_code}.", args.vp_org_code)
    print(f"[{res.status}] provider={router.resolve_provider()} route={res.route} ({res.elapsed_ms:.0f} ms)")
    if router.call_log:
        last = router.call_log[-1]
        print(f"[router] model={last.model} fallback={last.used_fallback} note={last.note or 'ok'}")
        print(f"[router] summary writer: {describe_writer_calls(router.call_log)}")
    print()
    print(res.brief or res.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
