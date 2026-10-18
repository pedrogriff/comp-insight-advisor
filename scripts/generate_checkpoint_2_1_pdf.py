"""Generates submission-ready PDF for Checkpoint 2.1 using Playwright and inline SVG."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
OUTPUT_PDF = OUTPUT_DIR / "checkpoint_2_1.pdf"

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

    /* Academic Header */
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

    /* Section Headers */
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

    /* Diagram Card */
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

    /* Structured content items */
    .card-item {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-left: 3px solid #3b82f6;
      border-radius: 5px;
      padding: 6px 10px;
      margin-bottom: 7px;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    .card-item.accent-cmu {
      border-left-color: #C41230;
    }

    .card-item.accent-emerald {
      border-left-color: #059669;
    }

    .card-item.accent-amber {
      border-left-color: #d97706;
    }

    .card-item.accent-purple {
      border-left-color: #7c3aed;
    }

    .card-title {
      font-weight: 700;
      font-size: 8.8pt;
      color: #0f172a;
      margin-bottom: 2px;
    }

    .card-body {
      font-size: 8.8pt;
      color: #334155;
      margin: 0;
      text-align: justify;
    }

    /* Numbered steps */
    .step-item {
      display: flex;
      gap: 9px;
      align-items: flex-start;
      margin-bottom: 7px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 6px 9px;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    .step-badge {
      flex-shrink: 0;
      width: 19px;
      height: 19px;
      background: #0f172a;
      color: #ffffff;
      font-size: 7.8pt;
      font-weight: 700;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-top: 1px;
    }

    .step-content {
      flex-grow: 1;
      font-size: 8.8pt;
      line-height: 1.42;
    }

    .step-content p {
      margin: 0;
    }

    .sub-branches {
      margin-top: 5px;
      padding-left: 8px;
      border-left: 2px solid #cbd5e1;
    }

    .sub-branch {
      margin-bottom: 4px;
      font-size: 8.5pt;
      color: #334155;
      text-align: justify;
    }

    .sub-branch:last-child {
      margin-bottom: 0;
    }

    .avoid-break {
      page-break-inside: avoid;
      break-inside: avoid;
    }

    strong {
      color: #0f172a;
      font-weight: 600;
    }

    em {
      color: #334155;
      font-style: italic;
    }
  </style>
</head>
<body>

  <!-- ==================== PAGE 1 ==================== -->
  <div class="header-banner">
    <div class="institution-meta">
      <div class="institution-name">Carnegie Mellon University &bull; School of Computer Science</div>
      <div class="program-name">Executive Education: Agentic AI Program &bull; Capstone Project</div>
      <h1 class="doc-title">Checkpoint 2.1: Reasoning Loops, Memory Architecture &amp; Tool Usage</h1>
    </div>
    <div class="meta-box">
      <div><strong>Student:</strong> Pedro Griff Marcincowski</div>
      <div><strong>Project:</strong> Strategic Comp Insight Advisor</div>
      <div><strong>Track:</strong> <span class="badge">Research Assistant</span></div>
      <div><strong>Submission:</strong> <span class="badge badge-cmu">Module 2 &bull; Checkpoint 2.1</span></div>
    </div>
  </div>

  <h2 class="section-header">System Architecture Diagram</h2>
  <div class="diagram-card">
    <div class="diagram-svg-container">
      <svg viewBox="0 0 860 390" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
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

        <!-- ==================== ENVIRONMENT DASHED CONTAINER ==================== -->
        <rect x="46" y="138" width="768" height="156" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5 4" />

        <!-- Environment Pill -->
        <g transform="translate(62, 138)">
          <rect x="0" y="-9" width="296" height="18" rx="4" fill="#ffffff" stroke="#94a3b8" stroke-width="1" />
          <text x="148" y="3.5" font-size="8.2" font-weight="800" fill="#475569" letter-spacing="0.04em" text-anchor="middle">DETERMINISTIC EXTERNAL TOOLS &amp; ENVIRONMENT</text>
        </g>

        <!-- ==================== BUS LINES & ARROWS ==================== -->

        <!-- Loop A: Verifier mismatch back to ReAct Controller -->
        <path d="M 275 366 L 24 366 L 24 93 L 240 93" fill="none" stroke="#dc2626" stroke-width="1.6" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(130, 56)">
          <rect x="-98" y="-9" width="196" height="18" rx="4" fill="#fff1f2" stroke="#fecdd3" stroke-width="1" />
          <text x="0" y="3.5" font-size="8.2" font-weight="700" fill="#be123c" text-anchor="middle">Untraced figure &rarr; Regenerate</text>
        </g>

        <!-- Verified brief return to Partner -->
        <path d="M 585 366 L 836 366 L 836 26 L 545 26" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(695, 26)">
          <rect x="-78" y="-9" width="156" height="18" rx="4" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1" />
          <text x="0" y="3.5" font-size="8.5" font-weight="700" fill="#15803d" text-anchor="middle">Verified brief &amp; CIs</text>
        </g>

        <!-- Row 1 -> Row 2: 1. Request VP org review -->
        <path d="M 380 42 L 380 76" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <g transform="translate(320, 59)">
          <rect x="-64" y="-8.5" width="128" height="17" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#1e40af" text-anchor="middle">1. Request VP org review</text>
        </g>

        <!-- Memory Link: ReAct Controller <-> Memory Module -->
        <path d="M 556 93 L 610 93" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-start="url(#arrow-purple)" marker-end="url(#arrow-purple)" />

        <!-- Partner Edits -> Memory Module -->
        <path d="M 510 42 L 715 42 L 715 72" fill="none" stroke="#7c3aed" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrow-purple)" />
        <g transform="translate(625, 42)">
          <rect x="-74" y="-8.5" width="148" height="17" rx="3" fill="#faf5ff" stroke="#e9d5ff" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#6b21a8" text-anchor="middle">5. Partner edits (3-session rule)</text>
        </g>

        <!-- Orthogonal Fan-out from ReAct Controller to Tools -->
        <path d="M 398 112 L 398 156" fill="none" stroke="#64748b" stroke-width="1.5" />
        <path d="M 145 156 L 715 156" fill="none" stroke="#64748b" stroke-width="1.5" />
        <path d="M 145 156 L 145 196" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <path d="M 335 156 L 335 196" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <path d="M 525 156 L 525 196" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <path d="M 715 156 L 715 196" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />

        <!-- Action Pills -->
        <g transform="translate(145, 175)">
          <rect x="-76" y="-8.5" width="152" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#334155" text-anchor="middle">Action 1: Scan org health</text>
        </g>
        <g transform="translate(335, 175)">
          <rect x="-78" y="-8.5" width="156" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#334155" text-anchor="middle">Action 2: Check market logs</text>
        </g>
        <g transform="translate(525, 175)">
          <rect x="-78" y="-8.5" width="156" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#334155" text-anchor="middle">Step 2b: Grade evidence CIs</text>
        </g>
        <g transform="translate(715, 175)">
          <rect x="-78" y="-8.5" width="156" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#334155" text-anchor="middle">Action 3: Policy (CONVERGENT)</text>
        </g>

        <!-- Observations Merge Bus -->
        <path d="M 145 240 L 145 278" fill="none" stroke="#d97706" stroke-width="1.5" />
        <path d="M 335 240 L 335 278" fill="none" stroke="#d97706" stroke-width="1.5" />
        <path d="M 525 240 L 525 278" fill="none" stroke="#d97706" stroke-width="1.5" />
        <path d="M 715 240 L 715 278" fill="none" stroke="#d97706" stroke-width="1.5" />
        <path d="M 145 278 L 715 278" fill="none" stroke="#d97706" stroke-width="1.5" />
        <path d="M 430 278 L 430 302" fill="none" stroke="#d97706" stroke-width="1.5" marker-end="url(#arrow-amber)" />

        <!-- Observation Pills -->
        <g transform="translate(145, 259)">
          <rect x="-74" y="-8.5" width="148" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#b45309" text-anchor="middle">Obs 1: Flagged cliff cohorts</text>
        </g>
        <g transform="translate(335, 259)">
          <rect x="-74" y="-8.5" width="148" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#b45309" text-anchor="middle">Obs 2: Offer &amp; counter counts</text>
        </g>
        <g transform="translate(525, 259)">
          <rect x="-78" y="-8.5" width="156" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#b45309" text-anchor="middle">Obs 2b: Pattern &amp; strength</text>
        </g>
        <g transform="translate(715, 259)">
          <rect x="-74" y="-8.5" width="148" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#b45309" text-anchor="middle">Obs 3: Governance clauses</text>
        </g>

        <!-- Action 4: Draft -> Verifier -->
        <path d="M 430 332 L 430 352" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />

        <!-- ==================== BOXES / NODES ==================== -->

        <!-- ROW 1: Strategic Comp Partner User -->
        <g filter="url(#card-shadow)">
          <rect x="295" y="10" width="250" height="32" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.75" />
          <text x="420" y="30" font-size="11.5" font-weight="700" fill="#1e3a8a" text-anchor="middle">Strategic Comp Partner User</text>
        </g>

        <!-- ROW 2 LEFT: ReAct Controller -->
        <g filter="url(#card-shadow)">
          <rect x="240" y="76" width="316" height="36" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.75" />
          <text x="398" y="92" font-size="10.5" font-weight="700" fill="#14532d" text-anchor="middle">ReAct Reasoning Controller (max_steps = 6)</text>
          <text x="398" y="105" font-size="8.5" font-weight="600" fill="#166534" text-anchor="middle">Thought &rarr; Structured JSON Action &rarr; Python Observation</text>
        </g>

        <!-- ROW 2 RIGHT: Two-Tier Memory Store -->
        <g filter="url(#card-shadow)">
          <rect x="610" y="72" width="210" height="44" rx="6" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.6" />
          <text x="715" y="88" font-size="9.5" font-weight="700" fill="#581c87" text-anchor="middle">Short- &amp; Long-Term Memory</text>
          <text x="715" y="100" font-size="8" font-weight="600" fill="#6b21a8" text-anchor="middle">STM: InvestigationState</text>
          <text x="715" y="111" font-size="8" font-weight="600" fill="#6b21a8" text-anchor="middle">LTM: SQLite Standing Preferences</text>
        </g>

        <!-- ROW 3 NODES: Four Tools (y=196..240) -->
        <g filter="url(#card-shadow)">
          <rect x="58" y="196" width="174" height="44" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.4" />
          <text x="145" y="214" font-size="9.5" font-weight="700" fill="#0f172a" text-anchor="middle">SQLite Roster Tool</text>
          <text x="145" y="228" font-size="8.2" font-weight="600" fill="#334155" text-anchor="middle">Census cliffs &amp; peer ranks</text>
        </g>

        <g filter="url(#card-shadow)">
          <rect x="248" y="196" width="174" height="44" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.4" />
          <text x="335" y="214" font-size="9.5" font-weight="700" fill="#0f172a" text-anchor="middle">SQLite Offers Tool</text>
          <text x="335" y="228" font-size="8.2" font-weight="600" fill="#334155" text-anchor="middle">Acceptance &amp; counter logs</text>
        </g>

        <g filter="url(#card-shadow)">
          <rect x="438" y="196" width="174" height="44" rx="6" fill="#ffffff" stroke="#2563eb" stroke-width="1.5" />
          <text x="525" y="214" font-size="9.5" font-weight="700" fill="#1e3a8a" text-anchor="middle">Evidence Check Tool</text>
          <text x="525" y="228" font-size="8.2" font-weight="600" fill="#1d4ed8" text-anchor="middle">95% Wilson &amp; Student-t CIs</text>
        </g>

        <g filter="url(#card-shadow)">
          <rect x="628" y="196" width="174" height="44" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.4" />
          <text x="715" y="214" font-size="9.5" font-weight="700" fill="#0f172a" text-anchor="middle">ChromaDB Policy Tool</text>
          <text x="715" y="228" font-size="8.2" font-weight="600" fill="#334155" text-anchor="middle">Sizing &amp; Tier 3 ceilings</text>
        </g>

        <!-- ROW 4: Action 4 Brief Synthesis -->
        <g filter="url(#card-shadow)">
          <rect x="255" y="302" width="350" height="30" rx="6" fill="#fefce8" stroke="#ca8a04" stroke-width="1.6" />
          <text x="430" y="321" font-size="10.5" font-weight="700" fill="#713f12" text-anchor="middle">Action 4: Option Synthesis &amp; Uncertainty Framing</text>
        </g>

        <!-- ROW 5: Deterministic Python Verifier -->
        <g filter="url(#card-shadow)">
          <rect x="275" y="352" width="310" height="28" rx="6" fill="#fdf2f2" stroke="#dc2626" stroke-width="1.6" />
          <text x="430" y="370" font-size="10.5" font-weight="700" fill="#991b1b" text-anchor="middle">Python Verifier: Figures, Sources &amp; Data Dates</text>
        </g>
      </svg>
    </div>
    <div class="diagram-caption">
      <strong>Figure 1:</strong> ReAct loop, two-tier memory and deterministic tools for Checkpoint 2.1. An evidence check with Wilson and Student's t intervals sits between the market query and policy retrieval. Standing preferences need three sessions and partner confirmation, a governance lock caps what memory can change, and the verifier traces every figure to a tool output, source and data date.
    </div>
  </div>

  <h2 class="section-header">Written Submission</h2>

  <div class="avoid-break">
    <h3 class="sub-header">1. Reasoning loop and evidence routing</h3>
    <p>
      The <strong>Strategic Talent and Compensation Insight Advisor</strong> runs a ReAct loop capped at six steps. Each thought picks one tool call in structured JSON, Python runs it, and the observation feeds the next thought. The loop tests the VP's concern before it prices anything. Models write the words, code computes the money, and people decide.
    </p>

    <div class="step-item">
      <div class="step-badge">1</div>
      <div class="step-content">
        <p><strong>Scan internal retention risk.</strong> For a VP organization review, the roster tool returns only cohorts where 10 percent or more of employees face a cashflow drop of 15 percent or more, or sit below the 25th peer percentile.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">2</div>
      <div class="step-content">
        <p><strong>Cross-examine market friction.</strong> For each flagged cohort, the offers tool returns new-hire acceptance, counter-offer win rates and competing premiums.</p>
      </div>
    </div>
  </div>

  <!-- ==================== PAGE 2 ==================== -->
  <div class="page-break"></div>

  <h2 class="section-header">Written Submission (Continued)</h2>

  <div class="avoid-break">
    <div class="step-item">
      <div class="step-badge">3</div>
      <div class="step-content">
        <p><strong>Grade the evidence before retrieving policy.</strong> The roster lists every employee, so a cohort's cliff share is a fact. The offers log holds 9 to 20 new-hire offers per job family, so each rate and average carries a 95 percent interval. An indicator counts as conclusive only when its whole interval clears the policy threshold. Evidence strength comes from these counts and intervals, never from the model's own confidence, which can run high on a wrong answer. The check labels the pattern and routes the next thought:</p>
        <div class="sub-branches">
          <div class="sub-branch"><strong><code>CONVERGENT</code>, a cliff backed by conclusive market pressure.</strong> The agent retrieves sizing rules and drafts costed options.</div>
          <div class="sub-branch"><strong><code>INTERNAL_ONLY</code>, a cliff in a calm market.</strong> The agent drafts a monitoring brief with no spend and sends high performers below the 25th percentile to refresh planning.</div>
          <div class="sub-branch"><strong><code>INCONCLUSIVE</code> or <code>INSUFFICIENT_DATA</code>, mixed or thin signals.</strong> Under 5 offer events or 20 employees, or when an interval straddles the 65 percent floor, the agent pools the job family across VP organizations, reads the loss drivers and names the data that would settle the question.</div>
        </div>
      </div>
    </div>
  </div>

  <div class="avoid-break" style="margin-top: 10px;">
    <h3 class="sub-header">2. Short-term working state and long-term partner memory</h3>
    <p>The task needs both kinds of memory, for different reasons:</p>

    <div class="card-item">
      <div class="card-title">Short-term working memory, during one review</div>
      <div class="card-body">A typed state object holds the VP organization, cohort filters, tool outputs and evidence ratings across the six steps, because later steps depend on earlier observations. Compact summaries in place of chat history avoid repeated queries. A mid-session partner edit updates this state and re-runs only the affected calculations.</div>
    </div>

    <div class="card-item accent-purple">
      <div class="card-title">Long-term episodic memory, across sessions</div>
      <div class="card-body">Partners repeat the same scoping choices every quarter. A SQLite log records each partner edit with the partner, VP organization and session. It stores only edits the partner makes, so memory cannot reinforce its own defaults.</div>
    </div>

    <div class="card-item accent-emerald">
      <div class="card-title">Long-term semantic and procedural memory, at the start of each review</div>
      <div class="card-body">One edit is a decision about one review, while three sessions make a pattern. When the same edit appears in three sessions, such as removing recent promotions from candidate lists, the next review proposes it as a standing preference. It applies only after the partner confirms it, and it returns for review after 180 days or a contradicting edit. Each brief lists the preferences it applied. Memory can shorten candidate lists, lower the budget cap, raise the evidence bar or move a declined option last. A governance lock stops it from switching off an audit, exceeding the department ledger or hiding an option.</div>
    </div>
  </div>

  <!-- ==================== PAGE 3 ==================== -->
  <div class="page-break"></div>

  <h2 class="section-header">Written Submission (Continued)</h2>

  <div class="avoid-break">
    <h3 class="sub-header">3. External tool usage and addressed limitations</h3>
    <p>Each tool covers a task that a language model alone gets wrong:</p>

    <div class="step-item">
      <div class="step-badge">1</div>
      <div class="step-content">
        <p><strong>Computation in SQLite and Pandas.</strong> Next-token prediction guesses probable digits instead of computing them. Python computes compa-ratios, cashflow drops and remaining budget across 2,000 employees and returns counts plus at most 15 flagged rows, never the raw roster.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">2</div>
      <div class="step-content">
        <p><strong>Grounding on small samples.</strong> The evidence tool computes Wilson intervals for rates and Student's t intervals for premiums, then flags whether the evidence supports spend and whether the brief must disclose uncertainty.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">3</div>
      <div class="step-content">
        <p><strong>Retrieval of policy rules.</strong> Semantic search over the synthetic governance playbook returns exact rules, such as the 1.20 post-grant compa-ratio cap, which sit outside any model's training data.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">4</div>
      <div class="step-content">
        <p><strong>Verification before delivery.</strong> A Python check matches every dollar figure, percentage and headcount in the draft to a tool output with its source table and data date. It blocks any figure it cannot trace, and the agent regenerates that section.</p>
      </div>
    </div>
  </div>

  <div class="avoid-break" style="margin-top: 12px;">
    <h3 class="sub-header">4. Improvements over a prompt-only approach</h3>
    <p>The design resolves three failure modes of a prompt-only approach:</p>

    <div class="card-item accent-cmu">
      <div class="card-title">Small samples read as settled facts</div>
      <div class="card-body">In <code>VP_CLOUD_AI</code>, 35 of 116 research scientists face a cliff, and competing premiums average 29.1 percent, interval 25.3 to 32.8. New-hire acceptance of 53.8 percent rests on 13 offers, interval 29.1 to 76.8. A prompt-only model reports a settled breach of the 65 percent floor, misses that 5 of the 10 lost offers cite base salary or level, which an equity grant cannot fix, and miscalculates grant totals. Our agent rates the evidence moderate and states both the sample size and the base-salary driver.</div>
    </div>

    <div class="card-item accent-amber">
      <div class="card-title">Invented intermediate results</div>
      <div class="card-body">An open-loop model invents intermediate numbers when arithmetic or a comparison such as 9.11 versus 9.9 stays in text. Pausing after each action and inserting the Python output keeps every step grounded.</div>
    </div>

    <div class="card-item accent-emerald">
      <div class="card-title">Forgetting partners, or drifting from policy</div>
      <div class="card-body">A prompt-only model forgets scoping rules after every chat, and unguarded memory could loosen policy limits. The three-session rule and the governance lock keep partner habits while every policy ceiling stays in force.</div>
    </div>
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
                  <span>Checkpoint 2.1 Submission</span>
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
