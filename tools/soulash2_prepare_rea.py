"""공식 Ghidra/JDK ZIP을 비공개 작업 폴더에 고정하고 내용 지문을 확인한다."""
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "working_private/SOULASH_2/toolchain"
GHIDRA_SHA256 = "ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db"
SOURCES = [
    ("ghidra", "NationalSecurityAgency/ghidra", "Ghidra_12.1.4_build", "ghidra_12.1.4_PUBLIC_20260921.zip"),
    ("jdk", "adoptium/temurin21-binaries", "jdk-21.0.12.1%2B1", "OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip"),
]

def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Soulash2-Korean-Patch-Toolchain"}), timeout=90)

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    selected = []
    for role, repo, tag, filename in SOURCES:
        api = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        with request(api) as response:
            metadata = json.load(response)
        (DEST / (role + "_release.json")).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        asset = next(a for a in metadata["assets"] if a["name"] == filename)
        if role == "ghidra":
            expected = GHIDRA_SHA256
        else:
            checksum_asset = next(a for a in metadata["assets"] if a["name"] == filename + ".sha256.txt")
            with request(checksum_asset["browser_download_url"]) as response:
                checksum = response.read().decode("ascii")
            (DEST / checksum_asset["name"]).write_text(checksum, encoding="ascii")
            expected = checksum.split()[0].lower()
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise RuntimeError("공식 체크섬의 형식이 잘못되었습니다.")
        selected.append({"role": role, "url": asset["browser_download_url"], "filename": filename,
                         "size": asset["size"], "sha256": expected, "release": metadata["html_url"]})
    required = sum(item["size"] for item in selected) * 4
    free = shutil.disk_usage(DEST).free
    print(json.dumps({"archives": selected, "required_upper_bytes": required, "free_bytes": free}), flush=True)
    if free < required:
        raise RuntimeError("작업 공간의 여유 용량이 부족합니다.")
    for item in selected:
        archive = DEST / item["filename"]
        if archive.exists():
            if sha256(archive) != item["sha256"]:
                raise RuntimeError(f"기존 ZIP의 내용 지문 불일치: {archive.name}")
        else:
            partial = archive.with_suffix(".download")
            if partial.exists():
                raise RuntimeError(f"이전 불완전 다운로드가 존재합니다: {partial.name}")
            written = 0
            next_report = 32 * 1024 * 1024
            with request(item["url"]) as response, partial.open("xb") as stream:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    stream.write(chunk)
                    written += len(chunk)
                    if written >= next_report:
                        print(f"{archive.name}: {written}/{item['size']}", flush=True)
                        next_report += 32 * 1024 * 1024
            if written != item["size"] or sha256(partial) != item["sha256"]:
                raise RuntimeError(f"다운로드 무결성 불일치: {archive.name}")
            partial.rename(archive)
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            roots = {n.split("/")[0] for n in names if n}
            if len(roots) != 1:
                raise RuntimeError("ZIP 최상위 경로가 예상과 다릅니다.")
            extracted = DEST / next(iter(roots))
            for name in names:
                target = (DEST / name).resolve()
                if not target.is_relative_to(DEST.resolve()):
                    raise RuntimeError("ZIP에 작업 폴더 밖 경로가 포함되어 있습니다.")
            if extracted.exists():
                raise RuntimeError(f"기존 추출 폴더를 덮어쓰지 않습니다: {extracted.name}")
            package.extractall(DEST)
            item["root"] = str(extracted)
            item["uncompressed_bytes"] = sum(i.file_size for i in package.infolist())
            item["file_count"] = sum(not i.is_dir() for i in package.infolist())
        print(json.dumps({"verified": item}), flush=True)
    (DEST / "toolchain_manifest.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
