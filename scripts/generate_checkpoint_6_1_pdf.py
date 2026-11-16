"""Generates submission-ready PDF for Checkpoint 6.1 using Playwright and inline SVG."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
OUTPUT_PDF = OUTPUT_DIR / "checkpoint_6_1.pdf"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
  <style>
    @page {
      size: letter;
      margin: 0.65in 0.75in 0.75in 0.75in;
    }

    * {
      box-sizing: border-box;
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #1e293b;
      background-color: #ffffff;
      line-height: 1.48;
      font-size: 9.2pt;
      margin: 0;
      padding: 0;
    }

    .header-banner {
      border-bottom: 2.5px solid #C41230;
      padding-bottom: 9px;
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }

    .institution-meta {
      max-width: 66%;
    }

    .institution-name {
      font-size: 8pt;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #C41230;
      margin-bottom: 2px;
    }

    .program-name {
      font-size: 9.2pt;
      font-weight: 600;
      color: #0f172a;
      margin-bottom: 4px;
    }

    .doc-title {
      font-size: 15pt;
      font-weight: 800;
      color: #0f172a;
      line-height: 1.2;
      margin: 0;
      letter-spacing: -0.01em;
    }

    .meta-box {
      text-align: right;
      font-size: 8pt;
      color: #475569;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 6px 10px;
      line-height: 1.45;
    }

    .meta-box strong {
      color: #0f172a;
    }

    .badge {
      display: inline-block;
      padding: 1.5px 6px;
      font-size: 7pt;
      font-weight: 700;
      border-radius: 4px;
      background: #eff6ff;
      color: #1d4ed8;
      border: 1px solid #bfdbfe;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .badge-cmu {
      background: #fdf2f2;
      color: #C41230;
      border-color: #fecaca;
    }

    h2.section-header {
      font-size: 10.5pt;
      font-weight: 700;
      color: #0f172a;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 4px;
      margin-top: 12px;
      margin-bottom: 9px;
      display: flex;
      align-items: center;
      gap: 7px;
      page-break-after: avoid;
      break-after: avoid;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    h2.section-header::before {
      content: "";
      display: inline-block;
      width: 4px;
      height: 13px;
      background-color: #C41230;
      border-radius: 2px;
    }

    h3.sub-header {
      font-size: 10pt;
      font-weight: 700;
      color: #0f172a;
      margin-top: 10px;
      margin-bottom: 5px;
      page-break-after: avoid;
      break-after: avoid;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    p {
      margin-top: 0;
      margin-bottom: 7px;
      text-align: justify;
      text-justify: inter-word;
    }

    code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8.2pt;
      background: #f1f5f9;
      color: #0f172a;
      padding: 1px 4px;
      border-radius: 3px;
    }

    .diagram-card {
      background: #fbfcfe;
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      padding: 8px 10px;
      margin-bottom: 10px;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    .diagram-caption {
      font-size: 7.4pt;
      color: #64748b;
      text-align: center;
      margin-top: 5px;
      font-weight: 500;
      border-top: 1px solid #e2e8f0;
      padding-top: 4px;
      line-height: 1.35;
    }

    .diagram-svg-container {
      display: flex;
      justify-content: center;
      width: 100%;
    }

    .diagram-svg-container svg {
      width: 100%;
      height: auto;
      display: block;
    }

    strong {
      color: #0f172a;
      font-weight: 600;
    }

    .section-block { margin-bottom: 6px; }
    ul.bullets { margin: 0 0 7px 0; padding-left: 16px; }
    ul.bullets li { margin-bottom: 4px; text-align: justify; }
  </style>
</head>
<body>

  <div class="header-banner">
    <div class="institution-meta">
      <div class="institution-name">Carnegie Mellon University &bull; School of Computer Science</div>
      <div class="program-name">Executive Education: Agentic AI Program &bull; Capstone Project</div>
      <h1 class="doc-title">Checkpoint 6.1: Safety Guardrails and Human Intervention Plan</h1>
    </div>
    <div class="meta-box">
      <div><strong>Student:</strong> Pedro Griff Marcincowski</div>
      <div><strong>Project:</strong> Strategic Comp Insight Advisor</div>
      <div><strong>Track:</strong> <span class="badge">Research Assistant</span></div>
      <div><strong>Submission:</strong> <span class="badge badge-cmu">Module 6 &bull; Checkpoint 6.1</span></div>
    </div>
  </div>

  <h2 class="section-header">System Architecture Diagram</h2>
  <div class="diagram-card">
    <div class="diagram-svg-container">
      <svg viewBox="0 0 860 396" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <defs>
          <marker id="arrow-slate" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#64748b" />
          </marker>
          <marker id="arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#2563eb" />
          </marker>
          <marker id="arrow-amber" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#d97706" />
          </marker>
          <marker id="arrow-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#dc2626" />
          </marker>
          <marker id="arrow-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#16a34a" />
          </marker>
          <marker id="arrow-purple" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#7c3aed" />
          </marker>
          <filter id="card-shadow" x="-5%" y="-5%" width="110%" height="115%">
            <feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-color="#0f172a" flood-opacity="0.06" />
          </filter>
        </defs>

        <!-- ==================== DASHED SCOPED EXECUTION CONTAINER ==================== -->
        <rect x="20" y="132" width="800" height="66" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5 4" />
        <g transform="translate(34, 132)">
          <rect x="0" y="-9" width="246" height="18" rx="4" fill="#ffffff" stroke="#94a3b8" stroke-width="1" />
          <text x="123" y="3.5" font-size="7.8" font-weight="800" fill="#475569" letter-spacing="0.04em" text-anchor="middle">G2 &amp; G3: SCOPED READ-ONLY EXECUTION</text>
        </g>

        <!-- ==================== CONNECTORS & EDGE LABELS ==================== -->
        <!-- 1. Partner -> G1 Screen -->
        <path d="M 380 38 L 380 66" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <g transform="translate(380, 52)">
          <rect x="-86" y="-8" width="172" height="16" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.8" font-weight="600" fill="#1e40af" text-anchor="middle">1. Request + PartnerContext</text>
        </g>

        <!-- 2. G1 Screen -> Refused -->
        <path d="M 556 87 L 620 87" fill="none" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(588, 87)">
          <rect x="-24" y="-7.5" width="48" height="15" rx="3" fill="#fff1f2" stroke="#fecdd3" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.5" font-weight="700" fill="#be123c" text-anchor="middle">Refuse</text>
        </g>

        <!-- 3. G1 Screen -> Squad (clear right of container title x=34..280) -->
        <path d="M 380 108 L 380 148" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(380, 125)">
          <rect x="-28" y="-7.5" width="56" height="15" rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.6" font-weight="700" fill="#166534" text-anchor="middle">ALLOW</text>
        </g>

        <!-- 4. Squad <-> PartnerMemory & SqliteSaver -->
        <path d="M 578 169 L 612 169" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-start="url(#arrow-purple)" marker-end="url(#arrow-purple)" />

        <!-- 5. Squad -> G4 Verifier & Monitor -->
        <path d="M 380 190 L 380 222" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <g transform="translate(380, 206)">
          <rect x="-56" y="-7.5" width="112" height="15" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.6" font-weight="700" fill="#1e40af" text-anchor="middle">Draft + SquadState</text>
        </g>

        <!-- 6. Revision loop: G4 -> Squad via left open channel x=68 -->
        <path d="M 134 244 L 68 244 L 68 169 L 132 169" fill="none" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(68, 206)">
          <rect x="-40" y="-8" width="80" height="16" rx="3" fill="#fff1f2" stroke="#fecdd3" stroke-width="0.9" />
          <text x="0" y="3" font-size="7.5" font-weight="700" fill="#be123c" text-anchor="middle">Revise &lt;= 2</text>
        </g>

        <!-- 7. G4 -> HOLD_FOR_HUMAN_REVIEW -->
        <path d="M 578 244 L 628 244" fill="none" stroke="#d97706" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrow-amber)" />
        <g transform="translate(603, 244)">
          <rect x="-20" y="-7.5" width="40" height="15" rx="3" fill="#fffbeb" stroke="#fde68a" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.5" font-weight="700" fill="#92400e" text-anchor="middle">Hold</text>
        </g>

        <!-- 8. G4 -> Risk Router -->
        <path d="M 380 266 L 380 298" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(380, 282)">
          <rect x="-56" y="-7.5" width="112" height="15" rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.6" font-weight="700" fill="#166534" text-anchor="middle">Verified + 0 flags</text>
        </g>

        <!-- 9. Risk Router -> AUTO_RELEASE -->
        <path d="M 250 340 L 250 358" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />

        <!-- 10. Risk Router -> Durable Approval Gate -->
        <path d="M 510 340 L 510 358" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-end="url(#arrow-purple)" />

        <!-- 11. Released Brief & Feedback return highway along x=844 -->
        <path d="M 792 374 L 844 374 L 844 23 L 542 23" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(694, 23)">
          <rect x="-118" y="-9" width="236" height="18" rx="4" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1" />
          <text x="0" y="3.4" font-size="8.0" font-weight="700" fill="#15803d" text-anchor="middle">RELEASED brief + provenance + feedback</text>
        </g>

        <!-- ==================== NODE BOXES ==================== -->
        <!-- Strategic Comp Partner -->
        <g filter="url(#card-shadow)">
          <rect x="220" y="8" width="320" height="30" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.75" />
          <text x="380" y="27" font-size="10.2" font-weight="700" fill="#1e3a8a" text-anchor="middle">Strategic Comp Partner (Gradio UI + session RBAC)</text>
        </g>

        <!-- G1 Integrity & Request Screen -->
        <g filter="url(#card-shadow)">
          <rect x="204" y="66" width="352" height="42" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.75" />
          <text x="380" y="83" font-size="9.5" font-weight="700" fill="#14532d" text-anchor="middle">G1: Playbook SHA-256 &amp; Request Screen</text>
          <text x="380" y="97" font-size="7.8" font-weight="600" fill="#166534" text-anchor="middle">verify_manifest() + screen_request() across 8 rules</text>
        </g>

        <!-- Blocked at G1 -->
        <g filter="url(#card-shadow)">
          <rect x="622" y="66" width="196" height="42" rx="6" fill="#fff1f2" stroke="#e11d48" stroke-width="1.5" />
          <text x="720" y="83" font-size="8.8" font-weight="700" fill="#9f1239" text-anchor="middle">Blocked at G1 (1.4 ms)</text>
          <text x="720" y="97" font-size="7.5" font-weight="600" fill="#be123c" text-anchor="middle">0 tool calls: injection, PII, write</text>
        </g>

        <!-- 5-Agent LangGraph StateGraph -->
        <g filter="url(#card-shadow)">
          <rect x="134" y="148" width="444" height="42" rx="5" fill="#ffffff" stroke="#2563eb" stroke-width="1.6" />
          <text x="356" y="165" font-size="9.3" font-weight="700" fill="#1e3a8a" text-anchor="middle">5-Agent LangGraph StateGraph (Send() parallel specialists)</text>
          <text x="356" y="179" font-size="7.8" font-weight="600" fill="#334155" text-anchor="middle">ScopedToolExecutor (1-3 tools, allowed_orgs) + SQLite ?mode=ro</text>
        </g>

        <!-- PartnerMemory & SqliteSaver -->
        <g filter="url(#card-shadow)">
          <rect x="614" y="148" width="194" height="42" rx="5" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.5" />
          <text x="711" y="165" font-size="8.7" font-weight="700" fill="#581c87" text-anchor="middle">PartnerMemory &amp; SqliteSaver</text>
          <text x="711" y="179" font-size="7.4" font-weight="600" fill="#6b21a8" text-anchor="middle">POLICY_LOCKED + preview/commit</text>
        </g>

        <!-- G4 Verifier, Output Guard & Monitor -->
        <g filter="url(#card-shadow)">
          <rect x="134" y="222" width="444" height="44" rx="6" fill="#fefce8" stroke="#ca8a04" stroke-width="1.6" />
          <text x="356" y="239" font-size="9.3" font-weight="700" fill="#713f12" text-anchor="middle">G4: Deterministic Verifier, Output Guard &amp; RuntimeMonitor</text>
          <text x="356" y="254" font-size="7.7" font-weight="600" fill="#854d0e" text-anchor="middle">Option figure triples, side-matched clauses, EMP_ ban, trace transition audit</text>
        </g>

        <!-- HOLD_FOR_HUMAN_REVIEW -->
        <g filter="url(#card-shadow)">
          <rect x="630" y="222" width="188" height="44" rx="6" fill="#fff7ed" stroke="#d97706" stroke-width="1.5" />
          <text x="724" y="239" font-size="8.4" font-weight="700" fill="#9a3412" text-anchor="middle">HOLD_FOR_HUMAN_REVIEW</text>
          <text x="724" y="254" font-size="7.4" font-weight="600" fill="#b45309" text-anchor="middle">Inspect or discard only</text>
        </g>

        <!-- Worst-Signal Risk Router -->
        <g filter="url(#card-shadow)">
          <rect x="180" y="298" width="400" height="42" rx="6" fill="#eff6ff" stroke="#2563eb" stroke-width="1.6" />
          <text x="380" y="315" font-size="9.3" font-weight="700" fill="#1e3a8a" text-anchor="middle">Worst-Signal Risk Router &amp; SHA-256 AuditLog</text>
          <text x="380" y="329" font-size="7.7" font-weight="600" fill="#1d4ed8" text-anchor="middle">assess_risk() over spend, Tier 3, budget headroom, CIs, and hash chain</text>
        </g>

        <!-- AUTO_RELEASE -->
        <g filter="url(#card-shadow)">
          <rect x="50" y="358" width="330" height="32" rx="5" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5" />
          <text x="215" y="378" font-size="8.4" font-weight="700" fill="#14532d" text-anchor="middle">AUTO_RELEASE: Policy Q&amp;A or $0 spend (78.3%)</text>
        </g>

        <!-- Durable Approval Gate -->
        <g filter="url(#card-shadow)">
          <rect x="412" y="358" width="380" height="32" rx="5" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.6" />
          <text x="602" y="378" font-size="8.4" font-weight="700" fill="#4c1d95" text-anchor="middle">Approval Gate: interrupt() + Bounded Card (21.7%)</text>
        </g>
      </svg>
    </div>
    <div class="diagram-caption">
      <strong>Figure 1:</strong> Checkpoint 6.1 wraps the five-agent LangGraph squad in four deterministic control layers: <code>G1</code> playbook SHA-256 and request screening, <code>G2/G3</code> session-scoped read-only SQLite execution, <code>G4</code> proposition-based output verification and trajectory monitoring, and worst-signal risk routing into <code>AUTO_RELEASE</code>, durable SQLite <code>interrupt()</code> sign-off, or <code>HOLD_FOR_HUMAN_REVIEW</code>.
    </div>
  </div>

  <h2 class="section-header">Written Submission</h2>

  <div class="section-block">
    <h3 class="sub-header">1. Purpose and workflow risks</h3>
    <p>The advisor runs a five-agent LangGraph <code>StateGraph</code> behind a Gradio console to draft cohort retention briefs, reactive-offer diagnostics, and cross-lever policy comparisons on synthetic Apex Cloud &amp; AI Corp data. Five workflow risks threaten safe operation: prompt injections or requests for individual pay, protected traits, and write actions; cross-organization data leaks across compensation partners; fabricated or swapped currency figures, headcounts, and percentages; wrong-population policy citations, such as applying new-hire caps to staff grants; and overconfident spend commitments issued without executive sign-off.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">2. Layered safety guardrails</h3>
    <p>Following the MAESTRO defense-in-depth blueprint and Baker et al.'s finding that chain-of-thought monitors fail under obfuscation, Python code enforces every guardrail on states and outputs rather than soft prompt instructions:</p>
    <ul class="bullets">
      <li><strong>Pre-execution at <code>G1</code>.</strong> <code>verify_manifest()</code> checks the playbook's SHA-256 digest before execution, and <code>screen_request()</code> blocks prompt injections, individual pay queries, protected traits, write orders, out-of-scope prompts, and cross-org requests in <code>1.4 ms</code> with zero tool calls.</li>
      <li><strong>Tool and state locks at <code>G2</code> and <code>G3</code>.</strong> <code>ScopedToolExecutor</code> enforces session-bound <code>allowed_orgs</code>, limits each role to one to three tools, and blocks duplicate calls. Roster SQLite connections open read-only via <code>?mode=ro</code>, while <code>PartnerMemory</code> blocks <code>POLICY_LOCKED</code> overrides and requires preview-and-commit confirmation.</li>
      <li><strong>Output and trajectory checks at <code>G4</code>.</strong> <code>deterministic_verify_brief()</code> and proposition-based <code>check_brief()</code> reject ungrounded numbers, swapped option costs, missing side-matched clauses, <code>EMP_</code> IDs, outcome guarantees, and approval claims across at most <code>MAX_REVISIONS = 2</code> redrafts. <code>review_trajectory()</code> checks node transitions and call budgets, while <code>AuditLog</code> writes a SHA-256 hash chain.</li>
    </ul>
  </div>

  <div class="section-block">
    <h3 class="sub-header">3. Workflow evaluation metrics</h3>
    <p><code>src/guardrails/evaluate.py</code> tracks five multi-scenario metrics aligned with HELM:</p>
    <ul class="bullets">
      <li><strong>Request boundary precision and recall.</strong> Across 136 cases in four splits, the screen refuses <code>0 of 50</code> benign requests, reaches <code>40 of 48</code> or <code>83.3%</code> single-pass accuracy on an untouched adversarial split <code>held_out_2</code>, and contains <code>10 of 10</code> leaked violations downstream.</li>
      <li><strong>Numeric and policy groundedness.</strong> All <code>23 of 23</code> clean briefs pass, and <code>155 of 160</code> or <code>96.9%</code> of seeded numerical, citation, PII, and promise faults are rejected.</li>
      <li><strong>Trajectory monitor accuracy.</strong> Clean runs trigger <code>0</code> false alarms while <code>7 of 7</code> seeded trace faults are flagged.</li>
      <li><strong>Escalation rate.</strong> Across <code>23</code> workflow runs, <code>18</code> or <code>78.3%</code> auto-release and <code>5</code> or <code>21.7%</code> escalate to human sign-off.</li>
      <li><strong>Latency overhead.</strong> Controls add <code>53.4 ms</code>, moving median runtime from <code>75.8 ms</code> to <code>129.1 ms</code>.</li>
    </ul>
  </div>

  <div class="section-block">
    <h3 class="sub-header">4. Risk routing and human intervention criteria</h3>
    <p>Instead of one universal gate, <code>assess_risk()</code> takes the worst signal across verification, monitor flags, spend, and playbook triggers to select four lanes. <code>AUTO_RELEASE</code> publishes cited policy comparisons and zero-spend briefs for <code>VP_ENT_APPS</code> and <code>VP_INFRA_SRE</code>. <code>PARTNER_APPROVAL</code> pauses in-budget cohort options without executive exceptions. <code>EXECUTIVE_SIGN_OFF</code> pauses runs via LangGraph <code>interrupt()</code> in SQLite when an option triggers Tier 3 grants requiring <code>VP</code> and <code>Head of Compensation</code>, over-budget spend requiring <code>VP</code>, level reviews requiring <code>Calibration committee</code>, or policy conflicts requiring <code>Compensation governance</code>, refusing <code>9 of 9</code> unacknowledged approvals. <code>HOLD_FOR_HUMAN_REVIEW</code> quarantines unverified drafts, tool errors, monitor flags, or hash mismatches for inspection or discard only.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">5. Closed-loop strategy and design trade-offs</h3>
    <p>Guardrails, metrics, and selective oversight form one closed loop. Code locks block irreversible actions, risk routing preserves autonomy and efficiency on <code>78.3%</code> of runs while focusing human oversight on <code>21.7%</code> high-impact briefs, and reason-coded reviewer edits such as <code>wrong_option_order</code> feed <code>PartnerMemory</code> proposals and new regression cases in <code>guardrail_cases.json</code>. Choosing deterministic rules over an LLM judge trades paraphrase recall at <code>G1</code>, where <code>8 of 30</code> disguised prompts pass <code>G1</code> before downstream scopes contain them, and existence-only percentage checks, which miss <code>5 of 160</code> faults when a swapped percentage already appears in tool output, for zero token cost, <code>53.4 ms</code> latency, and reproducible deployment reliability.</p>
  </div>

</body>
</html>
"""


