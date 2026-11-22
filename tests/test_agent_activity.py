import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from scripts import agent_activity


def response(items):
    return io.BytesIO(json.dumps(items).encode("utf-8"))


class AgentActivityTests(unittest.TestCase):
    def test_paginates_with_a_read_only_authenticated_request(self):
        first_page = [{"id": number} for number in range(100)]
        last_page = [{"id": 100}]
        with patch.object(
            agent_activity, "urlopen", side_effect=[response(first_page), response(last_page)]
        ) as urlopen:
            items = list(agent_activity.get_items("owner/repo", "issues", "token", state="all"))

        self.assertEqual(items, first_page + last_page)
        for page, call in enumerate(urlopen.call_args_list, 1):
            request = call.args[0]
            url = urlsplit(request.full_url)
            self.assertEqual(request.get_method(), "GET")
            self.assertNotIn("Authorization", request.headers)
            self.assertEqual(request.unredirected_hdrs["Authorization"], "Bearer token")
            self.assertEqual(url.netloc, "api.github.com")
            self.assertEqual(url.path, "/repos/owner/repo/issues")
            self.assertEqual(
                parse_qs(url.query), {"state": ["all"], "per_page": ["100"], "page": [str(page)]}
            )

    def test_counts_all_contribution_types_without_treating_subject_as_authorship(self):
        issues = [
            {"title": "Add an agent activity tracker", "user": {"type": "User"}},
            {"title": "[agent] Report a missing document", "user": {"type": "User"}},
            {"title": "[Codex] Fix double-counting", "pull_request": {}},
            {"title": "Fix report headings", "pull_request": {}},
        ]
        thread_comments = [
            {"user": {"login": "github-actions[bot]"}},
            {"body": "Can the agent check this?", "user": {"type": "User"}},
        ]
        review_comments = [{"user": {"type": "Bot"}}, {"user": None}]
        with patch.object(
            agent_activity,
            "urlopen",
            side_effect=[response(issues), response(thread_comments), response(review_comments)],
        ) as urlopen:
            report = agent_activity.summarize("owner/repo")

        self.assertEqual(report, {
            "repository": "owner/repo",
            "issues": {"agent_or_bot": 1, "other": 1},
            "pull_requests": {"agent_or_bot": 1, "other": 1},
            "comments": {"agent_or_bot": 2, "other": 2},
        })
        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(
            [urlsplit(request.full_url).path for request in requests],
            [
                "/repos/owner/repo/issues",
                "/repos/owner/repo/issues/comments",
                "/repos/owner/repo/pulls/comments",
            ],
        )
        for request in requests:
            self.assertIsNone(request.get_header("Authorization"))

    def test_refuses_to_treat_an_unexpected_response_as_zero_activity(self):
        with patch.object(agent_activity, "urlopen", return_value=response({"message": "unexpected"})):
            with self.assertRaisesRegex(ValueError, "GitHub did not return a list for issues"):
                list(agent_activity.get_items("owner/repo", "issues"))


if __name__ == "__main__":
    unittest.main()
