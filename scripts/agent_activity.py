#!/usr/bin/env python3
"""Summarize public GitHub contribution activity using explicit agent signals."""

import argparse
import json
import os
import re
import sys
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_REPOSITORY = "RuifengFu/agent-haven"
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
AGENT_TITLE = re.compile(r"^\[(agent|ai agent|bot|codex|claude|copilot)\]", re.IGNORECASE)
PAGE_SIZE = 100


def get_items(repository, endpoint, token=None, **filters):
    """Yield every item from one read-only GitHub API collection."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "agent-haven-activity"}
    page = 1
    while True:
        params = urlencode({**filters, "per_page": PAGE_SIZE, "page": page})
        request = Request(
            f"https://api.github.com/repos/{repository}/{endpoint}?{params}",
            headers=headers,
        )
        if token:
            request.add_unredirected_header("Authorization", "Bearer " + token)
        with urlopen(request, timeout=15) as response:
            items = json.load(response)
        if not isinstance(items, list):
            raise ValueError(f"GitHub did not return a list for {endpoint}")
        yield from items
        if len(items) < PAGE_SIZE:
            return
        page += 1


def has_agent_signal(item):
    user = item.get("user") or {}
    return (
        user.get("type") == "Bot"
        or user.get("login", "").lower().endswith("[bot]")
        or bool(AGENT_TITLE.match(item.get("title") or ""))
    )


def summarize(repository, token=None):
    counts = {
        kind: {"agent_or_bot": 0, "other": 0}
        for kind in ("issues", "pull_requests", "comments")
    }

    def count(kind, item):
        category = "agent_or_bot" if has_agent_signal(item) else "other"
        counts[kind][category] += 1

    # GitHub's issues collection includes PRs. Count each item once.
    for item in get_items(repository, "issues", token, state="all"):
        count("pull_requests" if "pull_request" in item else "issues", item)

    # Conversation comments and inline pull request review comments use
    # disjoint endpoints.
    for endpoint in ("issues/comments", "pulls/comments"):
        for item in get_items(repository, endpoint, token):
            count("comments", item)

    return {"repository": repository, **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY),
        help="repository in OWNER/NAME format",
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args()
    if not REPOSITORY.fullmatch(args.repository):
        parser.error("--repository must be in OWNER/NAME format")

    try:
        report = summarize(args.repository, os.environ.get("GITHUB_TOKEN"))
    except (URLError, TimeoutError, ValueError) as error:
        print(f"Could not retrieve GitHub activity: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Contribution activity for {report['repository']}")
        for key, label in (("issues", "Issues"), ("pull_requests", "Pull requests"), ("comments", "Comments")):
            counts = report[key]
            print(f"{label}: {counts['agent_or_bot']} with agent/bot signals, {counts['other']} other")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
