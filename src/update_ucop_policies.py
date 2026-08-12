"""Generate the UCOP policy sitemap from the advanced search results."""

from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


SEARCH_URL = (
    "https://policy.ucop.edu/advanced-search.php?action=search&op=results&"
    "keywords=&subject_area=0&audience=0&responsible_office=0&lookup=1&all=1"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "ucop_policies.xml"
POLICY_PATH = re.compile(r"/doc/\d+")
RESULT_TOTAL = re.compile(r"\b\d+\s+of\s+(\d+)\b")
USER_AGENT = "tritongpt-sitemaps/1.0 (+https://github.com/ucsd-ets/tritongpt-sitemaps)"


class PolicyLinkParser(HTMLParser):
    """Collect links from the UCOP policy search results."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return

        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def fetch_search_results(source_url: str, timeout: float) -> str:
    """Download and decode the UCOP search results page."""
    request = Request(source_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def extract_policy_urls(html: str, source_url: str = SEARCH_URL) -> list[str]:
    """Extract unique UCOP policy links and add the crawler-friendly PDF suffix."""
    parser = PolicyLinkParser()
    parser.feed(html)

    source_host = urlsplit(source_url).hostname
    urls: list[str] = []
    seen: set[str] = set()

    for href in parser.hrefs:
        absolute_url = urljoin(source_url, href)
        parsed = urlsplit(absolute_url)
        if parsed.hostname != source_host or not POLICY_PATH.fullmatch(parsed.path):
            continue

        # Keep the suffix used by the existing sitemap so downstream crawlers
        # recognize UCOP's redirecting /doc/<id> endpoints as PDF documents.
        pdf_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, ".pdf", ""))
        if pdf_url not in seen:
            seen.add(pdf_url)
            urls.append(pdf_url)

    return urls


def extract_reported_total(html: str) -> int | None:
    """Return the result total advertised by the search page, when present."""
    match = RESULT_TOTAL.search(html)
    return int(match.group(1)) if match else None


def render_sitemap(urls: list[str]) -> str:
    """Render policy URLs as a sitemap document."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        lines.extend(("  <url>", f"    <loc>{escape(url, quote=False)}</loc>", "  </url>"))
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=SEARCH_URL, help="UCOP search results URL")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output sitemap (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--timeout", type=float, default=30, help="request timeout in seconds")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        html = fetch_search_results(args.source_url, args.timeout)
        urls = extract_policy_urls(html, args.source_url)
        if not urls:
            raise RuntimeError("no UCOP policy links found; the search page may have changed")

        reported_total = extract_reported_total(html)
        if reported_total is not None and len(urls) != reported_total:
            raise RuntimeError(
                f"found {len(urls)} policy links, but UCOP reports {reported_total} results"
            )

        args.output.write_text(render_sitemap(urls), encoding="utf-8")
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Wrote {len(urls)} policy URLs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
