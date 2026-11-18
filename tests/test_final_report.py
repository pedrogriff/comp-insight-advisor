"""Tests that hold the final report to the scorecard, the course template and its own generator.

The advisor checks every figure in a brief against a tool output. The report gets the same
treatment: every dollar figure, percentage and "N of M" count in it must appear in the committed
scorecard, so the write-up cannot drift from what the code measures.
"""

from __future__ import annotations

import ast
import contextlib
import html
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from src.evaluation import scorecard

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "checkpoints" / "checkpoint_7_1.md"
LINKS = ROOT / "checkpoints" / "checkpoint_7_1_video_link.md"
REPO_URL = "https://github.com/pedrogriff/comp-insight-advisor"

_spec = importlib.util.spec_from_file_location("set_submission_links", ROOT / "scripts" / "set_submission_links.py")
set_links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(set_links)
# The ten sections of the course's final capstone report planning template, in order.
TEMPLATE_SECTIONS = [
    "1. Project title",
    "2. Problem and user",
    "3. System goal and scope",
    "4. Final system architecture",
    "5. Design evolution across the program",
    "6. Implementation overview",
    "7. Evaluation and results",
    "8. Safety and reliability considerations",
    "9. Limitations and next steps",
    "10. Public GitHub repository",
]
# A method setting, not a result: the confidence level of the intervals the evidence check reports.
NOT_RESULTS = {"95%"}


def written_submission(text: str) -> str:
    return text.split("## Written submission", 1)[1]


def count_words(block: str) -> int:
    """Words a reader sees: no heading marks, list marks, table rules or code ticks."""
    lines = []
    for line in block.splitlines():
        line = line.strip()
        if re.fullmatch(r"\|[\s:\-|]+\|", line):
            continue
        line = re.sub(r"^(#+|-|\d+\.)\s+", "", line)
        lines.append(line.replace("|", " ").replace("*", "").replace("`", ""))
    return len(re.findall(r"\S+", "\n".join(lines)))


class FinalReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = REPORT.read_text(encoding="utf-8")
        cls.body = written_submission(cls.text)
        cls.card = json.loads(scorecard.JSON_PATH.read_text(encoding="utf-8"))

    def test_links_come_first(self) -> None:
        lines = [line for line in self.text.splitlines() if line.strip()]
        self.assertEqual(lines[0], "# Checkpoint 7.1 final capstone report")
        self.assertEqual(lines[1], f"GitHub repository: {REPO_URL}")
        self.assertRegex(lines[2], r"^Video presentation: https://\S+$")

    def test_sections_follow_the_course_template(self) -> None:
        self.assertEqual(re.findall(r"^### (.+)$", self.body, flags=re.M), TEMPLATE_SECTIONS)
        for name in ("Goal.", "Design rationale.", "Evaluation criteria.", "Scope and constraints."):
            self.assertIn(f"**{name}**", self.body)
        self.assertIn(REPO_URL, self.body.split("### 10. Public GitHub repository", 1)[1])

    def test_length_is_inside_the_suggested_range(self) -> None:
        self.assertTrue(1000 <= count_words(self.body) <= 1500, count_words(self.body))

    def test_every_figure_is_in_the_scorecard(self) -> None:
        quotable = scorecard.quotable(self.card)
        stray = sorted(scorecard.figures(self.text) - quotable - NOT_RESULTS)
        self.assertEqual(stray, [], "figures in the report that the committed scorecard does not state")
        # The check has teeth: a changed figure is caught.
        self.assertIn("157 of 163", scorecard.figures(self.text.replace("158 of 163", "157 of 163")) - quotable)

    def test_no_dash_used_as_punctuation(self) -> None:
        for name, text in (("report", self.text), ("link document", LINKS.read_text(encoding="utf-8"))):
            self.assertNotRegex(text, "[\u2014\u2013]", name)
            self.assertNotRegex(text, r"\w - \w", name)


