"""교정한 구간 번역을 유일한 제작용 번역 원본으로 합칩니다."""
from common import *
from translation_checks import controls, check_rows, self_test

source = json.loads((WORK/"language_source.json").read_text(encoding="utf-8"))
lookup = dict(line.split("=",1) for line in (WORK/"translation/root_0_399.txt").read_text(encoding="utf-8").splitlines())
first = [dict(row, target=lookup[row["key"]]) for row in source[:400]]
check_rows(first, source[:400])
write_json(WORK/"translation/part_0_399.json", first)
rows = []
for name in ("part_0_399.json","part_400_799.json","part_800_1199.json","part_1200_1555.json"):
    rows += json.loads((WORK/"translation"/name).read_text(encoding="utf-8"))
check_rows(rows, source)
assert len({r["key"] for r in rows}) == len(rows)
additions = {
    "TooltipItemLevel":"{0}레벨",
    "TimeFormatMS":"{1}분 {2}초",
    "TimeFormatHMS":"{0}시간 {1}분 {2}초",
    "ForestCrewUnassigned2":"미배치 인부",
    "ForestCrewUnassignedDesc":"아직 작업을 배정받지 않은 인부입니다.",
    "SlotScroll":"두루마리",
}
assert not set(additions) & {r["key"] for r in rows}
write_json(WORK/"translation/canonical.json", {"rows":rows, "additions":additions,
           "source_sha256":sha(WORK/"language_source.json"),
           "addition_evidence_sha256":sha(WORK/"audit/key_coverage_original.json")})
content = "; Kingdom Inc. Demo 한국어 번역\n" + "\n".join(f'{r["key"]} = {r["target"]}' for r in rows)
content += "\n\n; 원본에서 누락된 표시 키 보완\n" + "\n".join(f"{k} = {v}" for k,v in additions.items()) + "\n"
(WORK/"translation/language_ko.txt").write_text(content, encoding="utf-8")
direct = json.loads((WORK/"audit/direct_translations.json").read_text(encoding="utf-8"))
code = json.loads((WORK/"audit/code_direct_translations.json").read_text(encoding="utf-8"))
for row in direct+code:
    controls(row["source"], row["expected"])
characters = sorted({ord(c) for c in content+"".join(r["expected"] for r in direct+code) if c not in "\r\n\t"} | set(range(32,127)))
write_json(WORK/"translation/required_characters.json", characters)
write_json(WORK/"translation/checks.json", {"status":"PASS","locations":len(rows),"added_keys":len(additions),
           "direct_assets":len(direct),"direct_code":len(code),"self_test":self_test(),
           "canonical_sha256":sha(WORK/"translation/canonical.json"),"required_characters":len(characters)})
print(json.dumps({"status":"PASS","table":len(rows),"additions":len(additions),"direct":len(direct),"code":len(code)}))
