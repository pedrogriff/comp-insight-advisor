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
      <div><strong>Submission:</strong> <span class="badge badge-cmu">645 Words &bull; Checkpoint 1.1</span></div>
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

        <!-- ==================== ROW 3 CONTAINER: ENVIRONMENT ==================== -->
        <rect x="65" y="160" width="730" height="96" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5 4" />
        <text x="78" y="175" font-size="9" font-weight="800" fill="#64748b" letter-spacing="0.06em">ENVIRONMENT: SYNTHETIC DATA &amp; POLICY CORPUS</text>

        <!-- ==================== CONNECTIONS / FLOWS ==================== -->

        <!-- Feedback Loop A: Left-side vertical feedback loop arrow from Row 5 to Row 2 -->
        <path d="M 275 366 L 30 366 L 30 104 L 265 104" fill="none" stroke="#dc2626" stroke-width="1.75" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(145, 93)">
          <rect x="-105" y="-10" width="210" height="20" rx="4" fill="#fff1f2" stroke="#fecdd3" stroke-width="1" />
          <text x="0" y="4" font-size="9" font-weight="700" fill="#be123c" text-anchor="middle">Loop A: Math/policy check &rarr; Re-query</text>
        </g>

        <!-- Return Flow: Right-side vertical return arrow from Row 5 to Row 1 -->
        <path d="M 585 366 L 830 366 L 830 31 L 565 31" fill="none" stroke="#16a34a" stroke-width="1.75" marker-end="url(#arrow-green)" />
        <g transform="translate(695, 20)">
          <rect x="-55" y="-10" width="110" height="20" rx="4" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1" />
          <text x="0" y="4" font-size="9.5" font-weight="700" fill="#15803d" text-anchor="middle">6. Verified draft</text>
        </g>

        <!-- Row 1 -> Row 2: 1. Request org brief -->
        <path d="M 395 48 L 395 86" fill="none" stroke="#2563eb" stroke-width="1.75" marker-end="url(#arrow-blue)" />
        <g transform="translate(345, 67)">
          <rect x="-58" y="-9" width="116" height="18" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#1e40af" text-anchor="middle">1. Request org brief</text>
        </g>

        <!-- Row 1 -> Row 2: Loop B: Partner edits (curved) -->
        <path d="M 465 48 C 485 58, 485 76, 465 86" fill="none" stroke="#7c3aed" stroke-width="1.75" stroke-dasharray="4 3" marker-end="url(#arrow-purple)" />
        <g transform="translate(530, 67)">
          <rect x="-52" y="-9" width="104" height="18" rx="3" fill="#faf5ff" stroke="#e9d5ff" stroke-width="0.8" />
          <text x="0" y="3.5" font-size="8.5" font-weight="600" fill="#6b21a8" text-anchor="middle">Loop B: Partner edits</text>
        </g>

        <!-- Row 2 -> Row 3 Fan-Out Arrows -->
        <path d="M 330 122 L 205 178" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <g transform="translate(245, 145)">
          <rect x="-75" y="-8" width="150" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="4" font-size="8.5" font-weight="600" fill="#334155" text-anchor="middle">2. Trigger: Query cliffs &amp; peers</text>
        </g>

        <path d="M 430 122 L 430 178" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <g transform="translate(430, 145)">
          <rect x="-80" y="-8" width="160" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="4" font-size="8.5" font-weight="600" fill="#334155" text-anchor="middle">3. Trigger: Query offers &amp; counters</text>
        </g>

        <path d="M 530 122 L 655 178" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <g transform="translate(615, 145)">
          <rect x="-65" y="-8" width="130" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="4" font-size="8.5" font-weight="600" fill="#334155" text-anchor="middle">4. Trigger: Retrieve policy</text>
        </g>

        <!-- Row 3 -> Row 4 Converging Arrows -->
        <path d="M 205 238 L 350 284" fill="none" stroke="#d97706" stroke-width="1.5" marker-end="url(#arrow-amber)" />
        <g transform="translate(255, 266)">
          <rect x="-65" y="-8" width="130" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="4" font-size="8.5" font-weight="600" fill="#b45309" text-anchor="middle">Cliff cohorts &amp; inversions</text>
        </g>

        <path d="M 430 238 L 430 284" fill="none" stroke="#d97706" stroke-width="1.5" marker-end="url(#arrow-amber)" />
        <g transform="translate(430, 266)">
          <rect x="-65" y="-8" width="130" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="4" font-size="8.5" font-weight="600" fill="#b45309" text-anchor="middle">Poaching &amp; decline stats</text>
        </g>

        <path d="M 655 238 L 510 284" fill="none" stroke="#d97706" stroke-width="1.5" marker-end="url(#arrow-amber)" />
        <g transform="translate(605, 266)">
          <rect x="-68" y="-8" width="136" height="17" rx="3" fill="#ffffff" stroke="#cbd5e1" stroke-width="0.8" />
          <text x="0" y="4" font-size="8.5" font-weight="600" fill="#b45309" text-anchor="middle">Governance &amp; sizing rules</text>
        </g>

        <!-- Row 4 -> Row 5: 5. Draft brief -->
        <path d="M 430 320 L 430 348" fill="none" stroke="#2563eb" stroke-width="1.75" marker-end="url(#arrow-blue)" />
        <g transform="translate(430, 334)">
          <rect x="-40" y="-8" width="80" height="16" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="4" font-size="8.5" font-weight="700" fill="#1e40af" text-anchor="middle">5. Draft brief</text>
        </g>

        <!-- ==================== BOXES / NODES ==================== -->

        <!-- ROW 1: Strategic Comp Partner User -->
        <g filter="url(#card-shadow)">
          <rect x="305" y="14" width="250" height="34" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.75" />
          <text x="430" y="35" font-size="12" font-weight="700" fill="#1e3a8a" text-anchor="middle">Strategic Comp Partner User</text>
        </g>

        <!-- ROW 2: Insight Advisor Orchestrator Agent -->
        <g filter="url(#card-shadow)">
          <rect x="265" y="86" width="330" height="36" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.75" />
          <text x="430" y="108" font-size="12" font-weight="700" fill="#14532d" text-anchor="middle">Insight Advisor Orchestrator Agent</text>
        </g>

        <!-- ROW 3 NODES: Three Side-by-Side Databases -->
        <!-- DB 1: SQLite / CSV: Org Roster & Multi-Year Cashflows -->
        <g filter="url(#card-shadow)">
          <rect x="80" y="186" width="225" height="52" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.5" />
          <text x="192" y="208" font-size="10.5" font-weight="700" fill="#0f172a" text-anchor="middle">SQLite / CSV:</text>
          <text x="192" y="224" font-size="10" font-weight="600" fill="#334155" text-anchor="middle">Org Roster &amp; Multi-Year Cashflows</text>
        </g>

        <!-- DB 2: SQLite / CSV: Reactive Offer & Counter-Offer Logs -->
        <g filter="url(#card-shadow)">
          <rect x="317" y="186" width="225" height="52" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.5" />
          <text x="430" y="208" font-size="10.5" font-weight="700" fill="#0f172a" text-anchor="middle">SQLite / CSV:</text>
          <text x="430" y="224" font-size="10" font-weight="600" fill="#334155" text-anchor="middle">Reactive Offer &amp; Counter-Offer Logs</text>
        </g>

        <!-- DB 3: ChromaDB Vector Store: Comp Playbooks & Policies -->
        <g filter="url(#card-shadow)">
          <rect x="555" y="186" width="225" height="52" rx="6" fill="#ffffff" stroke="#64748b" stroke-width="1.5" />
          <text x="667" y="208" font-size="10.5" font-weight="700" fill="#0f172a" text-anchor="middle">ChromaDB Vector Store:</text>
          <text x="667" y="224" font-size="10" font-weight="600" fill="#334155" text-anchor="middle">Comp Playbooks &amp; Policies</text>
        </g>

        <!-- ROW 4: Drafting & Option Evaluation Module -->
        <g filter="url(#card-shadow)">
          <rect x="265" y="284" width="330" height="36" rx="6" fill="#fefce8" stroke="#ca8a04" stroke-width="1.75" />
          <text x="430" y="306" font-size="12" font-weight="700" fill="#713f12" text-anchor="middle">Drafting &amp; Option Evaluation Module</text>
        </g>

        <!-- ROW 5: Verification & Guardrail Check -->
        <g filter="url(#card-shadow)">
          <rect x="275" y="348" width="310" height="36" rx="6" fill="#fdf2f2" stroke="#dc2626" stroke-width="1.75" />
          <text x="430" y="370" font-size="12" font-weight="700" fill="#991b1b" text-anchor="middle">Verification &amp; Guardrail Check</text>
        </g>
      </svg>
    </div>
    <div class="diagram-caption">
      <strong>Figure 1:</strong> Closed-loop agent architecture for the Strategic Talent &amp; Compensation Insight Advisor. Illustrates trigger-driven tool execution across structured data (SQLite) and policy retrieval (ChromaDB), evaluated through deterministic verification gates (Feedback Loop A) and steered by human-in-the-loop constraints (Feedback Loop B).
    </div>
  </div>

  <h2 class="section-header">Written Submission &bull; 645 Words</h2>

  <div class="avoid-break">
    <h3 class="sub-header">1. The agent, the problem, and the intended user</h3>
    <p>
      The <strong>Strategic Talent and Compensation Insight Advisor</strong> is a Research Assistant agent built for an enterprise <strong>Strategic Compensation Partner</strong> who advises Engineering Vice Presidents and Lead People Partners. Today, compensation teams often operate in two disconnected silos. A transactional Offers and Counter-Offers team handles external hiring and reactive retention when employees receive competing offers, while Strategic Compensation Partners manage proactive retention budgets, annual equity cycles, and organizational health.
    </p>
    <p>
      Before a monthly talent review with a VP, the Compensation Partner must manually stitch together spreadsheets of internal employee compensation, multi-year equity vesting schedules, recent offer decline logs, and evolving policy documents. Because this manual synthesis takes hours of spreadsheet work, partners struggle to spot early links between external hiring friction and internal retention risk, and executives receive dense tables rather than clear, actionable insights. The agent solves this by investigating structured workforce data alongside policy documentation to produce a concise, verified executive decision brief.
    </p>
  </div>

  <!-- ==================== PAGE 2 ==================== -->
  <div class="page-break"></div>

  <h2 class="section-header">Written Submission (Continued)</h2>

  <div class="avoid-break">
    <h3 class="sub-header">2. Why a standalone LLM or simple prompting is insufficient</h3>
    <p>A standalone LLM fails at this task for four fundamental architectural reasons:</p>
    
    <div class="card-item accent-cmu">
      <div class="card-title">Context window degradation and data scale</div>
      <div class="card-body">Dumping thousands of employee roster rows, multi-year vesting schedules, and dozens of policy documents into a single prompt exceeds smaller model context windows and degrades reasoning accuracy in larger models.</div>
    </div>
    
    <div class="card-item">
      <div class="card-title">Exact arithmetic vs. probabilistic text</div>
      <div class="card-body">Compensation analysis requires exact aggregations, percentile rankings, year-over-year cashflow drop calculations, and budget caps that LLMs hallucinate without deterministic data tools.</div>
    </div>
    
    <div class="card-item accent-amber">
      <div class="card-title">Multi-step conditional investigation</div>
      <div class="card-body">Investigating a talent hotspot requires iterative hypothesis testing. The system must first detect where internal equity cliffs exist, then check whether that same job family is experiencing declining new-hire offer acceptance rates or rising counter-offers, and finally retrieve the specific governance policy that governs whether to intervene through offer bands or proactive retention grants.</div>
    </div>
    
    <div class="card-item accent-emerald">
      <div class="card-title">Verification before executive delivery</div>
      <div class="card-body">Outputs shared with VPs require automated validation against source numbers and policy constraints before a human partner reviews them.</div>
    </div>
  </div>

  <div class="avoid-break" style="margin-top: 14px;">
    <h3 class="sub-header">3. The environment: documents, data sources, tools, and users</h3>
    <p>
      The agent operates within a local Python environment using a Gradio interface and a modular model router supporting OpenRouter cloud models and local Ollama models. It interacts with strictly synthetic data representing a 2,000-person technology organization:
    </p>
    
    <div class="card-item">
      <div class="card-title">Structured data sources</div>
      <div class="card-body">Three relational tables stored in SQLite and CSV format: an <em>Org Roster &amp; Cashflow Table</em> containing synthetic salaries, peer percentiles, performance ratings, and four-year vesting schedules; a <em>Reactive Offers &amp; Counters Log</em> tracking candidate offer acceptances, declines, competing employers, and counter-offer outcomes; and a <em>Department Budget Ledger</em>.</div>
    </div>

    <div class="card-item">
      <div class="card-title">Unstructured knowledge base</div>
      <div class="card-body">A ChromaDB vector store indexing synthetic compensation policy PDFs, guidelines defining the boundary between reactive counter-offers and proactive retention, and historical executive briefing templates.</div>
    </div>

    <div class="card-item">
      <div class="card-title">Tools and users</div>
      <div class="card-body">Deterministic Python/Pandas query tools for statistical aggregation, a semantic search tool over ChromaDB, a markdown report generator, and the Compensation Partner user who steers the investigation.</div>
    </div>
  </div>

  <!-- ==================== PAGE 3 ==================== -->
  <div class="page-break"></div>

  <h2 class="section-header">Written Submission (Continued)</h2>

  <div class="avoid-break">
    <h3 class="sub-header">4. The actions the agent needs to take and their triggers</h3>
    <p>Each action in the investigation is strictly bound to an operational trigger:</p>

    <div class="step-item">
      <div class="step-badge">1</div>
      <div class="step-content">
        <p><strong>Scan and aggregate org health metrics.</strong> <span class="trigger-tag">Triggered</span> when the user selects a VP organization and requests a talent review. The agent calls the roster analysis tool to identify cohorts with projected year-over-year cashflow drops exceeding 15 percent or peer positioning below the 25th percentile.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">2</div>
      <div class="step-content">
        <p><strong>Cross-examine reactive market signals.</strong> <span class="trigger-tag">Triggered</span> automatically when Action 1 flags an at-risk job family or location. The agent queries the Offers and Counters Log to measure whether offer acceptance rates have dropped or counter-offer volume has spiked in that same segment.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">3</div>
      <div class="step-content">
        <p><strong>Retrieve governance and handoff rules.</strong> <span class="trigger-tag">Triggered</span> when both reactive market pressure and internal retention risk appear in the same cohort. The agent queries ChromaDB for policy rules governing whether the issue should be addressed by the Offers team adjusting hiring bands or the Client Partner deploying proactive retention equity.</p>
      </div>
    </div>

    <div class="step-item">
      <div class="step-badge">4</div>
      <div class="step-content">
        <p><strong>Draft the executive insight brief.</strong> <span class="trigger-tag">Triggered</span> once data aggregation and policy retrieval complete. The agent synthesizes a one-page brief summarizing the risk, comparing intervention options against available budget, and citing exact source metrics.</p>
      </div>
    </div>
  </div>

  <div class="avoid-break" style="margin-top: 14px;">
    <h3 class="sub-header">5. How feedback guides behavior across steps</h3>
    <p>The system relies on three distinct feedback loops to adapt its behavior dynamically:</p>

    <div class="card-item accent-amber">
      <div class="card-title">Tool execution and schema feedback</div>
      <div class="card-body">If a SQLite or Pandas query returns an empty cohort, a syntax error, or a sample size too small for statistical relevance, the error signal prompts the agent to broaden its filter criteria, such as expanding from a single sub-team to the broader job family, before proceeding.</div>
    </div>

    <div class="card-item accent-cmu">
      <div class="card-title">Self-verification and policy audit loop</div>
      <div class="card-body">Before displaying the brief, a verification step compares every dollar figure and headcount number in the drafted text against the raw tool outputs and checks that proposed retention spend does not exceed the remaining budget in the ledger. Any discrepancy triggers a targeted regeneration of the flawed section.</div>
    </div>

    <div class="card-item accent-emerald">
      <div class="card-title">Human-in-the-loop partner refinement</div>
      <div class="card-body">When the Compensation Partner reviews the brief in the UI and adjusts a constraint, such as lowering the budget cap or excluding employees promoted within the last six months, the agent captures that feedback, updates its session memory, re-runs the affected tool calculations, and revises the trade-off recommendations.</div>
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
