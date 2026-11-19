"""공식 이미지를 보존하면서 Gorak 소개·리뷰와 카페 복사용 문서를 만듭니다."""
import hashlib
import html
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'working_private/THE_HORDE_OF_GORAK/introduction_20261102'
OUT = ROOT / 'deliverables/THE_HORDE_OF_GORAK_INTRO_20261102'
STAGE = SOURCE / 'repository/games/the-horde-of-gorak'
STORE = 'https://store.steampowered.com/app/4911050/The_Horde_of_Gorak/'
REMOTE = 'https://github.com/KIMDONGWHEE99/korean-game-patches/blob/main/games/the-horde-of-gorak'

ARTICLE = {
    'title': '[게임 소개·리뷰] 오크의 방식으로 대족장을 구출하라, The Horde of Gorak',
    'subtitle': '성 하나를 무너뜨릴 때마다 더 커지는 오크 군단',
    'intro': [
        '성을 부숴 번 자원으로 군대를 키우고, 그 군대로 더 단단한 성을 무너뜨린다면 어떨까요?',
        'The Horde of Gorak은 인간에게 붙잡힌 대족장을 구하기 위해 오크 무리를 이끄는 성장형 전략 게임입니다. 작은 야영지에서 출발해 마을과 군대를 키우며 인간의 왕국을 밀고 들어갑니다.'
    ],
    'facts': 'PC Windows · 싱글플레이 · 마을 성장·병력 강화·공성전 · 픽셀 그래픽',
    'sections': [
        {
            'heading': '1. 성벽을 두드릴수록 커지는 군단',
            'file': '02_siege.jpg', 'source': 'screenshot_05.jpg',
            'caption': '오크 병력과 공중 유닛이 성을 공격하는 공식 화면.',
            'paragraphs': [
                '성을 공격하면 핵심 자원인 성채 파편을 얻습니다. 이를 건물과 병력에 투자하면 다음 공성전을 준비할 수 있습니다.',
                '공격의 성과가 다음 강화로 이어지는 구조입니다. 눈앞의 성벽을 무너뜨리는 일과 군단을 키우는 일이 자연스럽게 맞물립니다.'
            ]
        },
        {
            'heading': '2. 작은 야영지를 전쟁의 기반으로',
            'file': '03_settlement.jpg', 'source': 'screenshot_00.jpg',
            'caption': '마을 건물과 병영 메뉴, 전투 중인 성채가 함께 보이는 화면.',
            'paragraphs': [
                '생산 건물과 군사 시설을 늘리고 강화하며 병력을 뒷받침할 기반을 마련합니다.',
                '지금 공격력을 올릴지, 이후 성장을 위해 건물에 투자할지 고민하게 됩니다. 전투가 벌어지는 화면 안에서 마을도 함께 자라는 모습이 특징입니다.'
            ]
        },
        {
            'heading': '3. 전사부터 공성 병기까지, 늘어나는 선택지',
            'file': '04_units.jpg', 'source': 'screenshot_02.jpg',
            'caption': '여러 병종과 공성 병기를 소개하는 책 형태의 유닛 도감.',
            'paragraphs': [
                '전사와 궁수, 더 강한 병력과 공성 병기를 확보해 공격을 보강합니다. 연구와 마법도 군단을 강화하는 수단입니다.',
                '도감에 보이는 다양한 병종은 다음 성장 목표를 떠올리게 합니다. 숫자 증가에 더해 전장에 새로운 병력이 등장하는 모습도 볼거리입니다.'
            ]
        },
        {
            'heading': '4. 대족장을 쫓아 더 깊은 왕국으로',
            'file': '05_world_map.jpg', 'source': 'screenshot_06.jpg',
            'caption': '공략할 성과 지역을 살펴보는 세계지도.',
            'paragraphs': [
                '성을 함락하면 인간들은 대족장을 더 강한 요새로 옮깁니다. 오크 군단은 추격을 계속하며 다음 성에 도전합니다.',
                '지도와 성채 정보는 공성전의 다음 목표를 보여 줍니다. 작은 병력들이 거대한 성을 두드리는 구도와 지역별 배경도 눈에 들어옵니다.'
            ]
        },
        {
            'heading': '5. 다음 원정에도 남는 성장',
            'file': '06_prestige.jpg', 'source': 'screenshot_04.jpg',
            'caption': '명성 점수를 투자하는 특전 목록과 원정 준비 화면.',
            'paragraphs': [
                '원정에서 얻은 명성 점수는 영구 특전에 투자할 수 있습니다. 다음 도전을 더 유리하게 시작하도록 돕는 성장 요소입니다.',
                '눈앞의 성을 공략하는 단기 목표와 이후 원정을 위한 장기 목표가 함께 있습니다. 다시 시작할 때 무엇을 먼저 강화할지도 선택하게 됩니다.'
            ]
        }
    ],
    'review': [
        ('짧은 리뷰: 전투와 성장이 한 화면에 담기는 재미', [
            '이 게임의 매력은 투자한 결과를 전장의 변화와 연결해 볼 수 있다는 점입니다. 건물을 늘리고 병력을 보강하는 일이 화면 속 오크 무리와 성채 공격으로 이어집니다. 작은 픽셀 병력과 커다란 성벽의 대비도 이 성장 과정을 보기 좋게 만들어 줍니다.',
            '성장 방향을 고르는 재미도 있습니다. 당장 성을 더 빨리 무너뜨릴 전력을 마련할지, 이후 원정에 도움이 될 기반을 챙길지 생각할 여지가 있습니다. 전투를 지켜보는 재미와 투자 순서를 정하는 재미를 함께 찾는 분에게 어울리는 구성입니다.'
        ]),
        ('취향이 갈릴 부분: 반복 자체를 즐길 수 있을까', [
            '핵심 흐름은 자원을 모으고 강화한 뒤 다음 성에 도전하는 반복입니다. 조금씩 효율을 높이는 과정이 즐겁다면 장점이 되지만, 매번 전혀 다른 사건이나 진행 방식을 기대한다면 단조롭게 느낄 수 있습니다.',
            '따라서 선택의 기준은 이야기의 결말보다 군단을 키워 가는 과정에 얼마나 끌리는지에 있습니다. 이 글에서는 장시간 플레이의 균형이나 엔딩 완성도까지 평가하지 않았습니다.'
        ])
    ],
    'recommendations': [
        '자원을 모아 건물과 병력을 강화하는 과정을 좋아하는 분',
        '반복 도전에서 조금씩 효율을 높이는 재미를 찾는 분',
        '오크 군단과 공성전을 담은 픽셀 그래픽을 즐기는 분'
    ],
    'closing': '여러분이라면 먼저 마을을 키우실 건가요, 아니면 병력을 모아 다음 성벽부터 두드리실 건가요?',
    'note': '2026년 11월 2일 작성. 공식 게임 설명과 2026년 10월 31일의 주요 화면·기능 검수 기록을 바탕으로 한 소개와 제한된 범위의 리뷰입니다. 전체 회차를 완주한 총평은 아닙니다. 이미지는 공식 Steam 영문 홍보 화면이며 한글패치 적용 화면은 아닙니다.',
    'credit': '개발: Digital Deer · 배급: Mad Octopus. 이미지 출처: 공식 Steam 상점. 원본 이미지를 수정하지 않고 사용했습니다.',
    'tags': '#TheHordeOfGorak #고라크 #게임소개 #게임리뷰 #성장형게임 #공성전 #인디게임'
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding='utf-8', newline='\n')


