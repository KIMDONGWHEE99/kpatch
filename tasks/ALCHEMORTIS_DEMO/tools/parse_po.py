from pathlib import Path
import re,json
p=Path('extracted_private/ALCHEMORTIS_DEMO/steam_25423154/raw/resources/translations/en.po');s=p.read_text(encoding='utf-8'); rows=[]; key=None; value=None; field=None
for line in s.splitlines():
 if line.startswith('msgid '):
  if key is not None: rows.append({'key':key,'source':value})
  key=json.loads(line[6:]);value='';field='key'
 elif line.startswith('msgstr '):value=json.loads(line[7:]);field='value'
 elif line.startswith('"'):
  if field=='key':key+=json.loads(line)
  else:value+=json.loads(line)
if key is not None:rows.append({'key':key,'source':value})
Path('working_private/ALCHEMORTIS_DEMO/discovery/english.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print('Total entries',len(rows)-1,'total chars',sum(len(x['source']) for x in rows),'empty',sum(not x['source'] for x in rows))
print('\n'.join(x['key']+' = '+x['source'] for x in rows[:45]))
