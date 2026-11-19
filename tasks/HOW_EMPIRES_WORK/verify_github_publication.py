"""인증 없는 원격 파일·릴리스 다운로드를 공개 허용 목록과 대조합니다."""
import concurrent.futures
import hashlib
import json
import urllib.request
from prepare_github import ROOT,PUBLIC,STAGE,REMOTE,TAG,NAME,read,sha,write

def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'HEW-Publication-Verification','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=60) as response:
        assert response.status==200
        return response.read()

def main():
    state=read(PUBLIC/'publish_state.json');assert state['phase']=='PUBLISHED'
    manifest=read(PUBLIC/'publication_manifest.json');commit=state['commit']
    prefix='https://api.github.com/repos/KIMDONGWHEE99/how-empires-work-korean-patch'
    repository=json.loads(fetch(prefix));assert not repository['private'] and repository['id']==state['repository_id']
    head=json.loads(fetch(prefix+'/commits/'+state['default_branch']));assert head['sha']==commit
    tree=json.loads(fetch(prefix+'/git/trees/'+commit+'?recursive=1'));assert not tree['truncated']
    files={r['path']:r for r in tree['tree'] if r['type']=='blob'}
    assert set(files)=={r['path'] for r in manifest['files']}
    def check(row):
        url=f'https://raw.githubusercontent.com/KIMDONGWHEE99/how-empires-work-korean-patch/{commit}/'+row['path']
        data=fetch(url);digest=hashlib.sha256(data).hexdigest()
        assert len(data)==row['size'] and digest==row['sha256']==sha(STAGE/row['path'])
        assert hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()==files[row['path']]['sha']
        return {'path':row['path'],'sha256':digest,'size':len(data),'status':'PASS'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(check,manifest['files']))
    print('공개 파일 18개 원격 지문 확인 완료',flush=True)
    release=json.loads(fetch(prefix+'/releases/tags/'+TAG));assert not release['draft'] and not release['prerelease']
    assets={r['name']:r for r in release['assets']};assert set(assets)=={NAME,'SHA256SUMS.txt'}
    assert assets[NAME]['size']==manifest['zip']['size']
    url=assets[NAME]['browser_download_url'];digest=hashlib.sha256();size=0
    request=urllib.request.Request(url,headers={'User-Agent':'HEW-Publication-Verification'})
    print('로그인 없는 ZIP 다운로드 검증 중',flush=True)
    with urllib.request.urlopen(request,timeout=90) as response:
        assert response.status==200
        for block in iter(lambda:response.read(1024*1024),b''):
            digest.update(block);size+=len(block)
    assert size==manifest['zip']['size'] and digest.hexdigest()==manifest['zip']['sha256']
    checksum=fetch(assets['SHA256SUMS.txt']['browser_download_url']);assert checksum==(STAGE/'SHA256SUMS.txt').read_bytes()
    result={'status':'PASS','repository':REMOTE,'visibility':'public','commit':commit,'default_branch':state['default_branch'],'release':release['html_url'],'tag':TAG,'public_files':len(results),'files':results,'anonymous_download':{'url':url,'bytes':size,'sha256':digest.hexdigest(),'status':'PASS'},'published_assets':2,'original_game_and_personal_saves_published':False,'game_or_patch_changes':'NONE'}
    write(PUBLIC/'publication_verified.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    output=ROOT/'validation/HOW_EMPIRES_WORK/github_publish_20261110';output.mkdir(exist_ok=True)
    write(output/'verification.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    write(output/'RESULT_REPORT.md',f'''# How Empires Work GitHub 공개 결과

2026-11-10, 사용자의 새 저장소·커밋 요청과 공개 저장소·릴리스 업로드 승인에 따라 게시했습니다.

- [전용 공개 저장소]({REMOTE})
- [업로드 커밋]({REMOTE}/commit/{commit})
- [패치 1.0.1 r2 릴리스]({release['html_url']})
- [패치 ZIP 다운로드]({url})

문서·설치기 소스·라이선스 등 18파일을 커밋했습니다. ZIP은 228,287,547바이트로 Git 기록에 넣지 않고 Releases에 첨부했으며, SHA256SUMS.txt도 함께 제공합니다. 로그인 없이 원격 18파일을 읽어 내용 지문과 Git 파일 지문을 대조했고 ZIP 전체를 내려받아 검증한 기존 ZIP의 SHA-256과 일치함을 확인했습니다.

ZIP SHA-256: `{digest.hexdigest()}`

원본 게임·개인 저장·검수 코드·원시 기록·개인 경로를 공개하지 않았습니다. 검증한 ZIP은 그대로이며 한글패치 내용·설치본·저장 및 다른 저장소는 변경하지 않았습니다. 게임 추가 실행도 하지 않았습니다. 전체 회차·모든 분기 완주 미검증과 이전판 저장 자동 복구 미포함 안내를 공개 README에 유지했습니다.

상세 원격 확인값은 [검증 기록](verification.json)에 있습니다. 로컬 공개 작업 사본은 비공개 작업 영역에 별도로 보관했습니다.
''')
    print(json.dumps({'status':'PASS','repository':REMOTE,'commit':commit,'release':release['html_url'],'public_files':len(results),'download_bytes':size},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
