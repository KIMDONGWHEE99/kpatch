"""동결된01을 보존하고 CRT 오류 문구를 포함한02를 새로 만듭니다."""
import json
import build_native_candidate as build
from native_crt_display_review import TRANSLATIONS
import verify_native_windows_resources as verify

build.OUT = build.ROOT / "working_private/THE_HORDE_OF_GORAK/native_candidate_02"
build.TRANSLATIONS.update(TRANSLATIONS)
build.main()
path = build.OUT / "native_patch_audit.json"
report = json.loads(path.read_text(encoding="utf-8"))
report["limitations"][2] = f"확인된 {len(report['translations'])}개 표시 필드만 포함. 전체 네이티브 문자열 분류 완료를 뜻하지 않음."
report["additional_evidence"] = "native_crt_display_evidence.json"
path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
verify.BASE = build.OUT
verify.main()
