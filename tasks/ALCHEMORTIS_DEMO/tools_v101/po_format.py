"""위치와 복수형을 보존하는 게임 PO 번역표 판독·작성 도구."""
import json

def parse(text):
    rows=[];row=None;field=None
    for line in text.splitlines():
        if line.startswith('msgid '):
            if row is not None:rows.append(row)
            row={'key':json.loads(line[6:]),'plural_key':None,'forms':{},'text':''};field='key'
        elif line.startswith('msgid_plural '):row['plural_key']=json.loads(line[13:]);field='plural_key'
        elif line.startswith('msgstr '):row['text']=json.loads(line[7:]);field='text'
        elif line.startswith('msgstr['):
            first,value=line.split(' ',1);field=int(first[7:-1]);row['forms'][field]=json.loads(value)
        elif line.startswith('"') and row is not None:
            if isinstance(field,int):row['forms'][field]+=json.loads(line)
            else:row[field]+=json.loads(line)
    if row is not None:rows.append(row)
    assert len({r['key'] for r in rows})==len(rows),'중복 키'
    return rows

def render(rows, translations, locale='ko'):
    header='Content-Type: text/plain; charset=UTF-8\nLanguage: '+locale+'\nPlural-Forms: nplurals=1; plural=0;\n'
    blocks=['msgid ""\nmsgstr '+json.dumps(header,ensure_ascii=False)]
    for row in rows:
        if not row['key']:continue
        value=translations[row['key']]
        lines=['msgid '+json.dumps(row['key'],ensure_ascii=False)]
        if row['plural_key'] is not None:
            lines+=['msgid_plural '+json.dumps(row['plural_key'],ensure_ascii=False),'msgstr[0] '+json.dumps(value,ensure_ascii=False)]
        else:lines+=['msgstr '+json.dumps(value,ensure_ascii=False)]
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)+'\n'

if __name__=='__main__':
    from pck_tools import EXTRACTED,WORK
    rows=parse((EXTRACTED/'raw/resources/translations/en.po').read_text(encoding='utf-8'))
    path=WORK/'translation';path.mkdir(exist_ok=True)
    (path/'source.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    for start in range(1,len(rows),100):
        chunk=rows[start:start+100]
        (path/f'source_{start:04}.txt').write_text('\n'.join(f"{i+start}\t{r['key']}\t{json.dumps(r['text'] or r['forms'],ensure_ascii=False)}" for i,r in enumerate(chunk)),encoding='utf-8')
    print(len(rows)-1,'항목',sum(bool(r['forms']) for r in rows),'복수형',sum(not r['text'] and not r['forms'] for r in rows),'빈 항목')