class SubmissionLinkTests(unittest.TestCase):
    def test_link_document_names_both_links_and_labels_the_pitch_optional(self) -> None:
        text = LINKS.read_text(encoding="utf-8")
        self.assertIn(f"GitHub repository: {REPO_URL}", text)
        self.assertRegex(text, r"(?m)^Video presentation, 8 to 10 minutes: https://\S+$")
        self.assertRegex(text, r"(?m)^Optional 90-second elevator pitch, not graded: .+$")
        summary = text.split("## Summary of the presentation", 1)[1].strip().split("\n\n")[0]
        self.assertTrue(2 <= len(re.findall(r"[.!?](?:\s|$)", summary)) <= 3, summary)
        card = json.loads(scorecard.JSON_PATH.read_text(encoding="utf-8"))
        self.assertEqual(sorted(scorecard.figures(text) - scorecard.quotable(card)), [])

    def test_the_two_documents_agree_on_the_video_link(self) -> None:
        now = set_links.current(ROOT)
        self.assertEqual(now["video"], now["video_in_link_document"])

    def test_setting_the_links_changes_all_three_files_and_nothing_else(self) -> None:
        video, pitch = "https://youtu.be/dQw4w9WgXcQ", "https://www.loom.com/share/0123abcd"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in (set_links.REPORT, set_links.LINKS, set_links.GENERATOR):
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / path, root / path)
            before = {path: (root / path).read_text(encoding="utf-8") for path in
                      (set_links.REPORT, set_links.LINKS, set_links.GENERATOR)}
            with contextlib.redirect_stdout(io.StringIO()) as out:
                # Before any link is set the check fails loudly, when the committed files still hold placeholders.
                pending = set_links.current(root)["video"] == set_links.VIDEO_PENDING
                self.assertEqual(set_links.main(["--check"], root), 1 if pending else 0)
                self.assertEqual(set_links.main(["--video", "http://youtu.be/x y"], root), 2)
                self.assertEqual(set_links.main(["--video", video, "--pitch", pitch], root), 0)
            self.assertIn("LINKS OK", out.getvalue())
            report, links, generator = (
                (root / path).read_text(encoding="utf-8")
                for path in (set_links.REPORT, set_links.LINKS, set_links.GENERATOR)
            )
            self.assertIn(f"\nVideo presentation: {video}\n", report)
            self.assertIn(f"\nVideo presentation, 8 to 10 minutes: {video}\n", links)
            self.assertIn(f"\nOptional 90-second elevator pitch, not graded: {pitch}\n", links)
            self.assertEqual(generator.count(f'<span class="video-link"><a href="{video}">{video}</a></span>'), 2)
            self.assertEqual(generator.count(f'<span class="pitch-link"><a href="{pitch}">{pitch}</a></span>'), 1)
            compile(generator, "generate_checkpoint_7_1_pdf.py", "exec")
            # Only the link lines changed: every other line of each file is as it was.
            for path, now in zip((set_links.REPORT, set_links.LINKS, set_links.GENERATOR), (report, links, generator)):
                changed = [(a, b) for a, b in zip(before[path].splitlines(), now.splitlines()) if a != b]
                self.assertEqual(len(before[path].splitlines()), len(now.splitlines()))
                self.assertTrue(all("link" in a.lower() or "Video presentation" in a or "pitch" in a
                                    for a, _ in changed), changed)
                self.assertLessEqual(len(changed), 3)

            # A second run replaces the first links, and --no-pitch drops the pitch link.
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(set_links.main(["--video", "https://vimeo.com/123456789", "--no-pitch"], root), 0)
            now = set_links.current(root)
            self.assertEqual((now["video"], now["pitch"]), ("https://vimeo.com/123456789", set_links.NO_PITCH))
            generator = (root / set_links.GENERATOR).read_text(encoding="utf-8")
            self.assertIn('<span class="pitch-link">not submitted</span>', generator)
            self.assertNotIn(video, generator)

    def test_generator_html_says_what_the_markdown_says(self) -> None:
        consts = {}
        for node in ast.walk(ast.parse((ROOT / set_links.GENERATOR).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str):
                consts[node.targets[0].id] = node.value.value

        def visible_words(fragment: str) -> list[str]:
            fragment = re.sub(r"<svg\b.*?</svg>", " ", fragment, flags=re.S)
            return html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split()

        def markdown_words(text: str) -> list[str]:
            lines = []
            for line in text.splitlines():
                line = line.strip()
                if re.fullmatch(r"\|[\s:\-|]+\|", line):
                    continue
                if line.startswith("#"):
                    line = line.lstrip("#").strip()
                else:
                    # A list item loses its mark. In HTML the browser draws the bullet or the number.
                    line = re.sub(r"^(-|\d+\.)\s+", "", line)
                lines.append(line.replace("|", " ").replace("**", "").replace("`", ""))
            return " ".join(lines).split()

        report_html = consts["HTML_TEMPLATE"].split('<h2 class="section-header">Written Submission</h2>', 1)[1]
        report_md = written_submission(REPORT.read_text(encoding="utf-8"))
        # Character for character, apart from white space, which HTML tags move around punctuation.
        self.assertEqual("".join(visible_words(report_html)), "".join(markdown_words(report_md)))

        links_md = LINKS.read_text(encoding="utf-8")
        summary = links_md.split("## Summary of the presentation", 1)[1].strip()
        self.assertIn("".join(summary.replace("`", "").split()),
                      "".join(visible_words(consts["LINKS_HTML_TEMPLATE"])))
        now = set_links.current(ROOT)
        for value in (now["video"], now["pitch"], REPO_URL):
            self.assertIn(value, consts["LINKS_HTML_TEMPLATE"])
        self.assertEqual(consts["HTML_TEMPLATE"].count(now["video"]) >= 1, True)


class SlideTests(unittest.TestCase):
    """The presentation has to agree with the report, so the slides get the same checks."""

    # The seven parts of the course's final presentation planning outline. The slides add a live demo part.
    OUTLINE = ["Why this problem matters", "System architecture", "Key design decisions", "Evaluation and results",
               "Repository and implementation", "Closing reflection"]
    # The figure the demo's fault-injection writer adds. It is the fault, not a result.
    SEEDED_FAULT = {"$9,999,999"}

    @classmethod
    def setUpClass(cls) -> None:
        tree = ast.parse((ROOT / "scripts" / "generate_final_slides_pdf.py").read_text(encoding="utf-8"))
        cls.html = next(node.value.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                        and getattr(node.targets[0], "id", "") == "SLIDES_HTML")
        body = re.sub(r"<(svg|style)\b.*?</\1>", " ", cls.html, flags=re.S)
        cls.text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body)).split())

    def test_eight_slides_follow_the_presentation_outline(self) -> None:
        self.assertEqual(len(re.findall(r'<section class="slide', self.html)), 8)
        kickers = re.findall(r'<div class="kicker">(.*?)</div>', self.html)
        self.assertEqual(len(kickers), 8)
        self.assertEqual([k for k in kickers if k in self.OUTLINE], self.OUTLINE)
        self.assertIn("Live demo", kickers)
        self.assertIn("github.com/pedrogriff/comp-insight-advisor", self.text)
        self.assertEqual(self.text.count("Models write the words. Code computes the money. People decide."), 2)

    def test_every_figure_on_a_slide_is_in_the_scorecard(self) -> None:
        card = json.loads(scorecard.JSON_PATH.read_text(encoding="utf-8"))
        stray = sorted(scorecard.figures(self.text) - scorecard.quotable(card) - self.SEEDED_FAULT)
        self.assertEqual(stray, [], "figures on the slides that the committed scorecard does not state")

    def test_slides_and_report_tell_the_same_design_story(self) -> None:
        report = written_submission(REPORT.read_text(encoding="utf-8"))
        rows = re.findall(r"(?m)^\| (\d) \| (.+?) \| .+ \|$", report)
        self.assertEqual([number for number, _ in rows], list("123456"))
        for _, added in rows:
            self.assertIn(added, self.text)


if __name__ == "__main__":
    unittest.main()
