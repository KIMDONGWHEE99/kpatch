using System;
using System.IO;
using System.Linq;
using Assets.Behaviour.UI;
using Assets.Behaviour.UI.Forest;
using Assets.Source.Adventure;
using Assets.Source.Flow.Elements;
using Assets.Source.Items.Data;
using Assets.Source.Player;
using UnityEngine;

namespace KoreanQA
{
    [Serializable] public class ScenarioState
    {
        public string war;
        public int stage, progress, partialProgress, notifiedStage, soldiers;
        public int unassigned, foragers, loggers, hunters;
        public bool forestBlocked;
    }

    [Serializable] public class ScenarioHeader
    {
        public string id, action, value, scope, company, product, persistentDataPath, writes;
    }

    [Serializable] public class CraftState
    {
        public string node, recipe;
        public float progress;
        public int outputItems;
        public bool crafting, canManualCraft, blackout;
    }

    [Serializable] public class CraftRecord
    {
        public string id, action, scope;
        public int clicks;
        public bool complete;
    }

    [Serializable] public class CurrencyState
    {
        public string currency;
        public long before, added, after;
        public bool unlocked;
    }

    public sealed partial class Driver
    {
        private CraftRecord pendingCraft;
        private CraftState craftBefore;
        private RecipeElement craftElement;

        private void ManualCraft(Command command)
        {
            var parts = (string.IsNullOrEmpty(command.value) ? "Forge|complete" : command.value).Split('|');
            var world = Node(parts[0]);
            craftElement = world.Element as RecipeElement;
            if (craftElement == null || craftElement.Recipe == null)
                throw new InvalidOperationException("수동 제작할 제작법이 선택되지 않았습니다.");
            if (!craftElement.CanManualCraft())
                throw new InvalidOperationException("원본 제작 가능 조건을 충족하지 않습니다. 재료·진행 상태를 확인하세요.");
            bool complete = parts.Length < 2 || parts[1] == "complete";
            int limit = complete ? 512 : int.Parse(parts[1]);
            if (limit < 1 || limit > 512) throw new ArgumentException("수동 제작 횟수는 1~512입니다.");
            craftBefore = CraftSnapshot(craftElement);
            int clicks = 0;
            // 실제 제작 버튼과 동일한 공개 동작만 호출합니다. 재료·진행도·튜토리얼 상태를 직접 바꾸지 않습니다.
            while (clicks < limit && craftElement.CanManualCraft())
            {
                world.ClickCraft();
                clicks++;
            }
            if (complete && craftElement.Progress < 1)
                throw new InvalidOperationException("허용 횟수 안에 수동 제작 진행이 완료되지 않았습니다.");
            pendingCraft = new CraftRecord
            {
                id = command.id, action = command.action, clicks = clicks, complete = complete,
                scope = "원본 WorldFlowElement.ClickCraft → RecipeElement.DoManualCraft 호출. 완료·결과 생산·첫 HUD 해제는 정상 Update에 맡김. OS 입력 없음."
            };
        }

        private void FinishScenario(Command command)
        {
            if (command.action != "manual_craft" || pendingCraft == null) return;
            var after = CraftSnapshot(craftElement);
            string header = JsonUtility.ToJson(pendingCraft, true);
            File.WriteAllText(Path.Combine(output, Safe(command.id) + ".craft.json"), header.Substring(0, header.LastIndexOf('}')).TrimEnd() +
                ",\n\"before\": " + JsonUtility.ToJson(craftBefore, true) + ",\n\"after\": " + JsonUtility.ToJson(after, true) + "\n}\n");
            bool firstComplete = pendingCraft.complete && craftBefore.blackout;
            pendingCraft = null;
            if (firstComplete && (after.blackout || after.outputItems <= craftBefore.outputItems))
                throw new InvalidOperationException("첫 정상 수동 제작 후 결과 생산 또는 HUD 해제가 확인되지 않았습니다.");
        }

        private static CraftState CraftSnapshot(RecipeElement element) => new CraftState
        {
            node = element.ElementType, recipe = element.Recipe.Identifier, progress = element.Progress,
            outputItems = element.Outputs.Sum(x => x.BufferedItems.Count),
            crafting = element.Crafting, canManualCraft = element.CanManualCraft(),
            blackout = TutorialUI.NewGameBlackout
        };

        private void PrepareEconomy(Command command)
        {
            string mode = string.IsNullOrEmpty(command.value) ? "initial" : command.value;
            if (mode != "initial" && mode != "demo") throw new ArgumentException("재화 검수 상태는 initial 또는 demo입니다.");
            var player = GamePlayer.Current;
            HideTooltip();
            GameUI.Instance.CloseAllExcept(null);
            var rows = new System.Collections.Generic.List<CurrencyState>();
            foreach (Currency currency in Enum.GetValues(typeof(Currency)))
            {
                if (!currency.IsUnlocked() || (mode == "initial" && currency != Currency.Gold)) continue;
                long before = player.GetCurrency(currency);
                long target = currency == Currency.Gold ? 123456 : 1234 + 111 * (int)currency;
                long added = Math.Max(0, target - before);
                player.AddCurrency(currency, added, false);
                rows.Add(new CurrencyState { currency = currency.ToString(), before = before, added = added,
                    after = player.GetCurrency(currency), unlocked = currency.IsUnlocked() });
            }
            var header = new ScenarioHeader
            {
                id = command.id, action = command.action, value = mode,
                scope = "격리된 검수 저장의 재화 HUD 출력용 상태. 정상 수입·획득을 검증한 것으로 기록하지 않음.",
                company = Application.companyName, product = Application.productName,
                persistentDataPath = Application.persistentDataPath,
                writes = "이미 해금된 재화만 GamePlayer.AddCurrency(...,isIncome:false)로 _currencyCount 증가. 기술·_currencyEarned·공급량 직접 변경 없음."
            };
            string text = JsonUtility.ToJson(header, true);
            File.WriteAllText(Path.Combine(output, Safe(command.id) + ".fixture.json"), text.Substring(0, text.LastIndexOf('}')).TrimEnd() +
                ",\n\"currencies\": [\n" + string.Join(",\n", rows.Select(x => JsonUtility.ToJson(x, true))) + "\n]\n}\n");
        }

