"""Generates submission-ready PDF for Checkpoint 4.1 using Playwright and inline SVG."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
OUTPUT_PDF = OUTPUT_DIR / "checkpoint_4_1.pdf"

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

    strong {
      color: #0f172a;
      font-weight: 600;
    }

    em {
      color: #334155;
      font-style: italic;
    }

    .section-block { margin-bottom: 6px; }
    ul.bullets, ol.numbered { margin: 0 0 7px 0; padding-left: 16px; }
    ul.bullets li, ol.numbered li { margin-bottom: 4px; text-align: justify; }
    table.data-table { width: 100%; border-collapse: collapse; margin: 4px 0 8px 0; font-size: 8.2pt;
      page-break-inside: avoid; break-inside: avoid; }
    table.data-table th { background: #f1f5f9; color: #0f172a; font-weight: 700; text-align: left;
      border: 1px solid #cbd5e1; padding: 3px 6px; }
    table.data-table td { border: 1px solid #e2e8f0; padding: 3px 6px; vertical-align: top; color: #334155; }
    table.data-table th.num, table.data-table td.num { text-align: right; }
    table.data-table td.num { white-space: nowrap; font-variant-numeric: tabular-nums; }
    table.data-table td:first-child { white-space: nowrap; }
  </style>
</head>
<body>

  <!-- ==================== PAGE 1 ==================== -->
  <div class="header-banner">
    <div class="institution-meta">
      <div class="institution-name">Carnegie Mellon University &bull; School of Computer Science</div>
      <div class="program-name">Executive Education: Agentic AI Program &bull; Capstone Project</div>
      <h1 class="doc-title">Checkpoint 4.1: Tree-of-Thought Integration Plan</h1>
    </div>
    <div class="meta-box">
      <div><strong>Student:</strong> Pedro Griff Marcincowski</div>
      <div><strong>Project:</strong> Strategic Comp Insight Advisor</div>
      <div><strong>Track:</strong> <span class="badge">Research Assistant</span></div>
      <div><strong>Submission:</strong> <span class="badge badge-cmu">Module 4 &bull; Checkpoint 4.1</span></div>
    </div>
  </div>

  <h2 class="section-header">System Architecture Diagram</h2>
  <div class="diagram-card">
    <div class="diagram-svg-container">
<svg viewBox="0 0 860 440" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
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

        <!-- ==================== CONTAINERS ==================== -->
        <rect x="16" y="128" width="370" height="172" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5 4" />
        <g transform="translate(32, 128)">
          <rect x="0" y="-9" width="232" height="18" rx="4" fill="#ffffff" stroke="#94a3b8" stroke-width="1" />
          <text x="116" y="3.5" font-size="8.2" font-weight="800" fill="#475569" letter-spacing="0.04em" text-anchor="middle">LINEAR STEPS: EXACT SQL TOOLS</text>
        </g>
        <rect x="414" y="128" width="430" height="172" rx="8" fill="#faf5ff" stroke="#a78bfa" stroke-width="1.5" stroke-dasharray="5 4" />
        <g transform="translate(430, 128)">
          <rect x="0" y="-9" width="262" height="18" rx="4" fill="#ffffff" stroke="#a78bfa" stroke-width="1" />
          <text x="131" y="3.5" font-size="8.2" font-weight="800" fill="#6d28d9" letter-spacing="0.04em" text-anchor="middle">TREE OF THOUGHT: OPTIONS PLANNER</text>
        </g>

        <!-- ==================== ARROWS ==================== -->
        <!-- Partner to controller -->
        <path d="M 380 38 L 380 64" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <g transform="translate(300, 51)">
          <rect x="-66" y="-8.5" width="132" height="17" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#1e40af" text-anchor="middle">1. Request VP org review</text>
        </g>
        <!-- Controller and memory -->
        <path d="M 530 84 L 610 84" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-start="url(#arrow-purple)" marker-end="url(#arrow-purple)" />
        <!-- Controller straight down into the Roster tool, clear of the container title -->
        <path d="M 300 102 L 300 142" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <!-- Tool sequence -->
        <path d="M 200 172 L 200 180" fill="none" stroke="#64748b" stroke-width="1.3" marker-end="url(#arrow-slate)" />
        <path d="M 200 210 L 200 218" fill="none" stroke="#64748b" stroke-width="1.3" marker-end="url(#arrow-slate)" />
        <path d="M 200 248 L 200 256" fill="none" stroke="#64748b" stroke-width="1.3" marker-end="url(#arrow-slate)" />
        <!-- Driver fit to the thought generator -->
        <path d="M 370 272 L 400 272 L 400 158 L 428 158" fill="none" stroke="#d97706" stroke-width="1.6" marker-end="url(#arrow-amber)" />
        <!-- Planner sequence -->
        <path d="M 636 172 L 636 180" fill="none" stroke="#7c3aed" stroke-width="1.3" marker-end="url(#arrow-purple)" />
        <path d="M 636 210 L 636 218" fill="none" stroke="#7c3aed" stroke-width="1.3" marker-end="url(#arrow-purple)" />
        <path d="M 529 248 L 529 256" fill="none" stroke="#7c3aed" stroke-width="1.3" marker-end="url(#arrow-purple)" />
        <path d="M 733 248 L 733 256" fill="none" stroke="#7c3aed" stroke-width="1.3" marker-start="url(#arrow-purple)" marker-end="url(#arrow-purple)" />
        <!-- The beam expands the next depth -->
        <path d="M 828 234 L 837 234 L 837 158 L 830 158" fill="none" stroke="#7c3aed" stroke-width="1.3" stroke-dasharray="3 2" marker-end="url(#arrow-purple)" />
        <!-- Options to the grounded context and to retrieval -->
        <path d="M 520 286 L 520 320" fill="none" stroke="#d97706" stroke-width="1.6" marker-end="url(#arrow-amber)" />
        <path d="M 600 286 L 600 310 L 764 310 L 764 320" fill="none" stroke="#2563eb" stroke-width="1.4" stroke-dasharray="4 3" marker-end="url(#arrow-blue)" />
        <!-- Retrieval to the grounded context -->
        <path d="M 684 337 L 662 337" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <!-- Grounded context to writer to verifier -->
        <path d="M 260 352 L 260 372" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <path d="M 380 389 L 448 389" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <!-- Verifier loop back to the writer -->
        <path d="M 615 404 L 615 422 L 250 422 L 250 406" fill="none" stroke="#dc2626" stroke-width="1.6" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(432, 422)">
          <rect x="-160" y="-8.5" width="320" height="17" rx="4" fill="#fff1f2" stroke="#fecdd3" stroke-width="1" />
          <text x="0" y="3.2" font-size="8" font-weight="700" fill="#be123c" text-anchor="middle">Untraced figure, unchecked plan or wrong-side clause: redraft</text>
        </g>
        <!-- Verified brief back to the partner -->
        <path d="M 780 389 L 850 389 L 850 23 L 562 23" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(705, 23)">
          <rect x="-82" y="-9" width="164" height="18" rx="4" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1" />
          <text x="0" y="3.5" font-size="8.5" font-weight="700" fill="#15803d" text-anchor="middle">Verified brief, 3 options</text>
        </g>

        <!-- ==================== BOXES ==================== -->
        <g filter="url(#card-shadow)">
          <rect x="300" y="8" width="260" height="30" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.75" />
          <text x="430" y="27.5" font-size="11.5" font-weight="700" fill="#1e3a8a" text-anchor="middle">Strategic Comp Partner</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="230" y="66" width="300" height="36" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.75" />
          <text x="380" y="81" font-size="10.5" font-weight="700" fill="#14532d" text-anchor="middle">ReAct Controller (max_steps = 6)</text>
          <text x="380" y="95" font-size="8.5" font-weight="600" fill="#166534" text-anchor="middle">Thought &#8594; JSON action &#8594; Python observation</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="610" y="62" width="220" height="44" rx="6" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.6" />
          <text x="720" y="78" font-size="9.5" font-weight="700" fill="#581c87" text-anchor="middle">Short- &amp; Long-Term Memory</text>
          <text x="720" y="90" font-size="8" font-weight="600" fill="#6b21a8" text-anchor="middle">Working state, partner preferences</text>
          <text x="720" y="101" font-size="8" font-weight="600" fill="#6b21a8" text-anchor="middle">3-session rule, 180-day expiry</text>
        </g>

        <!-- SQL tools -->
        <g filter="url(#card-shadow)">
          <rect x="30" y="144" width="340" height="28" rx="5" fill="#ffffff" stroke="#64748b" stroke-width="1.3" />
          <text x="44" y="162" font-size="9" font-weight="700" fill="#0f172a">Roster tool</text>
          <text x="356" y="162" font-size="8.2" font-weight="600" fill="#334155" text-anchor="end">Cliffs and peer percentiles</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="30" y="182" width="340" height="28" rx="5" fill="#ffffff" stroke="#64748b" stroke-width="1.3" />
          <text x="44" y="200" font-size="9" font-weight="700" fill="#0f172a">Offers tool</text>
          <text x="356" y="200" font-size="8.2" font-weight="600" fill="#334155" text-anchor="end">Acceptance and loss drivers</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="30" y="220" width="340" height="28" rx="5" fill="#ffffff" stroke="#64748b" stroke-width="1.3" />
          <text x="44" y="238" font-size="9" font-weight="700" fill="#0f172a">Evidence check</text>
          <text x="356" y="238" font-size="8.2" font-weight="600" fill="#334155" text-anchor="end">Only CONVERGENT cohorts go on</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="30" y="258" width="340" height="28" rx="5" fill="#ffffff" stroke="#d97706" stroke-width="1.6" />
          <text x="44" y="276" font-size="9" font-weight="700" fill="#92400e">Driver fit</text>
          <text x="356" y="276" font-size="8.2" font-weight="600" fill="#b45309" text-anchor="end">Drivers, lever costs, eligibility, budget</text>
        </g>

        <!-- Tree-of-Thought planner -->
        <g filter="url(#card-shadow)">
          <rect x="430" y="144" width="398" height="28" rx="5" fill="#ffffff" stroke="#7c3aed" stroke-width="1.4" />
          <text x="444" y="162" font-size="9" font-weight="700" fill="#4c1d95">Thought generator</text>
          <text x="814" y="162" font-size="8.2" font-weight="600" fill="#6d28d9" text-anchor="end">Adds one lever per child, 6 at the root</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="430" y="182" width="398" height="28" rx="5" fill="#ffffff" stroke="#7c3aed" stroke-width="1.4" />
          <text x="444" y="200" font-size="9" font-weight="700" fill="#4c1d95">Critic</text>
          <text x="814" y="200" font-size="8.2" font-weight="600" fill="#6d28d9" text-anchor="end">Code checks every child, a model reviews the 3 kept</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="430" y="220" width="398" height="28" rx="5" fill="#ffffff" stroke="#7c3aed" stroke-width="1.4" />
          <text x="444" y="238" font-size="9" font-weight="700" fill="#4c1d95">Controller</text>
          <text x="814" y="238" font-size="8.2" font-weight="600" fill="#6d28d9" text-anchor="end">Beam of 3, depth up to 4, at most 40 plans</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="430" y="258" width="198" height="28" rx="5" fill="#f5f3ff" stroke="#7c3aed" stroke-width="1.4" />
          <text x="529" y="270" font-size="8.6" font-weight="700" fill="#4c1d95" text-anchor="middle">Decision maker</text>
          <text x="529" y="281" font-size="7.8" font-weight="600" fill="#6d28d9" text-anchor="middle">3 distinct, non-dominated plans</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="638" y="258" width="190" height="28" rx="5" fill="#f5f3ff" stroke="#7c3aed" stroke-width="1.4" />
          <text x="733" y="270" font-size="8.6" font-weight="700" fill="#4c1d95" text-anchor="middle">Branch state (MCP)</text>
          <text x="733" y="281" font-size="7.8" font-weight="600" fill="#6d28d9" text-anchor="middle">Plan, facts, parent, pruning reason</text>
        </g>

        <!-- Grounded context, retrieval, writer, verifier -->
        <g filter="url(#card-shadow)">
          <rect x="190" y="322" width="470" height="30" rx="6" fill="#fefce8" stroke="#ca8a04" stroke-width="1.6" />
          <text x="425" y="341.5" font-size="10" font-weight="700" fill="#713f12" text-anchor="middle">Grounded context: 3 options, tool figures, sign-offs, clause IDs</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="684" y="322" width="160" height="30" rx="6" fill="#eef4ff" stroke="#2563eb" stroke-width="1.4" />
          <text x="764" y="334" font-size="8.4" font-weight="700" fill="#1e3a8a" text-anchor="middle">Retrieval (Checkpoint 3.1)</text>
          <text x="764" y="346" font-size="7.6" font-weight="600" fill="#1d4ed8" text-anchor="middle">Lever filters, cross-lever router</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="120" y="374" width="260" height="30" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.6" />
          <text x="250" y="393.5" font-size="10" font-weight="700" fill="#14532d" text-anchor="middle">Writer model drafts the brief</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="450" y="374" width="330" height="30" rx="6" fill="#fdf2f2" stroke="#dc2626" stroke-width="1.6" />
          <text x="615" y="393.5" font-size="10" font-weight="700" fill="#991b1b" text-anchor="middle">Python verifier: figures, plans, clauses</text>
        </g>
      </svg>
    </div>
    <div class="diagram-caption">
      <strong>Figure 1:</strong> Checkpoint 4.1 adds a Tree-of-Thought planner at the one step that needs it, building the brief's three options. The SQL steps stay linear. After the evidence check passes, the planner grows lever plans one decision at a time, code checks every plan, a beam keeps the best 3, and the decision maker hands three distinct plans to retrieval and the writer. The verifier checks figures, plans and clauses before the partner sees the brief.
    </div>
  </div>

  <h2 class="section-header">Written Submission</h2>

  <div class="section-block">
    <h3 class="sub-header">1. Does the agent need Tree-of-Thought reasoning?</h3>
    <p>Yes, at one step, and nowhere else. The SQL tools, the evidence check and retrieval are lookups with one right answer, so branching there would add model calls without adding accuracy. The tree goes where the playbook already asks for "Branching Intervention Options (Tree-of-Thought Trade-Offs)", three costed options for a cohort's loss drivers under a budget.</p>
  </div>
  <div class="section-block">
    <h3 class="sub-header">2. Where the tree runs and why a chain fails there</h3>
    <p>After the evidence check returns <code>CONVERGENT</code>, the agent picks which levers to combine: retention grants in three sizings, base lifts, level reviews and the new-hire band review. A linear chain commits early. The evidence says "cliff", so it starts with the default lever, a retention grant, and never revisits that choice. In Yao et al.'s Game of 24, about 60% of chain-of-thought samples failed at step one. For research scientists, grants spend $1,524,000 of the $2,150,000 left, level reviews no longer fit, and the chain ends at 2 of 4 departures. Only 1 of the 4 cited equity.</p>
    <p>The constraints also interact. Tier 0 and eligibility decide who can receive each lever, sign-offs depend on cost and tier, and costs don't add: 7 of the 9 level-review candidates also qualify for a base lift, which a promotion makes unnecessary.</p>
    <p>We measured this on the three cohorts that pass the evidence check, with the same code checks in every column, best plan inside the remaining budget:</p>
    <table class="data-table">
      <thead><tr><th>Cohort</th><th class="num">Template options</th><th class="num">Grant-first chain</th><th class="num">Tree</th></tr></thead>
      <tbody>
        <tr><td>Research scientists</td><td class="num">1 of 4, $1,524,000</td><td class="num">2 of 4, $1,804,600</td><td class="num">3 of 4, $1,236,800</td></tr>
        <tr><td>AI/ML engineers</td><td class="num">6 of 7, $1,715,000</td><td class="num">7 of 7, $2,009,200</td><td class="num">7 of 7, $2,009,200</td></tr>
        <tr><td>Cyber security engineers</td><td class="num">3 of 5, $2,142,000</td><td class="num">4 of 5, $2,574,400</td><td class="num">4 of 5, $2,574,400</td></tr>
      </tbody>
    </table>
    <p>For AI/ML and cyber, two of the three templates were one plan at one price. A chain that scores every step, instead of starting from grants, finds the tree's top plan in all three cohorts. So the tree earns its place through the option set. The brief needs three distinct, checked plans with their trade-offs, and a chain returns one.</p>
  </div>
  <div class="section-block">
    <h3 class="sub-header">3. The tree</h3>
    <ul class="bullets">
      <li><strong>Thought.</strong> One decision that extends a plan, such as "lift base to the 0.95 ceiling for the 18 eligible scientists".</li>
      <li><strong>Node.</strong> A plan so far, with the facts the tools compute for it: departures and declined offers addressed, first-year cost, budget fit and required sign-offs.</li>
      <li><strong>Branch and depth.</strong> A branch is a sequence of decisions. Depth is the number of levers decided, at most 4, one per lever.</li>
      <li><strong>Branching factor.</strong> 6 at the root, because grants come in three sizings, then at most 5, 4 and 3.</li>
      <li><strong>Termination.</strong> The search stops at depth 4, when no child adds coverage, or after 40 evaluated plans. The decision maker then picks three distinct plans that no other plan beats on coverage, cost and sign-offs at once: the most coverage inside the budget, the most coverage at any cost, and the cheapest plan that answers at least half the departures.</li>
    </ul>
    <p>For research scientists that gives 3 of 4 departures for $1,236,800, 4 of 4 for $2,760,800, $610,800 over budget with VP sign-off, and 2 of 4 for $1,078,000.</p>
  </div>
  <div class="section-block">
    <h3 class="sub-header">4. Search and evaluation</h3>
    <p><strong>Strategy: beam search, width 3.</strong> It is Yao et al.'s breadth-first search with a breadth limit, which the Lab 4.1 notebook calls a beam. Exhaustive search suits one cohort's 32 plans, but the org-level brief combines three cohorts, 32,768 plans, and a model critic call per node would cost too much. A beam of 3 matches the brief's three options and evaluated 24 to 27 plans per cohort. Depth-first search dives down one branch, the chain's failure, and Monte Carlo sampling adds variance where code computes every number. A beam is also the simplest to build and test, one loop and one ranking rule.</p>
    <p><strong>Who evaluates.</strong> Code checks every child. A reasoning model reviews only the three plans kept at each depth, for risks code can't score, such as a manager inversion flag. That caps cost at 12 calls and latency at 4 parallel rounds per cohort. The model can demote a plan with a reason, but never prunes one or changes a number.</p>
    <p><strong>Pruning and failure conditions.</strong></p>
    <ol class="numbered">
      <li>A lever with no eligible employee addresses nothing.</li>
      <li>A child that adds no departure or declined offer is dropped.</li>
      <li>Two paths to the same plan are evaluated once.</li>
      <li>A plan that covers no more and costs more than another isn't offered.</li>
      <li>A lever whose limit no retrieved clause states is a policy conflict, so the agent stops costing it.</li>
      <li>When no plan fits the budget, the brief offers the cheapest plan that answers at least half the departures and flags VP sign-off.</li>
    </ol>
    <p><strong>Ties.</strong> Inside the budget first, then more departures, more declined offers, fewer sign-offs, lower cost and fewer levers.</p>
  </div>
  <div class="section-block">
    <h3 class="sub-header">5. Roles mapped to tools</h3>
    <table class="data-table">
      <thead><tr><th>Role</th><th>Tool</th><th>Why</th></tr></thead>
      <tbody>
        <tr><td>Thought generator</td><td>CrewAI agent on a fast model</td><td>Picks the next decision from the six playbook actions. The code enumerator is its test oracle</td></tr>
        <tr><td>Critic</td><td>Python checks as MCP tools, plus a CrewAI critic on a reasoning model</td><td>Code owns every figure. The model judges what code can't</td></tr>
        <tr><td>Decision maker and controller</td><td>LangGraph (LangChain) state graph</td><td>Runs the beam loop, stopping rules and selection policy as testable steps</td></tr>
        <tr><td>Memory and state</td><td>MCP server</td><td>Holds each branch's plan, facts, parent and pruning reason, so all agents read one state and the partner sees why a plan was dropped</td></tr>
      </tbody>
    </table>
  </div>
  <div class="section-block">
    <h3 class="sub-header">6. Failure mode: weak evaluation signals</h3>
    <p>A critic that scores the wrong signal prunes good plans or keeps empty ones. Yao et al. saw the first failure in crosswords: without pruning, ToT found the right board in 4 of 20 games, 3 of which the pruned search missed within 100 steps. The template options score a lever by the drivers it addresses, not by who can receive it. In 8 of the 13 cohorts with departures, at least one template "addresses" departures for $0 because nobody qualifies. Only the evidence check stops them today. The planner prunes only in code, on the facts in Section 4. It checks eligibility and prices plans per employee, unit tests pin both, and it logs each pruned plan's reason.</p>
  </div>
  <div class="section-block">
    <h3 class="sub-header">7. Feedback from Checkpoint 3.1</h3>
    <p>The graders asked how the agent answers "Compare the equity caps for new hires versus current staff" without breaking its single-lever filters. One unfiltered search returned neither cap. The agent now runs one query per side, each inside a strict population and lever filter, and the writer sees one labeled group per side. So the new-hire limit, 1.20 times the equity guideline, and the Tier 3 ceiling for current staff, 150% to 200% of the refresh guideline, can't trade places. On 7 held-out comparisons, keyword search answered 5 of 11 sides against 0 with one query, and the verifier rejects a clause from the wrong side.</p>
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
                  <span>Checkpoint 4.1 Submission</span>
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
