"""Unit tests for exact state serialization and the durable SQLite checkpointer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

from src.agents import serialization
from src.agents.checkpoint_store import SqliteThreadCheckpointer
from src.agents.coordinator import MultiAgentCoordinator
from src.agents.state import Finding, SquadState
from src.retrieval.embeddings import make_embedder
from src.retrieval.policy_search import PLAYBOOK_PATH, PolicyRetriever
from src.tools.interview_search import NoteIndex, load_notes


@dataclass(frozen=True)
class _Local:
    """A dataclass that lives outside the src package."""

    value: int


class SerializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = PolicyRetriever(make_embedder("hashing"), path=PLAYBOOK_PATH)
        cls.notes = NoteIndex(load_notes())

    def _coordinator(self, **kwargs) -> MultiAgentCoordinator:
        return MultiAgentCoordinator(policy=self.policy, notes=self.notes, **kwargs)

    def test_plain_values_keep_their_types(self) -> None:
        value = {
            "tuple": (1, ("a", 2.5), None),
            "set": {3, 1, 2},
            "frozen": frozenset({"x", "y"}),
            "int_keys": {1: "one", 2: "two"},
            "tuple_keys": {("VP_CLOUD_AI", "SW_ENG"): 7},
            "day": date(2026, 11, 16),
            "moment": datetime(2026, 11, 16, 8, 29, 0),
            "path": Path("data/synthetic"),
            "order": {"zebra": 1, "apple": 2},
            "finding": Finding("reactive_analyst", "exit_notes", "VP_CLOUD_AI SW_ENG", "2 notes", {"n": (1, 2)}),
            "flags": [True, False, 0, 1.0],
        }
        back = serialization.loads(serialization.dumps(value))
        self.assertEqual(back, value)
        self.assertIsInstance(back["tuple"], tuple)
        self.assertIsInstance(back["tuple"][1], tuple)
        self.assertIsInstance(back["set"], set)
        self.assertIsInstance(back["frozen"], frozenset)
        self.assertIsInstance(back["finding"], Finding)
        self.assertIsInstance(back["finding"].payload["n"], tuple)
        self.assertIs(back["flags"][0], True)
        # Insertion order survives, because brief text is built by walking dicts in order.
        self.assertEqual(list(back["order"]), ["zebra", "apple"])

    def test_foreign_types_are_refused_both_ways(self) -> None:
        with self.assertRaises(serialization.StateEncodingError):
            serialization.encode(object())
        # A dataclass outside src encodes, but a checkpoint may not rebuild it.
        encoded = serialization.encode(_Local(3))
        with self.assertRaises(serialization.StateEncodingError):
            serialization.decode(encoded)
        with self.assertRaises(serialization.StateEncodingError):
            serialization.decode({"__kind__": "dataclass", "type": "os:system", "fields": {}})
        with self.assertRaises(serialization.StateEncodingError):
            serialization.decode({"__kind__": "mystery"})

    def test_every_run_mode_round_trips_exactly(self) -> None:
        coord = self._coordinator()
        runs = [
            coord.run("Prepare the brief.", vp_org_code="VP_CLOUD_AI", thread_id="s1"),
            coord.run("Prepare the brief.", vp_org_code="VP_ENT_APPS", thread_id="s2"),
            coord.run("Review options.", vp_org_code="VP_SEC_INTEL", job_family="CYBER_SEC_ENG", thread_id="s3"),
            coord.run(
                "How do equity caps differ for new-hire offers versus retention grants for current staff?",
                thread_id="s4",
            ),
        ]
        for state in runs:
            text = serialization.dumps(state)
            back = serialization.loads(text)
            self.assertIsInstance(back, SquadState)
            self.assertEqual(back, state)
            self.assertEqual(serialization.dumps(back), text)

    def test_sqlite_checkpointer_survives_a_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "nested" / "checkpoints.sqlite"
            store = SqliteThreadCheckpointer(db_path)
            coord = self._coordinator(checkpointer=store)
            state = coord.run("Prepare the brief.", vp_org_code="VP_CLOUD_AI", thread_id="durable-1")
            coord.run("Prepare the brief.", vp_org_code="VP_ENT_APPS", thread_id="durable-2")

            nodes = ["supervisor", "parallel_specialists", "executive_synthesizer", "governance_reviewer", "finalize"]
            history = store.history("durable-1")
            self.assertEqual([snap.node for snap in history], nodes)
            self.assertEqual([snap.step for snap in history], [1, 2, 3, 4, 5])
            # The first snapshot keeps the state as it was then, not as it ended.
            self.assertEqual(history[0].findings_count, 0)
            self.assertEqual(history[0].status, "IN_PROGRESS")
            self.assertEqual(history[-1].status, "APPROVED")
            self.assertEqual(store.latest("durable-1").node, "finalize")

            reopened = SqliteThreadCheckpointer(db_path)  # a new process would do exactly this
            self.assertEqual(reopened.load_state("durable-1"), state)
            self.assertEqual(reopened.load_state("durable-1", step=1).findings, [])
            self.assertIsNone(reopened.load_state("no-such-thread"))
            self.assertEqual([t["thread_id"] for t in reopened.threads()], ["durable-1", "durable-2"])
            timings = reopened.timings("durable-1")
            self.assertEqual([t["node"] for t in timings], nodes)
            self.assertTrue(all(t["elapsed_ms"] >= 0 for t in timings))


if __name__ == "__main__":
    unittest.main()
