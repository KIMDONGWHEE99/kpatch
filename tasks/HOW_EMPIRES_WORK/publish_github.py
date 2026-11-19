"""전용 저장소 생성·커밋·검증된 ZIP의 릴리스 첨부를 수행합니다."""
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from prepare_github import PUBLIC,STAGE,REMOTE,TAG,NAME,sha,read,write

OWNER='KIMDONGWHEE99'
REPOSITORY='how-empires-work-korean-patch'
FULL=OWNER+'/'+REPOSITORY
ENV=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')

def main():
    manifest=read(PUBLIC/'publication_manifest.json')
    for row in manifest['files']:assert sha(STAGE/row['path'])==row['sha256']
    archive=Path(manifest['zip']['path']);assert sha(archive)==manifest['zip']['sha256']
    p=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,env=ENV,timeout=30)
    assert p.returncode==0,'기존 GitHub 로그인 정보를 사용할 수 없습니다.'
    credentials=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
    token=credentials['password']
    def api(method,path,payload=None,raw=None,content_type='application/json'):
        url=path if path.startswith('https://') else 'https://api.github.com'+path
        assert urllib.parse.urlsplit(url).hostname in ('api.github.com','uploads.github.com')
        data=raw if raw is not None else (json.dumps(payload,ensure_ascii=False).encode('utf8') if payload is not None else None)
        request=urllib.request.Request(url,data=data,method=method,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':content_type,'User-Agent':'HEW-Korean-Patch-Publisher'})
        with urllib.request.urlopen(request,timeout=600) as response:return json.load(response)
    user=api('GET','/user');assert user['login']==OWNER
    try:
        api('GET','/repos/'+FULL)
    except urllib.error.HTTPError as e:
        assert e.code==404,e.code
    else:raise RuntimeError('같은 이름의 저장소가 이미 있으므로 덮어쓰지 않습니다.')
    repository=api('POST','/user/repos',{'name':REPOSITORY,'description':'How Empires Work 비공식 한국어 패치 — Windows Steam 빌드 26482667','private':False,'auto_init':True,'has_issues':True,'has_projects':False,'has_wiki':False})
    assert repository['full_name']==FULL and not repository['private']
    state={'repository_id':repository['id'],'repository':repository['html_url'],'default_branch':repository['default_branch'],'phase':'REPOSITORY_CREATED'}
    write(PUBLIC/'publish_state.json',json.dumps(state,ensure_ascii=False,indent=2))
    print('저장소 생성 완료',repository['html_url'],flush=True)
    local=PUBLIC/'repository';assert not local.exists()
    def git(args,cwd=None):
        result=subprocess.run(['git',*args],cwd=cwd,env=ENV,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=180)
        assert result.returncode==0,(args,result.stderr[-2000:])
        return result.stdout.strip()
    for attempt in range(6):
        result=subprocess.run(['git','ls-remote',REMOTE+'.git','refs/heads/'+state['default_branch']],env=ENV,capture_output=True,text=True,timeout=30)
        if result.returncode==0 and result.stdout.strip():break
        time.sleep(2)
    else:raise RuntimeError('초기 기본 브랜치가 생성되지 않았습니다.')
    git(['clone','--quiet',REMOTE+'.git',str(local)])
    git(['config','user.name',OWNER],local)
    git(['config','user.email',str(user['id'])+'+'+OWNER+'@users.noreply.github.com'],local)
    git(['config','core.autocrlf','false'],local)
    git(['switch','-c','codex/publish-1.0.1'],local)
    for row in manifest['files']:
        dest=local/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(STAGE/row['path'],dest)
    git(['add','--',*[r['path'] for r in manifest['files']]],local)
    changed=git(['diff','--cached','--name-only'],local).splitlines()
    assert set(changed)=={r['path'] for r in manifest['files']}
    git(['commit','-m','한국어 패치 1.0.1 r2와 설치·검증 안내 공개'],local)
    commit=git(['rev-parse','HEAD'],local)
    git(['push','origin','HEAD:refs/heads/'+state['default_branch']],local)
    state.update(commit=commit,phase='COMMITTED');write(PUBLIC/'publish_state.json',json.dumps(state,ensure_ascii=False,indent=2))
    print('커밋 업로드 완료',commit,flush=True)
    remote=api('GET','/repos/'+FULL+'/commits/'+state['default_branch']);assert remote['sha']==commit
    release=api('POST','/repos/'+FULL+'/releases',{'tag_name':TAG,'target_commitish':commit,'name':'한국어 패치 1.0.1 r2','body':(PUBLIC/'release_notes.md').read_text(encoding='utf8'),'draft':True,'prerelease':False})
    state.update(release_id=release['id'],phase='DRAFT_RELEASE');write(PUBLIC/'publish_state.json',json.dumps(state,ensure_ascii=False,indent=2))
    assets=[]
    for path,media in [(archive,'application/zip'),(STAGE/'SHA256SUMS.txt','text/plain')]:
        url=release['upload_url'].split('{',1)[0]+'?'+urllib.parse.urlencode({'name':path.name})
        print('파일 첨부 중',path.name,path.stat().st_size,flush=True)
        asset=api('POST',url,raw=path.read_bytes(),content_type=media)
        assert asset['state']=='uploaded' and asset['size']==path.stat().st_size and asset['name']==path.name
        if asset.get('digest'):assert asset['digest']=='sha256:'+sha(path)
        assets.append({'id':asset['id'],'name':asset['name'],'size':asset['size'],'url':asset['browser_download_url'],'sha256':sha(path)})
        state['assets']=assets;write(PUBLIC/'publish_state.json',json.dumps(state,ensure_ascii=False,indent=2))
    release=api('PATCH','/repos/'+FULL+'/releases/'+str(release['id']),{'draft':False,'make_latest':'true'})
    assert not release['draft'] and release['tag_name']==TAG
    state.update(release=release['html_url'],phase='PUBLISHED');write(PUBLIC/'publish_state.json',json.dumps(state,ensure_ascii=False,indent=2))
    assert not git(['status','--porcelain'],local)
    print(json.dumps({'repository':repository['html_url'],'commit':commit,'release':release['html_url'],'assets':len(assets)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
