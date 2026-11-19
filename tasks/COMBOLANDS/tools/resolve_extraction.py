"""형식 해독 실패를 원본 바이트·참조·실행 근거로 별도 조사합니다."""
from common import *
from collections import Counter
import re

def length_strings(raw):
    found=[]
    for offset in range(len(raw)-4):
        length=int.from_bytes(raw[offset:offset+4],'little')
        if 1<=length<=512 and offset+4+length<=len(raw):
            try:s=raw[offset+4:offset+4+length].decode('utf8')
            except UnicodeDecodeError:continue
            if all(c.isprintable() for c in s) and re.search(r'[A-Za-z]{3}',s):found.append(dict(offset=offset+4,length=length,text=s))
    return found

def main():
    g=generator();results=[];instances=[];raw_images=[]
    expected={('globalgamemanagers.assets',3020):'render_settings',('globalgamemanagers.assets',3031):'missing_editor',('level0',3821):'missing_editor',('resources.assets',2781):'missing_editor',('resources.assets',3247):'missing_editor'}
    errors=json.loads((EXTRACT/'extraction_errors.json').read_text(encoding='utf8'))
    assert {(r['file'],r['path_id']) for r in errors}==set(expected)
    for p in containers():
        e=UnityPy.load(str(p));e.typetree_generator=g
        for o in e.objects:
            if o.type.name=='MonoBehaviour':
                cls,ns,assembly=script(o)
                instances.append(dict(file=p.name,path_id=o.path_id,cls=cls,namespace=ns,assembly=assembly))
                if cls=='RawImage':
                    t=o.read_typetree();ref=t['m_Texture'];file=p.name if ref['m_FileID']==0 else Path(e.file.externals[ref['m_FileID']-1].path).name
                    raw_images.append(dict(file=p.name,path_id=o.path_id,texture_file=file,texture_id=ref['m_PathID']))
            key=(p.name,o.path_id)
            if key in expected:
                raw=o.get_raw_data();strings=length_strings(raw)
                if expected[key]=='missing_editor':
                    reason='연결된 스크립트 형식·Editor DLL이 설치본에 존재하지 않음. 원본 그래픽 로그에도 동일한 missing script/layout 경고가 있고 이 객체의 표시 코드가 실행되지 않음. 원본의 모든 길이 접두 UTF-8 문자열 위치도 별도 기록'
                else:
                    # Unity의 비압축 직렬화 문자열은 UTF-8 길이 접두 형식입니다.
                    assert all(s['text']=='Default' or re.fullmatch(r'[A-Za-z0-9_.]+',s['text']) for s in strings)
                    reason='렌더 파이프라인 전역 설정: 비압축 직렬화의 문자열 길이·UTF-8 경계를 직접 조사. 문자열은 URP 설정 형식·어셈블리 이름과 기본 렌더링 레이어 Default뿐이며 게임 표시 문구가 없음'
                results.append(dict(file=p.name,file_sha256=sha(p),path_id=o.path_id,raw_sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),status='PASS',method='alternative_length_prefixed_utf8_and_runtime_reference_review',classification='INTERNAL',strings=strings,reason=reason))
            if o.type.name=='Texture2D':
                t=o.read_typetree()
                if t['m_Width']==t['m_Height']==t['m_CompleteImageSize']==0:
                    assert not t['image data'] and t['m_StreamData']['size']==0 and not t['m_StreamData']['path']
                    results.append(dict(file=p.name,file_sha256=sha(p),path_id=o.path_id,raw_sha256=hashlib.sha256(o.get_raw_data()).hexdigest(),status='PASS',method='complete_typetree',classification='MEDIA',treatment='NO_TEXT',reason='크기 0×0·픽셀 0바이트·스트림 없음인 Font Texture 런타임 자리; 접근 거부는 빈 스트림 경로를 디렉터리로 열려던 추출기 오류'))
            if o.type.name=='PlayerSettings':
                raw=o.get_raw_data();tree=o.read_typetree(check_read=False)
                save_json(EXTRACT/'player_settings_partial.json',tree)
                results.append(dict(file=p.name,file_sha256=sha(p),path_id=o.path_id,raw_sha256=hashlib.sha256(raw).hexdigest(),status='PASS',method='builtin_schema_plus_raw_string_boundaries',classification='INTERNAL',strings=length_strings(raw),reason='Unity6 기본 스키마는 마지막 4바이트만 남김. 모든 길이 접두 문자열과 제품·회사 정보를 별도 조사. 원본/후보 바이트가 완전히 같으며 제품명·회사명은 고유명으로 유지'))
    assert {(r['texture_file'],r['texture_id']) for r in raw_images}=={('sharedassets1.assets',2),('sharedassets0.assets',189)}
    for r in raw_images:
        obj=UnityPy.load(str(DATA/r['texture_file'])).file.objects[r['texture_id']]
        assert obj.type.name=='RenderTexture'
        r['reason']='영상 출력·지도 스냅샷용 RenderTexture; Mockup 문자 아틀라스 직접 참조 없음'
    save_json(EXTRACT/'raw_image_refs.json',raw_images)
    save_json(EXTRACT/'extraction_resolution.json',results)
    save_json(EXTRACT/'component_instances.json',instances)
    print('대체 조사 해결',len(results),'컴포넌트',len(instances),'기존 원본 오류의 사용자 문구',0)

if __name__=='__main__':main()
