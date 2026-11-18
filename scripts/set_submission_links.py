"""Puts the video link into the final report, the link document and their PDF generator.

Run it once the video is uploaded, then render both PDFs:

    python3 scripts/set_submission_links.py --video https://youtu.be/XXXXXXXXXXX
    python3 scripts/set_submission_links.py --check
    python3 scripts/generate_checkpoint_7_1_pdf.py

It changes only the link lines, in three files, and writes nothing unless every line is found.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
REPORT = Path("checkpoints/checkpoint_7_1.md")
LINKS = Path("checkpoints/checkpoint_7_1_video_link.md")
GENERATOR = Path("scripts/generate_checkpoint_7_1_pdf.py")

VIDEO_PENDING = "https://youtu.be/VIDEO-LINK-PENDING"
URL_RE = re.compile(r"https://[A-Za-z0-9.\-]+/[A-Za-z0-9._~/?=&%\-]+")
KNOWN_HOSTS = ("youtu.be", "youtube.com", "vimeo.com", "loom.com", "drive.google.com")

REPORT_VIDEO = re.compile(r"(?m)^(Video presentation: ).+$")
LINKS_VIDEO = re.compile(r"(?m)^(Video presentation, 8 to 10 minutes: ).+$")
VIDEO_SPAN = re.compile(r'(<span class="video-link">).*?(</span>)')


def check_url(url: str) -> str:
    """Returns a warning for an unusual host, or an empty string. Raises ValueError for a bad URL."""
    if not URL_RE.fullmatch(url):
        raise ValueError(f"{url!r} is not a plain https link. Copy the share link, with no spaces or quotes.")
    host = url.split("/")[2].removeprefix("www.")
    return "" if host in KNOWN_HOSTS else f"{host} is not YouTube, Vimeo, Loom or Google Drive. Check that reviewers can open it."


def current(root: Path = ROOT) -> dict[str, str]:
    """The video link the files hold now."""
    report = (root / REPORT).read_text(encoding="utf-8")
    links = (root / LINKS).read_text(encoding="utf-8")
    return {
        "video": REPORT_VIDEO.search(report).group(0).split(": ", 1)[1],
        "video_in_link_document": LINKS_VIDEO.search(links).group(0).split(": ", 1)[1],
    }


def _html(value: str) -> str:
    return f'<a href="{value}">{value}</a>' if value.startswith("https://") else value


def apply(root: Path = ROOT, video: str | None = None) -> dict[str, str]:
    """Writes the video link across the report, the link document and the PDF generator."""
    texts = {path: (root / path).read_text(encoding="utf-8") for path in (REPORT, LINKS, GENERATOR)}
    edits: list[tuple[Path, re.Pattern[str], str, int]] = []
    if video is not None:
        check_url(video)
        edits += [(REPORT, REPORT_VIDEO, video, 1), (LINKS, LINKS_VIDEO, video, 1),
                  (GENERATOR, VIDEO_SPAN, _html(video), 2)]
    for path, pattern, value, expected in edits:
        closing = r"\2" if pattern.groups == 2 else ""
        texts[path], found = pattern.subn(lambda m, v=value, c=closing: m.group(1) + v + m.expand(c), texts[path])
        if found != expected:
            raise RuntimeError(f"{path}: expected {expected} link line(s), found {found}. Nothing was written.")
    for path, text in texts.items():
        (root / path).write_text(text, encoding="utf-8")
    return current(root)


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--video", help="link to the 8 to 10 minute presentation video")
    parser.add_argument("--check", action="store_true", help="print the link the files hold and change nothing")
    args = parser.parse_args(argv)

    if not args.check:
        if not args.video:
            parser.error("nothing to do: pass --video or --check")
        try:
            warning = check_url(args.video)
            if warning:
                print(f"note: {warning}")
            apply(root, args.video)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}")
            return 2

    now = current(root)
    print(f"video: {now['video']}")
    if now["video"] != now["video_in_link_document"]:
        print("error: the report and the link document name different videos")
        return 2
    if now["video"] == VIDEO_PENDING:
        print("LINKS PENDING: video. The PDFs are not ready to submit.")
        return 1
    print("LINKS OK. Now run: python3 scripts/generate_checkpoint_7_1_pdf.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