async def generate_pdf():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 1600})
        await page.set_content(HTML_TEMPLATE, wait_until="networkidle")
        await page.wait_for_selector("svg")
        await asyncio.sleep(1)

        pdf_bytes = await page.pdf(
            path=str(OUTPUT_PDF),
            format="Letter",
            print_background=True,
            margin={
                "top": "0.65in",
                "bottom": "0.7in",
                "left": "0.7in",
                "right": "0.7in",
            },
            display_header_footer=True,
            header_template='''
                <div style="font-size: 7.5pt; font-family: 'Inter', sans-serif; color: #94a3b8; width: 100%; display: flex; justify-content: space-between; padding: 0 0.7in;">
                  <span>Carnegie Mellon University &bull; SCS Executive Education: Agentic AI</span>
                  <span>Checkpoint 6.1 Submission</span>
                </div>
            ''',
            footer_template='''
                <div style="font-size: 7.5pt; font-family: 'Inter', sans-serif; color: #94a3b8; width: 100%; display: flex; justify-content: space-between; padding: 0 0.7in;">
                  <span>Strategic Talent &amp; Compensation Insight Advisor</span>
                  <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
                </div>
            ''',
        )
        print(f"Generated {OUTPUT_PDF} ({len(pdf_bytes)} bytes)")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(generate_pdf())
