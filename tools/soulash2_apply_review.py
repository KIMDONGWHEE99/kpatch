"""기존 번역 묶음을 보존하면서 위치별 교정 내용을 새 묶음에 적용한다."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "working_private/SOULASH_2/translations"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    override_path, output = args.overrides.resolve(), args.output.resolve()
    if not override_path.is_relative_to(TRANSLATIONS) or not output.is_relative_to(TRANSLATIONS):
        raise ValueError("번역 전용 폴더 밖 경로")
    overrides = rows(override_path)
    override_sha = sha(override_path)
    grouped, identities = {}, set()
    for change in overrides:
        if change["location_id"] in identities:
            raise ValueError("중복 교정 위치")
        identities.add(change["location_id"])
        path = (ROOT / change["previous_batch"]).resolve()
        if not path.is_relative_to(TRANSLATIONS) or sha(path) != change["previous_batch_sha256"]:
            raise ValueError("기존 번역 경로 또는 지문 불일치")
        if not change.get("review_status", "").startswith("REVIEWED_"):
            raise ValueError("검토하지 않은 교정")
        grouped.setdefault(path, []).append(change)
    output.mkdir(parents=True, exist_ok=False)
    manifest = []
    for path, changes in grouped.items():
        original_sha = sha(path)
        batch = rows(path)
        by_id = {row["location_id"]: row for row in batch}
        if len(by_id) != len(batch):
            raise ValueError("중복 번역 위치")
        for change in changes:
            row = by_id[change["location_id"]]
            for key in ("file", "field_path", "source", "source_file_sha256", "source_value_sha256"):
                if row[key] != change[key]:
                    raise ValueError("교정 원문 식별 불일치: " + key)
            if row["target"] != change["previous_target"] or hashlib.sha256(row["target"].encode()).hexdigest() != change["previous_target_sha256"]:
                raise ValueError("교정 전 번역 불일치")
            row["target"] = change["target"]
            row["review_override"] = {"path": override_path.relative_to(ROOT).as_posix(), "sha256": override_sha,
                                      "reason": change["reason"], "review_status": change["review_status"]}
        target = output / path.name
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            for row in batch:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        actual = rows(target)
        original = rows(path)
        allowed = {change["location_id"]: change for change in changes}
        if len(actual) != len(original):
            raise ValueError("재읽기 행 개수 불일치")
        for before, after in zip(original, actual):
            change = allowed.get(before["location_id"])
            if change is None:
                if before != after:
                    raise ValueError("허용하지 않은 위치 변경")
            else:
                if after["target"] != change["target"]:
                    raise ValueError("교정 재읽기 불일치")
                check = dict(after)
                check.pop("review_override")
                check["target"] = before["target"]
                if check != before:
                    raise ValueError("번역 외 필드 변경")
        if sha(path) != original_sha:
            raise ValueError("원본 묶음 변경")
        manifest.append({"source": path.relative_to(ROOT).as_posix(), "source_sha256": original_sha,
                         "output": target.relative_to(ROOT).as_posix(), "output_sha256": sha(target),
                         "rows": len(batch), "corrections": len(changes), "readback": "PASS"})
    if sha(override_path) != override_sha:
        raise ValueError("교정 파일 변경")
    report = {"status": "PASS", "created": datetime.now(timezone.utc).isoformat(),
              "scope": "위치별 교정 적용과 원본 불변 확인", "runtime_qa": "NOT_RUN",
              "tool_sha256": sha(Path(__file__)), "override_sha256": override_sha,
              "corrections": len(overrides), "files": manifest}
    (output / "review_application.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "corrections": len(overrides), "files": len(manifest)}))


if __name__ == "__main__":
    main()
