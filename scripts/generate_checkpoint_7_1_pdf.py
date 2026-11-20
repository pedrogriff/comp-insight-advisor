"""Generates the two submission PDFs for Assignment 7.1 using Playwright and inline SVG.

checkpoints/checkpoint_7_1.pdf is the final capstone report. checkpoints/checkpoint_7_1_video_link.pdf
is the one-page document with the video link and the summary. scripts/set_submission_links.py puts the
video link into both before this script runs.
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "checkpoints"
OUTPUT_PDF = OUTPUT_DIR / "checkpoint_7_1.pdf"
LINKS_PDF = OUTPUT_DIR / "checkpoint_7_1_video_link.pdf"

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
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }

    .institution-meta { max-width: 66%; }

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

    .meta-box strong { color: #0f172a; }

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

    .links-box {
      border: 1.5px solid #0f172a;
      border-radius: 6px;
      padding: 7px 11px;
      margin-bottom: 10px;
      font-size: 9.6pt;
      line-height: 1.6;
      background: #f8fafc;
    }

    .links-box a, p a, li a, td a { color: #1d4ed8; text-decoration: none; }

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
    ul.bullets, ol.numbered { margin: 0 0 7px 0; padding-left: 18px; }
    ul.bullets li, ol.numbered li { margin-bottom: 3px; text-align: justify; }

    table.grid {
      width: 100%;
      border-collapse: collapse;
      margin: 2px 0 8px 0;
      font-size: 8.6pt;
      line-height: 1.38;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    table.grid th {
      text-align: left;
      background: #f1f5f9;
      color: #0f172a;
      font-weight: 700;
      border: 1px solid #cbd5e1;
      padding: 4px 7px;
    }

    table.grid td {
      border: 1px solid #cbd5e1;
      padding: 4px 7px;
      vertical-align: top;
    }

    table.grid td:first-child { font-weight: 600; color: #0f172a; }
  </style>
</head>
<body>

  <div class="header-banner">
    <div class="institution-meta">
      <div class="institution-name">Carnegie Mellon University &bull; School of Computer Science</div>
      <div class="program-name">Executive Education: Agentic AI Program &bull; Capstone Project</div>
      <h1 class="doc-title">Assignment 7.1: Final Capstone Project Report</h1>
    </div>
    <div class="meta-box">
      <div><strong>Student:</strong> Pedro Griff Marcincowski</div>
      <div><strong>Project:</strong> Strategic Comp Insight Advisor</div>
      <div><strong>Track:</strong> <span class="badge">Research Assistant</span></div>
      <div><strong>Submission:</strong> <span class="badge badge-cmu">Module 7 &bull; Assignment 7.1</span></div>
    </div>
  </div>

  <div class="links-box">
    <div><strong>GitHub repository:</strong> <a href="https://github.com/pedrogriff/comp-insight-advisor">https://github.com/pedrogriff/comp-insight-advisor</a></div>
    <div><strong>Video presentation:</strong> <span class="video-link"><a href="https://youtu.be/VIDEO-LINK-PENDING">https://youtu.be/VIDEO-LINK-PENDING</a></span></div>
  </div>

  <h2 class="section-header">System Architecture Diagram</h2>
  <div class="diagram-card">
    <div class="diagram-svg-container">
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
    <div class="diagram-caption">
      <strong>Figure 1:</strong> The final system. A request passes the G1 screen, five nodes run with scoped tools on read-only data, and one model call writes the summary paragraph under a fact check. The G4 output check and the risk router then release the brief, send it to the approval gate, or hold it for a person.
    </div>
  </div>

  <h2 class="section-header">Written Submission</h2>

  <div class="section-block">
    <h3 class="sub-header">1. Project title</h3>
    <p>Strategic Talent and Compensation Insight Advisor, a guarded multi-agent research assistant for compensation partners.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">2. Problem and user</h3>
    <p>The user is a compensation partner preparing a quarterly retention and offer review for a VP. The partner joins four sources by hand: a roster that shows whose cash flow drops when equity runs out, a log of offers and counter-offers, exit and stay interview notes, and a governance playbook of 38 rules. Everything has to fit one department budget, and one wrong figure in front of a VP costs the partner's credibility.</p>
    <p>A chat assistant doesn't solve this, and I measured why. Given 500 roster rows, a model answered a count question right in 0 of 5 runs. Dividing in text, it matched the stored compa-ratio for a median of 297 of 300 employees. Asked whether equity has a compa-ratio cap, keyword and hybrid search ranked the new-hire offer rule first, the wrong population for a retention brief. Two teams also share one budget, and the best plan for each, priced separately, adds up to $3,246,000 against $2,150,000.</p>
    <p>All data is synthetic. Apex Cloud &amp; AI Corp has 2,000 employees, 4 VP orgs, 350 offer events and 261 interview notes, and it doesn't exist.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">3. System goal and scope</h3>
    <p><strong>Goal.</strong> From one request, the advisor drafts a brief the partner can take to a VP: the evidence, up to three costed options, the playbook clause behind each, and the sign-off each needs.</p>
    <p><strong>Design rationale.</strong> Counting, dividing, filtering by population and fitting a budget are jobs code does exactly. So models write the words, code computes the money, and people decide.</p>
    <p><strong>Evaluation criteria.</strong></p>
    <ol class="numbered">
      <li>Every dollar figure, percentage and coverage count in a brief traces to a tool output.</li>
      <li>Every cited rule belongs to the population the brief is about.</li>
      <li>Each option fits the budget or names who approves the overrun.</li>
      <li>Nothing that commits spend reaches a VP without a person's decision.</li>
      <li>The advisor refuses unsafe requests and answers legitimate ones.</li>
    </ol>
    <p><strong>Scope and constraints.</strong> The advisor reads and never writes, so a release is a document and no pay record changes. It answers about cohorts and refuses questions about one person's pay. If no model is configured or reachable, code writes the summary, so a brief never waits on a provider.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">4. Final system architecture</h3>
    <p>G1 comes first. It checks the playbook's hash and screens the request for prompt injection, questions about one person's pay, protected attributes, write orders and orgs outside the partner's scope, before any tool or model runs.</p>
    <p>Five nodes then run as a LangGraph <code>StateGraph</code> and pass typed state, never chat history. The supervisor plans the run and loads the partner's standing preferences. Two specialists run in parallel. The proactive strategist scans the roster, matches each reason for leaving to the lever that addresses it and searches lever plans with a beam of width 3. The reactive analyst reads the offers log, puts 95% intervals on its rates and searches the interview notes. The executive synthesizer composes one plan per org under the shared budget and retrieves each lever's clauses, filtered by lever and population. The governance reviewer checks every figure, clause and sign-off against the tool outputs and sends a failed draft back at most twice.</p>
    <p>The graph calls a language model at one point, the summary paragraph, because wording is the one step with no exact answer. The model gets code-written facts, and code rejects a draft that adds a number or a forbidden claim. After two rejected tries, the brief keeps the code-written paragraph. Every other decision is code.</p>
    <p>G4 then checks the output and the run's trace, and a risk router picks a lane. It releases a cited policy answer or a brief with no spend. A costed brief waits at an approval gate for the approvers the playbook names. Any flag holds the run for a person.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">5. Design evolution across the program</h3>
    <table class="grid">
      <thead><tr><th>Module</th><th>What I added</th><th>What feedback or a measurement changed</th></tr></thead>
      <tbody>
        <tr><td>1</td><td>One agent on paper</td><td>Graders asked about thin or conflicting data. I added an evidence check with intervals, and memory across sessions</td></tr>
        <tr><td>2</td><td>SQL tools that return summaries, not the raw roster</td><td>Graders asked me to separate why people leave. A driver-fit tool matches each reason to a lever</td></tr>
        <tr><td>3</td><td>38 tagged clauses and filtered retrieval</td><td>Graders asked about questions that span populations. A router runs one filtered query per side</td></tr>
        <tr><td>4</td><td>Tree-of-Thought beam search over lever plans</td><td>Graders asked whether pruning loses good plans. I tested the beam against exhaustive search</td></tr>
        <tr><td>5</td><td>Five nodes with scoped tools, one plan per org</td><td>My benchmark showed the saving comes from composing teams under one budget, not from the number of agents. Graders asked how shared state protects pay data. The roster scan was passing on rows with employee IDs, and tools now hand over counts only</td></tr>
        <tr><td>6</td><td>Guardrails, approval gate, audit log, console</td><td>Graders suggested counting what sends briefs to review, which the scorecard now does, and an embedding screen for reworded attacks, which is the next test. The final evaluation found that policy answers skipped the figure check. I fixed it and added 3 seeded faults</td></tr>
      </tbody>
    </table>
    <p>Two designs changed. Tree of Thought became a search that code scores, because every plan's cost and coverage are computable. Multi-agent became five nodes with at most 3 tools each, because I can test a node with a narrow job on its own.</p>
    <p>Three course methods are left out on purpose. No model picks a tool or reasons step by step, because every decision in this workflow has an answer code can check. Nothing is fine-tuned, because pay facts belong in tools. And the advisor is not packaged as a plugin, because its user works in the console.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">6. Implementation overview</h3>
    <p>The core is Python 3.12 with the standard library: <code>sqlite3</code> opened read-only for the roster tools, BM25 and reciprocal rank fusion for retrieval, and JSON files for test cases. LangGraph supplies the <code>StateGraph</code>, <code>Send()</code> for the parallel branch, <code>SqliteSaver</code> for checkpoints and <code>interrupt()</code> for the approval gate. A standard-library engine runs the same nodes when LangGraph is absent. Gradio serves a three-tab console. Embeddings come from <code>nomic-embed-text</code> through Ollama, and saved scores replay them offline. The summary writer calls any OpenAI-compatible chat endpoint or a local Ollama server, and <code>src/models/router.py</code> names the models. For the recorded run I chose a small model, <code>gemini-3.5-flash-lite</code>, because code supplies every fact and the model only words them.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">7. Evaluation and results</h3>
    <p>Every component has cases with a known right answer. One command, <code>python3 -m src.evaluation.scorecard</code>, reruns them all and compares the counts with the committed scorecard. A test checks this report's dollar figures, percentages and N-of-M counts against that file.</p>
    <table class="grid">
      <thead><tr><th>Question</th><th>Result</th></tr></thead>
      <tbody>
        <tr><td>Does retrieval find the right clause?</td><td>11 of 24 questions with keyword search, 24 of 24 with dense search, 23 of 24 with hybrid search</td></tr>
        <tr><td>Does a comparison get both sides?</td><td>9 of 11 held-out sides with one query per side, against 5 of 11 with a single query</td></tr>
        <tr><td>Does the beam match exhaustive search?</td><td>9 of 9 options at 105 of 105 budget levels, with 67.7% fewer critic reviews planned</td></tr>
        <tr><td>Does composing teams fit the budget?</td><td>$1,995,600 for 7 of 11 departures, against $3,246,000 with each team priced alone</td></tr>
        <tr><td>Does the screen refuse the right requests?</td><td>0 of 50 benign requests refused, 40 of 48 right on an unseen split</td></tr>
        <tr><td>Do later layers contain what the screen misses?</td><td>10 of 10, through scoped tools, the verifier and the approval route</td></tr>
        <tr><td>Do the checks catch a wrong brief?</td><td>158 of 163 seeded faults rejected, 23 of 23 clean briefs passed</td></tr>
        <tr><td>How often must a person look, and why?</td><td>5 of 23 requests waited for sign-off, 21.7%. The signals: an unreconciled budget ledger in 5 of 5, a Tier 3 grant in 5 of 5, a level decision in 4 of 5</td></tr>
        <tr><td>Does shared state stay at cohort level?</td><td>0 of 23 final states and 0 of 3 stored files name an employee</td></tr>
        <tr><td>Does a real model's paragraph pass?</td><td>With <code>gemini-3.5-flash-lite</code> writing, 22 of 23 runs ended on its first draft and 1 of 23 on its redraft</td></tr>
      </tbody>
    </table>
    <p>The checks hold whatever the model writes. A stand-in model that invents a figure in every draft ended 23 of 23 runs on the code-written paragraph, with the route unchanged. In the recorded run the fact check rejected 1 draft, which promised a guaranteed outcome, and the model's redraft passed. All 23 of 23 runs ended on the route of the code-written run. The tests replay those saved drafts against today's checks.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">8. Safety and reliability considerations</h3>
    <p>Code enforces every control, because a prompt is advice a model can ignore. Tools open the database read-only and accept only the orgs in the partner's session. They hand over counts, averages and totals, so the state the nodes share holds no row about one employee, and the monitor holds any run whose state names one. The model sees only the code-written facts. A hash guards the playbook, and a changed file stops the run. The reviewer, the output check and the monitor reject wrong figures, wrong-population clauses, employee IDs, promises and decision claims.</p>
    <p>When sources disagree, code doesn't pick a side. The evidence check asks whether the roster and the offers log agree, and only a cohort where both show risk gets costed options. A rate whose 95% interval straddles its threshold counts as inconclusive, and the brief discloses it. A limit that no retrieved clause states is reported as a policy conflict and adds compensation governance as an approver.</p>
    <p>Retries are bounded: one redraft for the model and two revisions for the reviewer. A third failure, a tool error or any flag holds the run for a person, who can inspect or discard it but never approve it. The gate refused 9 of 9 invalid approvals, and a waiting brief survives a restart. An audit log chains every step by hash, so an edit to any line shows. Each release carries the approver's decision, a label saying an AI assistant drafted it, and the hashes of the data and the playbook.</p>
  </div>

  <div class="section-block">
    <h3 class="sub-header">9. Limitations and next steps</h3>
    <ul class="bullets">
      <li>The data is synthetic, and no partner has used the advisor. The guardrails are tested on seeded faults, not validated on real requests. A pilot on masked data comes first.</li>
      <li>The screen let 8 of 30 unseen violations through. Later layers contained them. The graders suggested an embedding screen that compares a request with known attack patterns, and that is the next test.</li>
      <li>The 5 missed faults are invented percentages that match a number elsewhere in the tool output. Binding each figure to its claim would close that gap.</li>
      <li>The checks read numbers, clauses and banned phrases. A reworded sentence with no number can still be wrong.</li>
      <li>One model call is a narrow use of a model, and one recorded run on one model stands behind it. Reading the org and team from free text, checked against the partner's scope, is the next place for a model.</li>
    </ul>
  </div>

  <div class="section-block">
    <h3 class="sub-header">10. Public GitHub repository</h3>
    <p>The repository is public at <a href="https://github.com/pedrogriff/comp-insight-advisor">https://github.com/pedrogriff/comp-insight-advisor</a>. Its README explains the problem, the architecture, setup and usage. A section named "Review in five minutes" lists what to read on GitHub with nothing installed, maps each part of the video to its code, and gives four commands: the tests, the scorecard, the console and one guarded brief. <code>experiments/final_evaluation/</code> holds the scorecard, sample outputs and the recorded model run, and <code>checkpoints/</code> holds all seven write-ups.</p>
  </div>

</body>
</html>
"""

