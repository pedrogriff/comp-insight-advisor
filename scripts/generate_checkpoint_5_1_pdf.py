"""Generates submission-ready PDF for Checkpoint 5.1 using Playwright and inline SVG."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
OUTPUT_PDF = OUTPUT_DIR / "checkpoint_5_1.pdf"

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

    .page-break {
      page-break-before: always;
      break-before: page;
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
      <h1 class="doc-title">Checkpoint 5.1: Multi-Agent Architecture and Coordination Plan</h1>
    </div>
    <div class="meta-box">
      <div><strong>Student:</strong> Pedro Griff Marcincowski</div>
      <div><strong>Project:</strong> Strategic Comp Insight Advisor</div>
      <div><strong>Track:</strong> <span class="badge">Research Assistant</span></div>
      <div><strong>Submission:</strong> <span class="badge badge-cmu">Module 5 &bull; Checkpoint 5.1</span></div>
    </div>
  </div>

  <h2 class="section-header">System Architecture Diagram</h2>
  <div class="diagram-card">
    <div class="diagram-svg-container">
      <svg viewBox="0 0 860 392" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
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

        <!-- ==================== DASHED FAN-OUT CONTAINER ==================== -->
        <rect x="20" y="132" width="820" height="76" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5 4" />
        <g transform="translate(36, 132)">
          <rect x="0" y="-9" width="276" height="18" rx="4" fill="#ffffff" stroke="#94a3b8" stroke-width="1" />
          <text x="138" y="3.5" font-size="8.0" font-weight="800" fill="#475569" letter-spacing="0.04em" text-anchor="middle">PARALLEL SEND() FAN-OUT: SCOPED SPECIALISTS</text>
        </g>

        <!-- ==================== CONNECTORS & EDGE LABELS ==================== -->
        <!-- 1. Partner to Supervisor -->
        <path d="M 400 38 L 400 64" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <g transform="translate(400, 51)">
          <rect x="-82" y="-8.5" width="164" height="17" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#1e40af" text-anchor="middle">1. VP org or policy request</text>
        </g>

        <!-- 2. Supervisor <-> PartnerMemory & Checkpointer -->
        <path d="M 532 86 L 608 86" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-start="url(#arrow-purple)" marker-end="url(#arrow-purple)" />

        <!-- 3. Supervisor -> Proactive Strategist (clear right of container title badge x=36..312) -->
        <path d="M 368 106 L 368 150" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(368, 122)">
          <rect x="-44" y="-8" width="88" height="16" rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.8" font-weight="700" fill="#166534" text-anchor="middle">Send() task</text>
        </g>

        <!-- 4. Supervisor -> Reactive Analyst -->
        <path d="M 492 106 L 492 150" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(492, 122)">
          <rect x="-44" y="-8" width="88" height="16" rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.8" font-weight="700" fill="#166534" text-anchor="middle">Send() task</text>
        </g>

        <!-- 5. Proactive Strategist -> SquadState Shared Pool -->
        <path d="M 280 198 L 280 238" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-end="url(#arrow-purple)" />
        <g transform="translate(280, 218)">
          <rect x="-54" y="-8" width="108" height="16" rx="3" fill="#faf5ff" stroke="#ddd6fe" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.8" font-weight="700" fill="#5b21b6" text-anchor="middle">One-way Finding</text>
        </g>

        <!-- 6. Reactive Analyst -> SquadState Shared Pool -->
        <path d="M 580 198 L 580 238" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-end="url(#arrow-purple)" />
        <g transform="translate(580, 218)">
          <rect x="-54" y="-8" width="108" height="16" rx="3" fill="#faf5ff" stroke="#ddd6fe" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.8" font-weight="700" fill="#5b21b6" text-anchor="middle">One-way Finding</text>
        </g>

        <!-- 7. SquadState -> Executive Synthesizer (fan-in barrier) -->
        <path d="M 275 276 L 275 302" fill="none" stroke="#d97706" stroke-width="1.6" marker-end="url(#arrow-amber)" />
        <g transform="translate(275, 289)">
          <rect x="-48" y="-7.5" width="96" height="15" rx="3" fill="#fffbeb" stroke="#fde68a" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.6" font-weight="700" fill="#92400e" text-anchor="middle">Fan-in barrier</text>
        </g>

        <!-- 8. Executive Synthesizer -> Governance Reviewer -->
        <path d="M 400 322 L 466 322" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <g transform="translate(433, 322)">
          <rect x="-24" y="-7.5" width="48" height="15" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.6" font-weight="700" fill="#1e40af" text-anchor="middle">Draft</text>
        </g>

        <!-- 9. Two-way review loop: Governance Reviewer -> Executive Synthesizer -->
        <path d="M 540 348 L 540 370 L 210 370 L 210 350" fill="none" stroke="#dc2626" stroke-width="1.6" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(375, 370)">
          <rect x="-156" y="-8.5" width="312" height="17" rx="4" fill="#fff1f2" stroke="#fecdd3" stroke-width="1" />
          <text x="0" y="3.2" font-size="7.8" font-weight="700" fill="#be123c" text-anchor="middle">Two-way review: missing figure or clause (max 2)</text>
        </g>

        <!-- 10. Conditional escalation: Governance Reviewer -> Failover / HOLD -->
        <path d="M 712 348 L 712 360" fill="none" stroke="#d97706" stroke-width="1.5" stroke-dasharray="3 2" marker-end="url(#arrow-amber)" />

        <!-- 11. Verified Brief return path: Governance Reviewer -> Strategic Comp Partner -->
        <path d="M 824 322 L 850 322 L 850 23 L 532 23" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(690, 23)">
          <rect x="-102" y="-9" width="204" height="18" rx="4" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1" />
          <text x="0" y="3.5" font-size="8.2" font-weight="700" fill="#15803d" text-anchor="middle">APPROVED: verified brief, 3 options</text>
        </g>

        <!-- ==================== NODE BOXES ==================== -->
        <!-- Strategic Comp Partner -->
        <g filter="url(#card-shadow)">
          <rect x="270" y="8" width="260" height="30" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.75" />
          <text x="400" y="27.5" font-size="11" font-weight="700" fill="#1e3a8a" text-anchor="middle">Strategic Comp Partner</text>
        </g>

        <!-- Supervisor -->
        <g filter="url(#card-shadow)">
          <rect x="210" y="66" width="320" height="40" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.75" />
          <text x="370" y="82" font-size="9.8" font-weight="700" fill="#14532d" text-anchor="middle">Supervisor (fast model, 2 routing tools)</text>
          <text x="370" y="96" font-size="8" font-weight="600" fill="#166534" text-anchor="middle">Scope validation, PartnerMemory load, parallel dispatch</text>
        </g>

        <!-- PartnerMemory & Checkpointer -->
        <g filter="url(#card-shadow)">
          <rect x="610" y="64" width="228" height="44" rx="6" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.6" />
          <text x="724" y="80" font-size="9.2" font-weight="700" fill="#581c87" text-anchor="middle">PartnerMemory &amp; Checkpointer</text>
          <text x="724" y="92" font-size="7.8" font-weight="600" fill="#6b21a8" text-anchor="middle">Standing rules (3-session confirmation)</text>
          <text x="724" y="103" font-size="7.8" font-weight="600" fill="#6b21a8" text-anchor="middle">ThreadCheckpointer step snapshots</text>
        </g>

        <!-- Proactive Strategist -->
        <g filter="url(#card-shadow)">
          <rect x="36" y="152" width="374" height="46" rx="5" fill="#ffffff" stroke="#2563eb" stroke-width="1.5" />
          <text x="223" y="170" font-size="9.3" font-weight="700" fill="#1e3a8a" text-anchor="middle">Proactive Strategist (fast model, 3 internal tools)</text>
          <text x="223" y="183" font-size="7.9" font-weight="600" fill="#334155" text-anchor="middle">SQLite cliffs, eligibility, beam-3 cohort Pareto fronts</text>
          <text x="223" y="193.5" font-size="7.5" font-weight="600" fill="#2563eb" text-anchor="middle">ScopedToolExecutor: max 3 tools, duplicate guard</text>
        </g>

        <!-- Reactive Analyst -->
        <g filter="url(#card-shadow)">
          <rect x="450" y="152" width="374" height="46" rx="5" fill="#ffffff" stroke="#0284c7" stroke-width="1.5" />
          <text x="637" y="170" font-size="9.3" font-weight="700" fill="#0c4a6e" text-anchor="middle">Reactive Analyst (fast model, 3 market tools)</text>
          <text x="637" y="183" font-size="7.9" font-weight="600" fill="#334155" text-anchor="middle">Offer acceptance, 95% CIs, evidence gate, exit notes</text>
          <text x="637" y="193.5" font-size="7.5" font-weight="600" fill="#0284c7" text-anchor="middle">ScopedToolExecutor: max 3 tools, exception catch</text>
        </g>

        <!-- SquadState Shared Pool -->
        <g filter="url(#card-shadow)">
          <rect x="150" y="240" width="560" height="36" rx="6" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.6" />
          <text x="430" y="255" font-size="9.5" font-weight="700" fill="#4c1d95" text-anchor="middle">SquadState Shared Message Pool (findings: Annotated[list[Finding], operator.add])</text>
          <text x="430" y="268" font-size="8" font-weight="600" fill="#6d28d9" text-anchor="middle">Append-only parallel merge &bull; active partner rules &bull; control flags (error, revisions, status)</text>
        </g>

        <!-- Executive Synthesizer -->
        <g filter="url(#card-shadow)">
          <rect x="36" y="304" width="364" height="44" rx="6" fill="#fefce8" stroke="#ca8a04" stroke-width="1.6" />
          <text x="218" y="321" font-size="9.4" font-weight="700" fill="#713f12" text-anchor="middle">Executive Synthesizer (reasoning model, 2 RAG tools)</text>
          <text x="218" y="335" font-size="7.9" font-weight="600" fill="#854d0e" text-anchor="middle">plan_org_options() ($1,995,600 joint plan) + cited brief</text>
        </g>

        <!-- Governance Reviewer -->
        <g filter="url(#card-shadow)">
          <rect x="468" y="304" width="356" height="44" rx="6" fill="#fdf2f2" stroke="#dc2626" stroke-width="1.6" />
          <text x="646" y="321" font-size="9.4" font-weight="700" fill="#991b1b" text-anchor="middle">Governance Reviewer (1 Python verifier)</text>
          <text x="646" y="335" font-size="7.9" font-weight="600" fill="#b91c1c" text-anchor="middle">Independent figure, clause-side, and CI check</text>
        </g>

        <!-- Failover / Human Hold -->
        <g filter="url(#card-shadow)">
          <rect x="596" y="362" width="228" height="22" rx="4" fill="#fff7ed" stroke="#d97706" stroke-width="1.3" />
          <text x="710" y="376" font-size="7.8" font-weight="700" fill="#9a3412" text-anchor="middle">Failover or HOLD_FOR_HUMAN_REVIEW</text>
        </g>
      </svg>
    </div>
    <div class="diagram-caption">
      <strong>Figure 1:</strong> Checkpoint 5.1 replaces the 12-tool single controller with a five-agent LangGraph squad. The supervisor dispatches internal and external specialists in parallel via <code>Send()</code>, merges typed findings through <code>operator.add</code> on <code>SquadState</code>, composes cross-cohort budgets in <code>plan_org_options()</code>, and enforces a two-revision verification gate before delivery or human hold.
    </div>
  </div>

  <h2 class="section-header">Written Submission</h2>

  <div class="section-block">
    <h3 class="sub-header">1. Problem and why one generalist agent fails</h3>
    <p>The advisor builds executive compensation briefs for Apex Cloud &amp; AI Corp partners from SQLite equity cliffs, offer losses, exit notes, policy clauses, and partner preferences. Giving one generalist agent all 12 tools across three stores creates 66 tool-pair choices, runs 15 sequential rounds, and prices <code>VP_CLOUD_AI</code> cohorts separately. Its standalone <code>RESEARCH_SCI</code> and <code>AI_ML_ENG</code> plans sum to $3,246,000, overrunning the shared $2,150,000 proactive budget by $1,096,000. Multi-agent separation scopes each toolset, runs internal and external diagnostics in parallel, composes one shared budget, and isolates verification from drafting.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">2. Five-agent squad and role boundaries</h3>
    <p>The squad uses five agents inside Guo et al.'s three-to-five sweet spot before channels reach <code>n(n-1)/2 = 15</code> at six agents. Roles split only where permissions, corpora, parallelism, or independent checks differ:</p>
    <ul class="bullets">
      <li><code>supervisor</code> parses scope, loads <code>PartnerMemory</code>, and dispatches tasks on a fast model.</li>
      <li><code>proactive_strategist</code> runs three SQLite and beam-3 tools for cliffs, eligibility, and cohort Pareto fronts.</li>
      <li><code>reactive_analyst</code> runs three offer-loss, confidence-interval, and exit-theme tools.</li>
      <li><code>executive_synthesizer</code> runs two filtered policy tools, composes cross-cohort budgets on a reasoning model, and drafts the brief.</li>
      <li><code>governance_reviewer</code> runs one Python verifier across figures, clauses, and disclosures without drafting.</li>
    </ul>
  </div>

  <div class="section-block">
    <h3 class="sub-header">3. Hybrid graph coordination and execution flow</h3>
    <p>A hybrid LangGraph <code>StateGraph</code> governs execution so nodes write state flags while conditional edges only read flags. After scope validation, <code>supervisor</code> fans out via parallel <code>Send()</code> branches to <code>proactive_strategist</code> and <code>reactive_analyst</code>, halving diagnostic latency and scaling across cohorts. Both branches meet at a fan-in barrier before <code>executive_synthesizer</code> calls <code>plan_org_options()</code> to compose <code>VP_CLOUD_AI</code>'s joint $1,995,600 plan, covering 7 of 11 departures and 16 of 16 declined offers with $154,400 headroom. Tool exceptions route to <code>failover</code>, verified briefs route to <code>finalize</code>, and unresolved review cycles route to <code>HOLD_FOR_HUMAN_REVIEW</code>.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">4. Shared-pool communication and bounded feedback</h3>
    <p>Agents exchange typed objects through a <code>SquadState</code> shared message pool rather than free-form chat. Parallel specialists publish <code>Finding</code> records through Python's <code>operator.add</code> list-append reducer so concurrent writes never collide, while <code>PartnerMemory</code> injects confirmed preferences into <code>supervisor</code> and <code>executive_synthesizer</code>. Communication modes match each step's cost and risk. Specialists use one-way state broadcast for speed. <code>executive_synthesizer</code> and <code>governance_reviewer</code> use a two-way review loop carrying missing figures or wrong-side clause IDs for redrafting. Option search runs as width-3 beam pruning inside <code>proactive_strategist</code> instead of open multi-agent brainstorming.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">5. Reliability, complexity, and overhead trade-offs</h3>
    <p>Five chained agents at 95% step accuracy drop to <code>0.95^5 = 77.4%</code> reliability when unverified prose passes down a line. Parallel specialist grounding plus an independent deterministic verifier breaks that serial chain at the cost of explicit state schemas and routing edges. To cap overhead and block recursive doom loops, <code>ScopedToolExecutor</code> rejects out-of-role or duplicate tool calls, retrieval rewrites stop at <code>MAX_RETRIEVAL_ATTEMPTS = 2</code> per lever, and review loops stop at <code>MAX_REVISIONS = 2</code>. That completes <code>VP_CLOUD_AI</code> in 7 messages and 22 tool calls while <code>ThreadCheckpointer</code> snapshots every step.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">6. Feedback from <code>Checkpoint 4.1</code></h3>
    <p>The <code>Checkpoint 4.1</code> graders asked us to test width-3 beam pruning against exhaustive search across a cohort's 32 unique plans and justify multi-cohort limits. Across the three <code>CONVERGENT</code> cohorts, exhaustive search runs 96 code checks and 93 model calls to find 15 Pareto plans. Width 1 uses 42 checks and 11 calls yet misses 10 declined offers on <code>AI_ML_ENG</code> Option 3 and 44 of 105 budget thresholds. Width 2 drops <code>CYBER_SEC_ENG</code>'s $1,261,200 plan and misses 17 thresholds. Width 3 uses 76 checks and 30 calls, matching all 9 options, 15 Pareto plans, and 105 sweeps, while two-stage composition matches <code>VP_CLOUD_AI</code>'s 1,024-plan optimum in 85 checks and 22 calls where a flat 40-plan cap misses all 3.</p>
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
                  <span>Checkpoint 5.1 Submission</span>
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
