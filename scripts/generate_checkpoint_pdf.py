"""Generates submission-ready PDF for Checkpoint 1.1 using Playwright and Mermaid.js."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
OUTPUT_PDF = OUTPUT_DIR / "checkpoint_1_1.pdf"

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
      line-height: 1.52;
      font-size: 9.5pt;
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
      padding-bottom: 10px;
      margin-bottom: 14px;
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
      font-size: 9.5pt;
      font-weight: 600;
      color: #0f172a;
      margin-bottom: 4px;
    }
    
    .doc-title {
      font-size: 16pt;
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
      font-size: 11pt;
      font-weight: 700;
      color: #0f172a;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 4px;
      margin-top: 14px;
      margin-bottom: 10px;
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
      font-size: 10.5pt;
      font-weight: 700;
      color: #0f172a;
      margin-top: 12px;
      margin-bottom: 6px;
      page-break-after: avoid;
      break-after: avoid;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    p {
      margin-top: 0;
      margin-bottom: 8px;
      text-align: justify;
      text-justify: inter-word;
    }

    /* Diagram Card */
    .diagram-card {
      background: #fbfcfe;
      border: 1px solid #cbd5e1;
      border-radius: 7px;
      padding: 10px 12px;
      margin-bottom: 12px;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    .diagram-caption {
      font-size: 7.5pt;
      color: #64748b;
      text-align: center;
      margin-top: 6px;
      font-weight: 500;
      border-top: 1px solid #e2e8f0;
      padding-top: 5px;
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
      padding: 7px 10px;
      margin-bottom: 8px;
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

    .card-title {
      font-weight: 700;
      font-size: 9pt;
      color: #0f172a;
      margin-bottom: 3px;
    }

    .card-body {
      font-size: 9pt;
      color: #334155;
      margin: 0;
      text-align: justify;
    }

    /* Numbered steps */
    .step-item {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      margin-bottom: 9px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 7px 10px;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    .step-badge {
      flex-shrink: 0;
      width: 20px;
      height: 20px;
      background: #0f172a;
      color: #ffffff;
      font-size: 8pt;
      font-weight: 700;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-top: 1px;
    }

    .step-content {
      flex-grow: 1;
      font-size: 9pt;
      line-height: 1.45;
    }

    .step-content p {
      margin: 0;
    }

    .trigger-tag {
      display: inline-block;
      font-size: 7pt;
      font-weight: 700;
      padding: 1px 5px;
      background: #fef3c7;
      color: #92400e;
      border-radius: 3px;
      border: 1px solid #fde68a;
      margin-right: 4px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
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

    .callout-box {
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 8px 12px;
      margin-top: 10px;
      font-size: 8.5pt;
      color: #475569;
    }
  </style>
</head>
<body>

  <!-- ==================== PAGE 1 ==================== -->
  <div class="header-banner">
    <div class="institution-meta">
      <div class="institution-name">Carnegie Mellon University &bull; School of Computer Science</div>
      <div class="program-name">Executive Education: Agentic AI Program &bull; Capstone Project</div>
      <h1 class="doc-title">Checkpoint 1.1: Problem Framing &amp; Initial Agent Design</h1>
    </div>
    <div class="meta-box">
      <div><strong>Student:</strong> Pedro Griff Marcincowski</div>
      <div><strong>Project:</strong> Strategic Comp Insight Advisor</div>
      <div><strong>Track:</strong> <span class="badge">Research Assistant</span></div>
      <div><strong>Submission:</strong> <span class="badge badge-cmu">Module 1 &bull; Checkpoint 1.1</span></div>
    </div>
  </div>

  <h2 class="section-header">System Architecture Diagram</h2>
  <div class="diagram-card">
    <div class="diagram-svg-container">
      <svg viewBox="0 0 860 410" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
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
        <!-- Container: x=60, y=132, width=740, height=164 (y=132..296) -->
        <rect x="60" y="132" width="740" height="164" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5 4" />

        <!-- ==================== BUS LINES & ARROWS ==================== -->

        <!-- Loop A: Left-side vertical feedback from Row 5 (275, 386) to Row 2 (265, 95) -->
        <path d="M 275 386 L 28 386 L 28 68 L 220 68 L 220 95 L 265 95" fill="none" stroke="#dc2626" stroke-width="1.75" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(140, 68)">
          <rect x="-105" y="-10" width="210" height="20" rx="4" fill="#fff1f2" stroke="#fecdd3" stroke-width="1" />
          <text x="0" y="4" font-size="9" font-weight="700" fill="#be123c" text-anchor="middle">Loop A: Math/policy check &rarr; Re-query</text>
        </g>

        <!-- 6. Verified Draft: Right-side return from Row 5 (585, 386) via x=832 to Row 1 (555, 26) -->
        <path d="M 585 386 L 832 386 L 832 26 L 555 26" fill="none" stroke="#16a34a" stroke-width="1.75" marker-end="url(#arrow-green)" />
        <g transform="translate(693, 26)">
          <rect x="-55" y="-10" width="110" height="20" rx="4" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1" />
          <text x="0" y="4" font-size="9.5" font-weight="700" fill="#15803d" text-anchor="middle">6. Verified draft</text>
        </g>

        <!-- Row 1 -> Row 2: 1. Request org brief (centered at y=60) -->
        <path d="M 395 42 L 395 78" fill="none" stroke="#2563eb" stroke-width="1.75" marker-end="url(#arrow-blue)" />
        <g transform="translate(340, 60)">
          <rect x="-55" y="-9" width="110" height="18" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#1e40af" text-anchor="middle">1. Request org brief</text>
        </g>

        <!-- Row 1 -> Row 2: Loop B: Partner edits and approvals (curved, centered at y=60) -->
        <path d="M 465 42 C 485 50, 485 70, 465 78" fill="none" stroke="#7c3aed" stroke-width="1.75" stroke-dasharray="4 3" marker-end="url(#arrow-purple)" />
        <g transform="translate(535, 60)">
          <rect x="-66" y="-9" width="132" height="18" rx="3" fill="#faf5ff" stroke="#e9d5ff" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#6b21a8" text-anchor="middle">Loop B: Edits &amp; approvals</text>
        </g>

        <!-- Orthogonal Fan-out from Row 2 to DBs -->
        <!-- Vertical trunk from Orchestrator: M 430 112 L 430 152 -->
        <path d="M 430 112 L 430 152" fill="none" stroke="#64748b" stroke-width="1.5" />
        <!-- Horizontal bus bar inside container: M 180 152 L 680 152 -->
        <path d="M 180 152 L 680 152" fill="none" stroke="#64748b" stroke-width="1.5" />
        <!-- Three vertical arrows down to DBs (y=196) -->
        <path d="M 180 152 L 180 196" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <path d="M 430 152 L 430 196" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <path d="M 680 152 L 680 196" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />

        <!-- Trigger Pills centered at y=173 on x=180, x=430, x=680 -->
        <g transform="translate(180, 173)">
          <rect x="-78" y="-9" width="156" height="18" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#334155" text-anchor="middle">2. Trigger: Query cliffs &amp; peers</text>
        </g>
        <g transform="translate(430, 173)">
          <rect x="-84" y="-9" width="168" height="18" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#334155" text-anchor="middle">3. Trigger: Query offers &amp; counters</text>
        </g>
        <g transform="translate(680, 173)">
          <rect x="-68" y="-9" width="136" height="18" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#334155" text-anchor="middle">4. Trigger: Retrieve policy</text>
        </g>

        <!-- Orthogonal Merge from DBs to Row 4 -->
        <!-- Three vertical drop lines from DB bottom (y=242) to merge bus (y=286) -->
        <path d="M 180 242 L 180 286" fill="none" stroke="#d97706" stroke-width="1.5" />
        <path d="M 430 242 L 430 286" fill="none" stroke="#d97706" stroke-width="1.5" />
        <path d="M 680 242 L 680 286" fill="none" stroke="#d97706" stroke-width="1.5" />
        <!-- Horizontal merge bus at y=286: M 180 286 L 680 286 -->
        <path d="M 180 286 L 680 286" fill="none" stroke="#d97706" stroke-width="1.5" />
        <!-- Single vertical trunk into Row 4: M 430 286 L 430 310 -->
        <path d="M 430 286 L 430 310" fill="none" stroke="#d97706" stroke-width="1.5" marker-end="url(#arrow-amber)" />

        <!-- Output Pills centered at y=264 on x=180, x=430, x=680 -->
        <g transform="translate(180, 264)">
          <rect x="-68" y="-9" width="136" height="18" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#b45309" text-anchor="middle">Cliff cohorts &amp; inversions</text>
        </g>
        <g transform="translate(430, 264)">
          <rect x="-68" y="-9" width="136" height="18" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#b45309" text-anchor="middle">Poaching &amp; decline stats</text>
        </g>
        <g transform="translate(680, 264)">
          <rect x="-72" y="-9" width="144" height="18" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#b45309" text-anchor="middle">Governance &amp; sizing rules</text>
        </g>

        <!-- Arrow 5: Row 4 to Row 5 (M 430 342 L 430 370 with pill centered at y=356) -->
        <path d="M 430 342 L 430 370" fill="none" stroke="#2563eb" stroke-width="1.75" marker-end="url(#arrow-blue)" />
        <g transform="translate(430, 356)">
          <rect x="-40" y="-8" width="80" height="16" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="700" fill="#1e40af" text-anchor="middle">5. Draft brief</text>
        </g>

        <!-- Environment Pill on top-left border at translate(76, 132) (y=123..141) -->
        <g transform="translate(76, 132)">
          <rect x="0" y="-9" width="280" height="18" rx="4" fill="#ffffff" stroke="#94a3b8" stroke-width="1" />
          <text x="140" y="3.5" font-size="8.5" font-weight="800" fill="#475569" letter-spacing="0.05em" text-anchor="middle">ENVIRONMENT: SYNTHETIC DATA &amp; POLICY CORPUS</text>
        </g>

        <!-- ==================== BOXES / NODES ==================== -->

        <!-- ROW 1: Strategic Comp Partner User (x=305, y=10, width=250, height=32, y=10..42) -->
        <g filter="url(#card-shadow)">
          <rect x="305" y="10" width="250" height="32" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.75" />
          <text x="430" y="31" font-size="12" font-weight="700" fill="#1e3a8a" text-anchor="middle">Strategic Comp Partner User</text>
        </g>

        <!-- ROW 2: Insight Advisor Orchestrator Agent (x=265, y=78, width=330, height=34, y=78..112) -->
        <g filter="url(#card-shadow)">
          <rect x="265" y="78" width="330" height="34" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.75" />
          <text x="430" y="100" font-size="12" font-weight="700" fill="#14532d" text-anchor="middle">Insight Advisor Orchestrator Agent</text>
        </g>

        <!-- ROW 3 NODES: Three DB boxes (y=196..242, height=46) -->
        <!-- DB 1: centered at x=180 (x=70, width=220) -->
        <g filter="url(#card-shadow)">
          <rect x="70" y="196" width="220" height="46" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.5" />
          <text x="180" y="215" font-size="10.5" font-weight="700" fill="#0f172a" text-anchor="middle">SQLite / CSV:</text>
          <text x="180" y="230" font-size="10" font-weight="600" fill="#334155" text-anchor="middle">Org Roster &amp; Multi-Year Cashflows</text>
        </g>

        <!-- DB 2: centered at x=430 (x=320, width=220) -->
        <g filter="url(#card-shadow)">
          <rect x="320" y="196" width="220" height="46" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.5" />
          <text x="430" y="215" font-size="10.5" font-weight="700" fill="#0f172a" text-anchor="middle">SQLite / CSV:</text>
          <text x="430" y="230" font-size="10" font-weight="600" fill="#334155" text-anchor="middle">Reactive Offer &amp; Counter-Offer Logs</text>
        </g>

        <!-- DB 3: centered at x=680 (x=570, width=220) -->
        <g filter="url(#card-shadow)">
          <rect x="570" y="196" width="220" height="46" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.5" />
          <text x="680" y="215" font-size="10.5" font-weight="700" fill="#0f172a" text-anchor="middle">ChromaDB Vector Store:</text>
          <text x="680" y="230" font-size="10" font-weight="600" fill="#334155" text-anchor="middle">Comp Playbooks &amp; Policies</text>
        </g>

        <!-- ROW 4: Drafting & Option Evaluation Module (x=265, y=310, width=330, height=32, y=310..342) -->
        <g filter="url(#card-shadow)">
          <rect x="265" y="310" width="330" height="32" rx="6" fill="#fefce8" stroke="#ca8a04" stroke-width="1.75" />
          <text x="430" y="331" font-size="12" font-weight="700" fill="#713f12" text-anchor="middle">Drafting &amp; Option Evaluation Module</text>
        </g>

        <!-- ROW 5: Verification & Guardrail Check (x=275, y=370, width=310, height=32, y=370..402) -->
        <g filter="url(#card-shadow)">
          <rect x="275" y="370" width="310" height="32" rx="6" fill="#fdf2f2" stroke="#dc2626" stroke-width="1.75" />
          <text x="430" y="391" font-size="12" font-weight="700" fill="#991b1b" text-anchor="middle">Verification &amp; Guardrail Check</text>
        </g>
      </svg>
    </div>
    <div class="diagram-caption">
      <strong>Figure 1:</strong> Closed-loop agent architecture for the Strategic Talent &amp; Compensation Insight Advisor. Illustrates trigger-driven tool execution across structured data (SQLite) and policy retrieval (ChromaDB), evaluated through deterministic verification gates (Feedback Loop A) and steered by partner edits and approvals (Feedback Loop B).
    </div>
  </div>

  <h2 class="section-header">Written Submission</h2>

  <div class="avoid-break">
    <h3 class="sub-header">1. The agent, the problem, and the intended user</h3>
    <p>
      The <strong>Strategic Talent and Compensation Insight Advisor</strong> is a Research Assistant agent for a <strong>Strategic Compensation Partner</strong> who advises Engineering Vice Presidents and Lead People Partners. Compensation work sits in two silos. An Offers and Counter-Offers team handles external hiring and reactive retention when employees receive competing offers. Strategic Compensation Partners manage proactive retention budgets, annual equity cycles, and organizational health.
    </p>
    <p>
      Before a monthly VP talent review, the partner stitches together spreadsheets of employee compensation, vesting schedules, offer decline logs, and policy documents. The work takes hours. Early links between external hiring friction and internal retention risk go unnoticed, and executives get dense tables instead of a recommendation. The agent reads the data and the policies together and produces a short, verified decision brief.
    </p>
  </div>

  <!-- ==================== PAGE 2 ==================== -->
  <div class="page-break"></div>

  <h2 class="section-header">Written Submission (Continued)</h2>

  <div class="avoid-break">
    <h3 class="sub-header">2. Why a standalone LLM or simple prompting is insufficient</h3>
    <p>A standalone LLM fails at this task for four reasons:</p>

    <div class="card-item accent-cmu">
      <div class="card-title">Data scale</div>
      <div class="card-body">Thousands of roster rows, vesting schedules, and policy documents overflow a small model's context window and degrade reasoning in larger ones.</div>
    </div>

    <div class="card-item">
      <div class="card-title">Exact arithmetic</div>
      <div class="card-body">Percentile ranks, cashflow drops, and budget caps must be exact. Next-token prediction can return a plausible total that is wrong.</div>
    </div>

    <div class="card-item accent-amber">
      <div class="card-title">Dynamic, multi-step investigation</div>
      <div class="card-body">Finding a talent hotspot means testing hypotheses in order and choosing each next dataset or tool from intermediate results. The agent checks offer trends only for job families with equity cliffs, and retrieves policy only when both signals appear. A single prompt cannot sequence these checks, and a fixed pipeline wastes queries on healthy segments.</div>
    </div>

    <div class="card-item accent-emerald">
      <div class="card-title">Verification before delivery</div>
      <div class="card-body">A verifier must check every number in a VP brief against the source data and policy limits.</div>
    </div>

  </div>

  <div class="avoid-break" style="margin-top: 14px;">
    <h3 class="sub-header">3. The environment: documents, data sources, tools, and users</h3>
    <p>
      The agent runs locally in Python behind a Gradio interface. A two-tier model router sends routine tool calls to an 8B to 12B model and sends action selection and trade-off synthesis to a stronger reasoning model. Small models call tools reliably once the tools do the math and retrieval. All data is synthetic and describes a 2,000-person technology company:
    </p>

    <div class="card-item">
      <div class="card-title">Structured data</div>
      <div class="card-body">Three SQLite tables: an <em>Org Roster &amp; Cashflow Table</em> with salaries, peer percentiles, ratings, and vesting schedules; a <em>Reactive Offers &amp; Counters Log</em> with offer outcomes, competing employers, and counter-offers; and a <em>Department Budget Ledger</em>.</div>
    </div>

    <div class="card-item">
      <div class="card-title">Policy documents</div>
      <div class="card-body">A ChromaDB vector store of compensation policies, including the rules that separate reactive counter-offers from proactive retention.</div>
    </div>

    <div class="card-item">
      <div class="card-title">Tools and users</div>
      <div class="card-body">Read-only Python/Pandas query tools that return compact Markdown table summaries instead of raw rows, a semantic search tool over ChromaDB, a report generator, and the Compensation Partner.</div>
    </div>

  </div>

  <!-- ==================== PAGE 3 ==================== -->
  <div class="page-break"></div>

  <h2 class="section-header">Written Submission (Continued)</h2>

  <div class="avoid-break">
    <h3 class="sub-header">4. The actions the agent needs to take and their triggers</h3>
    <p>The current state decides which action runs next:</p>

    <div class="step-item">
      <div class="step-badge">1</div>
      <div class="step-content">
        <p><strong>Scan org health.</strong> <span class="trigger-tag">Triggered</span> when the user requests a talent review for a VP organization. The roster tool flags cohorts with a projected cashflow drop above 15 percent or peer positioning below the 25th percentile.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">2</div>
      <div class="step-content">
        <p><strong>Cross-examine market signals.</strong> <span class="trigger-tag">Triggered</span> when Action 1 flags an at-risk job family or location. The agent checks the Offers and Counters Log for falling offer acceptance or rising counter-offers in that segment.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">3</div>
      <div class="step-content">
        <p><strong>Retrieve governance rules.</strong> <span class="trigger-tag">Triggered</span> when both signals hit the same cohort. The agent searches ChromaDB for the policy that decides whether the Offers team adjusts hiring bands or the partner grants retention equity.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">4</div>
      <div class="step-content">
        <p><strong>Draft the brief.</strong> <span class="trigger-tag">Triggered</span> once aggregation and retrieval finish. The agent writes a one-page brief that states the risk, compares options against the remaining budget, and cites source metrics.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">5</div>
      <div class="step-content">
        <p><strong>Ask for approval.</strong> <span class="trigger-tag">Triggered</span> when an option needs a policy exception, such as a top-tier retention grant. The agent waits for the partner to accept or decline it.</p>
      </div>
    </div>

  </div>

  <div class="avoid-break" style="margin-top: 14px;">
    <h3 class="sub-header">5. How feedback guides behavior across steps</h3>
    <p>Three feedback loops shape the next step:</p>

    <div class="card-item accent-amber">
      <div class="card-title">Tool results</div>
      <div class="card-body">An empty cohort, a query error, or a sample too small to trust makes the agent widen its filter, say from one sub-team to the whole job family, or skip queries that no longer apply.</div>
    </div>

    <div class="card-item accent-cmu">
      <div class="card-title">Verification</div>
      <div class="card-body">Before the partner sees the brief, the verifier checks every dollar figure and headcount against the tool outputs and confirms that proposed spend fits the remaining budget. A mismatch regenerates only the flawed section.</div>
    </div>

    <div class="card-item accent-emerald">
      <div class="card-title">Partner review</div>
      <div class="card-body">When the partner changes a constraint, such as a lower budget cap or excluding recent promotions, the agent stores it in session memory, re-runs the affected calculations, and revises the recommendations. A declined exception drops that option from the brief.</div>
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
                  <span>Checkpoint 1.1 Submission</span>
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
