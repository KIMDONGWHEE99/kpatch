from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import UnityPy


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def locale_code(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("m_Code", ""))
    return str(value)


def script_details(obj: Any) -> dict[str, str]:
    try:
        head = obj.parse_monobehaviour_head()
        script = head.m_Script.deref_parse_as_object()
        return {
            "class": str(script.m_ClassName),
            "namespace": str(script.m_Namespace),
            "assembly": str(script.m_AssemblyName),
        }
    except Exception:
        return {"class": "", "namespace": "", "assembly": ""}


def main() -> None:
    parser = argparse.ArgumentParser(description="TFC2 Addressables 현지화 전수 인벤토리")
    parser.add_argument("--aa-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    files: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    shared_tables: list[dict[str, Any]] = []
    locale_objects: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for path in sorted(args.aa_root.rglob("*.bundle")):
        relative_path = path.relative_to(args.aa_root).as_posix()
        file_row: dict[str, Any] = {
            "relative_path": relative_path,
            "size": path.stat().st_size,
            "sha256": sha256_file(path),
            "object_counts": {},
        }
        try:
            env = UnityPy.load(str(path))
        except Exception as exc:
            errors.append(
                {"file": relative_path, "stage": "load", "error": f"{type(exc).__name__}: {exc}"}
            )
            files.append(file_row)
            continue

        counts: Counter[str] = Counter()
        for obj in env.objects:
            counts[obj.type.name] += 1
            if obj.type.name != "MonoBehaviour":
                continue
            details = script_details(obj)
            try:
                tree = obj.read_typetree()
            except Exception as exc:
                errors.append(
                    {
                        "file": relative_path,
                        "path_id": int(obj.path_id),
                        "stage": "typetree",
                        "error": f"{type(exc).__name__}: {exc}",
                        **details,
                    }
                )
                continue

            name = str(tree.get("m_Name", ""))
            if "m_TableData" in tree and "m_LocaleId" in tree:
                tables.append(
                    {
                        "file": relative_path,
                        "path_id": int(obj.path_id),
                        "name": name,
                        "locale": locale_code(tree.get("m_LocaleId")),
                        "shared_data": tree.get("m_SharedData"),
                        "metadata": tree.get("m_Metadata"),
                        "entries": tree.get("m_TableData", []),
                        **details,
                    }
                )
            elif "m_Entries" in tree and "m_TableCollectionName" in tree:
                shared_tables.append(
                    {
                        "file": relative_path,
                        "path_id": int(obj.path_id),
                        "name": name,
                        "table_collection_name": str(tree.get("m_TableCollectionName", "")),
                        "table_collection_name_guid": str(tree.get("m_TableCollectionNameGuid", "")),
                        "entries": tree.get("m_Entries", []),
                        **details,
                    }
                )
            elif "m_Identifier" in tree or details["class"] == "Locale":
                locale_objects.append(
                    {
                        "file": relative_path,
                        "path_id": int(obj.path_id),
                        "name": name,
                        "identifier": tree.get("m_Identifier"),
                        "locale_name": tree.get("m_LocaleName"),
                        "tree": tree,
                        **details,
                    }
                )
        file_row["object_counts"] = dict(sorted(counts.items()))
        files.append(file_row)

    keys_by_collection: dict[str, dict[int, str]] = {}
    for table in shared_tables:
        collection = str(table["table_collection_name"])
        keys_by_collection[collection] = {
            int(entry.get("m_Id", 0)): str(entry.get("m_Key", "")) for entry in table["entries"]
        }

    entries: list[dict[str, Any]] = []
    for table in tables:
        collection = str(table["name"]).rsplit("_", 1)[0]
        keys = keys_by_collection.get(collection, {})
        for index, entry in enumerate(table["entries"]):
            entry_id = int(entry.get("m_Id", 0))
            entries.append(
                {
                    "locale": table["locale"],
                    "collection": collection,
                    "table_name": table["name"],
                    "file": table["file"],
                    "table_path_id": table["path_id"],
                    "entry_index": index,
                    "id": entry_id,
                    "key": keys.get(entry_id, ""),
                    "source": str(entry.get("m_Localized", "")),
                    "metadata": entry.get("m_Metadata"),
                }
            )

    english_entries = [row for row in entries if row["locale"] == "en"]
    unique_sources: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in english_entries:
        unique_sources[str(row["source"])].append(row)
    english_unique = [
        {
            "index": index,
            "source": source,
            "collections": sorted({str(row["collection"]) for row in rows}),
            "sample_keys": sorted({str(row["key"]) for row in rows if row["key"]})[:12],
            "occurrences": len(rows),
            "translation": "",
        }
        for index, (source, rows) in enumerate(sorted(unique_sources.items()), 1)
    ]

    report = {
        "schema_version": 1,
        "aa_root": str(args.aa_root.resolve()),
        "bundle_count": len(files),
        "files_with_errors": len({row["file"] for row in errors}),
        "error_count": len(errors),
        "table_count": len(tables),
        "shared_table_count": len(shared_tables),
        "locale_object_count": len(locale_objects),
        "entry_count": len(entries),
        "entries_by_locale": dict(Counter(str(row["locale"]) for row in entries)),
        "english_entry_count": len(english_entries),
        "english_unique_count": len(english_unique),
        "files": files,
        "tables": tables,
        "shared_tables": shared_tables,
        "locale_objects": locale_objects,
        "entries": entries,
        "english_unique": english_unique,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {key: value for key, value in report.items() if key not in {
                "files", "tables", "shared_tables", "locale_objects", "entries", "english_unique", "errors"
            }},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

