"""실제 판독된 PNG의 런타임 문구를 번역 위치에 완전 일치로 연결합니다."""
import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from common import ROOT, DATA, EXTRACT, WORK, load_asset, sha, write_json

AUDIT = WORK / "audit"
CANONICAL = WORK / "translation/canonical.json"
DIRECT = AUDIT / "direct_translations.json"
STATIC = WORK / "1.0.0_rc5/static_validation.json"
STYLE_TAG = re.compile(
    r"</?(?:color|b|i|u|s|size|font|material|align|cspace|mspace|line-height|line-indent|"
    r"indent|margin|margin-left|margin-right|voffset|pos|width|rotate|space|"
    r"alpha|mark|link|noparse|nobr|lowercase|uppercase|smallcaps|sub|sup|sprite)(?:\s[^>]*|=[^>]*|)>",
    re.I,
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def absolute(path):
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def normalize(text, source_kind="runtime"):
    """번역기의 강조와 TMP 표시 제어만 제거하며 어휘·수치·자리표시자를 추정하지 않습니다."""
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    if source_kind == "translation":
        value = value.replace("\\n", "\n")
        value = re.sub(r"#(.*?)#", r"\1", value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = STYLE_TAG.sub("", value)
    value = value.replace("\u200b", "").replace("\ufeff", "")
    return value


def load_locations():
    canonical = read(CANONICAL)
    direct = read(DIRECT)
    locations = []
    for row in canonical["rows"]:
        locations.append({
            "id": "table:" + row["key"], "kind": "table", "key": row["key"],
            "asset_location": "resources.assets/21/m_Script:" + row["key"],
            "index": row["index"], "source": row["source"], "target": row["target"],
        })
    for key, target in canonical["additions"].items():
        locations.append({
            "id": "added:" + key, "kind": "added", "key": key,
            "asset_location": "resources.assets/21/m_Script:" + key,
            "source": None, "target": target,
        })
    for row in direct:
        locations.append({
            "id": "direct:" + row["id"], "kind": "direct", "asset_location": row["id"],
            "source": row["source"], "target": row["expected"],
            "file": row["file"], "path_id": row["path_id"], "field": row["field"],
        })
    assert len(locations) == 1716
    assert len({r["id"] for r in locations}) == len(locations)
    for row in locations:
        row["normalized_target"] = normalize(row["target"], "translation")
    return locations


def source_ui_paths(locations):
    """직접 TMP 필드와 @번역키의 정적 게임 오브젝트 경로를 정확히 연결합니다."""
    source_strings = read(EXTRACT / "strings.json") + read(EXTRACT / "additional_strings.json")
    wanted = defaultdict(list)
    for row in locations:
        if row["kind"] == "direct" and row["field"] in ("/m_text", "/m_Text"):
            wanted[row["file"]].append((row["path_id"], row["id"]))
    key_to_location = {r["key"]: r["id"] for r in locations if "key" in r}
    for row in source_strings:
        if row["field"] not in ("/m_text", "/m_Text"):
            continue
        key = re.fullmatch(r"@([A-Za-z0-9_]+)", row["source"])
        if key and key[1] in key_to_location:
            wanted[row["file"]].append((row["path_id"], key_to_location[key[1]]))
    result = defaultdict(set)
    details = []
    for filename, requests in wanted.items():
        env = load_asset(DATA / filename)
        names, transforms, go_transform = {}, {}, {}
        for obj in env.objects:
            if obj.type.name == "GameObject":
                tree = obj.read_typetree()
                names[obj.path_id] = tree["m_Name"]
            elif obj.type.name in ("Transform", "RectTransform"):
                tree = obj.read_typetree()
                transforms[obj.path_id] = (tree["m_GameObject"]["m_PathID"], tree["m_Father"]["m_PathID"])
                go_transform[tree["m_GameObject"]["m_PathID"]] = obj.path_id

        def path_for(go_id):
            parts, visited = [], set()
            while go_id and go_id not in visited:
                visited.add(go_id)
                if go_id not in names:
                    return None
                parts.append(names[go_id])
                transform = transforms.get(go_transform.get(go_id))
                if not transform:
                    break
                father = transforms.get(transform[1])
                go_id = father[0] if father else 0
            return "/".join(reversed(parts))

        for object_id, location_id in requests:
            tree = env.file.objects[object_id].read_typetree()
            go = tree.get("m_GameObject", {}).get("m_PathID")
            path = path_for(go) if go else None
            if path:
                result[path].add(location_id)
                details.append({"source_file": filename, "object_id": object_id, "runtime_path_exact": path, "location_id": location_id})
    return result, details


def review_images(patterns):
    reports = []
    images = {}
    for pattern in patterns:
        for report_path in sorted(AUDIT.glob(pattern)):
            if report_path in [p for p, _ in reports]:
                continue
            report = read(report_path)
            reports.append((report_path, report))
            for row in report.get("rows", report.get("images", [])):
                image_path = row.get("path") or row.get("image")
                if not image_path or not str(image_path).endswith(".png"):
                    continue
                image_path = absolute(image_path)
                expected_sha = row.get("image_sha256") or row.get("sha256")
                assert expected_sha, (report_path, image_path)
                assert image_path.is_file() and sha(image_path) == expected_sha, image_path
                capture_path = image_path.with_suffix(".json")
                assert capture_path.is_file(), capture_path
                known_capture_sha = row.get("capture_json_sha256") or row.get("text_json_sha256")
                if known_capture_sha:
                    assert sha(capture_path) == known_capture_sha, capture_path
                runtime_path = image_path.parent / "runtime.json"
                prepared_path = image_path.parent / "prepared-manifest.json"
                runtime_sha = row.get("runtime_sha256") or report.get("runtime_sha256")
                prepared_sha = (row.get("prepared_manifest_sha256") or row.get("preparedManifestSHA")
                                or report.get("prepared_manifest_sha256") or report.get("preparedManifestSHA"))
                assert runtime_sha and sha(runtime_path) == runtime_sha
                assert prepared_sha and sha(prepared_path) == prepared_sha
                name = str(image_path)
                if name not in images:
                    images[name] = {
                        "image": name, "image_sha256": expected_sha,
                        "capture_json": str(capture_path), "capture_json_sha256": sha(capture_path),
                        "runtime_sha256": runtime_sha, "prepared_manifest_sha256": prepared_sha,
                        "reviews": [], "eligible": False,
                    }
                images[name]["reviews"].append({
                    "report": str(report_path), "report_sha256": sha(report_path),
                    "status": row.get("status", "NOT_RUN"),
                    "observation": row.get("observations", row.get("observation", "")),
                })
                if row.get("status") == "PASS":
                    images[name]["eligible"] = True
    assert images
    return images, [{"path": str(p), "sha256": sha(p), "status": d.get("status")} for p, d in reports]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-glob", action="append",
                        help="audit 폴더의 실제 PNG 판독 보고서 패턴. 여러 번 지정 가능.")
    parser.add_argument("--output", default="runtime_translation_coverage.json")
    args = parser.parse_args()
    patterns = args.review_glob or ["visual_rc4*.json", "visual_rc5*.json"]
    locations = load_locations()
    by_id = {r["id"]: r for r in locations}
    by_text = defaultdict(list)
    for row in locations:
        if row["normalized_target"]:
            by_text[row["normalized_target"]].append(row["id"])
    ui_paths, path_evidence = source_ui_paths(locations)
    images, report_inputs = review_images(patterns)
    exact_links = defaultdict(list)
    ambiguous = []
    unmatched = defaultdict(list)
    excluded = Counter()
    seen_text_occurrences = 0
    for image in images.values():
        capture = read(image["capture_json"])
        width, height = capture["width"], capture["height"]
        for text_row in capture["texts"]:
            if not text_row.get("active") or not text_row.get("onScreen"):
                excluded["inactive_or_offscreen"] += 1
                continue
            value = text_row.get("text", "")
            normalized = normalize(value)
            if not normalized:
                excluded["empty_after_display_control_removal"] += 1
                continue
            seen_text_occurrences += 1
            occurrence = {
                "image": image["image"], "image_sha256": image["image_sha256"],
                "capture_json_sha256": image["capture_json_sha256"],
                "runtime_sha256": image["runtime_sha256"],
                "prepared_manifest_sha256": image["prepared_manifest_sha256"],
                "scene": capture["scene"], "runtime_path": text_row["path"],
                "font": text_row.get("font"), "material": text_row.get("material"),
                "text": value, "normalized_text": normalized,
                "active": True, "onScreen": True, "overflow": text_row.get("overflow"),
                "rect": {k: text_row.get(k) for k in ["left", "bottom", "width", "height"]},
            }
            if not image["eligible"]:
                excluded["image_without_pass_row"] += 1
                continue
            # 창 밖으로 나간 글자는 onScreen=True여도 온전한 관찰로 세지 않습니다.
            if (text_row["left"] < 0 or text_row["bottom"] < 0
                    or text_row["left"] + text_row["width"] > width + 0.01
                    or text_row["bottom"] + text_row["height"] > height + 0.01):
                excluded["rect_not_fully_inside_window"] += 1
                continue
            candidates = by_text.get(normalized, [])
            exact_bound = sorted(set(candidates) & ui_paths.get(text_row["path"], set()))
            resolved = None
            if len(exact_bound) == 1:
                resolved = exact_bound[0]
                occurrence["binding"] = "원본 정적 TMP 경로 또는 @번역키 경로와 런타임 path가 정확히 같음"
            elif len(candidates) == 1 and by_id[candidates[0]]["kind"] in ("table", "added"):
                resolved = candidates[0]
                occurrence["binding"] = "전체 1716위치 중 표시 문구가 완전히 일치하는 번역표 위치가 하나뿐임. 동적 호출의 키 자체를 계측한 것은 아님."
            elif (len(candidates) == 1 and by_id[candidates[0]]["asset_location"] == "globalgamemanagers/1/bundleVersion"):
                resolved = candidates[0]
                occurrence["binding"] = "고유한 게임 버전 문구의 전체 일치. Application.version 표시값이며 GameObject 필드 경로는 없음."
            if resolved:
                occurrence["match"] = "literal_exact" if value == by_id[resolved]["target"] else "format_normalized_exact"
                exact_links[resolved].append(occurrence)
            elif candidates:
                occurrence["candidate_location_ids"] = candidates
                occurrence["reason"] = "같은 표시값의 위치가 여러 개이거나 직접 자산 필드의 런타임 경로를 특정하지 못함. 관찰 위치 수에 포함하지 않음."
                ambiguous.append(occurrence)
            else:
                # 수치 삽입·여러 키 조합·사용자 이름 등에 substring/정규식 추정을 하지 않습니다.
                unmatched[normalized].append(occurrence)

    static = read(STATIC)
    assert static["status"] == "PASS"
    build_path = WORK / "1.0.0_rc5/build.json"
    assert sha(build_path) == static["build_sha256"]
    for record in static["verification_inputs"]:
        assert sha(record["path"]) == record["sha256"], record["path"]
    font_counts = Counter()
    observed = []
    unobserved = []
    for row in locations:
        linked = exact_links.get(row["id"], [])
        record = row | {
            "runtime_location_observation": "PASS" if linked else "NOT_RUN",
            "static_validation": "PASS",
            "runtime_observation_scope": "판독한 PASS PNG의 active/onScreen 문구 완전일치 발생. 개별 텍스트의 가림·모든 글리프 가독성을 자동 증명하지 않음.",
        }
        if linked:
            record["occurrences"] = linked
            record["occurrence_count"] = len(linked)
            record["binding_modes"] = dict(Counter(e["binding"] for e in linked))
            observed.append(record)
            font_counts.update(e["font"] for e in linked)
        else:
            if not row["normalized_target"]:
                reason = "빈 표시값"
            elif re.search(r"\{\d+(?:[^}]*)\}", row["normalized_target"]):
                reason = "자리표시자가 있는 문구. 동적 값과 템플릿의 부분 일치로 관찰 처리하지 않음."
            elif row["kind"] == "direct":
                reason = "직접 필드가 같은 정적 경로에서 전체 기대값으로 관찰되지 않음. 예비값·개발 화면도 임의로 INTERNAL 처리하지 않음."
            else:
                reason = "현재 확정 위치에 완전 일치로 연결된 런타임 문구가 없음. 모호한 중복값·조합 문구·다른 분기 포함."
            record["not_observed_reason"] = reason
            unobserved.append(record)
    assert len(observed) + len(unobserved) == 1716
    base = Path(args.output).stem
    observed_path = AUDIT / (base + "_observed.json")
    unobserved_path = AUDIT / (base + "_not_observed.json")
    ambiguous_path = AUDIT / (base + "_ambiguous.json")
    unmatched_path = AUDIT / (base + "_unmatched.json")
    path_map_path = AUDIT / (base + "_path_map.json")
    write_json(observed_path, observed)
    write_json(unobserved_path, unobserved)
    write_json(ambiguous_path, ambiguous)
    write_json(unmatched_path, [{"normalized_text": k, "occurrences": v} for k, v in unmatched.items()])
    write_json(path_map_path, path_evidence)
    result = {
        "status": "PASS",
        "status_meaning": "범위 계수·해시·완전 일치 연결 작업이 완료되었다는 뜻. 전체 1716위치를 실제 화면에서 검증했다는 뜻이 아님.",
        "utc": datetime.now(timezone.utc).isoformat(),
        "scope": "실제 제작자가 PNG를 열어 판독한 rc4/rc5 보고서에 명시된 이미지의 런타임 텍스트와 현재 rc5 번역 위치 연결.",
        "denominator": {"total_locations": 1716, "original_table": 1556, "added_table": 6, "direct_asset_fields": 154},
        "counts": {
            "reviewed_image_files": len(images),
            "pass_image_files_eligible": sum(i["eligible"] for i in images.values()),
            "active_onscreen_nonempty_occurrences": seen_text_occurrences,
            "exact_linked_translation_locations": len(observed),
            "not_observed_translation_locations": len(unobserved),
            "exact_location_percentage": round(len(observed) / 1716 * 100, 2),
            "observed_by_kind": dict(Counter(r["kind"] for r in observed)),
            "not_observed_by_kind": dict(Counter(r["kind"] for r in unobserved)),
            "ambiguous_occurrences_not_counted": len(ambiguous),
            "unmatched_display_values_not_inferred": len(unmatched),
            "excluded": dict(excluded),
        },
        "matching_rules": [
            "원문 문자열 전체가 정확히 같거나, 허용된 표시 태그/강조와 제어 줄바꿈만 제거한 전체 값이 정확히 같아야 함.",
            "substring, 어휘 포함 여부, 부분 정규식, 숫자 삽입 추정, 위치별 무차별 중복 계수 금지.",
            "중복 값은 원본 TMP 또는 @키의 GameObject 경로와 런타임 path가 정확히 같을 때만 위치를 특정.",
            "직접 자산 필드는 정확한 경로가 없으면 표시값이 같아도 미관찰 유지(고유 bundleVersion만 소비 방식상 예외).",
            "FAIL/BLOCKED 캡처와 창 밖으로 나간 텍스트 경계는 관찰 수에 넣지 않음.",
        ],
        "normalization": {
            "translation": "#...# 강조 제거, 문자형 \\n을 LF로 변환",
            "both": "CRLF/CR을 LF로 통일, 알려진 TMP 스타일/아이콘 태그 제거, br을 LF로 변환, U+200B/U+FEFF 표시 제어 제거",
            "preserved": "일반 공백·줄바꿈·문장·수치·자리표시자는 바꾸지 않음. 문장 결합이나 숫자 대입 없음.",
            "caveat": "표시 아이콘 태그 제거 후 텍스트의 일치만 계수하므로 아이콘 그림·태그 순서는 별도 G4/G5 증거를 참조한다.",
        },
        "limitations": [
            "active/onScreen과 화면 안 경계는 UI의 기하학적 상태다. 다른 패널 뒤 가림을 모두 판정하는 지표가 아니므로 개별 문장 가독성·글리프 관찰 완료와 동일시하지 않는다.",
            "고유 전체 문구 일치는 번역표 위치에 대한 표시값 연결이며 동적 호출이 전달한 key 자체의 계측은 아니다.",
            "필수 대표 화면군 PASS, 런타임 문구 발생 위치 수, 전체 문자열 실화면 관찰은 서로 다른 범위다.",
            "미관찰 1716분모 위치는 NOT_RUN/정적PASS로 남기며 INTERNAL이나 미구현으로 재분류하지 않는다.",
            "실제 숫자가 삽입된 문구·여러 키로 조합된 문구·생성 고유명사는 부분 일치로 번역 템플릿을 통과시키지 않는다.",
        ],
        "current_translation_inputs": [
            {"path": str(CANONICAL), "sha256": sha(CANONICAL)},
            {"path": str(DIRECT), "sha256": sha(DIRECT)},
            {"path": str(STATIC), "sha256": sha(STATIC)},
        ],
        "review_report_inputs": report_inputs,
        "image_evidence": list(images.values()),
        "font_occurrence_counts": dict(font_counts),
        "outputs": {k: {"path": str(p), "sha256": sha(p)} for k, p in {
            "observed": observed_path, "not_observed": unobserved_path, "ambiguous": ambiguous_path,
            "unmatched": unmatched_path, "source_ui_path_map": path_map_path,
        }.items()},
        "future_update": "새 실제 PNG 판독 보고서를 visual_rc5*.json으로 저장하거나 --review-glob을 추가하고 다시 실행한다. 캡처 존재만으로 자동 편입하지 않는다.",
    }
    write_json(AUDIT / args.output, result)
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
