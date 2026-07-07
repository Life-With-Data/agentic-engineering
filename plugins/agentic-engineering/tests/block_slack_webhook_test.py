"""Regression tests for ``scripts/block-slack-webhook.py``.

This PreToolUse hook blocks a Slack *incoming webhook* URL
(``hooks.slack.com/services/...``) from being hardcoded into code, config, or a
Bash command — such a URL is a live credential, and inlining it leaks a secret
into git history / CI. Like the other guards here it must be precise: fire on a
real introduction of the URL, but stay quiet when a doc merely *describes* the
anti-pattern.

Contract: exit code 2 blocks the tool call; exit code 0 allows it.

Run with: ``python3 -m unittest tests.block_slack_webhook_test``.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "block-slack-webhook.py"

BLOCK = 2
ALLOW = 0

# Assembled from fragments so this test file never carries the contiguous
# ``hooks.slack.com/services/...`` literal — otherwise secret scanners (and the
# hook under test, if it ever ran on this file) would flag the source itself.
# The hook receives the fully-joined string at runtime, which is what matters.
_HOST = "hooks.slack" + ".com"
_PATH = "/" + "services" + "/T00000000/B00000000/" + ("X" * 24)
WEBHOOK = "https://" + _HOST + _PATH


def _run(tool_name: str, tool_input: dict) -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": tool_name, "tool_input": tool_input}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


def _bash(command: str):
    return _run("Bash", {"command": command})


def _write(file_path: str, content: str):
    return _run("Write", {"file_path": file_path, "content": content})


def _edit(file_path: str, new_string: str):
    return _run("Edit", {"file_path": file_path, "new_string": new_string})


class BlockSlackWebhookTest(unittest.TestCase):
    # --- true introductions: MUST block ----------------------------------

    def test_blocks_curl_to_webhook(self) -> None:
        self.assertEqual(_bash(f"curl -X POST {WEBHOOK} -d '{{}}'").returncode, BLOCK)

    def test_blocks_write_of_webhook_into_code(self) -> None:
        result = _write("apps/web/notify.ts", f'const url = "{WEBHOOK}";')
        self.assertEqual(result.returncode, BLOCK)

    def test_blocks_edit_adding_webhook(self) -> None:
        self.assertEqual(_edit("config/alerts.yaml", f"webhook: {WEBHOOK}").returncode, BLOCK)

    def test_blocks_multiedit_adding_webhook(self) -> None:
        result = _run(
            "MultiEdit",
            {
                "file_path": "src/notify.py",
                "edits": [
                    {"old_string": "a", "new_string": "b"},
                    {"old_string": "c", "new_string": f'URL = "{WEBHOOK}"'},
                ],
            },
        )
        self.assertEqual(result.returncode, BLOCK)

    def test_block_message_is_actionable(self) -> None:
        result = _bash(f"curl {WEBHOOK}")
        self.assertEqual(result.returncode, BLOCK)
        self.assertIn("BLOCKED", result.stderr)

    # --- prose / self-reference: MUST allow ------------------------------

    def test_allows_webhook_mention_in_markdown(self) -> None:
        result = _write("docs/notifications.md", f"Do not hardcode {WEBHOOK} — use a secret.")
        self.assertEqual(result.returncode, ALLOW)

    def test_allows_reference_in_hook_script(self) -> None:
        # The guard's own tooling references the pattern by design.
        result = _write(
            "plugins/agentic-engineering/scripts/block-slack-webhook.py",
            f"# matches {WEBHOOK}",
        )
        self.assertEqual(result.returncode, ALLOW)

    # --- unrelated Slack usage: MUST allow (no false positives) ----------

    def test_allows_slack_app_api(self) -> None:
        # The Slack *app* (api.slack.com / chat.postMessage) is the correct path.
        result = _bash("curl -X POST https://slack.com/api/chat.postMessage -H 'Authorization: Bearer xoxb-...'")
        self.assertEqual(result.returncode, ALLOW)

    def test_allows_unrelated_command(self) -> None:
        self.assertEqual(_bash("git status && npm test").returncode, ALLOW)


if __name__ == "__main__":
    unittest.main()
