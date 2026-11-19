using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using Assets.Behaviour.Flow;
using Assets.Behaviour.Flow.Elements;
using Assets.Behaviour.UI;
using Assets.Behaviour.UI.Forest;
using Assets.Behaviour.UI.Shared;
using Assets.Behaviour.UI.TechTree;
using Assets.Source.Adventure;
using Assets.Source.Flow;
using Assets.Source.Items;
using Assets.Source.Items.Data;
using Assets.Source.Items.Type;
using Assets.Source.Player;
using Behaviour.UI;
using Behaviour.UI.Tooltip;
using UnityEngine;
using UnityEngine.UI;

namespace KoreanQA
{
    [Serializable] public class AccessRow
    {
        public int id;
        public string kind, key, path, title, body, error;
        public bool active;
        public float value;
    }

    // 실제 툴팁 그리기 코드를 재사용하는 검수용 문맥입니다. 문구를 새로 만들지 않습니다.
    public sealed class PreviewTooltipSource : TooltipSource
    {
        public InventoryItem Item;
        public TechNode Tech;
        public FlowElement Facility;
        public override string GetTitle() => Item != null ? Item.DisplayName :
            Tech != null ? Tech.Name : Facility != null ? Facility.Label : base.GetTitle();
        public override string GetBodyText() => Facility != null ? Facility.Description : base.GetBodyText();
        public override void AddCustomContent(UITooltip tooltip)
        {
            if (Item != null) Item.AddToTooltip(tooltip);
            else if (Tech != null) UITechNode.AddToTooltip(tooltip, Tech);
            else if (Facility != null) tooltip.AddCostLine(Facility.GetPurchaseCost());
            else base.AddCustomContent(tooltip);
        }
    }

    public sealed partial class Driver
    {
        private TooltipSource activeTooltip;
        private PreviewTooltipSource preview;

