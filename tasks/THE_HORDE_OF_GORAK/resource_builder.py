"""Fusion 296의 2226 메뉴와 225D Windows 자원을 구조에 맞춰 재조립합니다.

변경 계획은 target/offset/source/translated를 사용합니다. offset은 입력
청크의 원본 위치이며, 결과의 위치 이동은 반환 대장에 따로 기록합니다.
Windows 표준 DLGTEMPLATE만 지원하고 확장 양식은 명시적으로 거부합니다.
"""
from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass
from pathlib import Path

from dat_container import DatFile, sha


def align4(value):
    return (value + 3) & ~3


class Reader:
    def __init__(self, data, position=0, limit=None):
        self.data, self.position = data, position
        self.limit = len(data) if limit is None else limit

    def take(self, size):
        if size < 0 or self.position + size > self.limit:
            raise ValueError("Windows 자원 범위 초과")
        value = self.data[self.position:self.position + size]
        self.position += size
        return value

    def word(self):
        return struct.unpack("<H", self.take(2))[0]

    def padding(self):
        if any(self.take(align4(self.position) - self.position)):
            raise ValueError("지원하지 않는 비어 있지 않은 정렬 영역")


@dataclass
class Field:
    key: str
    offset: int
    value: str | int
    raw: bytes
    editable: bool = True

    def encode(self, replacements):
        if self.offset not in replacements:
            return self.raw
        if not self.editable or not isinstance(self.value, str):
            raise ValueError("표시 문구·글꼴이 아닌 필드는 수정할 수 없음")
        value = replacements[self.offset]
        if not isinstance(value, str) or "\0" in value or value.startswith("\uffff"):
            raise ValueError("잘못된 UTF-16 표시 문자열")
        return value.encode("utf-16le") + b"\0\0"


def read_field(reader, key, editable=True, ordinal=True):
    start = reader.position
    first = reader.word()
    if first == 0xFFFF:
        if not ordinal:
            raise ValueError("문자열 필드에 잘못된 리소스 번호")
        value = reader.word()
        editable = False
    else:
        while first:
            first = reader.word()
        value = reader.data[start:reader.position - 2].decode("utf-16le")
    return Field(key, start, value, reader.data[start:reader.position], editable)


class MenuResource:
    def __init__(self, data):
        self.data, self.fields = data, []
        if len(data) < 24:
            raise ValueError("메뉴 헤더가 너무 짧음")
        header_size, menu_offset, menu_size, accel_offset, accel_size = struct.unpack_from("<5I", data)
        if (header_size != 20 or menu_offset != 20 or menu_size < 4
                or accel_offset != menu_offset + menu_size or accel_size % 8
                or accel_offset + accel_size != len(data) or data[20:24] != b"\0" * 4):
            raise ValueError("검증한 표준 메뉴 구조와 다름")
        self.accelerators = data[accel_offset:]
        reader = Reader(data, 24, accel_offset)

        def items(parent=""):
            result = []
            while True:
                flags = reader.word()
                command = None if flags & 0x10 else reader.word()
                key = f"{parent}/{len(result)}"
                field = read_field(reader, "menu" + key, ordinal=False)
                self.fields.append(field)
                children = items(key) if flags & 0x10 else []
                result.append((flags, command, field, children))
                if flags & 0x80:
                    return result

        self.items = items()
        if reader.position != reader.limit:
            raise ValueError("메뉴 읽기 후 잔여 바이트")

    def build(self, replacements):
        validate_replacements(self.fields, replacements)
        payload = bytearray(b"\0" * 4)

        def emit(items):
            for flags, command, field, children in items:
                payload.extend(struct.pack("<H", flags))
                if command is not None:
                    payload.extend(struct.pack("<H", command))
                payload.extend(field.encode(replacements))
                emit(children)

        emit(self.items)
        return struct.pack("<5I", 20, 20, len(payload), 20 + len(payload), len(self.accelerators)) + payload + self.accelerators


