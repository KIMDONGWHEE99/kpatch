"""지정한 번역 원본 전체에서 글자를 계산하고 최종 글꼴의 실제 문자표와 대조한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python_deps"))
from fontTools.ttLib import TTFont


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    extra = ROOT / "working_private/SOULASH_2/font_probe/soulash_qa/required_visible_and_credits.json"
    required = set(json.loads(extra.read_text(encoding="utf-8"))["codepoints"])
    inputs = [{"path": extra.relative_to(ROOT).as_posix(), "sha256": sha(extra), "kind": "기존 표시·크레딧"}]
    rows, locations = 0, set()
    for path in args.batch:
        p = path.resolve()
        digest = sha(p)
        count = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not isinstance(row.get("target"), str):
                raise ValueError("번역이 없는 입력")
            required.update(ord(c) for c in row["target"] if c not in "\r\n\t")
            rows += 1
            count += 1
            locations.add(row["location_id"])
        if sha(p) != digest:
            raise ValueError("읽는 도중 입력 변경")
        inputs.append({"path": p.relative_to(ROOT).as_posix(), "sha256": digest, "rows": count})
    requested = {"codepoints": sorted(required), "count": len(required), "inputs": inputs, "completeness": "지정한 번역묶음 전부 및 기존 표시·크레딧 문자. 미해결 보류 번역은 재검사 필요"}
    (args.output / "required_codepoints.json").write_text(json.dumps(requested, ensure_ascii=False, indent=2), encoding="utf-8")
    fonts = []
    root = ROOT / "working_private/SOULASH_2/font_probe/release_20261030_v1/fonts"
    for p in sorted(root.glob("*.ttf")):
        with TTFont(p) as font:
            cmap = font.getBestCmap()
            missing = sorted(required - set(cmap))
            empty = [cp for cp in required if cp in cmap and 0xac00 <= cp <= 0xd7a3 and not font["glyf"][cmap[cp]].numberOfContours]
            fonts.append({"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p), "missing": missing, "empty_hangul": empty,
                          "modern_hangul_count": sum(cp in cmap for cp in range(0xac00, 0xd7a4)), "status": "FAIL" if missing or empty else "PASS"})
    result = {"created_utc": datetime.now(timezone.utc).isoformat(), "status": "PASS" if all(f["status"] == "PASS" for f in fonts) else "FAIL", "rows": rows, "unique_locations": len(locations),
              "required_codepoints": len(required), "fonts": fonts, "inputs": inputs, "tool_sha256": sha(__file__), "atlas": "NOT_RUN", "runtime_qa": "NOT_RUN"}
    (args.output / "coverage_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "inputs"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
