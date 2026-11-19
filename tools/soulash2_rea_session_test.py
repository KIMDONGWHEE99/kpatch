"""REA를 실행하지 않고 입력 수정·세션 보존·중단 뒤 복구 조건을 검증한다."""
import contextlib
import io
import json
import unittest
from pathlib import Path

from soulash2_rea_session import ReaSession, compact_error, input_contract_error


def response(value, failed=False):
    return {"result": {"isError": failed, "content": [{"type": "text", "text": json.dumps(value)}]}}


def failure(code="invalid_request", **extra):
    return response({"error": {"code": code, "message": "합성 오류", **extra}}, True)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.session = ReaSession.__new__(ReaSession)
        self.session.started = "synthetic_test"
        self.session.sequence = 0
        self.session.pause_token = None
        self.session.cleanup_confirmed = False
        self.session.discarded_commands = 0
        self.session.invalid_requests = {}
        self.calls, self.saved, self.responses = [], {}, {}
        self.captured = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.captured)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        self.session.call = self.call
        self.session.save = self.save

    def call(self, method, params):
        name = params.get("name", method)
        self.calls.append(name)
        self.session.sequence += 1
        if self.responses.get(name):
            value = self.responses[name].pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        if name == "tools/list":
            return {"result": {"tools": [{"name": "read_bytes", "description": "바이트 읽기", "inputSchema": {
                "type": "object", "properties": {"address": {"type": "string"}, "length": {"type": "integer"}},
                "required": ["address"], "additionalProperties": False}}]}}
        if name == "binary_session":
            return response({"result": {"open": False, "cleanup_pending": False}})
        return response({})

    def save(self, filename, value):
        self.saved[filename] = value
        return Path(filename)

    def command(self, tool="read_bytes", arguments=None):
        self.session.command({"tool": tool, "arguments": arguments or {}, "output": f"synthetic_{len(self.saved):05}.json"})

    def last(self):
        return json.loads(self.captured.getvalue().splitlines()[-1])

    def test_input_error_refreshes_only_catalog(self):
        self.responses["read_bytes"] = [failure(category="invalid_input")]
        self.command(arguments={"address": "0x140001000", "size": 6})
        self.assertIsNone(self.session.pause_token)
        self.assertEqual(self.calls, ["read_bytes", "tools/list"])
        self.assertEqual(self.last()["input_contract_refresh"]["input_fields"], ["address", "length"])
        self.assertFalse(self.last()["session_close_required"])
        self.assertTrue(any(name.startswith("input_contract_") for name in self.saved))

    def test_unchanged_input_rejected_and_corrected_input_retried(self):
        self.responses["read_bytes"] = [failure()]
        self.command(arguments={"address": "0x140001000", "size": 6})
        self.command(arguments={"size": 6, "address": "0x140001000"})
        self.assertEqual(self.calls, ["read_bytes", "tools/list"])
        self.assertTrue(self.last()["rejected"])
        self.command(arguments={"address": "0x140001000", "length": 6})
        self.assertEqual(self.calls, ["read_bytes", "tools/list", "read_bytes"])
        self.assertIsNone(self.session.pause_token)
        self.assertNotIn("read_bytes", self.session.invalid_requests)

    def test_jsonrpc_invalid_params_preserves_session(self):
        self.responses["read_bytes"] = [{"error": {"code": -32602, "message": "invalid parameters"}}]
        self.command()
        self.assertIsNone(self.session.pause_token)
        self.assertEqual(self.calls[-1], "tools/list")

    def test_invalid_input_code_preserves_session(self):
        self.responses["read_bytes"] = [failure("invalid_input")]
        self.command()
        self.assertIsNone(self.session.pause_token)

    def test_timeout_requires_cleanup_and_matching_token(self):
        self.responses["xrefs"] = [failure("provider_timeout")]
        self.command("xrefs")
        token = self.session.pause_token
        self.assertTrue(token)
        self.command("procedure_pseudo_code")
        self.assertEqual(self.calls, ["xrefs"])
        self.assertEqual(self.session.discarded_commands, 1)
        self.session.command({"resume": token})
        self.assertEqual(self.session.pause_token, token)
        self.command("close_binary")
        self.command("binary_session")
        self.assertTrue(self.session.cleanup_confirmed)
        self.session.command({"resume": "wrong-token"})
        self.assertEqual(self.session.pause_token, token)
        self.session.command({"resume": token})
        self.assertIsNone(self.session.pause_token)

    def test_pending_cleanup_does_not_allow_resume(self):
        self.responses["xrefs"] = [failure("provider_timeout")]
        self.responses["binary_session"] = [response({"result": {"open": False, "cleanup_pending": True}})]
        self.command("xrefs")
        token = self.session.pause_token
        self.command("close_binary")
        self.command("binary_session")
        self.session.command({"resume": token})
        self.assertFalse(self.session.cleanup_confirmed)
        self.assertEqual(self.session.pause_token, token)

    def test_interruption_remains_strict(self):
        for code in ["operation_cancelled", "provider_interrupted", "cleanup_incomplete"]:
            with self.subTest(code=code):
                self.session.pause_token = None
                self.responses["read_bytes"] = [failure(code)]
                self.command()
                self.assertTrue(self.session.pause_token)

    def test_transport_failure_pauses(self):
        self.responses["read_bytes"] = [RuntimeError("process EOF")]
        with self.assertRaisesRegex(RuntimeError, "process EOF"):
            self.command()
        self.assertTrue(self.session.pause_token)
        self.assertEqual(self.last()["recovery"], "transport_failure")

    def test_input_error_does_not_clear_existing_provider_pause(self):
        self.session.pause_token = "existing-token"
        self.responses["inspect_analysis_settings"] = [failure()]
        self.command("inspect_analysis_settings")
        self.assertEqual(self.session.pause_token, "existing-token")
        self.assertTrue(self.last()["session_close_required"])
        self.assertFalse(self.session.cleanup_confirmed)

    def test_cleanup_details_override_input_error(self):
        self.responses["read_bytes"] = [failure(details={"cleanup_pending": True})]
        self.command()
        self.assertTrue(self.session.pause_token)
        self.assertEqual(self.calls, ["read_bytes"])

    def test_unknown_error_and_untyped_iserror_remain_strict(self):
        for value in [failure("unexpected_failure"), response({"message": "unknown"}, True)]:
            self.session.pause_token = None
            self.responses["read_bytes"] = [value]
            self.command()
            self.assertTrue(self.session.pause_token)

    def test_catalog_failure_pauses(self):
        self.responses["read_bytes"] = [failure()]
        self.responses["tools/list"] = [{"error": {"code": -32603, "message": "internal error"}}]
        self.command()
        self.assertTrue(self.session.pause_token)
        self.assertTrue(self.last()["session_close_required"])
        self.assertIn("catalog_refresh_error", self.last())

    def test_nonjson_text_before_error_is_ignored(self):
        value = failure()
        value["result"]["content"].insert(0, {"type": "text", "text": "progress notice"})
        self.responses["read_bytes"] = [value]
        self.command()
        self.assertIsNone(self.session.pause_token)
        self.assertEqual(self.last()["recovery"], "correct_input_contract")

    def test_tools_list_input_error_does_not_recurse(self):
        self.responses["tools/list"] = [failure()]
        self.command("tools/list", {"invalid": True})
        self.assertEqual(self.calls, ["tools/list"])
        self.assertIsNone(self.session.pause_token)

    def test_malformed_error_code_does_not_crash(self):
        self.assertFalse(input_contract_error({"code": {"unexpected": True}}))
        self.assertFalse(input_contract_error("unexpected"))

    def test_error_summary_omits_large_details(self):
        summary = compact_error({"code": "provider_timeout", "message": "실패", "remediation": {"action": "정리"}, "details": {"large": "x" * 100000}})
        self.assertEqual(set(summary), {"code", "message", "remediation"})
        self.assertLess(len(json.dumps(summary)), 300)


if __name__ == "__main__":
    unittest.main(verbosity=2)
