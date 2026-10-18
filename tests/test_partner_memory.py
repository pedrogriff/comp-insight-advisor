"""Unit tests for the partner feedback memory that lasts beyond one session."""

from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.memory.partner_memory import (
    ALL_ORGS,
    PartnerMemory,
    PolicyLockedError,
    effective_budget_cap,
    order_options,
)

PARTNER = "partner_a"
ORG = "VP_ENT_APPS"
OCT_19 = date(2026, 10, 19)


class PartnerMemoryTest(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "memory" / "partner_memory.db"
        self.memory = PartnerMemory(self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _sessions(self, key, value, count=3, org=ORG, start=OCT_19, prefix="s"):
        """Records the same edit once in each of `count` weekly sessions."""
        result = None
        for i in range(count):
            result = self.memory.record_feedback(
                PARTNER, org, f"{prefix}{i + 1}", key, value, start + timedelta(weeks=i)
            )
        return result

    def _confirmed(self, key, value, org=ORG, prefix="s"):
        proposal = self._sessions(key, value, org=org, prefix=prefix)
        return self.memory.confirm(proposal.pref_id, PARTNER, OCT_19 + timedelta(weeks=3))

    def test_three_sessions_create_a_proposal_and_two_do_not(self) -> None:
        self.assertIsNone(self._sessions("exclude_promoted_last_6m", True, count=2))
        proposal = self.memory.record_feedback(
            PARTNER, ORG, "s3", "exclude_promoted_last_6m", True, OCT_19 + timedelta(weeks=2)
        )
        self.assertEqual(proposal.status, "proposed")
        self.assertEqual(proposal.session_count, 3)
        self.assertEqual((proposal.first_seen, proposal.last_seen), ("2026-10-19", "2026-11-02"))

    def test_repeats_inside_one_session_count_once(self) -> None:
        for _ in range(3):
            self.memory.record_feedback(PARTNER, ORG, "s1", "brief_detail", "summary", OCT_19)
        result = self.memory.record_feedback(PARTNER, ORG, "s2", "brief_detail", "summary", OCT_19)
        self.assertIsNone(result)

    def test_proposal_applies_only_after_the_partner_confirms(self) -> None:
        proposal = self._sessions("exclude_promoted_last_6m", True)
        loaded = self.memory.load_for_session(PARTNER, ORG, OCT_19 + timedelta(weeks=3))
        self.assertEqual(loaded["apply"], [])
        self.assertEqual([p.pref_id for p in loaded["ask_partner"]], [proposal.pref_id])

        active = self.memory.confirm(proposal.pref_id, PARTNER, date(2026, 11, 9))
        self.assertEqual((active.status, active.review_by), ("active", "2027-05-08"))
        loaded = self.memory.load_for_session(PARTNER, ORG, date(2026, 11, 16))
        self.assertEqual([(p.key, p.value) for p in loaded["apply"]], [("exclude_promoted_last_6m", True)])
        self.assertEqual(loaded["ask_partner"], [])

    def test_preference_goes_back_to_the_partner_after_review_date(self) -> None:
        active = self._confirmed("min_rating_for_grants", "rating_4")
        self.assertEqual(active.review_by, "2027-05-08")
        on_time = self.memory.load_for_session(PARTNER, ORG, date(2027, 5, 8))
        late = self.memory.load_for_session(PARTNER, ORG, date(2027, 5, 9))
        self.assertEqual(len(on_time["apply"]), 1)
        self.assertEqual((late["apply"], len(late["ask_partner"])), ([], 1))

    def test_contradicting_edit_sends_preference_back(self) -> None:
        active = self._confirmed("exclude_promoted_last_6m", True)
        self.memory.record_feedback(
            PARTNER, ORG, "s9", "exclude_promoted_last_6m", False, date(2026, 12, 7)
        )
        loaded = self.memory.load_for_session(PARTNER, ORG, date(2026, 12, 14))
        self.assertEqual(loaded["apply"], [])
        self.assertEqual([p.pref_id for p in loaded["ask_partner"]], [active.pref_id])
        self.assertTrue(loaded["ask_partner"][0].needs_review)

    def test_confirming_a_new_value_retires_the_old_one(self) -> None:
        self._confirmed("exclude_promoted_last_6m", True)
        replacement = self._confirmed("exclude_promoted_last_6m", False, prefix="t")
        loaded = self.memory.load_for_session(PARTNER, ORG, date(2026, 12, 1))
        self.assertEqual([p.pref_id for p in loaded["apply"]], [replacement.pref_id])
        self.assertEqual(loaded["apply"][0].value, False)
        self.assertEqual(loaded["ask_partner"], [])

    def test_policy_locked_unknown_and_invalid_feedback_is_rejected(self) -> None:
        with self.assertRaises(PolicyLockedError):
            self.memory.record_feedback(PARTNER, ORG, "s1", "waive_tier3_approval", True, OCT_19)
        with self.assertRaises(PolicyLockedError):
            self.memory.record_feedback(PARTNER, ORG, "s1", "raise_budget_cap", 5000000, OCT_19)
        with self.assertRaises(ValueError):
            self.memory.record_feedback(PARTNER, ORG, "s1", "favorite_color", "blue", OCT_19)
        with self.assertRaises(ValueError):
            self.memory.record_feedback(PARTNER, ORG, "s1", "budget_cap_usd", -5, OCT_19)
        with self.assertRaises(ValueError):
            self.memory.record_feedback(PARTNER, ORG, "s1", "min_evidence_for_options", "WEAK", OCT_19)

    def test_org_preference_beats_all_orgs_preference(self) -> None:
        self._confirmed("budget_cap_usd", 1500000, org=ALL_ORGS, prefix="g")
        self._confirmed("budget_cap_usd", 900000, org=ORG, prefix="o")
        here = self.memory.load_for_session(PARTNER, ORG, date(2026, 11, 16))
        elsewhere = self.memory.load_for_session(PARTNER, "VP_CLOUD_AI", date(2026, 11, 16))
        self.assertEqual([p.value for p in here["apply"]], [900000])
        self.assertEqual([p.value for p in elsewhere["apply"]], [1500000])

    def test_budget_cap_from_memory_never_rises_above_the_ledger(self) -> None:
        high = self._confirmed("budget_cap_usd", 1500000)
        self.assertEqual(effective_budget_cap([high], 1050000), 1050000)
        self.assertEqual(effective_budget_cap([high], 2150000), 1500000)
        self.assertEqual(effective_budget_cap([], 2150000), 2150000)

    def test_declined_options_move_last_but_stay_visible(self) -> None:
        declined = self._confirmed("rank_last_option", "Branch_B_Full_Proactive_Cliff_Coverage")
        options = [
            {"branch_id": "Branch_A_Offer_Posture_Plus_Top_Ceiling"},
            {"branch_id": "Branch_B_Full_Proactive_Cliff_Coverage"},
            {"branch_id": "Branch_C_Targeted_High_Performer_Bridge_And_Joint_Offer_Calibration"},
        ]
        ordered = order_options(options, [declined])
        self.assertEqual(len(ordered), 3)
        self.assertEqual(ordered[-1]["branch_id"], "Branch_B_Full_Proactive_Cliff_Coverage")
        self.assertTrue(ordered[-1]["memory_note"].startswith("Declined in 3 earlier sessions."))
        self.assertNotIn("memory_note", ordered[0])

    def test_multi_value_key_keeps_every_declined_option(self) -> None:
        self._confirmed("rank_last_option", "Branch_A", prefix="a")
        self._confirmed("rank_last_option", "Branch_B", prefix="b")
        loaded = self.memory.load_for_session(PARTNER, ORG, date(2026, 11, 16))
        self.assertEqual(sorted(p.value for p in loaded["apply"]), ["Branch_A", "Branch_B"])

    def test_retired_preference_needs_three_new_sessions(self) -> None:
        active = self._confirmed("exclude_tenure_under_1y", True)
        self.memory.retire(active.pref_id, PARTNER, "Partner turned it off", date(2026, 11, 20))
        self.assertEqual(self.memory.load_for_session(PARTNER, ORG, date(2026, 11, 23))["apply"], [])
        later = date(2026, 11, 30)
        self.assertIsNone(self._sessions("exclude_tenure_under_1y", True, count=2, start=later, prefix="n"))
        again = self.memory.record_feedback(
            PARTNER, ORG, "n3", "exclude_tenure_under_1y", True, later + timedelta(weeks=2)
        )
        self.assertEqual((again.pref_id, again.status, again.session_count), (active.pref_id, "proposed", 3))

    def test_preferences_survive_a_new_store_instance(self) -> None:
        self._confirmed("brief_detail", "summary")
        reopened = PartnerMemory(self.path)
        loaded = reopened.load_for_session(PARTNER, ORG, date(2026, 11, 16))
        self.assertEqual([(p.key, p.value) for p in loaded["apply"]], [("brief_detail", "summary")])


if __name__ == "__main__":
    unittest.main()
