using System;
using System.IO;
using Assets.Behaviour.UI;
using Assets.Source.Items.Data;
using UnityEngine;

namespace KoreanQA
{
    [Serializable] public class DeathPreviewRecord
    {
        public string id, action, item, scope, writes;
        public float beforeHealth01, afterHealth01;
        public int beforeHealth, afterHealth;
        public bool detachedPreview;
    }

    public sealed partial class Driver
    {
        private bool ActScreenExtension(Command command)
        {
            if (command.action == "alert_query")
            {
                // 원본의 예/아니요 렌더링을 검사합니다. 실제 선택 결과를 실행하는 콜백은 없습니다.
                UIAlertWindow.Query("@LGError", "@LGErrorCorrupt");
                return true;
            }
            if (command.action == "human_dead")
            {
                HideTooltip();
                GameUI.Instance.CloseAllExcept(null);
                var itemId = string.IsNullOrEmpty(command.value) ? "soldier" : command.value;
                var human = MakeItem(itemId).Data as HumanItemData;
                if (human == null) throw new ArgumentException("인물이 아닌 아이템입니다.");
                var record = new DeathPreviewRecord
                {
                    id = command.id, action = command.action, item = itemId,
                    scope = "새로 만든 독립 인물 미리보기만 Health01=0으로 설정하여 원본 HumanDetailsPopup의 사망 문구를 검사합니다. 실제 병력·보관함·저장 인물은 변경하지 않습니다.",
                    writes = "메모리에만 존재하는 독립 HumanItemData.Health01 및 검수 출력 파일",
                    beforeHealth01 = human.Health01, beforeHealth = human.CurrentHealth,
                    detachedPreview = true
                };
                human.Health01 = 0f;
                record.afterHealth01 = human.Health01;
                record.afterHealth = human.CurrentHealth;
                GameUI.Instance.ShowCharacterDetails(human);
                File.WriteAllText(Path.Combine(output, Safe(command.id) + ".fixture.json"), JsonUtility.ToJson(record, true));
                return true;
            }
            return false;
        }
    }
}
