"""검수 전후 원래 저장 상태·실제 프로세스 경로·후보 해시를 수집합니다."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import winreg
from common import ROOT, WORK, DATA_NAME, sha, write_json


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def file_state(path):
    path = Path(path)
    if not path.exists():
        return {"exists": False, "files": []}
    if path.is_file():
        return {"exists": True, "files": [{"name": path.name, "size": path.stat().st_size, "sha256": sha(path)}]}
    return {"exists": True, "files": [{"name": p.relative_to(path).as_posix(), "size": p.stat().st_size, "sha256": sha(p)}
                                      for p in sorted(path.rglob("*")) if p.is_file()]}


def registry_state(path):
    values = {}
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        return {"exists": False}
    with key:
        index = 0
        while True:
            try:
                name, value, kind = winreg.EnumValue(key, index)
            except OSError:
                break
            raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
            values[name] = {"type": kind, "sha256": hashlib.sha256(raw).hexdigest()}
            index += 1
        children = {}
        index = 0
        while True:
            try:
                name = winreg.EnumKey(key, index)
            except OSError:
                break
            children[name] = registry_state(path + "\\" + name)
            index += 1
    return {"exists": True, "values": values, "children": children}


def snapshot(output, name):
    output = Path(output).resolve()
    output.relative_to(WORK.resolve())
    save = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/Leaping Turtle/KingdomInc"
    steam_root = Path(r"D:\steam")
    steam = {}
    userdata = steam_root / "userdata"
    if userdata.exists():
        for account in userdata.iterdir():
            if account.is_dir():
                steam[account.name] = file_state(account / "4702410")
    state = {"files": file_state(save), "registry": registry_state(r"Software\Leaping Turtle\KingdomInc"),
             "steam": steam, "appmanifest": file_state(steam_root / "steamapps/appmanifest_4702410.acf")}
    write_json(output / (name + ".json"), {"utc": utc(), "state": state})
    return state


def launch(output):
    output = Path(output).resolve()
    output.relative_to(WORK.resolve())
    prep = json.loads((output / "preparation.json").read_text(encoding="utf-8"))
    game = Path(prep["game"]).resolve()
    game.relative_to(WORK.resolve())
    manifest = json.loads((output / "prepared-manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        assert sha(game / name) == expected["sha256"], name
    snapshot(output, "user-before")
    config = json.loads((game / "korean-qa.json").read_text(encoding="utf-8"))
    command = [str(game / "KingdomInc.exe"), "-screen-fullscreen", "0", "-screen-width", str(config["width"]),
               "-screen-height", str(config["height"]), "-logFile", str(output / "Player.log")]
    # 실행 때 포커스를 요구하지 않도록 요청합니다. 실행 후 창 위치·입력은 조작하지 않습니다.
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 4
    process = subprocess.Popen(command, cwd=game, startupinfo=startup)
    write_json(output / "launch.json", {"utc": utc(), "pid": process.pid, "requested_executable": str(game / "KingdomInc.exe"),
                                      "command": command, "prepared_manifest_sha256": sha(output / "prepared-manifest.json")})
    print(json.dumps({"pid": process.pid, "output": str(output)}, ensure_ascii=False))


def command(output, action, value):
    output = Path(output).resolve()
    output.relative_to(WORK.resolve())
    ident = datetime.datetime.now().strftime("%H%M%S_%f") + "_" + action
    data = {"id": ident, "action": action, "value": value, "capture": action not in ["quit", "unlock", "unlock_all"]}
    temp = output / "command.tmp"
    write_json(temp, data)
    temp.replace(output / "command.json")
    print(ident)


def finish(output):
    output = Path(output).resolve()
    output.relative_to(WORK.resolve())
    after = snapshot(output, "user-after")
    before = json.loads((output / "user-before.json").read_text(encoding="utf-8"))["state"]
    prep = json.loads((output / "preparation.json").read_text(encoding="utf-8"))
    runtime = json.loads((output / "runtime.json").read_text(encoding="utf-8"))
    launch_data = json.loads((output / "launch.json").read_text(encoding="utf-8"))
    expected_exe = Path(prep["game"]) / "KingdomInc.exe"
    issues = []
    if before != after:
        issues.append("원래 사용자 저장·설정·Steam 상태 변경")
    if Path(runtime["executable"]).resolve() != expected_exe.resolve() or runtime["pid"] != launch_data["pid"]:
        issues.append("실행 경로·프로세스 번호 불일치")
    if runtime["company"] != prep["company"] or runtime["product"] != prep["product"]:
        issues.append("검수 회사·제품 경계 불일치")
    expected_save = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow" / prep["company"] / prep["product"]
    if Path(runtime["persistentDataPath"]).resolve() != expected_save.resolve():
        issues.append("검수 저장 경로 불일치")
    config = json.loads((Path(prep["game"]) / "korean-qa.json").read_text(encoding="utf-8"))
    if runtime["steamInitialized"] or runtime["fullScreen"] or runtime["width"] > config["width"] or runtime["height"] > config["height"]:
        issues.append("Steam·창 크기·전체화면 조건 불일치")
    if runtime.get("monitorWidth", 0) and runtime["width"] > runtime["monitorWidth"] / 2 - 16:
        issues.append("화면 절반 너비 제한 초과")
    if runtime.get("windowX", -1) < 0 or runtime.get("windowY", -1) < 0:
        issues.append("검수 창 위치 확인 실패")
    if not runtime["graphicsDevice"] or "null" in runtime["graphicsDevice"].lower():
        issues.append("실제 그래픽 장치 확인 실패")
    manifest = json.loads((output / "prepared-manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        if sha(Path(prep["game"]) / name) != expected["sha256"]:
            issues.append("실행 사본 변경: " + name)
    logs = [json.loads(line) for line in (output / "messages.jsonl").read_text(encoding="utf-8").splitlines()] if (output / "messages.jsonl").exists() else []
    glyph = [x for x in logs if "unicode" in x["message"].lower() and ("not found" in x["message"].lower() or "missing" in x["message"].lower())]
    font_warnings = [x for x in logs if x["type"] == "Warning" and any(fragment in x["message"].lower()
                    for fragment in ["unable to add the requested character", "missing glyph", "please make the texture"])]
    exceptions = [x for x in logs if x["type"] in ["Exception", "Error", "Assert"]]
    if glyph:
        issues.append("글리프 누락 경고")
    if font_warnings:
        issues.append("글꼴 문자 생성·이미지 읽기 경고")
    if exceptions:
        issues.append("오류 로그가 있어 원본과 비교 검토 필요")
    results = [json.loads(p.read_text(encoding="utf-8")) for p in output.glob("*.result.json")]
    failures = [r for r in results if r["status"] == "FAIL"]
    if failures:
        issues.append("검수 화면 진입 명령 실패")
    for result in results:
        if result["status"] == "CAPTURED" and result["action"] not in ["quit", "unlock", "unlock_all"]:
            if not (output / (result["id"] + ".png")).is_file():
                issues.append("화면 이미지 미생성: " + result["id"])
    report = {"status": "PASS" if not issues else "FAIL", "utc": utc(), "issues": issues,
              "user_unchanged": before == after, "glyph_warnings": len(glyph), "font_warnings": len(font_warnings), "errors": len(exceptions),
              "captures": len(list(output.glob("*.png"))), "command_failures": failures,
              "error_log_review": "NOT_RUN" if exceptions else "NOT_APPLICABLE",
              "visual_review": "NOT_RUN", "note": "화면 캡처와 경로·저장 검사 결과이며 육안 검수·전체 플레이 통과를 뜻하지 않습니다."}
    write_json(output / "session-check.json", report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["launch", "command", "finish", "snapshot"])
    parser.add_argument("--output", required=True)
    parser.add_argument("--action")
    parser.add_argument("--value", default="")
    parser.add_argument("--name", default="user-check")
    args = parser.parse_args()
    if args.operation == "launch":
        launch(args.output)
    elif args.operation == "command":
        command(args.output, args.action, args.value)
    elif args.operation == "finish":
        finish(args.output)
    else:
        snapshot(args.output, args.name)
