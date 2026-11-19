"""REA의 공개 MCP 실행기와 한 번 연결하여 여러 읽기 전용 분석을 이어 간다.

입력은 한 줄에 JSON 한 개다. 응답 원문은 지정된 비공개 폴더에만 저장한다.
예: {"tool":"binary_session","arguments":{},"output":"session.json"}
종료: {"shutdown":true}
"""
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from soulash2_rea import ROOT, TOOLCHAIN, NODE, REA

OUTPUT = ROOT / "working_private/SOULASH_2/rea/responses"
TEMPORARY = ROOT / "working_private/SOULASH_2/rea/temp"


def emit(value, stream=None):
    print(json.dumps(value, ensure_ascii=True), file=stream or sys.stdout, flush=True)


def compact_error(error):
    if not isinstance(error, dict):
        return None if error is None else {"message": str(error)[:1200]}
    result = {key: error[key] for key in ("code", "message", "remediation") if key in error}
    if isinstance(result.get("message"), str):
        result["message"] = result["message"][:1200]
    remediation = result.get("remediation")
    if isinstance(remediation, dict):
        result["remediation"] = {"action": str(remediation.get("action", ""))[:1600]}
    return result


def structured_result(response):
    result = response.get("result", {})
    structured = result.get("structuredContent")
    if structured is None:
        for content in result.get("content", []):
            if content.get("type") == "text":
                try:
                    structured = json.loads(content["text"])
                except (ValueError, TypeError):
                    continue
                break
    return structured


def response_errors(response, structured=None):
    errors = []
    if response.get("error"):
        errors.append(response["error"])
    if isinstance(structured, dict) and structured.get("error"):
        errors.append(structured["error"])
    return errors


def input_contract_error(error):
    """명시적인 입력 계약 오류만 세션 보존 대상으로 삼는다."""
    if not isinstance(error, dict) or not isinstance(error.get("code"), (str, int)) or error.get("code") not in {"invalid_request", "invalid_input", -32600, -32602}:
        return False

    def retained_cleanup(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"cleanup_pending", "cleanup_incomplete", "cleanup_owners", "retained_cleanup_owners"} and child:
                    return True
                if key == "code" and isinstance(child, str) and child in {"cleanup_incomplete", "provider_timeout", "operation_cancelled", "provider_interrupted"}:
                    return True
                if retained_cleanup(child):
                    return True
        elif isinstance(value, list):
            return any(retained_cleanup(child) for child in value)
        return False

    return not retained_cleanup(error)


