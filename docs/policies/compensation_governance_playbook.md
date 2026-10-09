# Enterprise Compensation Governance and Partner Playbook

*Synthetic Policy Corpus for RAG Indexing in Checkpoint 3.1*

## Section 1. Compensation Philosophy and Core Principles

Apex Cloud & AI Corp structures total compensation around three principles:
1. **Cost-of-Labor Market Competitiveness.** Base salary bands and equity refresh targets are calibrated annually against local cost-of-labor benchmarks for each job family and level.
2. **Pay-for-Performance Differentiation.** Annual equity refresh multipliers and bonus outcomes scale with sustained multi-year performance ratings (`rating_3`, `rating_4`, and `rating_5`).
3. **Long-Term Ownership and Cashflow Continuity.** Equity grants vest over four years on a front-loaded schedule (`38% Year 1, 32% Year 2, 20% Year 3, 10% Year 4`). Strategic Compensation Partners monitor three-year forward Intended Cashflow (`ICF`) to prevent unintended compensation cliffs for high-performing talent.

---

## Section 2. Organizational Boundary: Reactive Offers Desk vs. Strategic Client Partners

To maintain internal equity and prevent ad-hoc bidding wars, responsibilities are divided between two teams:

### 2.1 The Reactive Offers and Counter-Offers Desk
- **Scope.** New-hire offer construction, candidate negotiations, and **reactive counter-offers** when a current employee presents a verified external written offer.
- **Thresholds.** Standard new-hire offers up to `1.00 Compa-Ratio` and `1.20x Equity Guideline` are approved within the Offers Desk. Reactive counter-offers require verification of the competing employer, level, and cash/equity breakdown.
- **Escalation Trigger to Strategic Client Partners.** Whenever a job family within a VP organization experiences **either** a new-hire offer acceptance rate below `65%` over a rolling quarter **or** more than `5` reactive counter-offers in a single quarter, the issue can no longer be treated as isolated candidate friction. The Offers Desk must trigger a joint review with the Strategic Compensation Partner to evaluate whether structural band adjustments or targeted proactive retention grants are warranted.

### 2.2 Strategic Client Compensation Partners
- **Scope.** Advising Engineering Vice Presidents and Lead People Partners on org-wide compensation health, annual cycle execution, **proactive retention equity grants**, and multi-year budget allocation.
- **Proactive vs. Reactive Rule.** Proactive retention grants are designed to bridge foreseeable `2027` and `2028` Intended Cashflow drops (`>15% YoY drop`) for top-tier talent *before* external poaching occurs. Reactive counter-offers must be charged to the **Reactive Counter Ledger** and must never be miscoded into the **Proactive Retention Budget** without Finance and VP sign-off.

---

## Section 3. The 4-Tier Proactive Retention Sizing Rubric

When evaluating a cohort or individual for a proactive retention award, Strategic Compensation Partners apply the deterministic 4-Tier Sizing Rubric:

- **Tier 0: Hold / No Action.**
  - *Criteria:* Employee has a `2025` rating of `rating_1` or `rating_2`, OR received a proactive retention grant within the past `24 months`, OR has a projected `2026-to-2027` cashflow drop smaller than `10%` with peer positioning above the `50th percentile`.
  - *Action:* Do not allocate proactive budget. Address retention through standard annual refresh planning.

- **Tier 1: Initial Anchor / Cliff Bridge.**
  - *Criteria:* Employee is rated `rating_3` with a projected `2026-to-2027` cashflow drop between `15%` and `22%`, or peer percentile dropping below the `25th percentile` in `2027`.
  - *Sizing Rule:* Grant size equals `50% to 75%` of the annual equity refresh guideline, structured over `24 months` to restore `2027` Intended Cashflow to at least `90%` of `2026` levels.

- **Tier 2: Target Competitive Restoration.**
  - *Criteria:* Employee is rated `rating_4` or tagged as `Critical AI Talent (Tier_1 or Tier_2)` in a high-poaching job family (`AI_ML_ENG`, `RESEARCH_SCI`, `CYBER_SEC_ENG`) with a projected `2027` cashflow drop exceeding `15%`.
  - *Sizing Rule:* Grant size equals `100% to 135%` of the annual equity refresh guideline, restoring `2027` Intended Cashflow to `100%` of `2026` levels and positioning the employee between the `65th and 80th peer percentile`.

- **Tier 3: Max In-Range Ceiling & Executive Escalation.**
  - *Criteria:* Employee is rated `rating_5` or holds a mission-critical architecture role facing active competitor raids (`>25%` external market premium observed in Offers Desk logs) and a `>20%` internal cashflow cliff.
  - *Sizing Rule:* Grant size up to `150% to 200%` of the annual equity refresh guideline. **Requires explicit Human-in-the-Loop approval** from both the VP and the Head of Compensation.

---

## Section 4. Governance Audits: Manager Inversions and Promotion Band Checks

Before any proactive retention recommendation or executive brief is finalized, the system must audit three governance rules:
1. **Multi-Year Manager Inversion Audit.** A direct report's projected `2026` or `2027` Intended Cashflow should not exceed their people manager's Intended Cashflow if the manager is at a higher job level (`IC4` manager vs. `IC3` IC), unless documented as a specialized technical fellow exception. Often, a manager's expiring prior retention grant creates a hidden `2027` inversion that must be flagged alongside IC retention planning.
2. **Stale Promotion Band Verification.** Employees promoted within the last `6 months` whose `Compa-Ratio` appears below `0.83` must be audited to verify that their Market Reference Point (`MRP`) and refresh guidelines reflect their new post-promotion level rather than cached pre-promotion tables.
3. **Ledger Reconciliation Check.** Compare YTD proactive spend against the department's `proactive_remaining_usd` cap. Flag any miscoded verbal counter-offers before recommending new proactive allocations.

---

## Section 5. Standards for Executive Insight Briefs

Vice Presidents and Lead People Partners require concise, decision-oriented briefs rather than raw data dumps. Every brief generated by the Strategic Talent and Compensation Insight Advisor must contain four sections:
1. **Executive Headline.** Two sentences stating the primary talent risk cohort, the link between reactive offer/counter friction and internal cashflow cliffs, and the budget status.
2. **Proactive vs. Reactive Diagnostic.** A side-by-side summary of what the Reactive Offers Log shows (accept rate, competing employer premiums, primary loss drivers) versus what the Internal Roster shows (headcount facing `>15%` cashflow drops in `2027`, peer percentile erosion, and governance flags).
3. **Branching Intervention Options (Tree-of-Thought Trade-Offs).** Three costed options comparing:
   - *Option A (Offer & Counter Posture Shift):* Adjusting new-hire/counter bands with the Offers Desk.
   - *Option B (Targeted Proactive Cliff Bridge):* Funding Tier 1 and Tier 2 proactive grants for high-performing cliff cohorts within existing department budget.
   - *Option C (Hybrid Co-Owned Plan):* Combining targeted Tier 2 proactive grants for critical talent with a joint Offers Desk calibration for new-hire bands.
4. **Governance & Human Sign-Off Checklist.** Explicit callouts of any 2027 manager inversions, ledger reconciliation discrepancies, or Tier 3 exceptions requiring human sign-off.