def main():
    assert not OUT.exists() and not STAGE.exists()
    sources = json.loads((SOURCE / 'image_sources.json').read_text(encoding='utf-8'))
    by_name = {r['file']: r for r in sources['images']}
    rows = []
    for name, original in [('01_title.jpg', 'header.jpg')] + [(s['file'], s['source']) for s in ARTICLE['sections']]:
        raw = (SOURCE / original).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assert digest == by_name[original]['sha256']
        for folder in (OUT, STAGE):
            (folder / 'images').mkdir(parents=True, exist_ok=True)
            (folder / 'images' / name).write_bytes(raw)
        rows.append({'filename': name, 'source_url': by_name[original]['url'], 'sha256': digest})
    a = ARTICLE
    md = ['# ' + a['title'], a['subtitle'], '![The Horde of Gorak](images/01_title.jpg)', *a['intro'], '**' + a['facts'] + '**', f'[공식 Steam 소개]({STORE})']
    txt = [a['title'], a['subtitle'], '[사진 01: 01_title.jpg]', *a['intro'], a['facts']]
    for s in a['sections']:
        md += ['## ' + s['heading'], f'![{s["caption"]}](images/{s["file"]})', '*' + s['caption'] + '*', *s['paragraphs']]
        txt += [s['heading'], f'[사진 {s["file"][:2]}: {s["file"]}]', s['caption'], *s['paragraphs']]
    for title, paragraphs in a['review']:
        md += ['## ' + title, *paragraphs]
        txt += [title, *paragraphs]
    tail = ['## 이런 취향이라면 살펴보세요', '\n'.join('- ' + p for p in a['recommendations']), a['closing'], '---', a['note'], a['credit'], f'[정보·이미지 출처: 공식 Steam]({STORE})']
    md += tail + ['[한글패치 안내](README.md)']
    txt += ['이런 취향이라면 살펴보세요', *a['recommendations'], a['closing'], a['note'], a['credit'], STORE, a['tags']]
    # 외부 게시 파일에는 개인 설치 경로나 비공개 분석 기록을 넣지 않습니다.
    for folder in (OUT, STAGE):
        write(folder / 'INTRODUCTION.md', '\n\n'.join(md) + '\n')
    write(OUT / '카페_본문.txt', '\n\n'.join(txt) + '\n')
    write(OUT / '이미지_출처.json', json.dumps({'date': '2026-11-02', 'source_page': STORE, 'images': rows}, ensure_ascii=False, indent=2) + '\n')
    css = re.search(r'<style>(.*?)</style>', (ROOT / 'deliverables/COBALT_MINER_CAFE_INTRO_20261102/미리보기.html').read_text(encoding='utf-8'), re.S).group(1)
    css = css.replace('#81551e', '#315a40').replace('#8b642d', '#477150')
    e = html.escape

    def figure(name, caption, cafe=False):
        if cafe:
            return f'<p class="facts">[사진 {name[:2]} 위치 — {e(name)}]</p><p class="source">{e(caption)}</p>'
        return f'<figure class="{"hero" if name.startswith("01") else "scene"}"><img src="images/{name}" alt="{e(caption)}"><figcaption>{e(caption)}</figcaption></figure>'

    def body(cafe=False):
        result = f'<main id="cafe-body"><header><p class="eyebrow">게임 소개 · 리뷰</p><h1>{e(a["title"])}</h1><p class="subtitle">{e(a["subtitle"])}</p></header>'
        result += figure('01_title.jpg', 'The Horde of Gorak 공식 타이틀 이미지', cafe)
        result += ''.join(f'<p>{e(p)}</p>' for p in a['intro']) + f'<p class="facts">{e(a["facts"])}</p>'
        result += f'<p class="source"><a href="{STORE}">공식 Steam 소개</a></p>'
        for s in a['sections']:
            result += f'<section><h2>{e(s["heading"])}</h2>' + figure(s['file'], s['caption'], cafe)
            result += ''.join(f'<p>{e(p)}</p>' for p in s['paragraphs']) + '</section>'
        for heading, paragraphs in a['review']:
            result += f'<section><h2>{e(heading)}</h2>' + ''.join(f'<p>{e(p)}</p>' for p in paragraphs) + '</section>'
        result += '<section><h2>이런 취향이라면 살펴보세요</h2><ul>' + ''.join(f'<li>{e(p)}</li>' for p in a['recommendations']) + f'</ul><p>{e(a["closing"])}</p></section>'
        result += f'<footer><p>{e(a["note"])}</p><p>{e(a["credit"])}</p><p><a href="{STORE}">정보·이미지 출처: 공식 Steam</a></p><p class="tags">{e(a["tags"])}</p></footer></main>'
        return result

    header = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(a["title"])}</title><style>{css}</style></head><body>'
    note = '<aside style="max-width:900px;margin:20px auto;padding:16px;background:#f3f7f0">이미지 배치 미리보기 · <a href="카페_복사용.html">카페 복사용 본문</a></aside>'
    copy_note = '<aside style="max-width:900px;margin:20px auto;padding:16px;background:#f3f7f0">본문을 복사한 뒤 사진 위치에 같은 번호 이미지를 첨부하세요. <button type="button" id="select-body">본문 선택</button></aside>'
    script = '<script>document.getElementById("select-body").addEventListener("click",function(){const r=document.createRange();r.selectNodeContents(document.getElementById("cafe-body"));const s=window.getSelection();s.removeAllRanges();s.addRange(r);});</script>'
    write(OUT / '미리보기.html', header + note + body() + '</body></html>\n')
    write(OUT / '카페_복사용.html', header + copy_note + body(True) + script + '</body></html>\n')
    write(OUT / 'README.md', f'# The Horde of Gorak 소개·리뷰\n\n미리보기.html에서 이미지 배치를 확인할 수 있습니다. 카페_복사용.html의 본문 선택 버튼으로 글을 복사하고 images 폴더의 같은 번호 사진을 첨부합니다. 카페 게시·로그인은 하지 않았습니다.\n\n[온라인 소개·리뷰]({REMOTE}/INTRODUCTION.md) · [한글패치 안내]({REMOTE}/README.md)\n\n공식 영문 홍보 화면이며 한글패치 적용 화면은 아닙니다. 본문과 이미지 출처를 함께 유지하세요.\n')
    write(SOURCE / 'article.json', json.dumps(a, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(OUT.with_suffix('.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(OUT).as_posix())
    print(json.dumps({'article': str(OUT / 'INTRODUCTION.md'), 'images': len(rows), 'sections': len(a['sections']), 'review_sections': len(a['review'])}, ensure_ascii=True))


if __name__ == '__main__':
    main()
