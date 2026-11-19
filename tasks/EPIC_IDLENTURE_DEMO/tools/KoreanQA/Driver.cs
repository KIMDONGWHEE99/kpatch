using System;
using System.IO;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using TMPro;
namespace KoreanQA {
public static class Bootstrap {
 public static void Start(){
  if(Application.productName!="Epic_KoreanQA1")throw new Exception("검수 사본 외 실행 금지");
  Application.runInBackground=true;
  var go=new GameObject("KoreanQaDriver");UnityEngine.Object.DontDestroyOnLoad(go);go.AddComponent<Driver>();
 }
}
[Serializable] public class TextRecord {public string path,text,font;public float width,height,preferredWidth,preferredHeight,fontSize;public bool overflowing;}
[Serializable] public class CaptureRecord {public string stage,time,device,product,savePath;public int frame,width,height;public List<TextRecord> texts=new List<TextRecord>();}
[Serializable] public class DialogSuite {public DialogData[] unused;public DialogBlock[] blocks;}
[Serializable] public class DialogBlock {public string name;public DialogData.Dialog[] Dialogs;}
public class Driver:MonoBehaviour {
 string root;
 float started;
 void Update(){if(Time.realtimeSinceStartup-started>300){File.WriteAllText(Path.Combine(root,"timeout.txt"),"검수 시간 초과");Application.Quit();}}
 const BindingFlags Flags=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Instance;
 T Find<T>() where T:Component{return UnityEngine.Object.FindObjectsByType<T>(FindObjectsInactive.Include,FindObjectsSortMode.None).FirstOrDefault();}
 object Call(object target,string name,params object[] args){return target.GetType().GetMethod(name,Flags).Invoke(target,args);}
 object Field(object target,string name){for(var t=target.GetType();t!=null;t=t.BaseType){var f=t.GetField(name,Flags);if(f!=null)return f.GetValue(target);}throw new Exception(name);}
 string ObjectPath(Transform t){return t.parent==null?t.name:ObjectPath(t.parent)+"/"+t.name;}
 void ShowDescription(UIDescription d){d.SetVisible(true);d.Rebuild();d.enabled=false;((RectTransform)d.transform).anchoredPosition=new Vector2(-600,300);}
 IEnumerator Research(){
  Time.timeScale=0;var manager=Find<UnlocksTreeWindowManager>();Find<WindowsManager>().ToggleWindow(manager);yield return new WaitForSecondsRealtime(.3f);
  var nodes=UnityEngine.Object.FindObjectsByType<UIUnlocksTreeNode>(FindObjectsInactive.Include,FindObjectsSortMode.None).Where(n=>n.UnlockData!=null&&n.UnlockData.EnabledInDemo).OrderByDescending(n=>n.UnlockData.Description.Length).Take(12).ToArray();if(nodes.Length==0)throw new Exception("연구 노드를 확보하지 못했습니다");
  int i=0;foreach(var node in nodes){Call(manager.TargetWindow,"OnNodeClicked",node);yield return Capture("research_"+(i++).ToString("D2"));}
  File.WriteAllText(Path.Combine(root,"complete.txt"),DateTime.UtcNow.ToString("O"));Application.Quit();
 }
 IEnumerator Extended(){
  Time.timeScale=0;UnlockablesManager.Unlock(UnlockableType.Inventory);UnlockablesManager.Unlock(UnlockableType.Socket1AndGems);
  var gems=(GemsManager)Field(Find<UIGemsWindow>(),"_gemsManager");var gemDescription=Find<UIGemDescription>();int i=0;
  foreach(GemType type in Enum.GetValues(typeof(GemType))){gems.AddGems(type,1);gemDescription.Refresh(gems.GetGemByType(type));ShowDescription(gemDescription);yield return Capture("gem_"+(i++).ToString("D2"));gemDescription.SetVisible(false);}
  var windows=Find<WindowsManager>();windows.ToggleWindow(Find<GemsWindowManager>());yield return Capture("extra_gems_unlocked");windows.HideCurrentWindow();
  var inventory=(PersistentHeroInventory)Field(Find<InventoryWindowManager>(),"_persistentHeroInventory");var items=(ItemsData)Field(inventory,"_itemsData");var quality=((ItemsQualityData)Field(inventory,"_itemsQualityData")).Qualities.Last();var itemDescription=Find<UIInventoryItemDescription>();i=0;
  foreach(ItemType type in Enum.GetValues(typeof(ItemType))){var data=items.GetItemsByType(type).OrderByDescending(d=>d.Name.Length).First();var item=new InventoryItem();item.Initialize(data,quality,999,new[]{AttributeType.CritChance,AttributeType.CritDamage},9);inventory.TryToAddItemToInventory(item);itemDescription.Refresh(item);ShowDescription(itemDescription);yield return Capture("item_"+(i++).ToString("D2"));itemDescription.SetVisible(false);}
  windows.ToggleWindow(Find<InventoryWindowManager>());yield return Capture("extra_inventory_full");windows.HideCurrentWindow();
  var manager=Find<AbilitiesWindowManager>();var dataList=((AbilitiesData)Field(manager,"_abilitiesData")).AbilitiesDataList;var map=(DungeonMapManager)Field(manager,"_dungeonMapManager");var abilityDescription=Find<UIAbilityDescription>();i=0;
  foreach(var data in dataList){abilityDescription.Refresh(data,(DungeonPlayerStats)map.Player.Stats,true,true,false);ShowDescription(abilityDescription);yield return Capture("ability_"+(i++).ToString("D2"));abilityDescription.SetVisible(false);}
  var unlockDescription=Find<UIUnlockDescription>();i=0;
  foreach(var node in UnityEngine.Object.FindObjectsByType<UIUnlocksTreeNode>(FindObjectsInactive.Include,FindObjectsSortMode.None).Where(n=>n.UnlockData!=null&&n.UnlockData.EnabledInDemo).OrderByDescending(n=>n.UnlockData.Description.Length).Take(12)){unlockDescription.Refresh(node.UnlockData);ShowDescription(unlockDescription);yield return Capture("research_"+(i++).ToString("D2"));unlockDescription.SetVisible(false);}
  File.WriteAllText(Path.Combine(root,"complete.txt"),DateTime.UtcNow.ToString("O"));Application.Quit();
 }
 IEnumerator Capture(string stage){
  yield return new WaitForSecondsRealtime(.4f);Canvas.ForceUpdateCanvases();
  var report=new CaptureRecord{stage=stage,time=DateTime.UtcNow.ToString("O"),device=SystemInfo.graphicsDeviceName,product=Application.productName,savePath=Application.persistentDataPath,frame=Time.frameCount,width=Screen.width,height=Screen.height};
  foreach(var text in UnityEngine.Object.FindObjectsByType<TMP_Text>(FindObjectsInactive.Include,FindObjectsSortMode.None)){
   if(!text.gameObject.activeInHierarchy||!text.enabled||string.IsNullOrWhiteSpace(text.text))continue;
   text.ForceMeshUpdate();var rect=text.rectTransform.rect;
   report.texts.Add(new TextRecord{path=ObjectPath(text.transform),text=text.text,font=text.font==null?"null":text.font.name,width=rect.width,height=rect.height,preferredWidth=text.preferredWidth,preferredHeight=text.preferredHeight,fontSize=text.fontSize,overflowing=text.isTextOverflowing});
  }
  string json=Newtonsoft.Json.JsonConvert.SerializeObject(report,Newtonsoft.Json.Formatting.Indented);
  File.WriteAllText(Path.Combine(root,stage+".json"),json);
  yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(root,stage+".png"));yield return null;
 }
 IEnumerator Start(){
  root=Path.GetFullPath(Path.Combine(Application.dataPath,"../../captures"));Directory.CreateDirectory(root);
  started=Time.realtimeSinceStartup;
  yield return new WaitForSecondsRealtime(4);
  if(!File.Exists(Path.Combine(root,"../full_qa.txt"))){yield return Capture("001_menu");yield return new WaitForSecondsRealtime(2);Application.Quit();yield break;}
  Screen.SetResolution(1280,720,FullScreenMode.Windowed);yield return new WaitForSecondsRealtime(1);
  yield return Capture("001_menu");
  var menu=Find<MenuController>();Call(menu,"ShowResetSavesPopup");yield return Capture("002_reset_confirmation");Find<DynamicCanvasManager>().Close();
  var story=(StoryManager)Field(menu,"_storyManager");story.TryToQueueChapter();if(story.CanPlayChapter())story.Play();else menu.StartCoroutine((IEnumerator)Call(menu,"LoadGame"));
  for(int tick=0,index=0;tick<90;tick++){
   yield return new WaitForSecondsRealtime(.25f);var dialog=Find<DialogManager>();
   if(dialog!=null&&dialog.DialogInProgress){Call(dialog,"ProgressDialog");yield return Capture("intro_"+(index++).ToString("D2"));Call(dialog,"ProgressDialog");}
   if(Find<WindowsManager>()!=null)break;
  }
  if(Find<WindowsManager>()==null)SceneUtilities.Load(SceneId.Gameplay);
  yield return new WaitForSecondsRealtime(2);yield return Capture("003_gameplay");
  string characters=Path.Combine(root,"../font_characters.txt");
  if(File.Exists(characters)){var font=TMP_Settings.fallbackFontAssets[0];bool ok=font.TryAddCharacters(File.ReadAllText(characters),out string missing);File.WriteAllText(Path.Combine(root,"font_coverage.json"),"{\"status\":\""+(ok?"PASS":"FAIL")+"\",\"missing\":\""+missing+"\",\"atlas_count\":"+font.atlasTextures.Length+",\"characters\":"+font.characterTable.Count+"}");}
  if(File.Exists(Path.Combine(root,"../research_qa.txt"))){yield return Research();yield break;}
  if(File.Exists(Path.Combine(root,"../extended_qa.txt"))){yield return Extended();yield break;}
  var dynamicCanvas=Find<DynamicCanvasManager>();dynamicCanvas.Show<UIDesktopOptions>();
  var display=(DesktopScreenOptionsManager)Field(Find<UIDesktopOptions>(),"_desktopScreenOptionsManager");int resolution=Array.FindIndex(display.Resolutions,r=>r.width==1280&&r.height==720);if(resolution>=0)display.SetResolution(resolution);display.SetScreenMode(2);dynamicCanvas.Close();dynamicCanvas.Show<UIDesktopOptions>();yield return Capture("004_options");
  var options=Find<UIDesktopOptions>();var confirm=(UIDesktopApplyOptionsPopup)Field(options,"_desktopApplyOptionsPopup");confirm.ShowWithDecline(()=>{});yield return Capture("005_display_confirmation");dynamicCanvas.Close();
  foreach(var name in new[]{"Inventory","Attributes","Skills","Quests","Socket1AndGems","Potion","AbilityCleave","AbilityWhirlwind","AbilityFireball","AbilityMagicMissiles","HealthUpgrade1","DamageUpgrade1","CritChanceUpgrade1","CritDamageUpgrade1","DodgeUpgrade1","DefenseUpgrade1","LootUpgrade1","StunUpgrade1","GoldBonusUpgrade1"})if(Enum.TryParse<UnlockableType>(name,out var value))UnlockablesManager.Unlock(value);
  var windows=Find<WindowsManager>();
  foreach(var manager in (WindowManager[])Field(windows,"_windows")){
   var required=(UnlockableType)Field(manager,"_requiredUnlockable");if(required!=UnlockableType.None)UnlockablesManager.Unlock(required);
   windows.ToggleWindow(manager);yield return Capture("window_"+manager.GetType().Name);
   var tooltip=manager.TargetWindow.TooltipInvoker;if(tooltip!=null){tooltip.OnPointerEnter(null);var description=(UIDescription)Field(tooltip,"_description");description.enabled=false;((RectTransform)description.transform).anchoredPosition=new Vector2(-600,300);yield return Capture("help_"+manager.GetType().Name);tooltip.OnPointerExit(null);description.enabled=true;}
   windows.HideCurrentWindow();
  }
  var suite=Newtonsoft.Json.JsonConvert.DeserializeObject<DialogSuite>(File.ReadAllText(Path.Combine(root,"../dialogues.json")));
  var dialogs=suite.blocks.Select(b=>{var d=ScriptableObject.CreateInstance<DialogData>();d.name=b.name;d.Dialogs=b.Dialogs;return d;}).ToArray();var dm=Find<DialogManager>();int di=0;
  foreach(var data in dialogs){dm.StartDialog(data);for(int j=0;j<data.Dialogs.Length;j++){Call(dm,"ProgressDialog");yield return Capture("dialog_"+(di++).ToString("D2"));Call(dm,"ProgressDialog");}}
  yield return Capture("006_after_dialogs");
  SRDebug.Init();foreach(SRDebugger.DefaultTabs tab in Enum.GetValues(typeof(SRDebugger.DefaultTabs))){if(tab.ToString()=="BugReporter")continue;SRDebug.Instance.ShowDebugPanel(tab,false);yield return Capture("debug_"+tab);SRDebug.Instance.HideDebugPanel();}
  var death=Find<DeathSequenceManager>();if(death!=null){death.StartCoroutine(death.Play());yield return new WaitForSecondsRealtime(1.6f);yield return Capture("007_death");yield return new WaitForSecondsRealtime(4);}
  var end=Find<DemoEndPopupManager>();if(end!=null){end.StartCoroutine(end.Play());yield return Capture("008_demo_end");}
  File.WriteAllText(Path.Combine(root,"complete.txt"),DateTime.UtcNow.ToString("O"));
  yield return new WaitForSecondsRealtime(2);Application.Quit();
 }
}
}
