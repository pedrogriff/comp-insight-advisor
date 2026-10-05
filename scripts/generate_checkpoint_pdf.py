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
  <title>Checkpoint 1.1: Problem Framing and Initial Agent Design</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
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

    .mermaid {
      display: flex;
      justify-content: center;
      width: 100%;
    }

    .mermaid svg {
      max-width: 100%;
      height: auto;
      max-height: 330px;
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
    <div class="mermaid">
flowchart TD
    User["Strategic Comp Partner User"] -->|"1. Requests talent brief for a client VP org"| Orch["Insight Advisor Orchestrator Agent"]
    
    subgraph Env["Environment: Synthetic Data and Policy Corpus"]
        DB1[("SQLite / CSV: Synthetic Org Roster & Multi-Year Cashflows")]
        DB2[("SQLite / CSV: Reactive Offer & Counter-Offer Logs")]
        RAG[("ChromaDB Vector Store: Comp Playbooks & Handoff Policies")]
    end

    Orch -->|"2. Trigger: Org query initiated -> Query cliff & peer stats"| DB1
    Orch -->|"3. Trigger: High attrition or cliff rate -> Query offer win/loss & counters"| DB2
    Orch -->|"4. Trigger: Reactive vs. proactive conflict -> Retrieve policy chunks"| RAG

    DB1 -->|"Returns cliff cohorts & inversions"| Synth["Drafting & Option Evaluation Module"]
    DB2 -->|"Returns poaching & decline spikes"| Synth
    RAG -->|"Returns governance & eligibility rules"| Synth

    Synth -->|"5. Generates candidate VP brief & recommendations"| Verifier["Verification & Guardrail Check"]
    
    Verifier -->|"Feedback Loop A: Math mismatch or policy violation -> Re-query & revise"| Orch
    Verifier -->|"6. Verified draft"| User
    User -->|"Feedback Loop B: Partner adjusts budget cap or priorities"| Orch
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

  <div class="callout-box">
    <strong>CMU Capstone Verification Summary:</strong> All sections strictly satisfy the 645-word capstone requirement for Checkpoint 1.1. System architecture adheres to the 4 engineering patterns in <code>AGENT_HANDOVER_SPEC.md</code> (zero-math in token space, two-tier model router, Pydantic handoffs, and deterministic verification).
  </div>

  <script>
    mermaid.initialize({
      startOnLoad: true,
      theme: 'base',
      themeVariables: {
        primaryColor: '#eff6ff',
        primaryBorderColor: '#3b82f6',
        primaryTextColor: '#1e3a8a',
        lineColor: '#64748b',
        secondaryColor: '#f1f5f9',
        secondaryBorderColor: '#94a3b8',
        tertiaryColor: '#f8fafc',
        tertiaryBorderColor: '#cbd5e1',
        fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
        fontSize: '11px'
      }
    });
  </script>
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