class Dialog:
    def __init__(self, reader, ident):
        self.ident, self.offset, self.fields, self.items = ident, reader.position, [], []
        if self.offset % 4:
            raise ValueError("대화상자 시작이 DWORD 경계가 아님")
        self.header = reader.take(18)
        style, _, count = struct.unpack_from("<IIH", self.header)
        if self.header[:4] == b"\x01\0\xff\xff":
            raise ValueError("확장 대화상자 양식은 지원하지 않음")
        for kind in ("menu", "class", "title"):
            self.fields.append(read_field(reader, f"dialog:{ident}/{kind}", kind == "title", kind != "title"))
        self.points = b""
        if style & 0x40:
            self.points = reader.take(2)
            self.fields.append(read_field(reader, f"dialog:{ident}/font", ordinal=False))
        for index in range(count):
            reader.padding()
            fixed = reader.take(18)
            item_class = read_field(reader, f"dialog:{ident}/item:{index}/class", False)
            title = read_field(reader, f"dialog:{ident}/item:{index}/title")
            extra_word = reader.take(2)
            extra_size = struct.unpack("<H", extra_word)[0]
            if extra_size == 1:
                raise ValueError("컨트롤 생성 데이터 크기 오류")
            extra = extra_word + reader.take(extra_size - 2 if extra_size else 0)
            self.items.append((fixed, item_class, title, extra))
            self.fields.extend((item_class, title))
        if reader.limit - reader.position > 3 or any(reader.take(reader.limit - reader.position)):
            raise ValueError("대화상자 마지막 정렬 영역 오류")

    def build(self, replacements):
        result = bytearray(self.header)
        for field in self.fields[:3]:
            result.extend(field.encode(replacements))
        if self.points:
            result.extend(self.points)
            result.extend(self.fields[3].encode(replacements))
        for fixed, item_class, title, extra in self.items:
            result.extend(b"\0" * (align4(len(result)) - len(result)))
            result.extend(fixed)
            result.extend(item_class.encode(replacements))
            result.extend(title.encode(replacements))
            result.extend(extra)
        result.extend(b"\0" * (align4(len(result)) - len(result)))
        return bytes(result)


class PlayerControlsResource:
    def __init__(self, data):
        self.data, self.fields, self.keys, self.dialogs = data, [], [], []
        if len(data) < 16:
            raise ValueError("플레이어 조작 자원 헤더가 너무 짧음")
        version, string_table, dialog_table = struct.unpack_from("<III", data)
        if version != 1 or string_table != 12 or dialog_table % 4 or dialog_table >= len(data):
            raise ValueError("지원하지 않는 플레이어 조작 자원 구조")

        def table(position, limit):
            reader = Reader(data, position, limit)
            count = struct.unpack("<I", reader.take(4))[0]
            if count > (limit - reader.position) // 8:
                raise ValueError("자원 위치표 길이 오류")
            pairs = [struct.unpack("<II", reader.take(8)) for _ in range(count)]
            if len({p[0] for p in pairs}) != count:
                raise ValueError("중복 자원 번호")
            return pairs, reader.position

        pairs, base = table(string_table, dialog_table)
        cursor = base
        for ident, offset in pairs:
            if base + offset != cursor:
                raise ValueError("문자열 위치표의 비순차·중복·공백은 지원하지 않음")
            reader = Reader(data, cursor, dialog_table)
            field = read_field(reader, f"key:{ident}", ordinal=False)
            self.keys.append((ident, field))
            self.fields.append(field)
            cursor = reader.position
        if dialog_table - cursor > 3 or any(data[cursor:dialog_table]):
            raise ValueError("문자열 표 끝의 정렬 오류")
        pairs, base = table(dialog_table, len(data))
        cursor = base
        for index, (ident, offset) in enumerate(pairs):
            start = base + offset
            end = base + pairs[index + 1][1] if index + 1 < len(pairs) else len(data)
            if start != cursor or start % 4 or end <= start or end > len(data):
                raise ValueError("대화상자 위치표 경계 오류")
            dialog = Dialog(Reader(data, start, end), ident)
            self.dialogs.append(dialog)
            self.fields.extend(dialog.fields)
            cursor = end

    def build(self, replacements):
        validate_replacements(self.fields, replacements)
        strings, key_table = bytearray(), bytearray(struct.pack("<I", len(self.keys)))
        for ident, field in self.keys:
            key_table.extend(struct.pack("<II", ident, len(strings)))
            strings.extend(field.encode(replacements))
        dialog_offset = align4(12 + len(key_table) + len(strings))
        result = bytearray(struct.pack("<III", 1, 12, dialog_offset)) + key_table + strings
        result.extend(b"\0" * (dialog_offset - len(result)))
        dialog_table = bytearray(struct.pack("<I", len(self.dialogs)))
        dialogs = bytearray()
        for dialog in self.dialogs:
            dialog_table.extend(struct.pack("<II", dialog.ident, len(dialogs)))
            dialogs.extend(dialog.build(replacements))
        return bytes(result + dialog_table + dialogs)