        private bool ActAccess(Command c)
        {
            if (c.action == "alert_query" || c.action == "human_dead") return ActScreenExtension(c);
            switch (c.action)
            {
                case "font_check":
                    CheckFonts(c);
                    break;
                case "manual_craft":
                    ManualCraft(c);
                    break;
                case "economy_fixture":
                    PrepareEconomy(c);
                    break;
                case "currency_tooltip":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    var currency = (Currency)Enum.Parse(typeof(Currency), c.value);
                    var cell = Resources.FindObjectsOfTypeAll<CurrencyCell>().FirstOrDefault(x =>
                        x.gameObject.scene.IsValid() && x.gameObject.activeInHierarchy &&
                        x.GetTooltipTitle() == currency.GetDisplayName());
                    if (cell == null) throw new InvalidOperationException("활성 재화 HUD에 해당 재화가 없습니다: " + c.value);
                    var currencyPreview = Preview();
                    currencyPreview.SetSource(cell.gameObject);
                    ShowTooltip(currencyPreview);
                    break;
                case "forest_fixture":
                case "war_fixture":
                    PrepareScenario(c);
                    break;
                case "catalog":
                    WriteCatalog();
                    break;
                case "tutorial":
                    switch (c.value)
                    {
                        case "build": TutorialUI.Instance.ShowBuildArrow(); break;
                        case "upgrade": TutorialUI.Instance.ShowUpgradeArrow(); break;
                        case "input": TutorialUI.Instance.ShowInputArrow(); break;
                        case "tech": TutorialUI.Instance.ShowTechArrow(); break;
                        case "finish": TutorialUI.Instance.FinishTutorial(); break;
                        default: throw new ArgumentException("튜토리얼 단계: build, upgrade, input, tech, finish");
                    }
                    break;
                case "unlock_demo":
                    // 데모에 없는 5단계 이상 기술을 해금하면 원본의 미구현 항목을 호출할 수 있습니다.
                    foreach (var tech in TechNode.Nodes.ToArray())
                        if (tech.CostTier <= 4 && !tech.Hidden(GamePlayer.Current) &&
                            tech.Identifier != "turtle_statue" && !GamePlayer.Current.HasTech(tech))
                            GamePlayer.Current.AddTech(tech);
                    break;
                case "node":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    EnsureNode(c.value);
                    break;
                case "node_focus":
                    GameUI.Instance.CloseAllExcept(null);
                    WorldFlowManager.Instance.ShowElement(Node(c.value).Element);
                    break;
                case "recipe":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowRecipe>(Node(c.value)).ShowRecipePopup();
                    break;
                case "recipe_selected":
                    var recipe = CraftingRecipe.Get(c.value);
                    if (recipe == null) throw new ArgumentException("없는 제작법: " + c.value);
                    GameUI.Instance.RecipePopup.RecipeSelected(recipe);
                    break;
                case "resource_select":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowResource>(Node(c.value)).ShowResourcePopup();
                    break;
                case "resource_selected":
                    var resource = ItemType.Get(c.value) as ResourceItemType;
                    if (resource == null) throw new ArgumentException("없는 광물/공급 자원: " + c.value);
                    GameUI.Instance.ResourcePopup.ResourceSelected(resource);
                    break;
                case "forest_select":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowForest>(Node("Forest")).OpenResourcePopup();
                    break;
                case "forest_tab":
                    GameUI.Instance.ForestResourcePopup.ShowCrew((ForestWorker)Enum.Parse(typeof(ForestWorker), c.value));
                    break;
                case "forest_selected":
                    var forestResource = ItemType.Get(c.value) as ForestItemType;
                    if (forestResource == null) throw new ArgumentException("없는 산림 자원: " + c.value);
                    GameUI.Instance.ForestResourcePopup.ResourceSelected(forestResource);
                    break;
                case "armory":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowArmory>(Node(string.IsNullOrEmpty(c.value) ? "Armory" : c.value)).TogglePopup();
                    break;
                case "armory_seed":
                    foreach (var id in c.value.Split(','))
                        GamePlayer.Current.Armory.AddRange(0, new[] { MakeItem(id.Trim()) });
                    break;
                case "requisition":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowReqOffice>(Node("RequisitionOffice")).OpenContractPopup();
                    break;
                case "war_select":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowWarEffort>(Node("WarEffort")).OpenWarEffortPopup();
                    break;
                case "filter":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowFilter>(Node("Filter")).ToggleFilterSelect();
                    break;
                case "appraiser":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowAppraiser>(Node("Appraiser")).ToggleAppraiserDetails();
                    break;
                case "accountant":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowAccountant>(Node("Accountant")).ToggleAccountantDetails();
                    break;
                case "timer":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    RequiredComponent<WorldFlowTimer>(Node("Timer")).OpenTimerSettingsPopup();
                    break;
                case "exchange":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    if (GameUI.Instance.CurrencyExchangePopup == null)
                        throw new NotSupportedException("이 데모 장면에는 환전 창이 연결되어 있지 않습니다.");
                    var exchangeArgs = (string.IsNullOrEmpty(c.value) ? "Ring|buy" : c.value).Split('|');
                    GameUI.Instance.CurrencyExchangePopup.SetCurrency((Currency)Enum.Parse(typeof(Currency), exchangeArgs[0]),
                        exchangeArgs.Length < 2 || exchangeArgs[1] == "buy");
                    GameUI.Instance.TogglePopupMenu(GameUI.Instance.CurrencyExchangePopup, true);
                    break;
                case "upgrade":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    var parts = c.value.Split('|');
                    var node = Node(parts[0]);
                    WorldFlowManager.Instance.ShowElement(node.Element);
                    int slot = parts.Length > 1 ? int.Parse(parts[1], CultureInfo.InvariantCulture) : 0;
                    var upgrade = node.GetComponentsInChildren<WorldFlowUpgrade>(true).FirstOrDefault(x => x.Slot == slot);
                    if (upgrade == null) throw new InvalidOperationException("강화 슬롯이 없습니다. 먼저 해당 시설의 자동화 기술을 해금하세요.");
                    upgrade.ToggleOptionSelect();
                    break;
                case "tech_list":
                    HideTooltip();
                    GameUI.Instance.ToggleTechMenu(true);
                    var menu = TechTreeMenu.Instance;
                    // 원본은 global_tech_upgrade 전까지 상위 UI 전체를 숨깁니다. 검수 화면 문맥만 켭니다.
                    var uiLabel = (RectTransform)typeof(TechTreeMenu).GetField("_uiLabel", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(menu);
                    uiLabel.gameObject.SetActive(true);
                    var list = (TechTreeListView)typeof(TechTreeMenu).GetField("_listView", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(menu);
                    list.gameObject.SetActive(true);
                    list.RefreshList();
                    if (!list.isActiveAndEnabled) throw new InvalidOperationException("기술 목록의 상위 화면이 비활성 상태입니다.");
                    break;
                case "tech_tooltip":
                    var techNode = TechNode.Get(c.value);
                    if (techNode == null) throw new ArgumentException("없는 기술: " + c.value);
                    if (techNode.CostTier > 4)
                        throw new NotSupportedException("5단계 이후 잔존 기술은 데모에 없는 조건을 참조하므로 정적 검수만 합니다.");
                    var techPreview = Preview();
                    techPreview.Tech = techNode;
                    ShowTooltip(techPreview);
                    break;
                case "item_tooltip":
                    var itemPreview = Preview();
                    itemPreview.Item = MakeItem(c.value);
                    ShowTooltip(itemPreview);
                    break;
                case "facility_tooltip":
                    var facilityPreview = Preview();
                    facilityPreview.Facility = FlowElement.GetAllTypes().First(x => x.ElementType == c.value);
                    ShowTooltip(facilityPreview);
                    break;
                case "node_tooltip":
                    // 현재 선택 자원·제작법을 가진 실제 게임 컴포넌트가 설명을 작성합니다.
                    var world = Node(c.value);
                    if (!world.GetComponents<Component>().Any(x => x is ITooltipTitleSource || x is ITooltipCustomSource))
                        throw new InvalidOperationException("시설 본체의 설명 제공 컴포넌트가 없습니다: " + c.value);
                    var nodePreview = Preview();
                    nodePreview.SetSource(world.gameObject);
                    ShowTooltip(nodePreview);
                    break;
                case "tooltip":
                    ShowTooltip(ResolveTooltip(c.value));
                    break;
                case "tooltip_close":
                    HideTooltip();
                    break;
                case "character":
                    HideTooltip();
                    GameUI.Instance.CloseAllExcept(null);
                    var humanIds = (string.IsNullOrEmpty(c.value) ? "soldier" : c.value).Split('|');
                    var human = MakeItem(humanIds[0]).Data as HumanItemData;
                    if (human == null) throw new ArgumentException("인물이 아닌 아이템입니다.");
                    foreach (var id in humanIds.Skip(1))
                    {
                        var gear = MakeItem(id);
                        if (!human.CanEquipItem(gear, true)) throw new InvalidOperationException("이 인물이 장착할 수 없는 장비: " + id);
                        human.AddEquipment(gear);
                    }
                    GameUI.Instance.ShowCharacterDetails(human);
                    break;
                case "scroll":
                    var scrollArgs = c.value.Split('|');
                    int instance = int.Parse(scrollArgs[0], CultureInfo.InvariantCulture);
                    var scroll = Resources.FindObjectsOfTypeAll<ScrollRect>().Single(x => x.GetInstanceID() == instance && x.gameObject.scene.IsValid());
                    float position = float.Parse(scrollArgs[1], CultureInfo.InvariantCulture);
                    scroll.verticalNormalizedPosition = Mathf.Clamp01(position);
                    break;
                default: return false;
            }
            return true;
        }

        private static T RequiredComponent<T>(WorldFlowElement world) where T : Component
        {
            var component = world.GetComponent<T>();
            if (component == null) throw new InvalidOperationException("이 시설에는 " + typeof(T).Name + " 화면이 없습니다.");
            return component;
        }

        private static WorldFlowElement Node(string name)
        {
            var world = WorldFlowManager.Instance.Elements.FirstOrDefault(x => x.Element.ElementType == name && x.gameObject.activeInHierarchy);
            if (world == null) throw new InvalidOperationException("먼저 node 명령으로 시설을 준비하세요: " + name);
            return world;
        }

        private static void EnsureNode(string name)
        {
            var existing = WorldFlowManager.Instance.Elements.FirstOrDefault(x => x.Element.ElementType == name && x.gameObject.activeInHierarchy);
            if (existing != null)
            {
                WorldFlowManager.Instance.ShowElement(existing.Element);
                return;
            }
            if (!FlowElement.GetAllTypes().Any(x => x.ElementType == name))
                throw new ArgumentException("데모에 구현된 시설이 아닙니다: " + name);
            var element = FlowElement.Create(name);
            element.Position = new Vector2Int(WorldFlowManager.Instance.CurrentFlow.Elements.Count * 200, 0);
            WorldFlowManager.Instance.CreateNewElement(element);
            WorldFlowManager.Instance.ShowElement(element);
        }

        private static InventoryItem MakeItem(string id)
        {
            var type = ItemType.Get(id);
            if (type == null) throw new ArgumentException("데모에 등록된 아이템이 아닙니다: " + id);
            var item = new InventoryItem(type);
            // 원본·번역본의 같은 검수 명령에서 같은 이름·개체를 얻습니다.
            typeof(InventoryItem).GetField("Seed", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(item, "KoreanQA/" + id);
            item.InitializeData();
            return item;
        }

        private PreviewTooltipSource Preview()
        {
            HideTooltip();
            if (preview == null) preview = gameObject.AddComponent<PreviewTooltipSource>();
            preview.Item = null;
            preview.Tech = null;
            preview.Facility = null;
            preview.SetSource(null);
            return preview;
        }

        private void ShowTooltip(TooltipSource source)
        {
            HideTooltip();
            activeTooltip = source;
            UITooltip.Show(source, source.Prefab);
            if (!UITooltip.Active) throw new InvalidOperationException("툴팁 표시가 게임 상태에 의해 차단되었습니다.");
        }

        private void HideTooltip()
        {
            if (activeTooltip != null) UITooltip.Hide(activeTooltip);
            activeTooltip = null;
        }

        private static TooltipSource ResolveTooltip(string selector)
        {
            var sources = Resources.FindObjectsOfTypeAll<TooltipSource>().Where(x => x.gameObject.scene.IsValid() && x.isActiveAndEnabled);
            if (selector.StartsWith("id:", StringComparison.Ordinal))
            {
                int id = int.Parse(selector.Substring(3), CultureInfo.InvariantCulture);
                return sources.Single(x => x.GetInstanceID() == id);
            }
            if (selector.StartsWith("path:", StringComparison.Ordinal))
                return sources.Single(x => ObjectPath(x.transform) == selector.Substring(5));
            string title = selector.StartsWith("title:", StringComparison.Ordinal) ? selector.Substring(6) : selector;
            var matches = sources.Where(x => x.GetTitle() == title).ToArray();
            if (matches.Length != 1) throw new InvalidOperationException("툴팁 제목이 " + matches.Length + "개입니다. context.json의 id: 값을 사용하세요.");
            return matches[0];
        }

        private void CaptureAccess(string stem)
        {
            var rows = new List<AccessRow>();
            foreach (var source in Resources.FindObjectsOfTypeAll<TooltipSource>().Where(x => x.gameObject.scene.IsValid() && x.isActiveAndEnabled))
            {
                var row = new AccessRow { id = source.GetInstanceID(), kind = "tooltip", path = ObjectPath(source.transform), active = true };
                try { row.title = source.GetTitle(); row.body = source.GetBodyText(); }
                catch (Exception ex) { row.error = ex.GetType().Name + ": " + ex.Message; }
                rows.Add(row);
            }
            foreach (var scroll in Resources.FindObjectsOfTypeAll<ScrollRect>().Where(x => x.gameObject.scene.IsValid() && x.isActiveAndEnabled))
                rows.Add(new AccessRow { id = scroll.GetInstanceID(), kind = "scroll", path = ObjectPath(scroll.transform), active = true, value = scroll.verticalNormalizedPosition });
            WriteRows(Path.Combine(output, stem + ".context.json"), rows);
        }

        private void WriteCatalog()
        {
            var rows = new List<AccessRow>();
            foreach (var item in ItemType.All)
                rows.Add(new AccessRow { kind = "item", key = item.Identifier, title = item.GetDisplayName(), body = item.GetDescription() });
            foreach (var tech in TechNode.Nodes)
                rows.Add(new AccessRow { kind = "tech", key = tech.Identifier, title = tech.Name, body = tech.Description, active = !tech.Hidden(GamePlayer.Current), value = tech.CostTier });
            foreach (var node in FlowElement.GetAllTypes())
                rows.Add(new AccessRow { kind = "facility", key = node.ElementType, title = node.Label, body = node.Description });
            WriteRows(Path.Combine(output, "access-catalog.json"), rows);
        }

        private static void WriteRows(string path, IEnumerable<AccessRow> rows)
        {
            File.WriteAllText(path, "{\n\"rows\": [\n" + string.Join(",\n", rows.Select(x => JsonUtility.ToJson(x, true))) + "\n]\n}\n");
        }
    }
}
