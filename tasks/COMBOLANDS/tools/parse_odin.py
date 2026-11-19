"""Odin 바이너리 형식의 항목 경계·문자열을 끝까지 읽습니다."""
from common import *
import struct
from collections import Counter

class Reader:
    def __init__(self,data):self.data=data;self.pos=0;self.rows=[];self.stack=[];self.types={}
    def read(self,n):
        assert n>=0 and self.pos+n<=len(self.data),(self.pos,n,len(self.data))
        b=self.data[self.pos:self.pos+n];self.pos+=n;return b
    def num(self,n):return int.from_bytes(self.read(n),'little',signed=False)
    def string(self):
        width=self.num(1);assert width in [0,1]
        n=self.num(4);return self.read(n*(width+1)).decode('utf-16-le' if width else 'latin1')
    def type(self):
        tag=self.num(1)
        if tag==47:
            index=self.num(4);text=self.string();self.types[index]=text;return text
        if tag==48:return self.types[self.num(4)]
        assert tag==46,tag
        return None
    def run(self):
        while self.pos<len(self.data):
            offset=self.pos;tag=self.num(1)
            if tag==49:assert self.pos==len(self.data);break
            assert 1<=tag<=51,tag
            name=self.string() if tag in [1,3,50] or (9<=tag<=45 and tag%2==1) else None
            row=dict(offset=offset,tag=tag,name=name,parents=list(self.stack))
            if tag in [1,2,3,4]:
                row['type']=self.type()
                if tag<=2:row['id']=self.num(4)
                self.stack.append(name or row['type'] or '?')
            elif tag==5:assert self.stack;self.stack.pop()
            elif tag==6:row['count']=self.num(8);self.stack.append('[]')
            elif tag==7:assert self.stack[-1]=='[]';self.stack.pop()
            elif tag==8:count=self.num(4);size=self.num(4);row['count']=count;row['size']=size;self.read(count*size)
            elif tag in [9,10,11,12,23,24,25,26,31,32]:self.read(4)
            elif tag in [15,16,17,18,43,44]:self.read(1)
            elif tag in [19,20,21,22,37,38]:self.read(2)
            elif tag in [27,28,29,30,33,34]:self.read(8)
            elif tag in [13,14,35,36,41,42]:self.read(16)
            elif tag in [39,40,50,51]:row['value']=self.string()
            elif tag in [45,46]:pass
            else:raise ValueError((offset,tag))
            row['end']=self.pos;self.rows.append(row)
        assert self.pos==len(self.data) and not self.stack,(self.pos,len(self.data),self.stack)
        return self.rows

def main():
    results=[];errors=[]
    for r in json.loads((EXTRACT/'odin_payloads.json').read_text(encoding='utf8')):
        data=r.pop('data')
        try:
            assert not data['SerializedBytesString'] and not data['SerializationNodes'] and not data['PrefabModifications']
            nodes=Reader(bytes(data['SerializedBytes'])).run()
            results.append(dict(**r,bytes_sha256=hashlib.sha256(bytes(data['SerializedBytes'])).hexdigest(),nodes=nodes))
        except Exception as e:errors.append(dict(**r,error=str(e)))
    save_json(EXTRACT/'odin_nodes.json',results);save_json(EXTRACT/'odin_errors.json',errors)
    values=[dict(file=r['file'],path_id=r['path_id'],cls=r['cls'],**n) for r in results for n in r['nodes'] if 'value' in n]
    save_json(EXTRACT/'odin_strings.json',values)
    print('완전 해석',len(results),'실패',len(errors),'문자열 값',len(values))
    for r in values[:60]:print(r['cls'],r['name'],repr(r['value']))
    if errors:print(errors[:3])

if __name__=='__main__':main()
