"""실제 그래픽 실행 중인 격리 사본에서 정해진 화면을 순서대로 확보합니다."""
import argparse
import json
import re
import time
from pathlib import Path
from pck_tools import WORK, EXTRACTED


def request(stage, identifier, operation, **values):
    # 같은 화면을 재확인할 때 이전 기록을 새 캡처로 오인하지 않습니다.
    try:
        previous_count = len(json.loads((stage / 'screens.json').read_text(encoding='utf-8')))
    except (FileNotFoundError, json.JSONDecodeError):
        previous_count = 0
    command = dict(values, id=identifier, operation=operation)
    temporary = stage / 'command_next.json'
    temporary.write_text(json.dumps(command, ensure_ascii=False), encoding='utf-8')
    temporary.replace(stage / 'command.json')
    deadline = time.monotonic() + values.get('wait', 1.2) + 15
    while time.monotonic() < deadline:
        try:
            events = json.loads((stage / 'screens.json').read_text(encoding='utf-8'))
            matching = [event for event in events[previous_count:] if event['id'] == identifier]
            if matching:
                event = matching[-1]
                assert event['status'] == 'PASS' and event['capture_error'] == 0, identifier
                print(identifier + ': CAPTURED', flush=True)
                return event
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(0.2)
    raise TimeoutError(identifier)


def execute(stage, phase, begin=None, end=None):
    # 화면 확보는 육안 판정을 대신하지 않습니다. 각 단계 후 실제 그림을 별도로 읽습니다.
    if phase == 'menus':
        sequence = [
            ('01_main', 'capture', {}),
            ('02_video', 'main_options', {}),
            ('03_audio', 'tab', {'index': 1}),
            ('04_input_top', 'tab', {'index': 2}),
            ('05_input_middle', 'input_scroll', {'scroll': 200}),
            ('06_input_bottom', 'input_scroll', {'scroll': 1000}),
            ('07_credits_tab', 'tab', {'index': 3}),
            ('08_main_return', 'main_close_options', {}),
            ('09_credits_window', 'main_credits', {}),
            ('10_credits_return', 'main_close_options', {}),
            ('11_new_game', 'new_game', {}),
            ('12_tutorial_tower', 'tutorial', {'part': 1}),
            ('13_tutorial_market', 'tutorial', {'part': 3}),
            ('14_tutorial_hide', 'tutorial_hide', {}),
            ('15_pause', 'pause', {}),
            ('16_pause_video', 'pause_options', {}),
            ('17_pause_audio', 'tab', {'index': 1}),
            ('18_pause_input', 'tab', {'index': 2}),
            ('19_pause_credits', 'tab', {'index': 3}),
            ('20_pause_options_close', 'pause_close_options', {}),
            ('21_pause_close', 'pause_close', {}),
            ('22_prestige', 'prestige', {}),
            ('23_portal_tooltip', 'skill', {'skill': 1}),
            ('24_prestige_close', 'close_menus', {}),
            ('25_locked_companions', 'companions', {}),
            ('26_locked_companion_fox', 'companion_detail', {'index': 1}),
            ('27_locked_companion_frog', 'companion_detail', {'index': 2}),
            ('28_default_companion', 'companion_detail', {'index': 3}),
            ('29_locked_companion_pig', 'companion_detail', {'index': 4}),
            ('30_companions_close', 'close_menus', {}),
        ]
    elif phase == 'expanded':
        sequence = [
            ('31_test_state', 'qa_state', {'unlock_companions': True}),
            ('32_unlocked_companions', 'companions', {}),
            *[(f'33_companion_{index}', 'companion_detail', {'index': index}) for index in range(1, 5)],
            ('34_companions_close', 'close_menus', {}),
            ('35_stages', 'stages', {}),
            *[(f'36_stage_{index}', 'stage_detail', {'index': index}) for index in range(3)],
            ('37_stages_close', 'close_menus', {}),
            ('38_forest', 'forest', {'wait': 2}),
            ('39_tutorial_harvest', 'tutorial', {'part': 2}),
            ('40_tutorial_attack', 'tutorial', {'part': 4}),
            ('41_tutorial_hide', 'tutorial_hide', {}),
            ('42_bag_almost', 'bag_state', {'amount': 3}),
            ('43_inventory', 'inventory', {}),
            ('44_bag_full', 'bag_state', {'amount': 4}),
            ('45_inventory_close', 'inventory', {}),
            ('46_result_success', 'result', {}),
            ('47_result_close', 'close_menus', {}),
            ('48_death_state', 'qa_state', {'died': True, 'unlock_companions': True}),
            ('49_result_death', 'result', {}),
            ('50_result_death_close', 'close_menus', {}),
            ('51_village', 'village', {'wait': 2}),
            ('52_demo_end', 'demo', {}),
            ('53_return_main', 'main_menu', {'wait': 3}),
            ('54_continue', 'continue_game', {'wait': 2}),
        ]
    elif phase == 'skills':
        scene = EXTRACTED / 'recovered/game/scenes/windows/prestige_container_demo.tscn'
        identifiers = sorted(set(map(int, re.findall(r'^prestige_id = (\d+)$', scene.read_text(encoding='utf-8'), re.M))))
        sequence = [('55_skill_tree', 'prestige', {})]
        sequence += [(f'skill_{identifier:03}', 'skill', {'skill': identifier, 'wait': .35}) for identifier in identifiers]
        sequence += [('56_skill_tree_close', 'close_menus', {})]
    else:
        sequence = [(f'prototype_{number}', 'prototype', {'level': number, 'wait': 2}) for number in (1, 2, 3)]
        sequence += [('prototype_color_picker', 'color_picker', {})]
    (stage / f'plan_{phase}.json').write_text(json.dumps(sequence, ensure_ascii=False, indent=2), encoding='utf-8')
    active = begin is None
    for identifier, operation, values in sequence:
        if identifier == begin:
            active = True
        if not active:
            continue
        request(stage, identifier, operation, **values)
        if identifier == end:
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate')
    parser.add_argument('phase', choices=['menus', 'expanded', 'skills', 'prototypes'])
    parser.add_argument('--begin')
    parser.add_argument('--end')
    args = parser.parse_args()
    stage = WORK / args.candidate
    assert stage.resolve().parent == WORK.resolve()
    execute(stage, args.phase, args.begin, args.end)
