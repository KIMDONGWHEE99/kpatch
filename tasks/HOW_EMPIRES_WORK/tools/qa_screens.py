"""실제 GPU 실행 중인 게임의 각 메뉴를 열고 표시된 프레임을 보존합니다."""
from common import *
import sys
stem='/root/Main/Game/MainScreenCanvas/MainView/SubmenuBar/MarginContainer/VBoxContainer/'
for button,label in [('RoadsButton','roads'),('ColoniesButton','exploration'),('ProvincesButton','provinces'),('Aristocrats','aristocrats'),('InstitutionsButton','institutions'),('ProductionButton','production'),('CountryTasksButton','country_tasks')]:
    for args in [['call',stem+button,'emit_signal','["pressed"]'],['capture',label],['call',stem+button,'emit_signal','["pressed"]']]:
        result=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).with_name('qa_control.py'))]+args,capture_output=True)
        assert result.returncode==0,result.stderr.decode('utf8',errors='replace')
    print(label,'captured',flush=True)