        private void PrepareScenario(Command command)
        {
            var player = GamePlayer.Current;
            var war = player.GetWarProgress(WarType.Get("forest"));
            if (war == null || player.ForestSettings == null)
                throw new InvalidOperationException("먼저 war_effort와 forest 기술을 검수 사본에서 해금하세요.");
            var before = ScenarioSnapshot(war);
            HideTooltip();
            GameUI.Instance.CloseAllExcept(null);
            string writes;
            if (command.action == "forest_fixture")
            {
                // 산림이 해금되어도 숲 전쟁 1단계가 끝나지 않으면 원본 규칙상 999% 차단 상태입니다.
                war.CurrentStage = Math.Max(war.CurrentStage, 1);
                war.StageProgress = Math.Max(war.StageProgress, war.MaxProgress / 2);
                var forest = player.ForestSettings;
                foreach (ForestWorker type in new[] { ForestWorker.Forager, ForestWorker.Logger, ForestWorker.Hunter })
                {
                    int missing = Math.Max(0, 2 - forest.GetWorkerCount(type));
                    if (missing == 0) continue;
                    forest.AddWorkerCount(ForestWorker.Unassigned, missing);
                    if (!forest.AddWorkerCount(type, missing)) throw new InvalidOperationException("작업반 배정 실패");
                }
                forest.UpdateResourceQuota();
                GameUI.Instance.ToggleForestCrewMenu(true);
                Find<ForestCrewMenu>().UpdateWorkerCount();
                writes = "WarProgress.CurrentStage/StageProgress; ForestSettings._workers는 AddWorkerCount를 통해 세 작업반 각 최소2명. UpdateResourceQuota 파생값 갱신.";
            }
            else
            {
                string state = string.IsNullOrEmpty(command.value) ? "advance" : command.value;
                if (!new[] { "advance", "complete", "defense", "lost" }.Contains(state))
                    throw new ArgumentException("전쟁 검수 상태: advance, complete, defense, lost");
                war.PartialProgress = 0;
                if (war.Soldiers.Count == 0)
                {
                    for (int i = 0; i < 3; i++)
                    {
                        var human = (HumanItemData)MakeItem("conscript").Data;
                        human.AddEquipment(MakeItem("iron_sword"));
                        war.Soldiers.Add(human);
                    }
                }
                switch (state)
                {
                    case "advance":
                        war.CurrentStage = 1;
                        war.StageProgress = war.MaxProgress / 2;
                        war.AddProgress(10);
                        break;
                    case "complete":
                        war.CurrentStage = war.War.Stages.Length;
                        war.StageProgress = war.MaxProgress;
                        war.NotifyStageComplete();
                        break;
                    case "defense":
                        war.CurrentStage = war.War.Stages.Length;
                        war.StageProgress = 25;
                        war.NotifyDefense();
                        break;
                    case "lost":
                        war.CurrentStage = 1;
                        war.StageProgress = war.MaxProgress / 2;
                        war.NotifyStageLost();
                        break;
                }
                GameUI.Instance.ToggleWarEffortMenu(war.War);
                writes = "WarProgress.CurrentStage/StageProgress/PartialProgress; Soldiers가 비어 있을 때 검수 인물3명만 추가. AddProgress/NotifyStageComplete/NotifyDefense/NotifyStageLost의 파생 추세·알림값. 실제 승리 달성 검증이 아님.";
            }
            var after = ScenarioSnapshot(war);
            var header = new ScenarioHeader
            {
                id = command.id, action = command.action, value = command.value,
                scope = "격리된 검수 저장의 UI 상태 준비. 실제 게임 규칙·정상 전쟁 승리를 통과했다고 기록하지 않음.",
                company = Application.companyName, product = Application.productName,
                persistentDataPath = Application.persistentDataPath, writes = writes
            };
            string text = JsonUtility.ToJson(header, true);
            File.WriteAllText(Path.Combine(output, Safe(command.id) + ".fixture.json"), text.Substring(0, text.LastIndexOf('}')).TrimEnd() +
                ",\n\"before\": " + JsonUtility.ToJson(before, true) + ",\n\"after\": " + JsonUtility.ToJson(after, true) + "\n}\n");
        }

        private static ScenarioState ScenarioSnapshot(WarProgress war)
        {
            var forest = GamePlayer.Current.ForestSettings;
            return new ScenarioState
            {
                war = war.War.Identifier, stage = war.CurrentStage, progress = war.StageProgress,
                partialProgress = war.PartialProgress, notifiedStage = war.NotifiedStage, soldiers = war.Soldiers.Count,
                unassigned = forest.GetWorkerCount(ForestWorker.Unassigned),
                foragers = forest.GetWorkerCount(ForestWorker.Forager), loggers = forest.GetWorkerCount(ForestWorker.Logger),
                hunters = forest.GetWorkerCount(ForestWorker.Hunter), forestBlocked = forest.IsBlocked
            };
        }
    }
}
