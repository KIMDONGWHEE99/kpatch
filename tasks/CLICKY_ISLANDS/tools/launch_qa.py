"""검수 사본을 실제 그래픽 장치에서 실행하고, 실행 전후 사용자 저장 지문을 비교합니다.

사용: python launch_qa.py <run_id> [--os-locale=ko|en]
창은 포커스를 가져가지 않게 띄우고(SW_SHOWNOACTIVATE) 소리 장치는 끕니다. 최소화하지 않습니다.
저장·설정·로그는 APPDATA를 검수 폴더로 바꿔 분리하고, 저장 폴더 이름도 검수용으로 바꿔 둡니다.
HOW_EMPIRES_WORK의 launch_qa.py를 고쳐 썼습니다.
"""
import ctypes
import datetime
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import WORK, PCK_NAME, EXE_NAME, save, load, sha

REAL_APPDATA = Path(os.environ['APPDATA'])
SETTINGS = '''[audio]

master_volume=0.0
music_volume=0.0
effects_volume=0.0
mute_focus_out=false

[misc]

locale_confirmed=false
locale="auto"
open_all_fossils=false
build_panel_compact=false
disable_custom_cursor=false
disable_crt_shader=false
disable_camera_shake=false
enable_auto_click=false
skip_island_naming=false

[graphics]

fullscreen=false
vsync=true
max_fps=60.0
game_scale=1.0
'''


def roots():
    result = [REAL_APPDATA / 'Karrot Games', REAL_APPDATA / 'Godot/app_userdata/Clicky Islands']
    steam_users = Path('D:/steam/userdata')
    if steam_users.exists():
        for user in steam_users.iterdir():
            if user.is_dir():
                result += [user / '4178790', user / '4401470']
    return result


def snapshot():
    data = {}
    for root in roots():
        data[str(root)] = ({p.relative_to(root).as_posix(): {'size': p.stat().st_size, 'sha256': sha(p)}
                            for p in root.rglob('*') if p.is_file()} if root.exists() else None)
    return data


def main():
    run_id = sys.argv[1]
    run = WORK / 'qa' / run_id
    game = run / 'game'
    boundary = load(run / 'qa_boundary.json')
    before = snapshot()
    save(run / 'user_before.json', before)
    env = os.environ.copy()
    for key in ('APPDATA', 'LOCALAPPDATA'):
        dest = run / key
        dest.mkdir(exist_ok=True)
        env[key] = str(dest)
    userdata = run / 'APPDATA' / boundary['user_dir_name']
    userdata.mkdir(parents=True, exist_ok=True)
    settings = userdata / 'settings_demo_1_3_6.ini'
    if not settings.exists():
        settings.write_text(SETTINGS, encoding='utf-8', newline='\n')
    # 창의 대부분을 화면 오른쪽 밖에 두어 사용자의 작업 화면을 가리지 않게 합니다(왼쪽 200픽셀만 보임).
    screen_width = ctypes.windll.user32.GetSystemMetrics(0)
    command = [str(game / EXE_NAME), '--windowed', '--resolution', '1920x1080', '--position', f'{screen_width - 200},40',
               '--audio-driver', 'Dummy']
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 4
    process = subprocess.Popen(command, cwd=game, env=env, startupinfo=startup,
                               stdout=(run / 'stdout.log').open('wb'), stderr=(run / 'stderr.log').open('wb'))
    save(run / 'launch.json', {'pid': process.pid, 'command': command, 'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                               'exe_sha256': sha(game / EXE_NAME), 'pck_sha256': sha(game / PCK_NAME), 'userdata': str(userdata),
                               'expected_pck_sha256': boundary['qa_pck_sha256']})
    print('QA PID', process.pid, flush=True)
    code = process.wait()
    after = snapshot()
    save(run / 'user_after.json', after)
    save(run / 'exit.json', {'pid': process.pid, 'exit_code': code, 'ended': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                             'user_saves_unchanged': before == after})
    print('QA exit', code, 'user saves unchanged', before == after, flush=True)
    assert before == after


if __name__ == '__main__':
    main()