def validate_replacements(fields, replacements):
    editable = {f.offset: f for f in fields if f.editable and isinstance(f.value, str)}
    if set(replacements) - set(editable):
        raise ValueError("원본에서 확인하지 못한 표시 필드 위치")
    for offset in replacements:
        editable[offset].encode(replacements)


def resource_for(chunk_id, data):
    if chunk_id == 0x2226:
        return MenuResource(data)
    if chunk_id == 0x225D:
        return PlayerControlsResource(data)
    raise ValueError("지원하지 않는 자원 청크")


def patch_resources(dat, changes):
    """모든 계획을 검사한 후에만 청크를 변경합니다. 실패 시 부분 적용하지 않습니다."""
    grouped, pending, report = {}, [], []
    for change in changes:
        grouped.setdefault(change["target"], []).append(change)
    for target, plan in grouped.items():
        if target not in dat.by_location:
            raise ValueError("없는 청크 위치")
        chunk = dat.by_location[target]
        data = chunk.decoded if chunk.replacement is None else chunk.replacement
        resource = resource_for(chunk.chunk_id, data)
        if resource.build({}) != data:
            raise ValueError("자원 원본 무변경 왕복 불일치")
        fields = {f.offset: f for f in resource.fields}
        replacements = {}
        for change in plan:
            offset = change["offset"]
            if offset in replacements or offset not in fields or fields[offset].value != change["source"]:
                raise ValueError("중복 위치 또는 기대 원문 불일치")
            if change.get("source_container_sha256", sha(data)) != sha(data):
                raise ValueError("자원 원본 해시 불일치")
            replacements[offset] = change["translated"]
        rebuilt = resource.build(replacements)
        reread = resource_for(chunk.chunk_id, rebuilt)
        after = {f.key: f for f in reread.fields}
        if set(after) != {f.key for f in resource.fields}:
            raise ValueError("필드 추가 또는 삭제 발견")
        for field in resource.fields:
            expected = replacements.get(field.offset, field.value)
            actual = after[field.key]
            if actual.value != expected:
                raise ValueError("위치별 기대 번역 불일치")
            report.append({"target": target, "key": field.key, "original_offset": field.offset,
                           "output_offset": actual.offset, "source": field.value, "actual": actual.value,
                           "changed": field.offset in replacements, "status": "PASS"})
        pending.append((chunk, rebuilt))
    for chunk, rebuilt in pending:
        chunk.replacement = rebuilt
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    target = args.output.resolve()
    allowed = [root / area / "THE_HORDE_OF_GORAK" for area in ("working_private", "build_candidate", "extracted_private")]
    if not any(target.is_relative_to(base) for base in allowed) or target == args.source.resolve() or target.exists():
        raise ValueError("새 비공개 출력 경로만 허용")
    dat = DatFile.load(args.source)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    report = patch_resources(dat, plan)
    output = dat.serialize()
    check = DatFile(output)
    if check.serialize() != output or check.integrity_summary()["status"] != "PASS":
        raise ValueError("DAT 재추출 또는 검사값 오류")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(output)
    result = {"source_sha256": sha(dat.original), "output_sha256": sha(output), "fields": report,
              "status": "PASS", "scope": "구조 재조립·위치별 대조", "graphics_qa": "NOT_RUN"}
    target.with_suffix(".resource_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "output_sha256", "graphics_qa")}))


if __name__ == "__main__":
    main()
