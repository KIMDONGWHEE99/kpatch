"""현재 프로세스에만 Ghidra/JDK 경로를 지정해 REA 공개 실행기를 호출한다."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = ROOT / "working_private/SOULASH_2/toolchain"
NODE = Path(r"C:\Program Files\nodejs\node.exe")
REA = Path(r"C:\Users\PC\AppData\Local\npm-cache\_npx\da7caeae9db9c589\node_modules\rea-agents\scripts\rea.mjs")

def main():
    manifest = json.loads((TOOLCHAIN / "toolchain_manifest.json").read_text(encoding="utf-8"))
    by_role = {entry["role"]: entry for entry in manifest}
    environment = os.environ.copy()
    environment["GHIDRA_INSTALL_DIR"] = by_role["ghidra"]["root"]
    environment["JAVA_HOME"] = by_role["jdk"]["root"]
    environment["PATH"] = str(Path(by_role["jdk"]["root"]) / "bin") + os.pathsep + environment.get("PATH", "")
    temporary = ROOT / "working_private/SOULASH_2/rea/temp"
    temporary.mkdir(parents=True, exist_ok=True)
    environment["TEMP"] = str(temporary)
    environment["TMP"] = str(temporary)
    result = subprocess.run([str(NODE), str(REA), *sys.argv[1:]], env=environment, cwd=ROOT)
    raise SystemExit(result.returncode)

if __name__ == "__main__":
    main()
