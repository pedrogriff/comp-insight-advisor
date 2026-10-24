"""Generates submission-ready PDF for Checkpoint 3.1 using Playwright and inline SVG."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
OUTPUT_PDF = OUTPUT_DIR / "checkpoint_3_1.pdf"

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
    table.data-table.flags td:nth-child(2) { color: #b91c1c; font-weight: 600; white-space: nowrap; }
    table.data-table th.num, table.data-table td.num { text-align: right; }
    table.data-table td.num { white-space: nowrap; font-variant-numeric: tabular-nums; }
    table.data-table:not(.flags) td:first-child { white-space: nowrap; }
  </style>
</head>
<body>

  <!-- ==================== PAGE 1 ==================== -->
  <div class="header-banner">
    <div class="institution-meta">
      <div class="institution-name">Carnegie Mellon University &bull; School of Computer Science</div>
      <div class="program-name">Executive Education: Agentic AI Program &bull; Capstone Project</div>
      <h1 class="doc-title">Checkpoint 3.1: Retrieval Design &amp; Data Grounding</h1>
    </div>
    <div class="meta-box">
      <div><strong>Student:</strong> Pedro Griff Marcincowski</div>
      <div><strong>Project:</strong> Strategic Comp Insight Advisor</div>
      <div><strong>Track:</strong> <span class="badge">Research Assistant</span></div>
      <div><strong>Submission:</strong> <span class="badge badge-cmu">Module 3 &bull; Checkpoint 3.1</span></div>
    </div>
  </div>

  <h2 class="section-header">System Architecture Diagram</h2>
  <div class="diagram-card">
    <div class="diagram-svg-container">
<svg viewBox="0 0 860 436" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
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
          <text x="116" y="3.5" font-size="8.2" font-weight="800" fill="#475569" letter-spacing="0.04em" text-anchor="middle">STRUCTURED DATA: EXACT SQL TOOLS</text>
        </g>
        <rect x="414" y="128" width="430" height="172" rx="8" fill="#f5f8ff" stroke="#60a5fa" stroke-width="1.5" stroke-dasharray="5 4" />
        <g transform="translate(430, 128)">
          <rect x="0" y="-9" width="262" height="18" rx="4" fill="#ffffff" stroke="#60a5fa" stroke-width="1" />
          <text x="131" y="3.5" font-size="8.2" font-weight="800" fill="#1d4ed8" letter-spacing="0.04em" text-anchor="middle">UNSTRUCTURED TEXT: RETRIEVAL LAYER</text>
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
        <!-- Controller to the SQL tools -->
        <path d="M 300 102 L 300 114 L 200 114 L 200 142" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />
        <!-- Tool sequence -->
        <path d="M 200 172 L 200 180" fill="none" stroke="#64748b" stroke-width="1.3" marker-end="url(#arrow-slate)" />
        <path d="M 200 210 L 200 218" fill="none" stroke="#64748b" stroke-width="1.3" marker-end="url(#arrow-slate)" />
        <path d="M 200 248 L 200 256" fill="none" stroke="#64748b" stroke-width="1.3" marker-end="url(#arrow-slate)" />
        <!-- Driver fit to the query builder and to the notes -->
        <path d="M 370 272 L 400 272 L 400 158 L 428 158" fill="none" stroke="#d97706" stroke-width="1.6" marker-end="url(#arrow-amber)" />
        <path d="M 400 272 L 400 294 L 736 294 L 736 288" fill="none" stroke="#d97706" stroke-width="1.4" stroke-dasharray="4 3" marker-end="url(#arrow-amber)" />
        <!-- Query builder to hybrid search to playbook -->
        <path d="M 636 172 L 636 180" fill="none" stroke="#2563eb" stroke-width="1.3" marker-end="url(#arrow-blue)" />
        <path d="M 532 210 L 532 218" fill="none" stroke="#2563eb" stroke-width="1.3" marker-end="url(#arrow-blue)" />
        <!-- Into the grounded context -->
        <path d="M 250 300 L 250 320" fill="none" stroke="#d97706" stroke-width="1.6" marker-end="url(#arrow-amber)" />
        <g transform="translate(176, 311)">
          <rect x="-62" y="-8.5" width="124" height="17" rx="3" fill="#ffffff" stroke="#fde68a" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#b45309" text-anchor="middle">Costs, counts, flags</text>
        </g>
        <path d="M 610 300 L 610 320" fill="none" stroke="#d97706" stroke-width="1.6" marker-end="url(#arrow-amber)" />
        <g transform="translate(728, 311)">
          <rect x="-106" y="-8.5" width="212" height="17" rx="3" fill="#ffffff" stroke="#fde68a" stroke-width="0.8" />
          <text x="0" y="3.2" font-size="8" font-weight="600" fill="#b45309" text-anchor="middle">3 clauses per lever, 1 per flag, exit notes</text>
        </g>
        <!-- Grounded context to writer to verifier -->
        <path d="M 260 352 L 260 372" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <path d="M 380 389 L 448 389" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <!-- Verifier loop back to the writer -->
        <path d="M 615 404 L 615 422 L 250 422 L 250 406" fill="none" stroke="#dc2626" stroke-width="1.6" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(432, 422)">
          <rect x="-160" y="-8.5" width="320" height="17" rx="4" fill="#fff1f2" stroke="#fecdd3" stroke-width="1" />
          <text x="0" y="3.2" font-size="8" font-weight="700" fill="#be123c" text-anchor="middle">Untraced figure, wrong-population clause or conflict: redraft</text>
        </g>
        <!-- Verified brief back to the partner -->
        <path d="M 780 389 L 850 389 L 850 23 L 562 23" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(705, 23)">
          <rect x="-82" y="-9" width="164" height="18" rx="4" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1" />
          <text x="0" y="3.5" font-size="8.5" font-weight="700" fill="#15803d" text-anchor="middle">Verified brief with citations</text>
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
          <text x="356" y="238" font-size="8.2" font-weight="600" fill="#334155" text-anchor="end">Intervals and pattern label</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="30" y="258" width="340" height="28" rx="5" fill="#ffffff" stroke="#d97706" stroke-width="1.6" />
          <text x="44" y="276" font-size="9" font-weight="700" fill="#92400e">Driver fit</text>
          <text x="356" y="276" font-size="8.2" font-weight="600" fill="#b45309" text-anchor="end">Levers, options, costs and flags</text>
        </g>

        <!-- Retrieval layer -->
        <g filter="url(#card-shadow)">
          <rect x="430" y="144" width="398" height="28" rx="5" fill="#ffffff" stroke="#2563eb" stroke-width="1.4" />
          <text x="444" y="162" font-size="9" font-weight="700" fill="#1e3a8a">Query builder</text>
          <text x="814" y="162" font-size="8.2" font-weight="600" fill="#1d4ed8" text-anchor="end">One query per lever and per flag, lever filter</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="430" y="182" width="398" height="28" rx="5" fill="#ffffff" stroke="#2563eb" stroke-width="1.4" />
          <text x="444" y="200" font-size="9" font-weight="700" fill="#1e3a8a">Hybrid search</text>
          <text x="814" y="200" font-size="8.2" font-weight="600" fill="#1d4ed8" text-anchor="end">Embeddings + BM25, rank fusion, SQLite vectors</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="430" y="220" width="200" height="66" rx="6" fill="#eef4ff" stroke="#2563eb" stroke-width="1.4" />
          <text x="530" y="239" font-size="9.5" font-weight="700" fill="#1e3a8a" text-anchor="middle">Governance playbook</text>
          <text x="530" y="255" font-size="8.2" font-weight="600" fill="#1d4ed8" text-anchor="middle">38 rule chunks</text>
          <text x="530" y="268" font-size="8.2" font-weight="600" fill="#1d4ed8" text-anchor="middle">tagged by lever and population</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="638" y="220" width="190" height="66" rx="6" fill="#eef4ff" stroke="#2563eb" stroke-width="1.4" />
          <text x="733" y="239" font-size="9.5" font-weight="700" fill="#1e3a8a" text-anchor="middle">Interview notes</text>
          <text x="733" y="255" font-size="8.2" font-weight="600" fill="#1d4ed8" text-anchor="middle">261 synthetic notes</text>
          <text x="733" y="268" font-size="8.2" font-weight="600" fill="#1d4ed8" text-anchor="middle">looked up by cohort</text>
        </g>

        <!-- Grounded context, writer, verifier -->
        <g filter="url(#card-shadow)">
          <rect x="190" y="322" width="480" height="30" rx="6" fill="#fefce8" stroke="#ca8a04" stroke-width="1.6" />
          <text x="430" y="341.5" font-size="10.5" font-weight="700" fill="#713f12" text-anchor="middle">Grounded context: tool figures, clause IDs, note IDs</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="120" y="374" width="260" height="30" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.6" />
          <text x="250" y="393.5" font-size="10" font-weight="700" fill="#14532d" text-anchor="middle">Writer model drafts the brief</text>
        </g>
        <g filter="url(#card-shadow)">
          <rect x="450" y="374" width="330" height="30" rx="6" fill="#fdf2f2" stroke="#dc2626" stroke-width="1.6" />
          <text x="615" y="393.5" font-size="10" font-weight="700" fill="#991b1b" text-anchor="middle">Python verifier: figures, clauses, code limits</text>
        </g>
      </svg>
    </div>
    <div class="diagram-caption">
      <strong>Figure 1:</strong> Checkpoint 3.1 adds a retrieval layer beside the SQL tools. After the evidence check and the driver-fit tool, the agent retrieves policy clauses by lever and flag and every exit note for the cohort. The writer sees only tool figures, clause IDs and note IDs, and the verifier checks figures, cited clauses and the code's limits against the clauses.
    </div>
  </div>

  <h2 class="section-header">Written Submission</h2>

  <div class="section-block">
    <h3 class="sub-header">1. Does the agent need retrieval?</h3>
    <p>Yes for policy text and interview notes, and no for numbers. The agent answers three kinds of questions:</p>
    <ul class="bullets">
      <li><strong>How many and how much.</strong> Cliff counts, acceptance rates, costs and budgets come from SQL over the synthetic roster, offers log and budgets. Similarity search would return rows that look alike, not the right total, so numbers stay in SQL and text goes to a vector store, as Jesse Barkley advised in the Week 2 office hour.</li>
      <li><strong>What the rules allow.</strong> Approvals, raise limits and required disclosures live in the 1,869-word governance playbook. No model learned them, because the company is synthetic, and they change. Section 6 arrived on Oct 22, after the 2.1 grading.</li>
      <li><strong>Why people left.</strong> 261 synthetic exit and stay interview notes give reasons in the employees' own words. SQL filters them by cohort but can't rank them by meaning.</li>
    </ul>
    <p>Lecture Slide 61 says to include a small corpus whole and to retrieve when it is large, frequently updated or expensive to include. The playbook is small but it changes, and a real deployment adds interview notes every quarter. A whole playbook also puts every limit in front of the writer at once, 1.00 and 1.20 for new-hire offers and 0.80 and 0.95 for current pay. Our Checkpoint 2.1 draft cited "the 1.20 post-grant compa-ratio cap", which the playbook doesn't contain. Its only 1.20 belongs to the new-hire clause. Retrieval sends only the clauses for the lever at hand. The full-playbook prompt stays as an untested baseline that retrieval has to beat in the Checkpoint 7.1 evaluation.</p>
  </div>
  <div class="section-block">
    <h3 class="sub-header">2. How semantic retrieval fits into the loop</h3>
    <p>The external sources are the playbook, cut into 38 rule-sized chunks, and the 261 notes. An open embedding model, <code>nomic-embed-text</code> served locally by Ollama, turns each chunk into a vector. SQLite stores the vectors with the model name and a hash of the playbook, so a changed playbook or model triggers a rebuild. A BM25 index covers the same chunks, and reciprocal rank fusion merges the two rankings, because dense vectors catch paraphrases while keyword search still wins on exact terms such as "Tier 0", as the DPR paper found. Metadata filters run first.</p>
    <p>After the evidence check returns <code>CONVERGENT</code> and the driver-fit tool names the levers in play, the agent:</p>
    <ol class="numbered">
      <li>sends one query per lever, written in playbook terms from the lever and the cohort's loss drivers and filtered to that lever's clauses;</li>
      <li>sends one query for each checklist item a tool flag raises;</li>
      <li>fetches every exit note for the cohort by metadata, since the brief needs all of them, not the nearest five.</li>
    </ol>
    <p>The writer model sees only the tool figures, the clauses and the notes, and it cites their IDs. BM25 needs no model, and the tests replay the embedding model's saved scores, so the default run and the 103 unit tests work offline.</p>
  </div>
  <div class="section-block">
    <h3 class="sub-header">3. How retrieval changes the brief</h3>
    <p><code>VP_CLOUD_AI</code> research scientists, the case the 2.1 graders raised, show the change. The tools return the same numbers either way. Of 4 departures after a counter-offer, 2 cite level, 1 base salary and 1 equity. Option A fits the $2,150,000 remaining budget at $1,524,000 but addresses 1 departure, and Option C addresses all 4 at $4,006,600.</p>
    <table class="data-table flags">
      <thead><tr><th>Checklist item from the tools</th><th>Without retrieval</th><th>With retrieval</th></tr></thead>
      <tbody>
        <tr><td>Grants address 1 of 4 departures</td><td>Unsupported</td><td>Section 6.1, a grant "changes neither base salary nor level"</td></tr>
        <tr><td>4 departures, below the minimum of 5</td><td>Unsupported</td><td>Section 6.5, state counts instead of percentages and name the data that would settle it</td></tr>
        <tr><td>5 employees below the floor, $21,100 to fix</td><td>Unsupported</td><td>Section 6.2, no base salary below a 0.80 compa-ratio</td></tr>
        <tr><td>9 level review candidates, $1,078,000 a year</td><td>Unsupported</td><td>Section 6.3, the people manager and the calibration committee decide</td></tr>
        <tr><td>Option C is $1,856,600 over budget</td><td>Unsupported</td><td>Section 6.2, adjustments above the remaining budget need VP sign-off</td></tr>
      </tbody>
    </table>
    <p>Without retrieval, the verifier blocks each unsourced rule, so the brief gives numbers without the rules behind them. With retrieval, all 5 items cite a clause, and the 4 exit notes add reasons such as EXIT-0024, "The counter-offer added stock but left my salary where it was." The brief separates the drivers, matches each to its lever and shows the trade-off with its rules, as the graders asked. <code>python3 -m src.retrieval.grounded_options --compare</code> prints both columns.</p>
    <p>Retrieval also picks up policy changes without retraining, as the RAG paper showed by swapping its 2016 index for a 2018 one. In a playbook copy that lowers the raise ceiling from 0.95 to 0.90, no clause states the code's 0.95 any more, so the agent reports a conflict and stops costing Option C's base lifts.</p>
  </div>
  <div class="section-block">
    <h3 class="sub-header">4. Retrieval design choices</h3>
    <ul class="bullets">
      <li><strong>Sources.</strong> The playbook for rules, the notes for reasons and SQL for tables.</li>
      <li><strong>Segmentation.</strong> One chunk per rule, meaning each bullet, numbered item or paragraph, plus the lever table. The lecture's usual 800 to 1,000 tokens would hold a third or more of the playbook and mix the rules it warned against mixing. The 38 chunks run 13 to 161 words, with a median of 30.5. Search reads each chunk with its section heading in front, as DPR puts the article title before each passage, and tags record its levers and population. On 24 test questions, rule chunks and 120-word windows with 30 words of overlap each found the right clause in the top 3 for 11. The windows carried 133 words of context on average against 47, and a window spans up to 5 rules, so a citation can't point to one.</li>
      <li><strong>How many results.</strong> 3 clauses per lever, inside the lecture's usual 2 or 3, plus 1 per checklist item and every exit note in the cohort. A larger k adds recall but also noise and tokens, so when a limit the code applies is missing from the 3, an exact lookup adds its clause instead, as it did for the level review's 2-year rule and the Tier 0 rule for grants.</li>
      <li><strong>When to return nothing.</strong> A clause must match half of the query's terms or score at least 0.60 with the embedding model. Lab 3.2 warned against tuning on the test set, so the 0.60 comes from the 16 tuning questions alone. There, every answerable question had a clause scoring at least 0.607, and no unanswerable one had a clause above 0.584. Lowering the keyword bar to a quarter raised tuning hits from 8 to 12, but on the 8 held-out questions it still found 3 and answered a question the playbook doesn't cover, so the bar stays at half.</li>
    </ul>
  </div>
  <div class="section-block">
    <h3 class="sub-header">5. Failure mode: a relevant clause for the wrong population</h3>
    <p>The lecture called this a similarity trap, where high similarity means shared vocabulary, not the correct answer. In the playbook it appears as two populations. Section 2.1 lets the Offers Desk approve new-hire offers up to a 1.00 compa-ratio and 1.20 times the equity guideline, and Section 6.2 caps raises for current employees at 0.95. Asked "Is there a compa-ratio cap for equity?", BM25 ranks the new-hire clause first, and a writer that reads it can repeat our 2.1 error. The embedding model barely separates the two. It scores the 0.80 floor for current employees at 0.700 and the new-hire clause at 0.698, so hybrid search still ranks the new-hire clause first.</p>
    <p>Three checks manage the risk:</p>
    <ol class="numbered">
      <li><strong>Filters.</strong> Chunks carry their levers and population, and the agent's queries filter on the lever, so a retention query never sees Section 2.1. A playbook section without tags fails a unit test.</li>
      <li><strong>Clause verification.</strong> Slide 29 calls a nearby vector "a candidate, not proof". Each rule in a draft cites a clause ID, and a Python check confirms that each number appears in that clause and that the clause governs the lever. "1.20" for a retention grant fails, because it appears only in a new-hire clause.</li>
      <li><strong>Code against policy.</strong> Tools compute every dollar, and the limit check confirms that each limit the code applies, such as the 0.95 lift ceiling or the ratings Tier 0 excludes from grants, appears in a clause for that lever.</li>
    </ol>
    <p>As Slide 54 advises, we compared dense search with keyword and hybrid baselines on the same 28 questions:</p>
    <table class="data-table">
      <thead><tr><th>Search</th><th class="num">Tuning: right clause in top 3</th><th class="num">Held-out: right clause in top 3</th><th class="num">Unanswerable: nothing returned</th><th class="num">Context words per question</th></tr></thead>
      <tbody>
        <tr><td>Keyword, BM25</td><td class="num">8 of 16</td><td class="num">3 of 8</td><td class="num">4 of 4</td><td class="num">47</td></tr>
        <tr><td>Dense, <code>nomic-embed-text</code></td><td class="num">16 of 16</td><td class="num">8 of 8</td><td class="num">3 of 4</td><td class="num">113</td></tr>
        <tr><td>Hybrid, fused by rank</td><td class="num">16 of 16</td><td class="num">7 of 8</td><td class="num">3 of 4</td><td class="num">122</td></tr>
      </tbody>
    </table>
    <p>All 13 keyword misses use a partner's words rather than the playbook's, such as the held-out "Can anyone on staff be paid far under market?", where dense search ranks the 0.80 floor rule first. Both embedding modes also answer the held-out "How much is the annual bonus for sales staff?" with a level review clause that mentions the bonus target. Hybrid search lost "Who signs off on the largest retention awards?" because keyword matches on "sign-off" pushed the Tier 3 rule out of the top 3. With 19 paraphrases among the 24 answerable questions, the Checkpoint 7.1 evaluation adds questions in the playbook's own terms, such as "Tier 0", before choosing between dense and hybrid. Neither removes the population trap, so the filters and the clause check stay.</p>
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
                  <span>Checkpoint 3.1 Submission</span>
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