LINKS_HTML_TEMPLATE = """<!DOCTYPE html>
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
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }

    .institution-meta { max-width: 66%; }

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

    .meta-box strong { color: #0f172a; }

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

    .links-box {
      border: 1.5px solid #0f172a;
      border-radius: 6px;
      padding: 7px 11px;
      margin-bottom: 10px;
      font-size: 9.6pt;
      line-height: 1.6;
      background: #f8fafc;
    }

    .links-box a, p a, li a, td a { color: #1d4ed8; text-decoration: none; }

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
    ul.bullets, ol.numbered { margin: 0 0 7px 0; padding-left: 18px; }
    ul.bullets li, ol.numbered li { margin-bottom: 3px; text-align: justify; }

    table.grid {
      width: 100%;
      border-collapse: collapse;
      margin: 2px 0 8px 0;
      font-size: 8.6pt;
      line-height: 1.38;
      page-break-inside: avoid;
      break-inside: avoid;
    }

    table.grid th {
      text-align: left;
      background: #f1f5f9;
      color: #0f172a;
      font-weight: 700;
      border: 1px solid #cbd5e1;
      padding: 4px 7px;
    }

    table.grid td {
      border: 1px solid #cbd5e1;
      padding: 4px 7px;
      vertical-align: top;
    }

    table.grid td:first-child { font-weight: 600; color: #0f172a; }
  </style>
</head>
<body>

  <div class="header-banner">
    <div class="institution-meta">
      <div class="institution-name">Carnegie Mellon University &bull; School of Computer Science</div>
      <div class="program-name">Executive Education: Agentic AI Program &bull; Capstone Project</div>
      <h1 class="doc-title">Assignment 7.1: Presentation Video and Summary</h1>
    </div>
    <div class="meta-box">
      <div><strong>Student:</strong> Pedro Griff Marcincowski</div>
      <div><strong>Project:</strong> Strategic Comp Insight Advisor</div>
      <div><strong>Track:</strong> <span class="badge">Research Assistant</span></div>
      <div><strong>Submission:</strong> <span class="badge badge-cmu">Module 7 &bull; Assignment 7.1</span></div>
    </div>
  </div>

  <p>Pedro Griff Marcincowski. Strategic Talent and Compensation Insight Advisor.</p>

  <div class="links-box">
    <div><strong>Video presentation, 8 to 10 minutes:</strong> <span class="video-link"><a href="https://youtu.be/VIDEO-LINK-PENDING">https://youtu.be/VIDEO-LINK-PENDING</a></span></div>
    <div><strong>GitHub repository:</strong> <a href="https://github.com/pedrogriff/comp-insight-advisor">https://github.com/pedrogriff/comp-insight-advisor</a></div>
    <div><strong>Final report:</strong> attached to this submission as <code>checkpoint_7_1.pdf</code>.</div>
  </div>

  <h2 class="section-header">Summary of the Presentation</h2>
  <p>The video presents a research assistant that drafts retention briefs for compensation partners on synthetic data, built on one rule: models write the words, code computes the money, and people decide. It explains the problem, the architecture and the main design decisions, then runs the system live: a costed brief that waits for sign-off, a policy comparison, a refused request and a draft with an invented figure. It closes with the evaluation, where the checks rejected 158 of 163 seeded faults and the screen refused 0 of 50 benign requests, and with the public GitHub repository.</p>

</body>
</html>
"""

