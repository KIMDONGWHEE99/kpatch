"""Addressables 2.9.1의 이진 카탈로그를 키→위치→옵션 순서로 해석합니다."""
from common import *
import struct,json,hashlib
from build_candidate import CANDIDATE,REPORT

NULL=0xffffffff
class Catalog:
    def __init__(self,data):
        self.data=data;self.header=self.values(0,8);assert self.header[1]==2
        self.keys=[];self.locations={}
        for key,location_set in self.array(self.header[2],2):
            value=self.object(key)
            locs=[v[0] for v in self.array(location_set,1)]
            self.keys.append({'key':value,'locations':locs})
            for offset in locs:self.location(offset)
    def values(self,offset,count):
        assert 0<=offset and offset+count*4<=len(self.data),(offset,count)
        return struct.unpack_from('<'+'I'*count,self.data,offset)
    def array(self,offset,width):
        if offset==NULL:return []
        size=self.values(offset-4,1)[0];assert size%(width*4)==0
        return [self.values(p,width) for p in range(offset,offset+size,width*4)]
    def string(self,offset,separator=''):
        if offset==NULL:return None
        if offset&0x40000000:
            assert separator
            parts=[];seen=set()
            while offset!=NULL:
                ptr=offset&0x3fffffff;assert ptr not in seen;seen.add(ptr)
                part,offset=self.values(ptr,2);parts.append(self.string(part))
            return separator.join(reversed(parts))
        encoding='utf-16-le' if offset&0x80000000 else 'ascii';offset&=0x3fffffff
        length=self.values(offset-4,1)[0];assert offset+length<=len(self.data)
        return self.data[offset:offset+length].decode(encoding)
    def typename(self,offset):
        assembly,name=self.values(offset,2)
        return self.string(assembly,'.'),self.string(name,'.')
    def object(self,offset):
        if offset==NULL:return None
        type_id,object_id=self.values(offset,2);assembly,cls=self.typename(type_id)
        if cls=='System.String':
            ptr=self.values(object_id,1)[0];sep=chr(struct.unpack_from('<H',self.data,object_id+4)[0])
            return self.string(ptr,'' if sep=='\0' else sep)
        if cls=='System.Int32':return struct.unpack_from('<i',self.data,object_id)[0]
        return {'type':cls,'offset':object_id}
    def location(self,offset):
        if offset in self.locations:return
        key,internal,provider,deps,dep_hash,extra,typename=self.values(offset,7)
        row={'offset':offset,'key':self.string(key,'/'),'internal':self.string(internal,'/'),'provider':self.string(provider,'.'),'dependencies':[v[0] for v in self.array(deps,1)],'dependency_hash':dep_hash,'type':self.typename(typename),'extra':self.object(extra)}
        self.locations[offset]=row
        if isinstance(row['extra'],dict) and row['extra']['type'].endswith('AssetBundleRequestOptions'):
            p=row['extra']['offset'];hash_id,name_id,crc,size,common=self.values(p,5)
            timeout,redirect,retry,flags=struct.unpack_from('<hBBI',self.data,common)
            assert hash_id+16<=len(self.data)
            row['options']={'offset':p,'hash_offset':hash_id,'hash_bytes':self.data[hash_id:hash_id+16].hex(),'bundle_name':self.string(name_id,'_'),'crc':crc,'size':size,'timeout':timeout,'redirect':redirect,'retry':retry,'flags':flags}
        for dependency in row['dependencies']:self.location(dependency)

def update():
    src=next((DATA/'StreamingAssets/aa').glob('catalog*.bin'));dest=CANDIDATE/src.relative_to(SOURCE)
    original=src.read_bytes();parsed=Catalog(original);output=bytearray(original);changes=[]
    for row in parsed.locations.values():
        if 'options' not in row:continue
        name=row['internal'].replace('\\','/').rsplit('/',1)[-1]
        path=DATA/'StreamingAssets/aa/StandaloneWindows64'/name
        assert path.is_file(),row
        opts=row['options'];assert opts['size']==path.stat().st_size,(name,opts)
        candidate=CANDIDATE/path.relative_to(SOURCE)
        if sha(path)==sha(candidate):continue
        newhash=bytes.fromhex(sha(candidate)[:32]);newhashoffset=len(output);output.extend(newhash)
        struct.pack_into('<I',output,opts['offset'],newhashoffset)
        struct.pack_into('<II',output,opts['offset']+8,0,candidate.stat().st_size)
        changes.append({'file':str(path.relative_to(SOURCE)),'location_offset':row['offset'],'options_offset':opts['offset'],'before':opts,'after_size':candidate.stat().st_size,'after_hash_bytes':newhash.hex(),'candidate_sha256':sha(candidate)})
    dest.write_bytes(output);check=Catalog(dest.read_bytes());assert parsed.keys==check.keys
    assert set(parsed.locations)==set(check.locations)
    changed_locations={r['location_offset'] for r in changes}
    for offset,old in parsed.locations.items():
        new=check.locations[offset]
        if offset not in changed_locations:assert old==new
        else:
            assert {k:v for k,v in old.items() if k!='options'}=={k:v for k,v in new.items() if k!='options'}
            expected=next(r for r in changes if r['location_offset']==offset)
            assert new['options']['size']==expected['after_size'] and new['options']['crc']==0 and new['options']['hash_bytes']==expected['after_hash_bytes']
    write_json(EXTRACT/'catalog_parsed.json',{'keys':parsed.keys,'locations':list(parsed.locations.values())})
    write_json(REPORT/'catalog.json',{'original_sha256':sha(src),'candidate_sha256':sha(dest),'key_count':len(parsed.keys),'location_count':len(parsed.locations),'changes':changes,'policy':'수정된 로컬 묶음의 CRC 0 및 새 콘텐츠 해시. 설치기는 SHA-256으로 파일 내용 검증. 로딩 경로·의존 관계는 보존.','status':'PASS'})
    print('catalog',len(parsed.keys),'keys',len(parsed.locations),'locations',len(changes),'changed bundles')
if __name__=='__main__':update()
