using System;
using System.IO;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using TMPro;
using Battles1000;
namespace KoreanQA {
public static class Bootstrap {
 public static void Start(){
  if(!Application.productName.StartsWith("MarchConquerQA_"))throw new Exception("검수 사본 외 실행 금지");
  Application.runInBackground=true;
  PlayerPrefs.SetInt("options_window_mode",0);PlayerPrefs.SetInt("options_resolution",0);PlayerPrefs.SetInt("ShowIntroOnNewGame",1);
  var go=new GameObject("KoreanQaDriver");UnityEngine.Object.DontDestroyOnLoad(go);go.AddComponent<Driver>();
 }
}
[Serializable] public class TextRecord {public string path,text,font;public float width,height,preferredWidth,preferredHeight,fontSize;public bool overflowing;}
[Serializable] public class CaptureRecord {public string stage,time,device,product,savePath;public int frame,width,height,textCount;public List<TextRecord> texts=new List<TextRecord>();}
public class Driver:MonoBehaviour {
 string root;
 const BindingFlags Flags=BindingFlags.Instance|BindingFlags.Public|BindingFlags.NonPublic;
 T Find<T>() where T:Component{return UnityEngine.Object.FindObjectsByType<T>(FindObjectsInactive.Include,FindObjectsSortMode.None).FirstOrDefault();}
 object Call(object target,string name,params object[] args){return target.GetType().GetMethod(name,Flags).Invoke(target,args);}
 object Field(object target,string name){return target.GetType().GetField(name,Flags).GetValue(target);}
 string ObjectPath(Transform t){return t.parent==null?t.name:ObjectPath(t.parent)+"/"+t.name;}
 IEnumerator Capture(string stage){
  yield return new WaitForSecondsRealtime(.35f);Canvas.ForceUpdateCanvases();
  var report=new CaptureRecord{stage=stage,time=DateTime.UtcNow.ToString("O"),device=SystemInfo.graphicsDeviceName,product=Application.productName,savePath=Application.persistentDataPath,frame=Time.frameCount,width=Screen.width,height=Screen.height};
  var allTexts=UnityEngine.Object.FindObjectsByType<TextMeshProUGUI>(FindObjectsInactive.Include,FindObjectsSortMode.None).Cast<TMP_Text>().Concat(UnityEngine.Object.FindObjectsByType<TextMeshPro>(FindObjectsInactive.Include,FindObjectsSortMode.None));
  foreach(var text in allTexts){
   if(!text.gameObject.activeInHierarchy||!text.enabled||string.IsNullOrWhiteSpace(text.text))continue;
   text.ForceMeshUpdate();var rect=text.rectTransform.rect;
   report.texts.Add(new TextRecord{path=ObjectPath(text.transform),text=text.text,font=text.font==null?"null":text.font.name,width=rect.width,height=rect.height,preferredWidth=text.preferredWidth,preferredHeight=text.preferredHeight,fontSize=text.fontSize,overflowing=text.isTextOverflowing});
  }
  report.textCount=report.texts.Count;
  string json=JsonUtility.ToJson(report,true).TrimEnd();json=json.Substring(0,json.Length-1)+",\"texts\":["+string.Join(",",report.texts.Select(t=>JsonUtility.ToJson(t)))+"]}";
  File.WriteAllText(Path.Combine(root,stage+".json"),json);
  yield return new WaitForEndOfFrame();ScreenCapture.CaptureScreenshot(Path.Combine(root,stage+".png"));yield return null;
 }
 IEnumerator Start(){
  root=Path.GetFullPath(Path.Combine(Application.dataPath,"../../captures"));Directory.CreateDirectory(root);
  yield return new WaitForSecondsRealtime(3);Screen.SetResolution(1280,720,FullScreenMode.Windowed);yield return new WaitForSecondsRealtime(1);
  yield return Capture("001_menu");
  var ui=Find<SingleSceneUIController>();var options=Find<OptionsMenuUI>();
  Call(options,"Show");yield return Capture("002_options");
  Call(options,"OnLanguageDropdownChanged",1);yield return Capture("002b_language_de");
  Call(options,"OnLanguageDropdownChanged",0);yield return Capture("002c_language_ko");
  options.ApplyDisplayFromButton();yield return Capture("002d_display_confirm");
  yield return new WaitForSecondsRealtime(11);yield return Capture("002e_display_reverted");Call(options,"Hide");
  ui.OnNewRunPressed();yield return new WaitForSecondsRealtime(1.5f);yield return Capture("003_intro");
  Call(ui,"HandleIntroContinuePressed");Find<IntroMessageUI>().Hide();yield return new WaitForSecondsRealtime(.5f);
  var battle=Find<BattleManager>();Call(battle,"SetPaused",true);
  yield return Capture("004_hud");
  options.Show();yield return Capture("004b_paused_options");options.Hide();Call(battle,"SetPaused",true);
  var db=Find<DatabaseLookup>();var detail=Find<SkillNodeDetailsUI>();detail.GetType().GetField("hoverCloseGraceSeconds",Flags).SetValue(detail,10000f);
  var anchor=new GameObject("KoreanQaAnchor",typeof(RectTransform)).GetComponent<RectTransform>();
  anchor.SetParent(((RectTransform)Field(detail,"popupRoot")).parent,false);anchor.anchoredPosition=new Vector2(300,0);
  int index=0;
  foreach(var node in db.GetAllNodes()){
   if(node==null)continue;var state=new NodeRuntimeState{nodeId=node.nodeId,isVisible=true,isUnlocked=true,currentRank=0};
   detail.ShowNode(node,state,anchor);yield return Capture("node_"+(index++).ToString("D3")+"_"+node.nodeId);detail.HideNode();
  }
  var hover=UnityEngine.Object.Instantiate((BattleUnitHoverPopup)Field(battle,"battleUnitHoverPopupPrefab"),(Transform)Field(battle,"worldPopupRoot"));
  index=0;
  foreach(var unit in db.GetAllUnits()){
   if(unit==null)continue;
   hover.gameObject.SetActive(true);hover.transform.position=new Vector3(-10,0,0);hover.SetData(UnitRuntimeData.Create(unit,BattleSide.Player));yield return Capture("unit_"+(index++).ToString("D3")+"_"+unit.unitId);
  }
  hover.gameObject.SetActive(false);
  var between=Find<BetweenBattleMessageUI>();between.ShowVictoryRewards(12345,6789);yield return Capture("005_victory");between.Hide();
  between.ShowLandConqueredRewards(12345,6789);yield return Capture("006_land");between.Hide();
  var run=Find<RunManager>();run.CurrentRun.totalBattlesWon=60;run.CurrentRun.totalEnemiesKilled=12345;run.CurrentRun.totalGoldGathered=999999;run.CurrentRun.totalManaGathered=123456;run.CurrentRun.playTimeSeconds=3661;
  Call(ui,"HandleDemoCompleted");yield return Capture("007_demo_complete");Find<IntroMessageUI>().Hide();
  Find<GameOverUI>().Show("패배!",60,12345,999999,123456,3661);yield return Capture("008_defeat");Find<GameOverUI>().Hide();
  Find<SaveSystem>().Save(run.CurrentRun);ui.OnBackToMenuPressed();yield return new WaitForSecondsRealtime(1);yield return Capture("009_saved_menu");
  ui.OnNewRunPressed();yield return Capture("010_new_confirm");Find<NewGameConfirmUI>().Hide();
  ui.OnContinueRunPressed();yield return new WaitForSecondsRealtime(1);Call(battle,"SetPaused",true);yield return Capture("011_load");
  File.WriteAllText(Path.Combine(root,"completed.txt"),DateTime.UtcNow.ToString("O"));
  yield return new WaitForSecondsRealtime(1);Application.Quit();
 }
}
}
