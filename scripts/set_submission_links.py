"""Puts the video links into the final report, the link document and their PDF generator.

Run it once the videos are uploaded, then render both PDFs:

    python3 scripts/set_submission_links.py --video https://youtu.be/XXXXXXXXXXX --pitch https://youtu.be/YYYYYYYYYYY
    python3 scripts/set_submission_links.py --video https://youtu.be/XXXXXXXXXXX --no-pitch
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
PITCH_PENDING = "https://youtu.be/PITCH-LINK-PENDING"
NO_PITCH = "not submitted"
URL_RE = re.compile(r"https://[A-Za-z0-9.\-]+/[A-Za-z0-9._~/?=&%\-]+")
KNOWN_HOSTS = ("youtu.be", "youtube.com", "vimeo.com", "loom.com", "drive.google.com")

REPORT_VIDEO = re.compile(r"(?m)^(Video presentation: ).+$")
LINKS_VIDEO = re.compile(r"(?m)^(Video presentation, 8 to 10 minutes: ).+$")
LINKS_PITCH = re.compile(r"(?m)^(Optional 90-second elevator pitch, not graded: ).+$")
VIDEO_SPAN = re.compile(r'(<span class="video-link">).*?(</span>)')
PITCH_SPAN = re.compile(r'(<span class="pitch-link">).*?(</span>)')


def check_url(url: str) -> str:
    """Returns a warning for an unusual host, or an empty string. Raises ValueError for a bad URL."""
    if not URL_RE.fullmatch(url):
        raise ValueError(f"{url!r} is not a plain https link. Copy the share link, with no spaces or quotes.")
    host = url.split("/")[2].removeprefix("www.")
    return "" if host in KNOWN_HOSTS else f"{host} is not YouTube, Vimeo, Loom or Google Drive. Check that reviewers can open it."


def current(root: Path = ROOT) -> dict[str, str]:
    """The links the three files hold now."""
    report = (root / REPORT).read_text(encoding="utf-8")
    links = (root / LINKS).read_text(encoding="utf-8")
    return {
        "video": REPORT_VIDEO.search(report).group(0).split(": ", 1)[1],
        "video_in_link_document": LINKS_VIDEO.search(links).group(0).split(": ", 1)[1],
        "pitch": LINKS_PITCH.search(links).group(0).split(": ", 1)[1],
    }


def _html(value: str) -> str:
    return f'<a href="{value}">{value}</a>' if value.startswith("https://") else value


def apply(root: Path = ROOT, video: str | None = None, pitch: str | None = None) -> dict[str, str]:
    """Writes the links. pitch is a link, NO_PITCH, or None to leave it as it is."""
    texts = {path: (root / path).read_text(encoding="utf-8") for path in (REPORT, LINKS, GENERATOR)}
    edits: list[tuple[Path, re.Pattern[str], str, int]] = []
    if video is not None:
        check_url(video)
        edits += [(REPORT, REPORT_VIDEO, video, 1), (LINKS, LINKS_VIDEO, video, 1),
                  (GENERATOR, VIDEO_SPAN, _html(video), 2)]
    if pitch is not None:
        if pitch != NO_PITCH:
            check_url(pitch)
        edits += [(LINKS, LINKS_PITCH, pitch, 1), (GENERATOR, PITCH_SPAN, _html(pitch), 1)]
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
    parser.add_argument("--pitch", help="link to the optional 90-second elevator pitch")
    parser.add_argument("--no-pitch", action="store_true", help="say that no elevator pitch was submitted")
    parser.add_argument("--check", action="store_true", help="print the links the files hold and change nothing")
    args = parser.parse_args(argv)
    if args.pitch and args.no_pitch:
        parser.error("use --pitch or --no-pitch, not both")

    if not args.check:
        if not (args.video or args.pitch or args.no_pitch):
            parser.error("nothing to do: pass --video, --pitch, --no-pitch or --check")
        try:
            for url in (args.video, args.pitch):
                warning = check_url(url) if url else ""
                if warning:
                    print(f"note: {warning}")
            apply(root, args.video, NO_PITCH if args.no_pitch else args.pitch)
        except (ValueError, RuntimeError) as exc:
            print(f"error: {exc}")
            return 2

    now = current(root)
    print(f"video: {now['video']}")
    print(f"pitch: {now['pitch']}")
    pending = [name for name, value, placeholder in (("video", now["video"], VIDEO_PENDING),
                                                      ("pitch", now["pitch"], PITCH_PENDING)) if value == placeholder]
    if now["video"] != now["video_in_link_document"]:
        print("error: the report and the link document name different videos")
        return 2
    if pending:
        print(f"LINKS PENDING: {' and '.join(pending)}. The PDFs are not ready to submit.")
        return 1
    print("LINKS OK. Now run: python3 scripts/generate_checkpoint_7_1_pdf.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
