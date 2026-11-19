"""공개 파일과 소개문 연결을 확인하고 공유 가능한 요약을 남깁니다."""
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "working_private/COBALT_MINER/github_publish_20261102"
REPO = "KIMDONGWHEE99/cobalt-miner-korean-patch"
COMMIT = "f49c3aec5219a39e75874ee1531f46658c7672d8"
TREE = "e37c35d71b9b9e5ca8adf1e851c2c6b86a08bdd6"


def fetch(url):
    request = Request(url, headers={"User-Agent": "CobaltMiner-Publication-Check"})
    with urlopen(request, timeout=40) as response:
        return response.read()


class Document(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.images = []
        self.links = []
        self.sections = 0
        self.ids = set()
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img":
            self.images.append(attrs)
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "section":
            self.sections += 1
        if "id" in attrs:
            self.ids.add(attrs["id"])


def main():
    manifest = json.loads((STAGE / "upload_manifest.json").read_text(encoding="utf-8"))
    remote_tree = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/trees/{TREE}?recursive=1"))
    assert not remote_tree.get("truncated")
    remote = {item["path"]: item for item in remote_tree["tree"] if item["type"] == "blob"}
    assert set(remote) == {item["path"] for item in manifest["files"]}
    for item in manifest["files"]:
        assert remote[item["path"]]["sha"] == item["git_blob"], item["path"]
        assert remote[item["path"]]["size"] == item["bytes"], item["path"]
    ref = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/ref/heads/main"))
    assert ref["object"]["sha"] == COMMIT
    package = next(item for item in manifest["files"] if item["path"].endswith(".zip"))
    downloaded = fetch(f"https://raw.githubusercontent.com/{REPO}/main/{package['path']}")
    digest = hashlib.sha256(downloaded).hexdigest()
    assert digest == package["sha256"] and len(downloaded) == package["bytes"]

    folder = ROOT / "deliverables/COBALT_MINER_CAFE_INTRO_20261102"
    preview = Document((folder / "미리보기.html").read_text(encoding="utf-8"))
    copy_text = (folder / "카페_복사용.html").read_text(encoding="utf-8")
    copy_doc = Document(copy_text)
    assert len(preview.images) == 6 and preview.sections == 6
    for item in preview.images:
        assert (folder / item["src"]).is_file() and item["alt"]
    for link in preview.links:
        if link and not link.startswith(("https://", "http://", "#")):
            assert (folder / link).is_file(), link
    assert not copy_doc.images
    assert {"cafe-body", "select-body"} <= copy_doc.ids
    assert len(re.findall(r"\[사진 \d{2} 위치", copy_text)) == 6
    intro = (STAGE / "repository/INTRODUCTION.md").read_text(encoding="utf-8")
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", intro)
    assert len(images) == 6
    assert all((STAGE / "repository" / item).is_file() for item in images)
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "repository": f"https://github.com/{REPO}",
        "commit": COMMIT,
        "remote_allowlist": {"status": "PASS", "files": len(remote)},
        "anonymous_download": {"status": "PASS", "bytes": len(downloaded), "sha256": digest},
        "introduction_structure_and_links": {"status": "PASS", "images": 6, "feature_sections": 5},
        "local_html_visual": {"status": "NOT_RUN", "reason": "브라우저의 로컬 파일 프로토콜 보안 정책으로 열기 차단. 우회하지 않음."},
    }
    (STAGE / "publication_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