HEADER_TEMPLATE = """
    <div style="font-size: 7.5pt; font-family: 'Inter', sans-serif; color: #94a3b8; width: 100%; display: flex; justify-content: space-between; padding: 0 0.7in;">
      <span>Carnegie Mellon University &bull; SCS Executive Education: Agentic AI</span>
      <span>Assignment 7.1 Submission</span>
    </div>
"""

FOOTER_TEMPLATE = """
    <div style="font-size: 7.5pt; font-family: 'Inter', sans-serif; color: #94a3b8; width: 100%; display: flex; justify-content: space-between; padding: 0 0.7in;">
      <span>Strategic Talent &amp; Compensation Insight Advisor</span>
      <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
    </div>
"""


async def render(browser, html_text, out_path, wait_for):
    page = await browser.new_page(viewport={"width": 1200, "height": 1600})
    await page.set_content(html_text, wait_until="networkidle")
    await page.wait_for_selector(wait_for)
    await asyncio.sleep(1)
    pdf_bytes = await page.pdf(
        path=str(out_path),
        format="Letter",
        print_background=True,
        margin={
            "top": "0.65in",
            "bottom": "0.7in",
            "left": "0.7in",
            "right": "0.7in",
        },
        display_header_footer=True,
        header_template=HEADER_TEMPLATE,
        footer_template=FOOTER_TEMPLATE,
    )
    print(f"Generated {out_path} ({len(pdf_bytes)} bytes)")
    await page.close()


async def generate_pdf():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        await render(browser, HTML_TEMPLATE, OUTPUT_PDF, "svg")
        await render(browser, LINKS_HTML_TEMPLATE, LINKS_PDF, ".links-box")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(generate_pdf())