def request_fingerprint(arguments):
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class ReaSession:
    def __init__(self):
        manifest = json.loads((TOOLCHAIN / "toolchain_manifest.json").read_text(encoding="utf-8"))
        by_role = {entry["role"]: entry for entry in manifest}
        environment = os.environ.copy()
        environment["GHIDRA_INSTALL_DIR"] = by_role["ghidra"]["root"]
        environment["JAVA_HOME"] = by_role["jdk"]["root"]
        # 첫 실패가 반환한 REA 권고에 따라 새 분석의 시작 제한을 30분으로 늘린다.
        environment["REA_GHIDRA_STARTUP_TIMEOUT_MS"] = "1800000"
        environment["PATH"] = str(Path(by_role["jdk"]["root"]) / "bin") + os.pathsep + environment.get("PATH", "")
        TEMPORARY.mkdir(parents=True, exist_ok=True)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        environment["TEMP"] = str(TEMPORARY)
        environment["TMP"] = str(TEMPORARY)
        self.started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        self.messages = queue.Queue()
        self.sequence = 0
        self.pause_token = None
        self.cleanup_confirmed = False
        self.discarded_commands = 0
        self.invalid_requests = {}
        self.process = subprocess.Popen(
            [str(NODE), str(REA), "--mcp"], cwd=ROOT, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        threading.Thread(target=self.read_stdout, daemon=True).start()
        threading.Thread(target=self.read_stderr, daemon=True).start()

    def read_stdout(self):
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                self.messages.put({"protocol_error": "MCP 출력의 JSON 해석 실패", "preview": line[:200]})
        self.messages.put({"process_eof": True})

    def read_stderr(self):
        log = OUTPUT / ("server_" + self.started + ".log")
        with log.open("x", encoding="utf-8") as stream:
            for line in self.process.stderr:
                stream.write(line)
                stream.flush()
                emit({"server_stderr": line.rstrip()[:800]}, sys.stderr)

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=True) + "\n")
        self.process.stdin.flush()

    def call(self, method, parameters):
        self.sequence += 1
        request_id = self.sequence
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": parameters})
        while True:
            message = self.messages.get()
            if message.get("process_eof"):
                raise RuntimeError(f"REA 프로세스가 종료되었습니다: {self.process.poll()}")
            if "protocol_error" in message:
                raise RuntimeError(message["protocol_error"] + ": " + message["preview"])
            if message.get("id") == request_id:
                return message
            if "method" in message and "id" in message:
                self.send({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "This client does not expose interactive methods."}})
                emit({"server_request_declined": message["method"]}, sys.stderr)
            else:
                emit({"notification": message.get("method"), "params": message.get("params")}, sys.stderr)

    def save(self, filename, message):
        if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json", filename):
            raise ValueError("output은 영문/숫자/밑줄/마침표/하이픈으로 된 JSON 파일명이어야 합니다.")
        path = OUTPUT / filename
        with path.open("x", encoding="utf-8") as stream:
            json.dump(message, stream, ensure_ascii=False, indent=2)
        return path

    def initialize(self):
        response = self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "soulash2-analysis", "version": "1.0.0"}})
        if "error" in response:
            raise RuntimeError(json.dumps(response["error"]))
        self.save("initialize_" + self.started + ".json", response)
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        catalog = self.call("tools/list", {})
        path = self.save("tools_" + self.started + ".json", catalog)
        emit({"ready": True, "pid": self.process.pid, "tools": len(catalog.get("result", {}).get("tools", [])), "catalog": str(path)})

    def pause(self):
        self.pause_token = secrets.token_hex(12)
        self.cleanup_confirmed = False
        return {"paused": True, "resume_token": self.pause_token,
                "next": "필요 증거 저장 → close_binary → binary_session의 open=false/cleanup_pending=false → {resume: 토큰}"}

    def refresh_input_contract(self, tool):
        catalog = self.call("tools/list", {})
        path = self.save(f"tools_refresh_{self.started}_{self.sequence:05}.json", catalog)
        if response_errors(catalog, structured_result(catalog)) or catalog.get("result", {}).get("isError"):
            raise RuntimeError("입력 명세를 갱신하지 못했습니다. 저장된 응답을 확인하세요: " + str(path))
        matches = [entry for entry in catalog.get("result", {}).get("tools", []) if entry.get("name") == tool]
        info = {"catalog": str(path), "tool_found": len(matches) == 1}
        if len(matches) == 1:
            contract = {key: matches[0][key] for key in ("name", "description", "inputSchema") if key in matches[0]}
            schema_path = self.save(f"input_contract_{self.started}_{self.sequence:05}.json", contract)
            schema = contract.get("inputSchema", {})
            info.update({"input_contract": str(schema_path), "input_fields": sorted(schema.get("properties", {})),
                         "required_fields": schema.get("required", [])})
        return info

    def command(self, command):
        if "resume" in command:
            if not self.pause_token or command["resume"] != self.pause_token:
                emit({"resumed": False, "reason": "현재 pause 토큰과 일치하지 않습니다."})
            elif not self.cleanup_confirmed:
                emit({"resumed": False, "reason": "close_binary 후 binary_session에서 open=false와 cleanup_pending=false 확인이 필요합니다."})
            else:
                self.pause_token = None
                emit({"resumed": True, "discarded_commands": self.discarded_commands})
            return
        tool = command["tool"]
        maintenance = {"binary_session", "close_binary", "export_evidence_bundle", "tools/list", "inspect_analysis_settings", "update_analysis_settings"}
        if self.pause_token and tool not in maintenance:
            self.discarded_commands += 1
            emit({"discarded": True, "tool": tool, "paused": True,
                  "reason": "직전 오류 후 대기열의 분석 명령을 실행하지 않습니다.", "resume_token": self.pause_token})
            return
        filename = command.get("output", f"response_{self.started}_{self.sequence + 1:05}.json")
        # 분석을 시작하기 전에 저장 경로를 검증한다.
        if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json", filename):
            raise ValueError("유효한 output JSON 파일명이 필요합니다.")
        if (OUTPUT / filename).exists():
            raise FileExistsError(f"기존 증거를 덮어쓰지 않습니다: {filename}")
        parameters = command.get("arguments", {})
        if self.invalid_requests.get(tool) == request_fingerprint(parameters):
            emit({"rejected": True, "tool": tool, "paused": bool(self.pause_token), "reason": "입력 오류로 거부된 요청과 같습니다. 현재 명세를 보고 필드를 수정한 뒤 다시 요청하세요."})
            return
        try:
            if tool == "tools/list":
                response = self.call("tools/list", parameters)
            else:
                response = self.call("tools/call", {"name": tool, "arguments": parameters})
        except Exception:
            # 응답 없이 통신이 끊긴 경우에는 작업 중단·자원 해제를 추정하지 않는다.
            emit({"tool": tool, "recovery": "transport_failure", **self.pause()})
            raise
        path = self.save(filename, response)
        result = response.get("result", {})
        summary = {"tool": tool, "output": str(path), "jsonrpc_error": compact_error(response.get("error")), "isError": result.get("isError", False), "result_keys": list(result)}
        structured = structured_result(response)
        if isinstance(structured, dict):
            summary["content_keys"] = list(structured)
            if "error" in structured:
                summary["tool_error"] = compact_error(structured["error"])
            if "evidence_id" in structured:
                summary["evidence_id"] = structured["evidence_id"]
        errors = response_errors(response, structured)
        failed = bool(errors or result.get("isError"))
        if failed:
            if errors and all(input_contract_error(error) for error in errors):
                self.invalid_requests[tool] = request_fingerprint(parameters)
                summary.update({"paused": bool(self.pause_token), "recovery": "correct_input_contract", "session_close_required": bool(self.pause_token),
                                "next": "해당 도구의 현재 입력 명세를 확인하고 잘못된 필드를 수정하여 재요청. 동일 요청은 차단합니다."})
                if tool != "tools/list":
                    try:
                        summary["input_contract_refresh"] = self.refresh_input_contract(tool)
                    except Exception as exc:
                        summary.update({"catalog_refresh_error": str(exc)[:1200], "session_close_required": True, **self.pause()})
            else:
                summary.update(self.pause())
        elif tool == "binary_session" and self.pause_token:
            state = structured.get("result", structured) if isinstance(structured, dict) else {}
            self.cleanup_confirmed = state.get("open") is False and state.get("cleanup_pending") is False
            summary["cleanup_confirmed"] = self.cleanup_confirmed
        elif not failed:
            self.invalid_requests.pop(tool, None)
        emit(summary)

    def close(self):
        if self.process.poll() is None:
            try:
                response = self.call("tools/call", {"name": "close_binary", "arguments": {}})
                self.save("close_" + self.started + ".json", response)
                emit({"closed": True})
            except Exception as exc:
                emit({"close_error": str(exc)}, sys.stderr)
            self.process.stdin.close()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=10)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    session = ReaSession()
    try:
        session.initialize()
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                command = json.loads(line)
                if command.get("shutdown"):
                    break
                session.command(command)
            except Exception as exc:
                emit({"command_error": type(exc).__name__, "message": str(exc)})
    finally:
        session.close()


if __name__ == "__main__":
    main()
