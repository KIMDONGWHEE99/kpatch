from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def load_translations(inventory_path: Path, translations_dir: Path) -> tuple[dict[int, str], dict[str, str]]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    sources = {int(row["index"]): str(row["source"]) for row in inventory["english_unique"]}
    translations: dict[int, str] = {}
    for path in sorted(translations_dir.glob("localization_ko_part*.json")):
        for raw_index, target in json.loads(path.read_text(encoding="utf-8-sig")).items():
            translations[int(raw_index)] = str(target)
    missing = sorted(set(sources) - set(translations))
    if missing:
        raise RuntimeError(f"번역 분할 파일에 누락된 번호: {missing}")
    by_source = {source: translations[index] for index, source in sources.items()}
    return translations, by_source


def pointer_path_id(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    return int(value.get("m_PathID", 0) or 0)


def safe_keep(source: str) -> bool:
    """언어가 아닌 숫자·기호·조작 키 표시는 번역하지 않고 그대로 둔다."""
    if not re.search(r"[A-Za-z]", source):
        return True
    compact = source.strip()
    return bool(
        re.fullmatch(r"(?:F(?:[1-9]|1[0-2])|WASD|W|A|S|D|Q|E|R|T|Y|U|I|O|P|H|J|K|L|Z|X|C|V|B|N|M)", compact)
        or re.fullmatch(r"(?:L |R )?(?:Ctrl|Shift|Alt)", compact, re.IGNORECASE)
        or re.fullmatch(r"(?:Tab|Esc|Escape|Enter|Return|Space|Backspace|Delete|Home|End|PgUp|PgDn|Up|Down|Left|Right)", compact, re.IGNORECASE)
        or re.fullmatch(r"v?\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.]+)?", compact)
    )


def normalized_text(source: str) -> str:
    return re.sub(r"\s+", " ", source).strip().casefold()


def main() -> None:
    parser = argparse.ArgumentParser(description="장면·공유 자산의 직접 UI 문구와 로컬라이즈 연결을 전수 분류")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--unitypy-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--translations-dir", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unity-version", default="6000.2.9f1")
    args = parser.parse_args()

    sys.path.insert(0, str(args.unitypy_root.resolve()))
    import UnityPy  # type: ignore
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator  # type: ignore

    _, translation_by_source = load_translations(args.inventory, args.translations_dir)
    translation_by_normalized_source: dict[str, str] = {}
    normalized_collisions: set[str] = set()
    for source, translation in translation_by_source.items():
        normalized = normalized_text(source)
        previous = translation_by_normalized_source.get(normalized)
        if previous is not None and previous != translation:
            normalized_collisions.add(normalized)
        else:
            translation_by_normalized_source[normalized] = translation
    for normalized in normalized_collisions:
        translation_by_normalized_source.pop(normalized, None)
    localization = json.loads(args.inventory.read_text(encoding="utf-8"))
    english_by_id = {
        int(row["id"]): str(row["source"])
        for row in localization["entries"]
        if row.get("locale") == "en"
    }
    review = json.loads(args.review.read_text(encoding="utf-8"))
    by_source_review = review.get("by_source", {})
    by_occurrence_review = review.get("by_occurrence", {})

    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))
    container_names = [
        "globalgamemanagers",
        "resources.assets",
        *[f"sharedassets{index}.assets" for index in range(13)],
        *[f"level{index}" for index in range(8)],
    ]
    paths = [args.data_root / name for name in container_names if (args.data_root / name).is_file()]

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for file_index, path in enumerate(paths, 1):
        print(f"[{file_index}/{len(paths)}] {path.name}", flush=True)
        try:
            env = UnityPy.load(str(path))
            env.typetree_generator = generator
        except Exception as exc:
            errors.append({"file": path.name, "stage": "load", "error": f"{type(exc).__name__}: {exc}"})
            continue

        text_objects: dict[int, dict[str, Any]] = {}
        localized_targets: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                head = obj.parse_monobehaviour_head()
                script = head.m_Script.deref_parse_as_object()
                class_name = str(script.m_ClassName)
                namespace = str(script.m_Namespace)
                assembly = str(script.m_AssemblyName)
            except Exception:
                continue
            if class_name not in {"TextMeshProUGUI", "TextMeshPro", "Text", "LocalizeStringEvent"}:
                continue
            try:
                tree = obj.read_typetree()
            except Exception as exc:
                errors.append(
                    {
                        "file": path.name,
                        "path_id": int(obj.path_id),
                        "class": class_name,
                        "stage": "typetree",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            game_object = ""
            try:
                game_object = str(head.m_GameObject.deref_parse_as_object().m_Name)
            except Exception:
                pass
            if class_name == "LocalizeStringEvent":
                reference = tree.get("m_StringReference", {})
                entry_reference = reference.get("m_TableEntryReference", {}) if isinstance(reference, dict) else {}
                key_id = int(entry_reference.get("m_KeyId", 0) or 0) if isinstance(entry_reference, dict) else 0
                calls = (
                    tree.get("m_UpdateString", {})
                    .get("m_PersistentCalls", {})
                    .get("m_Calls", [])
                )
                for call in calls if isinstance(calls, list) else []:
                    target_id = pointer_path_id(call.get("m_Target")) if isinstance(call, dict) else 0
                    if target_id:
                        localized_targets[target_id].append(
                            {
                                "event_path_id": int(obj.path_id),
                                "key_id": key_id,
                                "english_source": english_by_id.get(key_id),
                                "method": str(call.get("m_MethodName", "")),
                            }
                        )
                continue

            text_field = "m_text" if "m_text" in tree else "m_Text" if "m_Text" in tree else ""
            if not text_field:
                continue
            source = str(tree.get(text_field, ""))
            if not source:
                continue
            text_objects[int(obj.path_id)] = {
                "file": path.name,
                "path_id": int(obj.path_id),
                "class": class_name,
                "namespace": namespace,
                "assembly": assembly,
                "game_object": game_object,
                "field": text_field,
                "source": source,
            }

        for path_id, row in text_objects.items():
            links = localized_targets.get(path_id, [])
            classification = "UNKNOWN"
            target = None
            reason = "명시적 검토 필요"
            linked_source = next((link["english_source"] for link in links if link.get("english_source")), None)
            if linked_source is not None and linked_source in translation_by_source:
                classification = "VISIBLE_TRANSLATE"
                target = translation_by_source[linked_source]
                reason = "LocalizeStringEvent의 영어 항목 ID와 연결됨"
            elif row["source"] in translation_by_source:
                classification = "VISIBLE_TRANSLATE"
                target = translation_by_source[row["source"]]
                reason = "영어 로컬라이제이션 원문과 정확히 일치"
            elif normalized_text(row["source"]) in translation_by_normalized_source:
                classification = "VISIBLE_TRANSLATE"
                target = translation_by_normalized_source[normalized_text(row["source"])]
                reason = "대소문자·공백만 다른 영어 로컬라이제이션 원문과 일치"
            elif safe_keep(row["source"]):
                classification = "VISIBLE_KEEP"
                target = row["source"]
                reason = "언어와 무관한 숫자·기호·조작 키·버전 표시"
            elif row["file"] == "resources.assets":
                classification = "INTERNAL"
                reason = "Unity 기본 UI/TMP 예제·편집기용 자원이며 게임 장면의 실제 표시 문구가 아님"
            elif row["file"] == "level3" and row["game_object"].casefold() == "names":
                classification = "VISIBLE_KEEP"
                target = row["source"]
                reason = "제작진·감사 명단의 사람 이름과 온라인 별명"

            occurrence_key = f"{row['file']}|{row['path_id']}"
            decision = by_source_review.get(row["source"])
            if occurrence_key in by_occurrence_review:
                decision = by_occurrence_review[occurrence_key]
            if decision is not None:
                classification = str(decision["classification"])
                target = decision.get("translation", row["source"] if classification == "VISIBLE_KEEP" else None)
                reason = str(decision.get("reason", "명시적 검토표"))

            row.update(
                {
                    "classification": classification,
                    "translation": target,
                    "reason": reason,
                    "localize_links": links,
                }
            )
            rows.append(row)

    counts = Counter(str(row["classification"]) for row in rows)
    unknown_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["classification"] == "UNKNOWN":
            unknown_by_source[str(row["source"])].append(
                {key: row[key] for key in ("file", "path_id", "class", "game_object")}
            )
    report = {
        "schema_version": 1,
        "data_root": str(args.data_root.resolve()),
        "container_count": len(paths),
        "record_count": len(rows),
        "classification_counts": dict(sorted(counts.items())),
        "unknown_unique_count": len(unknown_by_source),
        "error_count": len(errors),
        "errors": errors,
        "unknown_by_source": dict(sorted(unknown_by_source.items(), key=lambda item: item[0].casefold())),
        "records": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"records", "unknown_by_source", "errors"}}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if unknown_by_source or errors else 0)


if __name__ == "__main__":
    main()
