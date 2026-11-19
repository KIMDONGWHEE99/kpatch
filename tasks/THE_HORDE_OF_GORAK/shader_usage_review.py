"""원본 DAT의 셰이더 자료·장면/레이어 효과·이벤트 참조를 전수 대조한다."""
import collections
import json
import re
import struct
from pathlib import Path

from dat_container import DatFile, sha

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'working_private/THE_HORDE_OF_GORAK'
RAW = WORK / 'investigation_20261031/classification/raw_frames.json'
PACKAGE = ROOT / 'extracted_private/THE_HORDE_OF_GORAK/steam_26336311/nebula_03/package.json'
SOURCE = ROOT / 'source_original/THE_HORDE_OF_GORAK/steam_26336311/THOG.dat'


def main():
    dat = DatFile.load(SOURCE)
    package = json.loads(PACKAGE.read_text(encoding='utf-8'))
    raw = json.loads(RAW.read_text(encoding='utf-8'))
    objects = dat.one(0x2255)
    assert len(objects.decoded) == 1006 * 4 and objects.decoded == bytes(1006 * 4)
    assert all(item['Shader']['ShaderHandle'] == -1 for item in package['FrameItems']['Items'].values())
    assert not package['ShaderBank']['Shaders'] and not package['DX9ShaderBank']['Shaders']
    bank_chunks = [chunk.location for chunk in dat.chunks if chunk.chunk_id in (0x2243, 0x225A)]
    assert not bank_chunks
    frames = []
    for index, (chunk, semantic) in enumerate(zip([c for c in dat.chunks if c.chunk_id == 0x3333], package['Frames'])):
        effect = next(c for c in chunk.children if c.chunk_id == 0x3349)
        layer = next(c for c in chunk.children if c.chunk_id == 0x3345)
        assert len(effect.decoded) == 16
        assert struct.unpack_from('<ii', effect.decoded, 8) == (-1, 0)
        assert semantic['FrameEffects']['ShaderHandle'] == -1
        layers = semantic['FrameLayers']['Layers']
        assert len(layer.decoded) == len(layers) * 20
        for i, item in enumerate(layers):
            assert struct.unpack_from('<iii', layer.decoded, i * 20 + 8) == (-1, 0, 0)
            assert item['Effect']['ShaderHandle'] == -1 and not item['Effect']['ShaderParameters']
        frames.append({'frame': index, 'effect_location': effect.location, 'effect_sha256': sha(effect.decoded),
                       'layer_location': layer.location, 'layer_sha256': sha(layer.decoded), 'layers': len(layers),
                       'shader_handle': -1, 'shader_parameter_count': 0})
    hits, shader_strings, layer_actions = [], [], []
    operations = expressions = 0
    for frame in raw:
        for event in frame['events']:
            for kind in ('Conditions', 'Actions'):
                for operation in event[kind]:
                    operations += 1
                    if kind == 'Actions' and ((operation['type'] == -3 and operation['num'] in (32, 33, 34))
                                             or (operation['type'] >= 0 and operation['num'] in (63, 64, 67))):
                        hits.append({'frame': frame['frame'], 'event': event['index'], 'operation': operation})
                    if kind == 'Actions' and operation['type'] == 36:
                        layer_actions.append({'frame': frame['frame'], 'event': event['index'],
                                              'target': frame['chunk'], 'operation': operation})
                    for parameter in operation['parameters']:
                        expressions += len(parameter['expressions'])
                        for text in parameter['strings']:
                            if re.search(r'(?i)\.fx\b|hlsl|shader|sampler\w*|float[234]x?[234]?|technique|SV_Target', text['value']):
                                shader_strings.append({'frame': frame['frame'], 'event': event['index'], 'text': text})
    assert not hits and not shader_strings
    assert collections.Counter(item['operation']['num'] for item in layer_actions) == {111: 2, 112: 3}
    assert all(not p['strings'] for item in layer_actions for p in item['operation']['parameters'])
    report = {'status': 'PASS', 'source_sha256': sha(dat.original), 'semantic_sha256': sha(PACKAGE.read_bytes()),
              'raw_frames_sha256': sha(RAW.read_bytes()), 'tool_sha256': sha(Path(__file__).read_bytes()),
              'object_shader_chunk': {'location': objects.location, 'decoded_sha256': sha(objects.decoded),
                                      'records': 1006, 'all_lengths_zero': True},
              'shader_bank_chunks': bank_chunks, 'semantic_shader_banks_empty': True,
              'frames': frames, 'layers_total': sum(f['layers'] for f in frames),
              'event_operations': operations, 'event_expressions': expressions,
              'shader_operation_hits': hits, 'shader_source_string_hits': shader_strings,
              'layer_extension_actions': layer_actions,
              'conclusion': '원본 DAT에 사용자 셰이더은행·객체셰이더·장면/레이어셰이더·효과설정 이벤트·셰이더소스 문자열을 찾지 못함. 모든 효과 ShaderHandle=-1.',
              'limitations': 'DAT 내용의 보조 근거이며 엔진 자체의 기본 렌더링 효과 생성·D3D 진단 함수 실행 불가능성을 단독 증명하지 않음. 네이티브 호출 경계와 함께 판단.'}
    path = WORK / 'investigation_20261031/shader_usage_review.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'objects': 1006, 'frames': len(frames),
                      'layers': report['layers_total'], 'operations': operations, 'expressions': expressions}))


if __name__ == '__main__':
    main()
