from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

import UnityPy
from fontTools.ttLib import TTFont
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("_")
    return cleaned or "font"


def pptr(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {"file_id": 0, "path_id": 0}
    return {
        "file_id": int(value.get("m_FileID", 0)),
        "path_id": int(value.get("m_PathID", 0)),
    }


def script_class(obj: Any) -> str:
    try:
        head = obj.parse_monobehaviour_head()
        return str(head.m_Script.deref_parse_as_object().m_ClassName)
    except Exception:
        return ""


def codepoints_from_font(data: bytes) -> tuple[set[int], str]:
    font = TTFont(io.BytesIO(data), lazy=True)
    points: set[int] = set()
    for table in font["cmap"].tables:
        points.update(int(point) for point in table.cmap)
    flavor = str(getattr(font.reader, "sfntVersion", ""))
    font.close()
    return points, flavor


def main() -> None:
    parser = argparse.ArgumentParser(description="SuperReap Demo 글꼴 자산 검사")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--managed-dir", type=Path, required=True)
    parser.add_argument("--containers", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--unity-version", default="2022.3.62f3")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    generator = TypeTreeGenerator(args.unity_version)
    generator.load_local_dll_folder(str(args.managed_dir))

    font_rows: list[dict[str, Any]] = []
    tmp_font_assets: list[dict[str, Any]] = []
    tmp_text_usages: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for relative in args.containers:
        source = args.data_root / relative
        try:
            env = UnityPy.load(str(source))
            env.typetree_generator = generator
        except Exception as exc:
            errors.append({"file": relative.as_posix(), "stage": "load", "error": str(exc)})
            continue
        for obj in env.objects:
            if obj.type.name == "Font":
                try:
                    value = obj.read()
                    name = str(getattr(value, "m_Name", ""))
                    data = bytes(getattr(value, "m_FontData", b""))
                    row: dict[str, Any] = {
                        "file": relative.as_posix(),
                        "path_id": int(obj.path_id),
                        "name": name,
                        "bytes": len(data),
                        "sha256": sha256_bytes(data) if data else "",
                    }
                    if data:
                        target = raw_dir / f"{safe_name(name)}_{int(obj.path_id)}.font"
                        target.write_bytes(data)
                        row["raw_path"] = str(target)
                        try:
                            points, flavor = codepoints_from_font(data)
                            row.update(
                                {
                                    "font_format": flavor,
                                    "codepoint_count": len(points),
                                    "has_hangul_syllables": all(point in points for point in (0xAC00, 0xB098, 0xD7A3)),
                                    "hangul_syllable_count": sum(0xAC00 <= point <= 0xD7A3 for point in points),
                                    "hangul_jamo_count": sum(0x1100 <= point <= 0x11FF for point in points),
                                }
                            )
                        except Exception as exc:
                            row["font_parse_error"] = f"{type(exc).__name__}: {exc}"
                    font_rows.append(row)
                except Exception as exc:
                    errors.append(
                        {
                            "file": relative.as_posix(),
                            "path_id": int(obj.path_id),
                            "stage": "font",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
            elif obj.type.name == "MonoBehaviour":
                class_name = script_class(obj)
                if class_name not in {"TMP_FontAsset", "TextMeshPro", "TextMeshProUGUI"}:
                    continue
                try:
                    tree = obj.read_typetree()
                except Exception as exc:
                    errors.append(
                        {
                            "file": relative.as_posix(),
                            "path_id": int(obj.path_id),
                            "class": class_name,
                            "stage": "typetree",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                if class_name == "TMP_FontAsset":
                    characters = tree.get("m_CharacterTable", [])
                    unicode_values = [int(item.get("m_Unicode", -1)) for item in characters if isinstance(item, dict)]
                    tmp_font_assets.append(
                        {
                            "file": relative.as_posix(),
                            "path_id": int(obj.path_id),
                            "name": str(tree.get("m_Name", "")),
                            "atlas_population_mode": tree.get("m_AtlasPopulationMode"),
                            "source_font_file": pptr(tree.get("m_SourceFontFile")),
                            "atlas_textures": [pptr(item) for item in tree.get("m_AtlasTextures", [])],
                            "fallback_font_assets": [pptr(item) for item in tree.get("m_FallbackFontAssetTable", [])],
                            "character_count": len(unicode_values),
                            "has_hangul_syllables": all(point in unicode_values for point in (0xAC00, 0xB098, 0xD7A3)),
                            "hangul_syllable_count": sum(0xAC00 <= point <= 0xD7A3 for point in unicode_values),
                        }
                    )
                else:
                    tmp_text_usages.append(
                        {
                            "file": relative.as_posix(),
                            "path_id": int(obj.path_id),
                            "class": class_name,
                            "text": str(tree.get("m_text", "")),
                            "font_asset": pptr(tree.get("m_fontAsset")),
                        }
                    )

    report = {
        "fonts": font_rows,
        "tmp_font_assets": tmp_font_assets,
        "tmp_text_usages": tmp_text_usages,
        "errors": errors,
    }
    (args.output_dir / "font_inventory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "fonts": len(font_rows),
                "fonts_with_hangul": sum(bool(item.get("has_hangul_syllables")) for item in font_rows),
                "tmp_font_assets": len(tmp_font_assets),
                "tmp_font_assets_with_hangul": sum(bool(item.get("has_hangul_syllables")) for item in tmp_font_assets),
                "tmp_text_usages": len(tmp_text_usages),
                "errors": len(errors),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
