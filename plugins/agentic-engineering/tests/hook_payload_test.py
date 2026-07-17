"""Tests for scripts/hook_payload.py harness normalization."""
from __future__ import annotations

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "hook_payload.py"
spec = importlib.util.spec_from_file_location("hook_payload", SCRIPT)
assert spec and spec.loader
hook_payload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook_payload)
normalize = hook_payload.normalize
emit_allow = hook_payload.emit_allow


class HookPayloadTest(unittest.TestCase):
    def test_claude_bash_passthrough(self):
        data = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
        self.assertEqual(normalize(data)["tool_name"], "Bash")
        self.assertEqual(normalize(data)["tool_input"]["command"], "echo hi")

    def test_cursor_shell_alias(self):
        data = {"tool_name": "Shell", "tool_input": {"command": "git status"}}
        out = normalize(data)
        self.assertEqual(out["tool_name"], "Bash")
        self.assertEqual(out["tool_input"]["command"], "git status")

    def test_cursor_before_shell_execution(self):
        out = normalize({"command": "git commit --no-verify"})
        self.assertEqual(out["tool_name"], "Bash")
        self.assertEqual(out["tool_input"]["command"], "git commit --no-verify")

    def test_write_passthrough(self):
        data = {"tool_name": "Write", "tool_input": {"file_path": "a.ts", "content": "x"}}
        out = normalize(data)
        self.assertEqual(out["tool_name"], "Write")
        self.assertEqual(out["tool_input"]["content"], "x")

    def test_codex_apply_patch_keeps_canonical_shape(self):
        patch = "*** Begin Patch\n*** Add File: a.ts\n+x\n*** End Patch"
        out = normalize({"tool_name": "apply_patch", "tool_input": {"command": patch}})
        self.assertEqual(out["tool_name"], "apply_patch")
        self.assertEqual(out["tool_input"]["command"], patch)


class EmitAllowTest(unittest.TestCase):
    """emit_allow() must print Cursor's allow decision and exit 0.

    Cursor `failClosed: true` hooks treat empty stdout as a failure and block,
    so the allow path must emit `{"permission": "allow"}`. exit 0 keeps Claude
    Code / Codex (exit-code contract) allowing the call.
    """

    def _capture(self) -> str:
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm, redirect_stdout(buf):
            emit_allow()
        self.assertEqual(cm.exception.code, 0)
        return buf.getvalue()

    def test_exits_zero(self):
        self._capture()  # asserts SystemExit(0) internally

    def test_stdout_is_cursor_allow_json(self):
        self.assertEqual(json.loads(self._capture()), {"permission": "allow"})


if __name__ == "__main__":
    unittest.main()
