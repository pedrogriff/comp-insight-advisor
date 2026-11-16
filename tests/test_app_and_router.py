"""Unit tests for the two-tier ModelRouter and the Gradio AdvisorAppController."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from src.app import DEMO_PRESETS, AdvisorAppController, gradio_available
from src.guardrails.pipeline import AWAITING_APPROVAL, HOLD, REFUSED, RELEASED, GuardedAdvisor
from src.models.router import (
    FAST_TOOL_MODEL,
    GEMINI_REASONING_MODEL,
    OLLAMA_REASONING_MODEL,
    OPENAI_REASONING_MODEL,
    REASONING_SYNTHESIS_MODEL,
    ModelRouter,
    load_dotenv_file,
    normalize_ollama_url,
)


class ModelRouterTests(unittest.TestCase):
    def test_normalize_ollama_url_and_dotenv_loader(self) -> None:
        self.assertEqual(normalize_ollama_url("http://localhost:11434/v1"), "http://localhost:11434")
        self.assertEqual(normalize_ollama_url("http://127.0.0.1:11434/v1/"), "http://127.0.0.1:11434")
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "OPENROUTER_API_KEY=your_openrouter_api_key_here\n"
                "GEMINI_API_KEY=real_test_key_12345\n"
                "OLLAMA_BASE_URL=http://localhost:11434/v1\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                loaded = load_dotenv_file(env_file, override=True)
                self.assertNotIn("OPENROUTER_API_KEY", loaded)
                self.assertEqual(os.environ.get("GEMINI_API_KEY"), "real_test_key_12345")
                self.assertEqual(os.environ.get("OLLAMA_BASE_URL"), "http://localhost:11434")
                router = ModelRouter(provider="auto", env_path=None)
                self.assertEqual(router.resolve_provider(), "gemini")

    def test_role_tier_mapping_across_providers(self) -> None:
        router = ModelRouter(provider="offline", env_path=None)
        self.assertEqual(router.model_for_role("supervisor", "openrouter"), FAST_TOOL_MODEL)
        self.assertEqual(router.model_for_role("proactive_strategist", "openrouter"), FAST_TOOL_MODEL)
        self.assertEqual(router.model_for_role("reactive_analyst", "openrouter"), FAST_TOOL_MODEL)
        self.assertEqual(router.model_for_role("executive_synthesizer", "openrouter"), REASONING_SYNTHESIS_MODEL)
        self.assertEqual(router.model_for_role("governance_reviewer", "openrouter"), REASONING_SYNTHESIS_MODEL)
        self.assertEqual(router.model_for_role("executive_synthesizer", "gemini"), GEMINI_REASONING_MODEL)
        self.assertEqual(router.model_for_role("executive_synthesizer", "openai"), OPENAI_REASONING_MODEL)
        self.assertEqual(router.model_for_role("executive_synthesizer", "ollama"), OLLAMA_REASONING_MODEL)

    def test_live_transport_hallucination_repair_and_offline_fallback(self) -> None:
        calls: list[dict] = []

        def fake_transport(url: str, headers: dict, payload: dict, timeout_s: float) -> dict:
            calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_s})
            if len(calls) == 1:
                # Round 0: model invents an ungrounded $7,777,777 figure.
                return {"choices": [{"message": {"content": "Spend $7,777,777 across VP_CLOUD_AI immediately."}}]}
            # Round 1: prompt carries reviewer issues, and the model writes grounded prose.
            user_prompt = payload["messages"][1]["content"]
            self.assertIn("failed deterministic verification", user_prompt)
            return {
                "choices": [
                    {
                        "content_check": "ok",
                        "message": {
                            "content": (
                                "VP_CLOUD_AI combines 2 convergent cohorts under a $2,150,000 effective "
                                "proactive budget, led by the $1,995,600 joint Option 1."
                            )
                        },
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ, {"OPENROUTER_API_KEY": "sk-or-test-real-key"}, clear=True
        ):
            router = ModelRouter(provider="openrouter", env_path=None, transport=fake_transport)
            advisor = GuardedAdvisor(runtime_dir=tmp, writer_fn=router.make_writer())
            res = advisor.run("Prepare the Q1 retention brief for VP_CLOUD_AI.", "VP_CLOUD_AI")
            self.assertEqual(res.status, AWAITING_APPROVAL)
            self.assertEqual(len(calls), 2)
            self.assertEqual(res.state.revisions, 1)
            self.assertIn("$1,995,600", res.brief)

        # Network error falls back cleanly to the deterministic writer when fallback_on_error=True.
        def failing_transport(url: str, headers: dict, payload: dict, timeout_s: float) -> dict:
            raise urllib.error.URLError("offline test environment")

        with tempfile.TemporaryDirectory() as tmp:
            ollama_router = ModelRouter(provider="ollama", env_path=None, transport=failing_transport)
            advisor = GuardedAdvisor(runtime_dir=tmp, writer_fn=ollama_router.make_writer())
            res = advisor.run("Prepare the Q1 retention brief for VP_CLOUD_AI.", "VP_CLOUD_AI")
            self.assertEqual(res.status, AWAITING_APPROVAL)
            self.assertTrue(ollama_router.call_log[-1].used_fallback)


class AdvisorAppControllerTests(unittest.TestCase):
    def test_all_six_demo_presets_and_trace_inspector(self) -> None:
        self.assertIsInstance(gradio_available(), bool)
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = AdvisorAppController(runtime_dir=tmp, engine="auto")
            self.assertIn("Models write the words. Code computes the money. People decide.", ctrl.system_banner_markdown())
            expected_statuses = [
                AWAITING_APPROVAL,
                RELEASED,
                RELEASED,
                REFUSED,
                REFUSED,
                HOLD,
            ]
            names = list(DEMO_PRESETS.keys())
            self.assertEqual(len(names), 6)
            for name, want_status in zip(names, expected_statuses):
                p, o, fam, w, q = ctrl.apply_preset(name)
                out = ctrl.run_investigation(p, o, fam, w, q)
                self.assertEqual(out["status"], want_status, name)

            # Inspect Preset 1 (VP_CLOUD_AI) clauses, Finding table, and approval flow.
            p1 = ctrl.apply_preset(names[0])
            out1 = ctrl.run_investigation(*p1)
            tid = out1["thread_id"]
            self.assertIn("Retrieved & Verified Playbook Clauses", out1["clauses_md"])
            self.assertIn("Specialist `Finding` Objects Merged at `executive_synthesizer`", out1["trace_md"])
            self.assertIn("`chain ok: True`", out1["trace_md"])

            # Missing Head of Compensation acknowledgement is refused by the gate.
            refused = ctrl.submit_decision(tid, p1[0], "approve", "Option 1", ["VP"], "", "")
            self.assertFalse(refused["ok"])
            self.assertIn("[GATE REFUSED]", refused["gate_md"])

            # Durable reload from a brand-new controller instance on the same runtime_dir.
            ctrl_restarted = AdvisorAppController(runtime_dir=tmp, engine="auto")
            reloaded = ctrl_restarted.load_thread(tid, p1[0])
            self.assertEqual(reloaded["status"], AWAITING_APPROVAL)

            # Cross-org partner cannot load VP_CLOUD_AI thread when scoped to VP_SEC_INTEL.
            with self.assertRaises(Exception):
                ctrl_restarted.load_thread(tid, "HRBP_SEC_ONLY (Scoped to VP_SEC_INTEL)")

            # Valid approval releases the brief with decision record and SHA-256 provenance.
            approved = ctrl_restarted.submit_decision(
                tid, p1[0], "approve", "Option 1", ["VP", "Head of Compensation"], "", "Approved for Q1 review"
            )
            self.assertTrue(approved["ok"])
            self.assertEqual(approved["status"], RELEASED)
            self.assertIn("Decision record:", approved["brief_md"])
            self.assertIn("Provenance: playbook sha256", approved["brief_md"])

    def test_partner_memory_preview_and_commit_guards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = AdvisorAppController(runtime_dir=tmp, engine="stdlib")
            partner = "HRBP_DEFAULT (All 4 VP orgs)"
            org = "VP_CLOUD_AI"

            # 1. Policy-locked keys cannot be previewed.
            msg, tok = ctrl.preview_memory_change(partner, org, "record_feedback", "skip_manager_inversion_audit", "true")
            self.assertEqual(tok, "")
            self.assertIn("[POLICY LOCKED]", msg)

            # 2. Commit without preview token is refused.
            c_msg, _ = ctrl.commit_memory_change("", partner, org)
            self.assertIn("[COMMIT REFUSED]", c_msg)

            # 3. Three preview-and-commit sessions propose a standing budget cap, then confirm and retire it.
            last_mem_md = ""
            for _ in range(3):
                p_msg, tok = ctrl.preview_memory_change(partner, org, "record_feedback", "budget_cap_usd", "1800000")
                self.assertTrue(tok, p_msg)
                # Cross-partner commit attempt is refused and consumes the token.
                bad_msg, _ = ctrl.commit_memory_change(tok, "HRBP_CLOUD_ONLY (Scoped to VP_CLOUD_AI)", org)
                self.assertIn("[COMMIT REFUSED]", bad_msg)
                # Re-preview and commit as the rightful owner.
                _, tok2 = ctrl.preview_memory_change(partner, org, "record_feedback", "budget_cap_usd", "1800000")
                c_msg, last_mem_md = ctrl.commit_memory_change(tok2, partner, org)
                self.assertIn("Committed", c_msg)
                # Reusing the consumed token fails.
                reuse_msg, _ = ctrl.commit_memory_change(tok2, partner, org)
                self.assertIn("[COMMIT REFUSED]", reuse_msg)

            self.assertIn("Proposals & Renewals Awaiting Confirmation", last_mem_md)
            _, c_tok = ctrl.preview_memory_change(partner, org, "confirm_preference", "1")
            c_msg, active_md = ctrl.commit_memory_change(c_tok, partner, org)
            self.assertIn("confirmed preference ID 1", c_msg)
            self.assertIn("Active Confirmed Preferences", active_md)

            # Retirement requires a reason.
            r_bad, r_empty = ctrl.preview_memory_change(partner, org, "retire_preference", "1", reason="")
            self.assertEqual(r_empty, "")
            self.assertIn("[PREVIEW REJECTED]", r_bad)
            _, r_tok = ctrl.preview_memory_change(partner, org, "retire_preference", "1", reason="Q2 budget reset")
            r_msg, retired_md = ctrl.commit_memory_change(r_tok, partner, org)
            self.assertIn("retired preference ID 1", r_msg)
            self.assertIn("_None._", retired_md)


if __name__ == "__main__":
    unittest.main()
