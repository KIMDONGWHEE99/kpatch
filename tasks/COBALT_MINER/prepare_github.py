"""카페 소개 양식과 공개 저장소의 명시적 파일 목록을 준비합니다."""
import hashlib
import html
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/COBALT_MINER/github_publish_20261102'
OUT = ROOT / 'deliverables/COBALT_MINER_CAFE_INTRO_20261102'
REPO = WORK / 'repository'
SOURCE = ROOT / 'working_private/COBALT_MINER/introduction_20261102'
STORE = 'https://store.steampowered.com/app/4601880/Cobalt_Miner/'
REMOTE = 'https://github.com/KIMDONGWHEE99/cobalt-miner-korean-patch'
ZIP_NAME = 'COBALT_MINER_KOREAN_PATCH_1.0.0_r1.zip'
ZIP_HASH = 'e80c32201aebef5941f723ca017c90dd15721c2720a4701f68f84605cda9d615'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding='utf-8', newline='\n')


def main():
    assert not OUT.exists() and not REPO.exists()
    article = dict(
        title='[게임 소개] 빚을 갚기 위해 황무지를 개척하는 광부, Cobalt Miner',
        subtitle='채굴과 제작, 자동화와 오토바이 탐험으로 이어지는 픽셀 생존 생활',
        intro=['한 덩이씩 캐낸 광물이 작업장이 되고, 더 먼 곳으로 떠날 배터리가 된다면 어떨까요?',
               'Cobalt Miner는 거대 기업에 빚을 진 광부가 되어 메마른 황무지를 개척하는 게임입니다. 2046년의 세계에서 자원을 모으고 생산 기반을 키워 갑니다.'],
        facts='PC Windows · 싱글플레이 · 채굴·제작·자동화 · 픽셀 그래픽',
        sections=[
            dict(heading='1. 광물을 캐며 시작하는 황무지 생활', file='02_mining.jpg', source='screenshot_02.jpg',
                 caption='광맥과 강 주변에서 주민에게 정보를 얻는 장면.',
                 paragraphs=['코발트와 여러 자원을 캐서 판매하거나 제작 재료로 사용합니다.',
                             '새로운 광맥을 찾아다니는 탐험과 필요한 물건을 만드는 작업이 이어집니다.']),
            dict(heading='2. 작은 작업에서 커지는 생산 기반으로', file='03_upgrades.jpg', source='screenshot_04.jpg',
                 caption='기력·이동·채굴·저장 능력 등을 개선하는 강화 화면.',
                 paragraphs=['벌어들인 돈으로 능력을 강화하고, 채굴 설비·운반 드론·전력·창고를 갖춰 생산을 늘립니다.',
                             '조금씩 작업 효율을 높여 가는 성장 과정을 즐길 수 있습니다.']),
            dict(heading='3. 배터리를 챙겨 떠나는 오토바이 탐험', file='04_motorbike.jpg', source='screenshot_01.jpg',
                 caption='전기 오토바이로 정착지 사이를 이동하는 모습.',
                 paragraphs=['전기 오토바이를 타고 새로운 지역으로 이동합니다. 먼 길을 떠날 때는 배터리도 관리해야 합니다.',
                             '탈것으로 오가는 풍경이 도보 채굴과 다른 분위기를 보여줍니다.']),
            dict(heading='4. 채굴과 휴식 사이에서 하루를 꾸리기', file='05_daily_life.jpg', source='screenshot_00.jpg',
                 caption='잠자리의 회복 안내와 보유 자원을 확인하는 화면.',
                 paragraphs=['채굴만큼 에너지와 보관 공간을 관리하는 일도 중요합니다.',
                             '공식 화면에서는 잠자리, 작업 공간, 자원 표시가 함께 보여 광부의 하루를 살펴볼 수 있습니다.']),
            dict(heading='5. 거대한 기업 아래 살아가는 사람들', file='06_corporate_world.jpg', source='screenshot_03.jpg',
                 caption='산업 차량 앞을 지나는 작은 광부와 주변 주민들.',
                 paragraphs=['정착지에서 사람들과 만나고 거래하며 기업의 통제 아래 살아가는 이야기를 접합니다.',
                             '황량한 풍경과 거대한 설비가 빚에 묶인 광부의 처지를 드러냅니다.'])
        ],
        recommendations=['자원을 모아 설비와 능력을 키우는 과정을 좋아하는 분',
                         '채굴·제작에 탐험과 이야기가 곁들여진 게임을 찾는 분',
                         '황량한 미래 배경의 픽셀 그래픽을 즐기는 분'],
        closing='여러분이라면 먼저 작업 효율을 높이실 건가요, 아니면 오토바이를 타고 새로운 광맥을 찾아 떠나실 건가요?',
        note='2026년 11월 2일 확인 기준입니다. 이미지는 공식 Steam 상점의 영문 홍보 화면이며 한글패치 적용 화면은 아닙니다.',
        credit='개발: Digital Deer Studio · 배급: MadOctopus. 이미지 출처: 공식 Steam 상점. 원본 이미지를 수정하지 않고 사용했습니다.',
        tags='#CobaltMiner #코발트마이너 #게임소개 #채굴게임 #자동화 #인디게임')
    meta = json.loads((SOURCE / 'image_sources.json').read_text(encoding='utf-8'))
    by_name = {r['file']: r for r in meta['images']}
    (OUT / 'images').mkdir(parents=True)
    image_rows = []
    for name, source in [('01_title.jpg', 'header.jpg')] + [(r['file'], r['source']) for r in article['sections']]:
        raw = (SOURCE / source).read_bytes()
        assert sha(raw) == by_name[source]['sha256']
        (OUT / 'images' / name).write_bytes(raw)
        image_rows.append(dict(filename=name, source_url=by_name[source]['url'], sha256=sha(raw)))
    template = (ROOT / 'deliverables/SOULASH_2_CAFE_INTRO_20261101/미리보기.html').read_text(encoding='utf-8')
    css = re.search(r'<style>(.*?)</style>', template, re.S).group(1)
    # 원본 양식의 폭·간격·모바일 배치는 보존하고 게임 분위기에 맞춰 강조색만 바꿉니다.
    for before, after in {'#315a40':'#81551e','#315e40':'#81551e','#477150':'#8b642d','#426849':'#81551e'}.items():
        css = css.replace(before, after)
    e = html.escape
    source = f'<p class="source">정보 출처: <a href="{STORE}">Cobalt Miner 공식 Steam 상점</a></p>'
    def figure(name, caption, cafe=False, hero=False):
        number = name.split('_')[0]
        if cafe:
            return f'<p class="facts">[사진 {number} 위치 — {e(name)} 파일을 카페의 사진 버튼으로 직접 업로드]</p>' + ('' if hero else f'<p class="source">{e(caption)}</p>')
        width, height = (460, 215) if hero else (1920, 1080)
        return f'<figure class="{"hero" if hero else "scene"}"><a href="images/{name}"><img src="images/{name}" width="{width}" height="{height}" alt="{e(caption)}"></a>' + ('' if hero else f'<figcaption>{e(caption)}</figcaption>') + '</figure>'
    def body(cafe=False):
        text = f'<main id="cafe-body"><header><p class="eyebrow">게임 소개 · COBALT MINER</p><h1>{e(article["title"])}</h1><p class="subtitle">{e(article["subtitle"])}</p></header>'
        text += figure('01_title.jpg', 'Cobalt Miner 공식 타이틀 이미지', cafe, True)
        text += ''.join(f'<p>{e(p)}</p>' for p in article['intro'])
        text += f'<p class="facts">{e(article["facts"])}</p>' + source
        for section in article['sections']:
            text += f'<section><h2>{e(section["heading"])}</h2>' + figure(section['file'], section['caption'], cafe)
            text += ''.join(f'<p>{e(p)}</p>' for p in section['paragraphs']) + source + '</section>'
        text += '<section><h2>이런 취향이라면 살펴보세요</h2><ul>'
        text += ''.join(f'<li>{e(p)}</li>' for p in article['recommendations'])
        text += f'</ul><p>{e(article["closing"])}</p></section><footer><p>{e(article["note"])}</p><p>{e(article["credit"])}</p><p class="tags">{e(article["tags"])}</p></footer></main>'
        return text
    header = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(article["title"])}</title><style>{css}</style></head><body>'
    preview_note = '<aside style="max-width:900px;margin:20px auto;padding:20px;background:#fff1d4;border:2px solid #a37725;line-height:1.8"><strong>이미지 배치 참고용입니다.</strong><br><a href="카페_복사용.html">카페 복사용 본문 열기</a> · 카페에 게시할 사진은 images 폴더에서 별도로 첨부하세요.</aside>'
    copy_note = '<aside style="max-width:900px;margin:20px auto;padding:20px;background:#fff1d4;border:1px solid #a37725;line-height:1.8"><strong>카페 복사용 본문 — 사진은 별도 업로드</strong><br>본문을 선택해 복사하고, 각 사진 위치에 같은 번호의 이미지를 첨부하세요.<br><button type="button" id="select-body" style="margin-top:12px;padding:10px 18px;font:inherit;cursor:pointer">본문 선택</button></aside>'
    script = '''<script>
document.getElementById('select-body').addEventListener('click', function () {
  const range = document.createRange();
  range.selectNodeContents(document.getElementById('cafe-body'));
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
});
</script>'''
    write(OUT / '미리보기.html', header + preview_note + body() + '</body></html>\n')
    write(OUT / '카페_복사용.html', header + copy_note + body(True) + script + '</body></html>\n')
    parts = [article['title'], article['subtitle'], '[사진 01: 01_title.jpg]', *article['intro'], article['facts']]
    md = ['# ' + article['title'], article['subtitle'], '![Cobalt Miner](images/01_title.jpg)', *article['intro'], '**' + article['facts'] + '**', f'[공식 Steam 소개]({STORE})']
    for section in article['sections']:
        parts += [section['heading'], '[사진 ' + section['file'][:2] + ': ' + section['file'] + ']', section['caption'], *section['paragraphs']]
        md += ['## ' + section['heading'], '![' + section['caption'] + '](images/' + section['file'] + ')', '*' + section['caption'] + '*', *section['paragraphs']]
    parts += ['이런 취향이라면 살펴보세요', *article['recommendations'], article['closing'], article['note'], article['credit'], STORE, article['tags']]
    md += ['## 이런 취향이라면 살펴보세요', '\n'.join('- ' + p for p in article['recommendations']), article['closing'], article['note'], article['credit'], f'[정보·이미지 출처: 공식 Steam]({STORE})', '[패치 다운로드·설치 안내](README.md)']
    write(OUT / '카페_본문.txt', '\n\n'.join(parts) + '\n')
    write(OUT / '이미지_출처.json', json.dumps(dict(source_page=STORE, date='2026-11-02', images=image_rows), ensure_ascii=False, indent=2) + '\n')
    write(OUT / '업로드_안내.txt', 'Cobalt Miner 카페 소개글 사용 안내\n\n1. 미리보기.html에서 이미지 배치를 확인합니다.\n2. 카페_복사용.html의 본문 선택 버튼을 누르고 Ctrl+C로 복사해 카페에 붙여 넣습니다.\n3. [사진 위치]에 images 폴더의 같은 번호 사진을 직접 첨부하고 표시 문구를 지웁니다. 총6장입니다.\n4. 제목은 카페_본문.txt 첫 줄을 사용하고 이미지 출처를 유지합니다.\n\n이미지는 공식 영문 홍보 화면이며 한글패치 적용 화면이 아닙니다. 카페 게시·로그인은 수행하지 않았습니다.\n')
    shutil.copytree(OUT, REPO)
    write(REPO / 'INTRODUCTION.md', '\n\n'.join(md) + '\n')
    readme = f'''# Cobalt Miner 한국어 패치 1.0.0

![Cobalt Miner](images/01_title.jpg)

[**한글패치 ZIP 다운로드**]({REMOTE}/raw/refs/heads/main/downloads/{ZIP_NAME}) · [게임 소개와 이미지6장](INTRODUCTION.md) · [확인 범위·버전 안내](releases/v1.0.0.md)

Steam 앱 **4601880 / 빌드24347666** 전용입니다. 메뉴·대사397종517위치, 실행 모듈192필드, 이미지12개와 한글 글꼴을 반영했습니다. 영어 언어 슬롯을 한국어로 바꿉니다.

## 설치와 제거

1. 게임을 종료하고 위 ZIP을 다운로드해 새 폴더에 모두 풉니다.
2. `Install.cmd`를 실행하고 Cobalt Miner 설치 폴더를 선택합니다.
3. Steam에서 게임을 실행합니다. 필요하면 설정에서 ‘한국어’를 선택합니다.
4. 제거하려면 같은 ZIP의 `Remove.cmd`를 실행합니다. 중단된 설치도 같은 설치·제거기로 복구합니다.

다른 빌드나 변조 파일에는 강제 적용하지 않습니다. 게임 원본이 필요한 차이 패치이며 게임 전체 파일은 포함하지 않습니다. 폰트와 도구 라이선스는 ZIP의 `licenses` 폴더에 있습니다.

## 확인 범위

확인된 번역 대상의 누락0건, 현재 후보 재추출·글꼴·이미지 변경 경계, 최종 ZIP 설치·복구 검사를 통과했습니다. 사용자 요청으로 추가 조사·화면 검수를 종료한 개인용 버전입니다. 엔진 문구1237개 표시 여부와 전체 시설·도움말·분기는 미확인이며, 전체 G0~G8 통과판이 아닙니다.

검수 사본의 빠른 A엔딩→이어하기→종료 오류는 원본과 후보 모두에서 재현됐고, 대기한 후보 경로는 무오류였습니다. 이전 B엔딩 검수 종료 오류 원인은 미확정입니다. 자세한 내용은 [버전 안내](releases/v1.0.0.md)를 확인하세요.

## 이미지가 포함된 소개글

[게임 소개](INTRODUCTION.md)는 같은 내용의 GitHub용 문서입니다. `미리보기.html`은 이미지 배치를, `카페_복사용.html`은 사진 위치가 표시된 복사용 본문을 제공합니다. HTML을 PC에서 열려면 저장소의 **Code → Download ZIP**으로 문서와 images 폴더를 함께 받아 주세요. 소개 이미지는 공식 영문 홍보 화면입니다.

패치 ZIP SHA-256: `{ZIP_HASH}`
'''
    write(REPO / 'README.md', readme)
    release = f'''# Cobalt Miner 한국어 패치 1.0.0

공개일: 2026-11-02 · 지원 Steam 빌드:24347666

[패치 ZIP]({REMOTE}/raw/refs/heads/main/downloads/{ZIP_NAME}) · [설치·제거 안내](../README.md)

일반397종517위치·네이티브192필드·이미지12개·필요 문자616종을 검사했습니다. 주요 대사107개·설명20개·주변 대사30개와 기재한 메뉴·설정·도입·엔딩·강화·표지를 판독했습니다.

수정6파일의 정·역 복원, ZIP23파일 허용 목록, 최종 ZIP43시험과 부분 설치 종합 판정1개를 확인했습니다. 지원할 이전 공개판은 없습니다. 시험 도구의 모형 EXE 기대값 오류는 바로잡고 같은 ZIP의 나머지 검사를 완료했습니다.

추가 조사·실행 검수는 사용자 요청으로 종료했습니다. 엔진 문자열1237개가 실제 표시되는지, 전체 시설·도움말·예비 화면·분기·회차 및 최종 후보의 새 프로세스 불러오기는 미확인입니다. G2·G5는 FAIL이며 공통 완성판의 G8도 통과하지 않았습니다.

빠른 A엔딩→이어하기→종료에서 원본과 후보 모두 같은 접근 오류가 관측됐습니다. 충분히 대기한 후보의 저장·엔딩·이어하기·종료 경로는 오류0건이었습니다. B엔딩 검수 사본 종료의 그래픽 모듈 오류는 원인 미확정입니다. 모든 환경에서 무오류를 보장하는 버전으로 표시하지 않습니다.

게임 제목·제작진·로고·모델 코드·수치와 한국어 외 언어 슬롯 일부는 보존했습니다. 이미지12개는 광고판11장과 발전소 간판1장입니다. 원본 강화 설명과 동작의 수치 차이는 게임 규칙을 고치지 않고 원문 뜻을 번역했습니다.

SHA-256: `{ZIP_HASH}`
'''
    write(REPO / 'releases/v1.0.0.md', release)
    write(REPO / 'SHA256SUMS.txt', ZIP_HASH + '  downloads/' + ZIP_NAME + '\n')
    archive = ROOT / 'release_output' / ZIP_NAME
    assert sha(archive.read_bytes()) == ZIP_HASH
    (REPO / 'downloads').mkdir()
    shutil.copyfile(archive, REPO / 'downloads' / ZIP_NAME)
    package = json.loads((ROOT / 'working_private/COBALT_MINER/package_1.0.0_r1/package.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == set(package['allowed_files']) and z.testzip() is None
    files = []
    for path in sorted(REPO.rglob('*')):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        name = path.relative_to(REPO).as_posix()
        if path.suffix in ('.md', '.html', '.txt', '.json'):
            content = raw.decode('utf-8')
            assert not re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]|file://|gh[pousr]_[A-Za-z0-9]{20}', content), name
        files.append(dict(path=name, bytes=len(raw), sha256=sha(raw), git_blob=hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()))
    expected = {'README.md', 'INTRODUCTION.md', '미리보기.html', '카페_복사용.html', '카페_본문.txt', '업로드_안내.txt', '이미지_출처.json', 'SHA256SUMS.txt', 'releases/v1.0.0.md', 'downloads/' + ZIP_NAME}
    expected.update('images/' + r['filename'] for r in image_rows)
    assert {r['path'] for r in files} == expected and len(files) == 16
    write(WORK / 'article.json', json.dumps(article, ensure_ascii=False, indent=2))
    write(WORK / 'upload_manifest.json', json.dumps(dict(repository='KIMDONGWHEE99/cobalt-miner-korean-patch', visibility='public', status='PASS', files=files, original_game_assets_included=False, private_logs_included=False), ensure_ascii=False, indent=2))
    print(json.dumps(dict(status='PASS', files=len(files), images=len(image_rows), preview=str(OUT / '미리보기.html')), ensure_ascii=False))


if __name__ == '__main__':
    main()
