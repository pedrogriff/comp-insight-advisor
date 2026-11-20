"""Generates the eight slides for the Assignment 7.1 presentation video as a 16:9 PDF.

The slides follow the course's final presentation planning outline: opening, why the problem matters,
system architecture, key design decisions, evaluation and results, repository, closing reflection. One
more slide lists the four requests of the live demo. Open checkpoints/final_presentation.pdf in a PDF
viewer's presentation mode. Every figure on a slide comes from experiments/final_evaluation/scorecard.md.
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
OUTPUT_PDF = OUTPUT_DIR / "final_presentation.pdf"

SLIDES_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
  <style>
    @page { size: 13.333in 7.5in; margin: 0; }

    * {
      box-sizing: border-box;
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }

    html, body { margin: 0; padding: 0; background: #ffffff; }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      color: #1e293b;
    }

    .slide {
      width: 13.333in;
      height: 7.5in;
      padding: 0.5in 0.7in 0.6in 0.7in;
      position: relative;
      overflow: hidden;
      page-break-after: always;
      break-after: page;
      display: flex;
      flex-direction: column;
    }

    .slide:last-child { page-break-after: auto; break-after: auto; }

    .kicker {
      font-size: 12pt;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #C41230;
      margin-bottom: 6pt;
    }

    h1 {
      font-size: 30pt;
      line-height: 1.15;
      font-weight: 800;
      color: #0f172a;
      margin: 0 0 16pt 0;
      letter-spacing: -0.01em;
    }

    h1.cover { font-size: 40pt; margin-top: 0.7in; margin-bottom: 10pt; }

    .sub { font-size: 20pt; color: #334155; font-weight: 500; margin-bottom: 26pt; }

    .rule {
      font-size: 24pt;
      font-weight: 800;
      color: #0f172a;
      border-left: 7px solid #C41230;
      padding: 6pt 0 6pt 16pt;
      margin-top: auto;
      margin-bottom: 14pt;
    }

    .lines { font-size: 18pt; line-height: 1.45; margin: 0; padding: 0; list-style: none; }
    .lines li { margin-bottom: 10pt; }
    .lines strong { color: #0f172a; font-weight: 700; }

    .footer {
      position: absolute;
      left: 0.7in;
      right: 0.7in;
      bottom: 0.26in;
      display: flex;
      justify-content: space-between;
      font-size: 10pt;
      color: #64748b;
      border-top: 1px solid #e2e8f0;
      padding-top: 5pt;
    }

    .cards { display: grid; gap: 14pt; flex: 1; }
    .cards.four { grid-template-columns: repeat(4, 1fr); }
    .cards.two-by-four { grid-template-columns: repeat(4, 1fr); grid-template-rows: 1fr 1fr; }

    .card {
      border: 1.5px solid #cbd5e1;
      border-radius: 10px;
      padding: 14pt 14pt 12pt 14pt;
      background: #f8fafc;
      display: flex;
      flex-direction: column;
    }

    .card .big { font-size: 32pt; font-weight: 800; color: #0f172a; line-height: 1.1; margin-bottom: 8pt; }
    .card .big.small { font-size: 25pt; }
    .card .what { font-size: 14pt; line-height: 1.35; color: #334155; }
    .card .versus { font-size: 12pt; color: #64748b; margin-top: auto; padding-top: 8pt; }
    .card.bad { background: #fff1f2; border-color: #fecdd3; }
    .card.bad .big { color: #9f1239; }
    .card.good { background: #f0fdf4; border-color: #bbf7d0; }
    .card.good .big { color: #14532d; }

    .takeaway { font-size: 18pt; font-weight: 600; color: #0f172a; margin-top: 14pt; }

    .slide.split { flex-direction: row; gap: 0.25in; padding: 0.3in 0.4in 0.52in 0.5in; }
    .slide.split .side { width: 2.5in; flex: none; padding-top: 0.5in; }
    .slide.split h1 { font-size: 25pt; margin-bottom: 22pt; }
    .slide.split .lines { font-size: 14.5pt; line-height: 1.4; }
    .slide.split .lines li { margin-bottom: 14pt; }
    .diagram { flex: 1; display: flex; justify-content: center; align-items: center; min-height: 0; min-width: 0; }
    .diagram svg { height: 100%; width: auto; max-width: 100%; display: block; }

    ol.steps { font-size: 20pt; line-height: 1.4; margin: 0; padding-left: 30pt; }
    ol.steps li { margin-bottom: 14pt; padding-left: 6pt; }
    ol.steps strong { color: #0f172a; }
    ol.steps .lane { color: #64748b; font-size: 16pt; display: block; }

    table.decisions { width: 100%; border-collapse: collapse; font-size: 14.5pt; line-height: 1.3; }
    table.decisions th {
      text-align: left;
      background: #f1f5f9;
      border: 1px solid #cbd5e1;
      padding: 6pt 9pt;
      color: #0f172a;
    }
    table.decisions td { border: 1px solid #cbd5e1; padding: 6pt 9pt; vertical-align: top; }
    table.decisions td:first-child { font-weight: 800; color: #C41230; text-align: center; width: 6%; }
    table.decisions td:nth-child(2) { width: 34%; font-weight: 600; color: #0f172a; }

    .columns { display: grid; grid-template-columns: 1.25fr 1fr; gap: 26pt; flex: 1; }
    .columns h2 { font-size: 16pt; margin: 0 0 8pt 0; color: #C41230; text-transform: uppercase; letter-spacing: 0.06em; }
    .columns ul { font-size: 15.5pt; line-height: 1.4; margin: 0; padding-left: 18pt; }
    .columns li { margin-bottom: 7pt; }

    .repo {
      font-family: 'JetBrains Mono', monospace;
      font-size: 22pt;
      font-weight: 500;
      color: #1d4ed8;
      background: #eff6ff;
      border: 1.5px solid #bfdbfe;
      border-radius: 8px;
      padding: 8pt 14pt;
      margin-bottom: 18pt;
      align-self: flex-start;
    }

    code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9em;
      background: #f1f5f9;
      padding: 1px 5px;
      border-radius: 4px;
    }

    .three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16pt; flex: 1; }
    .three .card h2 { font-size: 16pt; margin: 0 0 8pt 0; text-transform: uppercase; letter-spacing: 0.06em; color: #C41230; }
    .three .card ul { font-size: 15pt; line-height: 1.4; margin: 0; padding-left: 18pt; color: #1e293b; }
    .three .card li { margin-bottom: 8pt; }
  </style>
</head>
<body>

  <section class="slide">
    <div class="kicker">Carnegie Mellon University, Agentic AI Program, final capstone</div>
    <h1 class="cover">Strategic Talent and Compensation Insight Advisor</h1>
    <div class="sub">A guarded multi-agent research assistant for compensation partners</div>
    <ul class="lines">
      <li><strong>User.</strong> A compensation partner preparing a quarterly retention and offer review for a VP.</li>
      <li><strong>Goal.</strong> A brief with the evidence, up to three costed options, the playbook clause behind each, and the sign-off each needs.</li>
    </ul>
    <div class="rule">Models write the words. Code computes the money. People decide.</div>
    <div class="footer"><span>Strategic Talent and Compensation Insight Advisor, Pedro Griff Marcincowski. All data is synthetic.</span><span>1 / 8</span></div>
  </section>

  <section class="slide">
    <div class="kicker">Why this problem matters</div>
    <h1>A chat assistant fails this job in ways I could measure</h1>
    <div class="cards four">
      <div class="card bad">
        <div class="big">0 of 5</div>
        <div class="what">runs right when a model counted from 500 roster rows</div>
        <div class="versus">5 of 5 right when it read the tool's summary</div>
      </div>
      <div class="card bad">
        <div class="big">297 of 300</div>
        <div class="what">compa-ratios right when a model divided in text, median of 5 runs</div>
        <div class="versus">300 of 300 with a divide tool</div>
      </div>
      <div class="card bad">
        <div class="big small">Wrong rule first</div>
        <div class="what">keyword and hybrid search ranked the new-hire rule first for a question about an equity cap</div>
        <div class="versus">a population filter removes it</div>
      </div>
      <div class="card bad">
        <div class="big small">$3,246,000</div>
        <div class="what">for two teams priced separately, against a $2,150,000 shared budget</div>
        <div class="versus">$1,995,600 when the plan is composed</div>
      </div>
    </div>
    <div class="takeaway">An agent fits the job, on one condition: code does every part that has an exact answer.</div>
    <div class="footer"><span>Strategic Talent and Compensation Insight Advisor, why this problem matters</span><span>2 / 8</span></div>
  </section>

  <section class="slide split">
    <div class="side">
      <div class="kicker">System architecture</div>
      <h1>One request, five nodes, three ways out</h1>
      <ul class="lines">
        <li><strong>Code decides.</strong> Screen, tools, planner and checks are code.</li>
        <li><strong>The model writes.</strong> One paragraph, held to the facts.</li>
        <li><strong>A person signs.</strong> Spend waits at the gate.</li>
      </ul>
    </div>
    <div class="diagram">
      <svg viewBox="0 0 860 590" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
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

        <!-- ==================== DASHED SQUAD CONTAINER ==================== -->
        <rect x="16" y="126" width="828" height="182" rx="8" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5 4" />
        <g transform="translate(560, 126)">
          <rect x="0" y="-9" width="270" height="18" rx="4" fill="#ffffff" stroke="#94a3b8" stroke-width="1" />
          <text x="135" y="3.5" font-size="7.8" font-weight="800" fill="#475569" letter-spacing="0.04em" text-anchor="middle">SQUAD: FIVE NODES, SCOPED TOOLS, READ-ONLY DATA</text>
        </g>

        <!-- ==================== CONNECTORS & EDGE LABELS ==================== -->
        <!-- 1. Partner -> G1 -->
        <path d="M 96 38 L 96 60" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />
        <g transform="translate(96, 49)">
          <rect x="-55" y="-7" width="110" height="14" rx="3" fill="#eff6ff" stroke="#bfdbfe" stroke-width="0.8" />
          <text x="0" y="2.8" font-size="7.4" font-weight="600" fill="#1e40af" text-anchor="middle">request + partner scope</text>
        </g>

        <!-- 2. G1 -> Refused -->
        <path d="M 390 82 L 448 82" fill="none" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(418, 82)">
          <rect x="-19" y="-7.5" width="38" height="15" rx="3" fill="#fff1f2" stroke="#fecdd3" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.5" font-weight="700" fill="#be123c" text-anchor="middle">refuse</text>
        </g>

        <!-- 3. G1 -> Supervisor -->
        <path d="M 96 102 L 96 176" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(96, 114)">
          <rect x="-20" y="-7" width="40" height="14" rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.8" />
          <text x="0" y="2.8" font-size="7.5" font-weight="700" fill="#166534" text-anchor="middle">allow</text>
        </g>

        <!-- 4. Supervisor -> Proactive strategist -->
        <path d="M 162 194 L 181 194 L 181 181 L 198 181" fill="none" stroke="#2563eb" stroke-width="1.5" marker-end="url(#arrow-blue)" />

        <!-- 5. Supervisor -> Reactive analyst -->
        <path d="M 162 218 L 181 218 L 181 245 L 198 245" fill="none" stroke="#2563eb" stroke-width="1.5" marker-end="url(#arrow-blue)" />

        <!-- 6. Proactive strategist -> Executive synthesizer -->
        <path d="M 410 181 L 429 181 L 429 194 L 446 194" fill="none" stroke="#2563eb" stroke-width="1.5" marker-end="url(#arrow-blue)" />

        <!-- 7. Reactive analyst -> Executive synthesizer -->
        <path d="M 410 245 L 429 245 L 429 218 L 446 218" fill="none" stroke="#2563eb" stroke-width="1.5" marker-end="url(#arrow-blue)" />

        <!-- 8. Executive synthesizer -> Governance reviewer -->
        <path d="M 624 206 L 660 206" fill="none" stroke="#2563eb" stroke-width="1.6" marker-end="url(#arrow-blue)" />

        <!-- 9. Revision loop: Governance reviewer -> Executive synthesizer, above both nodes -->
        <path d="M 746 178 L 746 152 L 536 152 L 536 176" fill="none" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrow-red)" />
        <g transform="translate(641, 152)">
          <rect x="-43" y="-7" width="86" height="14" rx="3" fill="#fff1f2" stroke="#fecdd3" stroke-width="0.9" />
          <text x="0" y="2.8" font-size="7.4" font-weight="700" fill="#be123c" text-anchor="middle">revise, at most 2</text>
        </g>

        <!-- 10. Executive synthesizer <-> Language model -->
        <path d="M 536 236 L 536 256" fill="none" stroke="#7c3aed" stroke-width="1.5" marker-start="url(#arrow-purple)" marker-end="url(#arrow-purple)" />

        <!-- 11. Governance reviewer -> G4 output check -->
        <path d="M 800 234 L 800 336" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(800, 322)">
          <rect x="-36" y="-7" width="72" height="14" rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.8" />
          <text x="0" y="2.8" font-size="7.4" font-weight="700" fill="#166534" text-anchor="middle">verified brief</text>
        </g>

        <!-- 12. Supervisor <-> Partner memory -->
        <path d="M 96 236 L 96 476" fill="none" stroke="#7c3aed" stroke-width="1.5" marker-start="url(#arrow-purple)" marker-end="url(#arrow-purple)" />
        <g transform="translate(96, 392)">
          <rect x="-33" y="-7" width="66" height="14" rx="3" fill="#faf5ff" stroke="#e9d5ff" stroke-width="0.8" />
          <text x="0" y="2.8" font-size="7.4" font-weight="700" fill="#6b21a8" text-anchor="middle">preferences</text>
        </g>

        <!-- 13. G4 -> Held -->
        <path d="M 448 358 L 392 358" fill="none" stroke="#d97706" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arrow-amber)" />
        <g transform="translate(421, 358)">
          <rect x="-15" y="-7.5" width="30" height="15" rx="3" fill="#fffbeb" stroke="#fde68a" stroke-width="0.8" />
          <text x="0" y="3" font-size="7.5" font-weight="700" fill="#92400e" text-anchor="middle">flag</text>
        </g>

        <!-- 14. G4 -> Risk router -->
        <path d="M 639 378 L 639 406" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(639, 392)">
          <rect x="-24" y="-7" width="48" height="14" rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.8" />
          <text x="0" y="2.8" font-size="7.4" font-weight="700" fill="#166534" text-anchor="middle">no flags</text>
        </g>

        <!-- 15. Risk router -> Audit log -->
        <path d="M 448 428 L 392 428" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow-slate)" />

        <!-- 16. Risk router -> Released without a person -->
        <path d="M 538 448 L 538 476" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />
        <g transform="translate(538, 462)">
          <rect x="-23" y="-7" width="46" height="14" rx="3" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="0.8" />
          <text x="0" y="2.8" font-size="7.4" font-weight="700" fill="#166534" text-anchor="middle">18 of 23</text>
        </g>

        <!-- 17. Risk router -> Approval gate -->
        <path d="M 740 448 L 740 476" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-end="url(#arrow-purple)" />
        <g transform="translate(740, 462)">
          <rect x="-21" y="-7" width="42" height="14" rx="3" fill="#faf5ff" stroke="#e9d5ff" stroke-width="0.8" />
          <text x="0" y="2.8" font-size="7.4" font-weight="700" fill="#6b21a8" text-anchor="middle">5 of 23</text>
        </g>

        <!-- 18. Released without a person -> Brief -->
        <path d="M 538 516 L 538 544" fill="none" stroke="#16a34a" stroke-width="1.6" marker-end="url(#arrow-green)" />

        <!-- 19. Approval gate -> Brief -->
        <path d="M 740 516 L 740 544" fill="none" stroke="#7c3aed" stroke-width="1.6" marker-end="url(#arrow-purple)" />
        <g transform="translate(740, 530)">
          <rect x="-25" y="-7" width="50" height="14" rx="3" fill="#faf5ff" stroke="#e9d5ff" stroke-width="0.8" />
          <text x="0" y="2.8" font-size="7.4" font-weight="700" fill="#6b21a8" text-anchor="middle">approved</text>
        </g>

        <!-- ==================== NODE BOXES ==================== -->
        <!-- Compensation partner -->
        <g filter="url(#card-shadow)">
          <rect x="30" y="8" width="330" height="30" rx="6" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.75" />
          <text x="195" y="27" font-size="9.6" font-weight="700" fill="#1e3a8a" text-anchor="middle">Compensation partner: Gradio console, session scope</text>
        </g>

        <!-- G1 -->
        <g filter="url(#card-shadow)">
          <rect x="30" y="62" width="360" height="40" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.75" />
          <text x="210" y="79" font-size="9.5" font-weight="700" fill="#14532d" text-anchor="middle">G1: playbook hash and request screen</text>
          <text x="210" y="93" font-size="7.8" font-weight="600" fill="#166534" text-anchor="middle">runs before any tool or model</text>
        </g>

        <!-- Refused -->
        <g filter="url(#card-shadow)">
          <rect x="450" y="62" width="200" height="40" rx="6" fill="#fff1f2" stroke="#e11d48" stroke-width="1.5" />
          <text x="550" y="79" font-size="8.8" font-weight="700" fill="#9f1239" text-anchor="middle">Refused or asked to clarify</text>
          <text x="550" y="93" font-size="7.5" font-weight="600" fill="#be123c" text-anchor="middle">injection, one person's pay, write order</text>
        </g>

        <!-- Supervisor -->
        <g filter="url(#card-shadow)">
          <rect x="30" y="178" width="132" height="56" rx="5" fill="#ffffff" stroke="#2563eb" stroke-width="1.6" />
          <text x="96" y="203" font-size="9.3" font-weight="700" fill="#1e3a8a" text-anchor="middle">Supervisor</text>
          <text x="96" y="218" font-size="7.6" font-weight="600" fill="#334155" text-anchor="middle">plan, scope, memory</text>
        </g>

        <!-- Proactive strategist -->
        <g filter="url(#card-shadow)">
          <rect x="200" y="158" width="210" height="46" rx="5" fill="#ffffff" stroke="#2563eb" stroke-width="1.6" />
          <text x="305" y="177" font-size="9.3" font-weight="700" fill="#1e3a8a" text-anchor="middle">Proactive strategist</text>
          <text x="305" y="192" font-size="7.6" font-weight="600" fill="#334155" text-anchor="middle">roster scan, driver fit, beam planner</text>
        </g>

        <!-- Reactive analyst -->
        <g filter="url(#card-shadow)">
          <rect x="200" y="222" width="210" height="46" rx="5" fill="#ffffff" stroke="#2563eb" stroke-width="1.6" />
          <text x="305" y="241" font-size="9.3" font-weight="700" fill="#1e3a8a" text-anchor="middle">Reactive analyst</text>
          <text x="305" y="256" font-size="7.6" font-weight="600" fill="#334155" text-anchor="middle">offers log, evidence check, interview notes</text>
        </g>

        <!-- Executive synthesizer -->
        <g filter="url(#card-shadow)">
          <rect x="448" y="178" width="176" height="56" rx="5" fill="#ffffff" stroke="#2563eb" stroke-width="1.6" />
          <text x="536" y="203" font-size="9.3" font-weight="700" fill="#1e3a8a" text-anchor="middle">Executive synthesizer</text>
          <text x="536" y="218" font-size="7.6" font-weight="600" fill="#334155" text-anchor="middle">joint plan, clauses, summary</text>
        </g>

        <!-- Governance reviewer -->
        <g filter="url(#card-shadow)">
          <rect x="662" y="178" width="168" height="56" rx="5" fill="#fefce8" stroke="#ca8a04" stroke-width="1.6" />
          <text x="746" y="203" font-size="9.3" font-weight="700" fill="#713f12" text-anchor="middle">Governance reviewer</text>
          <text x="746" y="218" font-size="7.6" font-weight="600" fill="#854d0e" text-anchor="middle">figures, clauses, sign-offs</text>
        </g>

        <!-- Language model -->
        <g filter="url(#card-shadow)">
          <rect x="448" y="258" width="176" height="38" rx="5" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.5" />
          <text x="536" y="274" font-size="8.6" font-weight="700" fill="#581c87" text-anchor="middle">Language model</text>
          <text x="536" y="287" font-size="7.3" font-weight="600" fill="#6b21a8" text-anchor="middle">writes one paragraph, held to the facts</text>
        </g>

        <!-- G4 output check and monitor -->
        <g filter="url(#card-shadow)">
          <rect x="448" y="338" width="382" height="40" rx="6" fill="#fefce8" stroke="#ca8a04" stroke-width="1.6" />
          <text x="639" y="355" font-size="9.3" font-weight="700" fill="#713f12" text-anchor="middle">G4: output check and runtime monitor</text>
          <text x="639" y="369" font-size="7.6" font-weight="600" fill="#854d0e" text-anchor="middle">employee IDs, promises, decision claims, tool scope, node order</text>
        </g>

        <!-- Held -->
        <g filter="url(#card-shadow)">
          <rect x="180" y="338" width="210" height="40" rx="6" fill="#fff7ed" stroke="#d97706" stroke-width="1.5" />
          <text x="285" y="355" font-size="8.8" font-weight="700" fill="#9a3412" text-anchor="middle">Held for a person</text>
          <text x="285" y="369" font-size="7.5" font-weight="600" fill="#b45309" text-anchor="middle">inspect or discard, never approve</text>
        </g>

        <!-- Risk router -->
        <g filter="url(#card-shadow)">
          <rect x="448" y="408" width="382" height="40" rx="6" fill="#eff6ff" stroke="#2563eb" stroke-width="1.6" />
          <text x="639" y="425" font-size="9.3" font-weight="700" fill="#1e3a8a" text-anchor="middle">Risk router: the worst signal picks the lane</text>
          <text x="639" y="439" font-size="7.6" font-weight="600" fill="#1d4ed8" text-anchor="middle">spend, Tier 3 grants, budget overrun, policy conflict</text>
        </g>

        <!-- Audit log -->
        <g filter="url(#card-shadow)">
          <rect x="180" y="408" width="210" height="40" rx="6" fill="#f8fafc" stroke="#64748b" stroke-width="1.5" />
          <text x="285" y="425" font-size="8.8" font-weight="700" fill="#1e293b" text-anchor="middle">Audit log</text>
          <text x="285" y="439" font-size="7.5" font-weight="600" fill="#475569" text-anchor="middle">hash-chained record of every step</text>
        </g>

        <!-- Released without a person -->
        <g filter="url(#card-shadow)">
          <rect x="448" y="478" width="180" height="38" rx="5" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5" />
          <text x="538" y="494" font-size="8.6" font-weight="700" fill="#14532d" text-anchor="middle">Released without a person</text>
          <text x="538" y="507" font-size="7.4" font-weight="600" fill="#166534" text-anchor="middle">policy answer or no spend</text>
        </g>

        <!-- Approval gate -->
        <g filter="url(#card-shadow)">
          <rect x="650" y="478" width="180" height="38" rx="5" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.6" />
          <text x="740" y="494" font-size="8.6" font-weight="700" fill="#4c1d95" text-anchor="middle">Approval gate</text>
          <text x="740" y="507" font-size="7.4" font-weight="600" fill="#6b21a8" text-anchor="middle">named approvers, durable queue</text>
        </g>

        <!-- Partner memory -->
        <g filter="url(#card-shadow)">
          <rect x="30" y="478" width="360" height="38" rx="5" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.5" />
          <text x="210" y="494" font-size="8.6" font-weight="700" fill="#581c87" text-anchor="middle">Partner memory and checkpoints in SQLite</text>
          <text x="210" y="507" font-size="7.4" font-weight="600" fill="#6b21a8" text-anchor="middle">a preference needs 3 sessions and a confirmation</text>
        </g>

        <!-- Brief to the partner -->
        <g filter="url(#card-shadow)">
          <rect x="30" y="546" width="800" height="34" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.6" />
          <text x="430" y="567" font-size="9.2" font-weight="700" fill="#14532d" text-anchor="middle">Brief to the partner: clauses, sign-offs, decision record, AI label, data and playbook hashes</text>
        </g>
      </svg>
    </div>
    <div class="footer"><span>Strategic Talent and Compensation Insight Advisor, system architecture</span><span>3 / 8</span></div>
  </section>

  <section class="slide">
    <div class="kicker">Live demo</div>
    <h1>Four requests, one for each way a run can end</h1>
    <ol class="steps">
      <li><strong>An org brief with spend.</strong> Five nodes, a joint plan of $1,995,600, cited clauses.
        <span class="lane">Waits at the approval gate until the named approvers are acknowledged.</span></li>
      <li><strong>A policy comparison.</strong> New hires against current staff, one filtered query per side.
        <span class="lane">Released without a person, with every side cited.</span></li>
      <li><strong>An unsafe request.</strong> A prompt injection that asks for one person's pay.
        <span class="lane">Refused before any tool or model runs.</span></li>
      <li><strong>A draft with an invented figure.</strong> A writer that adds $9,999,999.
        <span class="lane">Held for a person. It can be inspected or discarded, never approved.</span></li>
    </ol>
    <div class="footer"><span>Strategic Talent and Compensation Insight Advisor, live demo</span><span>4 / 8</span></div>
  </section>

  <section class="slide">
    <div class="kicker">Key design decisions</div>
    <h1>Each module's design changed after feedback or a measurement</h1>
    <table class="decisions">
      <thead><tr><th>Module</th><th>What I added</th><th>What changed it</th></tr></thead>
      <tbody>
        <tr><td>1</td><td>One agent on paper</td><td>Graders asked about thin or conflicting data. Evidence check with intervals, memory across sessions</td></tr>
        <tr><td>2</td><td>SQL tools that return summaries, not the raw roster</td><td>Graders asked me to separate why people leave. A driver-fit tool matches each reason to a lever</td></tr>
        <tr><td>3</td><td>38 tagged clauses and filtered retrieval</td><td>Graders asked about questions that span populations. One filtered query per side</td></tr>
        <tr><td>4</td><td>Tree-of-Thought beam search over lever plans</td><td>Graders asked whether pruning loses good plans. Beam tested against exhaustive search</td></tr>
        <tr><td>5</td><td>Five nodes with scoped tools, one plan per org</td><td>Graders asked how shared state protects pay data. Tools now hand over counts, never one employee's row</td></tr>
        <tr><td>6</td><td>Guardrails, approval gate, audit log, console</td><td>The final evaluation found that policy answers skipped the figure check. Fixed. Graders asked what triggers review. Counted</td></tr>
      </tbody>
    </table>
    <div class="footer"><span>Strategic Talent and Compensation Insight Advisor, key design decisions</span><span>5 / 8</span></div>
  </section>

  <section class="slide">
    <div class="kicker">Evaluation and results</div>
    <h1>Every component has cases with a known right answer</h1>
    <div class="cards two-by-four">
      <div class="card good">
        <div class="big">24 of 24</div>
        <div class="what">questions get the right clause with dense search</div>
        <div class="versus">11 of 24 with keyword search</div>
      </div>
      <div class="card good">
        <div class="big">9 of 11</div>
        <div class="what">held-out comparison sides answered with one query per side</div>
        <div class="versus">5 of 11 with a single query</div>
      </div>
      <div class="card good">
        <div class="big">9 of 9</div>
        <div class="what">options match exhaustive search, at 105 of 105 budget levels</div>
        <div class="versus">67.7% fewer critic reviews planned</div>
      </div>
      <div class="card good">
        <div class="big small">$1,995,600</div>
        <div class="what">joint plan for 7 of 11 departures, inside the budget</div>
        <div class="versus">$3,246,000 with each team priced alone</div>
      </div>
      <div class="card good">
        <div class="big">0 of 50</div>
        <div class="what">benign requests refused by the screen</div>
        <div class="versus">40 of 48 right on an unseen split</div>
      </div>
      <div class="card good">
        <div class="big">158 of 163</div>
        <div class="what">seeded faults rejected by the checks</div>
        <div class="versus">23 of 23 clean briefs passed</div>
      </div>
      <div class="card">
        <div class="big">10 of 10</div>
        <div class="what">violations that passed the screen were contained by later layers</div>
        <div class="versus">8 of 30 unseen violations passed the screen</div>
      </div>
      <div class="card">
        <div class="big">5 of 23</div>
        <div class="what">requests waited for a person's sign-off</div>
        <div class="versus">18 of 23 released without a person</div>
      </div>
    </div>
    <div class="takeaway">With a real model writing, 22 of 23 first drafts passed and the check sent 1 back.</div>
    <div class="footer"><span>Strategic Talent and Compensation Insight Advisor, evaluation and results</span><span>6 / 8</span></div>
  </section>

  <section class="slide">
    <div class="kicker">Repository and implementation</div>
    <h1>The public repository holds the code, the tests and the evidence</h1>
    <div class="repo">github.com/pedrogriff/comp-insight-advisor</div>
    <div class="columns">
      <div>
        <h2>What you can find there</h2>
        <ul>
          <li>A README with the problem, the architecture, setup, and a five-minute review path</li>
          <li><code>src/</code>: tools, retrieval, planner, the five-node squad, guardrails, the console</li>
          <li><code>tests/</code>: unit tests that run offline with no packages</li>
          <li><code>experiments/final_evaluation/</code>: the scorecard behind every figure here, and the recorded model run</li>
          <li><code>checkpoints/</code>: all seven write-ups, this report included</li>
        </ul>
      </div>
      <div>
        <h2>Built with</h2>
        <ul>
          <li>Python 3.12 standard library for tools, retrieval and checks</li>
          <li>LangGraph for the graph, checkpoints and the approval pause</li>
          <li>Gradio for the console</li>
          <li><code>nomic-embed-text</code> through Ollama for embeddings</li>
          <li><code>gemini-3.5-flash-lite</code> for the summary paragraph, or any OpenAI-compatible model</li>
        </ul>
      </div>
    </div>
    <div class="footer"><span>Strategic Talent and Compensation Insight Advisor, repository and implementation</span><span>7 / 8</span></div>
  </section>

  <section class="slide">
    <div class="kicker">Closing reflection</div>
    <h1>What worked, what did not, and what comes next</h1>
    <div class="three">
      <div class="card good">
        <h2>What worked</h2>
        <ul>
          <li>Giving the model one job and checking it in code. A real model promised a guaranteed outcome once in 23 runs, and the check sent that draft back</li>
          <li>Evaluating every week. The final evaluation found a real hole, and a test now guards it</li>
        </ul>
      </div>
      <div class="card bad">
        <h2>Limits</h2>
        <ul>
          <li>Synthetic data, and no partner has used it</li>
          <li>8 of 30 unseen violations passed the first screen</li>
          <li>5 invented percentages passed the verifier</li>
          <li>A sentence with no number can still be wrong</li>
        </ul>
      </div>
      <div class="card">
        <h2>Next</h2>
        <ul>
          <li>A pilot on masked data</li>
          <li>Bind each figure to its claim</li>
          <li>An embedding screen for reworded attacks, as the graders suggested</li>
          <li>Let a model read the org and team from the request, checked against the partner's scope</li>
        </ul>
      </div>
    </div>
    <div class="rule" style="margin-top: 14pt;">Models write the words. Code computes the money. People decide.</div>
    <div class="footer"><span>Strategic Talent and Compensation Insight Advisor, closing reflection</span><span>8 / 8</span></div>
  </section>

</body>
</html>
"""


async def generate_pdf():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.set_content(SLIDES_HTML, wait_until="networkidle")
        await page.wait_for_selector("svg")
        await asyncio.sleep(1)
        pdf_bytes = await page.pdf(
            path=str(OUTPUT_PDF),
            width="13.333in",
            height="7.5in",
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        print(f"Generated {OUTPUT_PDF} ({len(pdf_bytes)} bytes)")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(generate_pdf())
