using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Assets.Behaviour.UI;
using Assets.Behaviour.UI.MainMenu;
using Assets.Behaviour.UI.BuyMenu;
using Assets.Behaviour.UI.TechTree;
using Assets.Source.Player;
using Assets.Source.Flow;
using Assets.Source.Util;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;

namespace KoreanQA
{
    // 검수 사본에서만 직접 화면 함수를 호출합니다. 운영체제 입력은 사용하지 않습니다.
    public static class Bootstrap
    {
        public static void Initialize()
        {
            if (Driver.Instance != null) return;
            var host = new GameObject("KoreanQA");
            UnityEngine.Object.DontDestroyOnLoad(host);
            host.AddComponent<Driver>();
        }
    }

    [Serializable] public class Config { public string output; public string mode = "manual"; public int width = 1200; public int height = 900; }
    [Serializable] public class Command { public string id; public string action; public string value; public bool capture = true; }
    [Serializable] public class TextRow
    {
        public string path, text, font, material;
        public bool active, overflow, onScreen;
        public float fontSize, left, bottom, width, height;
        public int characters, visibleCharacters;
    }
    [Serializable] public class CaptureInfo
    {
        public string id, action, utc, scene, image;
        public int width, height;
    }
    [Serializable] public class RunInfo
    {
        public string utc, executable, dataPath, persistentDataPath, company, product, graphicsDevice, unity, mode;
        public int pid, width, height, windowX, windowY, monitorWidth, monitorHeight;
        public bool fullScreen, steamInitialized;
    }
    [Serializable] public class Result { public string id, action, status, error, utc; }
    [Serializable] public class LogRow { public string utc, type, message, stack; }

    public sealed partial class Driver : MonoBehaviour
    {
        public static Driver Instance;
        private Config config;
        private string output;
        private string lastCommand;
        private bool busy;
        private float poll;

        private void Awake()
        {
            Instance = this;
            var game = Directory.GetParent(Application.dataPath).FullName;
            config = JsonUtility.FromJson<Config>(File.ReadAllText(Path.Combine(game, "korean-qa.json")));
            output = Path.GetFullPath(config.output);
            Directory.CreateDirectory(output);
            Application.logMessageReceived += Log;
            Application.runInBackground = true;
            AudioListener.volume = 0;
            // 게임 안의 입력 수신만 끕니다. 사용자가 다른 앱에서 사용하는 장치는 건드리지 않습니다.
            foreach (var device in InputSystem.devices.ToArray()) InputSystem.DisableDevice(device);
            int width = Math.Min(config.width, Math.Max(320, Screen.currentResolution.width / 2 - 16));
            int height = Math.Min(config.height, Math.Max(240, Screen.currentResolution.height - 80));
            Screen.SetResolution(width, height, false);
        }

        private IEnumerator Start()
        {
            yield return new WaitForSecondsRealtime(.5f);
            // Unity가 자기 창만 이동합니다. 마우스·키보드·다른 앱의 창은 조작하지 않습니다.
            var displays = new List<DisplayInfo>();
            Screen.GetDisplayLayout(displays);
            if (displays.Count > 0)
            {
                var display = displays[0];
                var move = Screen.MoveMainWindowTo(in display, new Vector2Int(8, 32));
                if (move != null) yield return move;
            }
            yield return new WaitForSecondsRealtime(3f);
            WriteRunInfo();
            if (config.mode == "probe")
            {
                yield return Execute(new Command { id = "01-main", action = "main_menu" });
                yield return Execute(new Command { id = "02-options", action = "options" });
                yield return Execute(new Command { id = "03-keys", action = "keybindings" });
                yield return Execute(new Command { id = "04-main-return", action = "main_menu" });
                File.WriteAllText(Path.Combine(output, "probe-complete.txt"), DateTime.UtcNow.ToString("O"));
                Application.Quit();
            }
            else
            {
                yield return Execute(new Command { id = "00-start", action = "capture" });
            }
        }

        private void Update()
        {
            AudioListener.volume = 0;
            if (busy || config.mode == "probe" || Time.realtimeSinceStartup < poll) return;
            poll = Time.realtimeSinceStartup + .2f;
            string path = Path.Combine(output, "command.json");
            if (!File.Exists(path)) return;
            Command command;
            try { command = JsonUtility.FromJson<Command>(File.ReadAllText(path)); }
            catch { return; }
            if (command == null || string.IsNullOrWhiteSpace(command.id) || command.id == lastCommand) return;
            lastCommand = command.id;
            StartCoroutine(Execute(command));
        }

        private IEnumerator Execute(Command command)
        {
            busy = true;
            string error = null;
            try { Act(command); }
            catch (Exception ex) { error = ex.ToString(); }
            if (error == null)
            {
                yield return new WaitForSecondsRealtime(command.action == "new_game" || command.action == "load_latest" ? 5f :
                    command.action == "manual_craft" ? 3f : 1f);
                try { FinishScenario(command); }
                catch (Exception ex) { error = ex.ToString(); }
                if (error == null && command.capture)
                {
                    yield return new WaitForEndOfFrame();
                    try { Capture(command); }
                    catch (Exception ex) { error = ex.ToString(); }
                    yield return new WaitForSecondsRealtime(.3f);
                }
            }
            var result = new Result { id = command.id, action = command.action, status = error == null ? "CAPTURED" : "FAIL", error = error, utc = DateTime.UtcNow.ToString("O") };
            File.WriteAllText(Path.Combine(output, Safe(command.id) + ".result.json"), JsonUtility.ToJson(result, true));
            busy = false;
        }

        private static T Find<T>() where T : Component =>
            Resources.FindObjectsOfTypeAll<T>().First(x => x.gameObject.scene.IsValid());

        private void Act(Command c)
        {
            switch (c.action)
            {
                case "capture": break;
                case "main_menu": MainMenuUI.Instance.ShowMainMenu(); break;
                case "options": MainMenuUI.Instance.ShowOptions(); break;
                case "keybindings": MainMenuUI.Instance.ShowKeyBindings(); break;
                case "load_menu": MainMenuUI.Instance.ShowLoadGame(); break;
                case "new_game": MainMenuUI.Instance.DoNewGame(); break;
                case "tutorial_close": TutorialUI.Instance.HideNewGameOverlay(); break;
                case "close_panels": GameUI.Instance.CloseAllExcept(null); break;
                case "buy":
                    GameUI.Instance.ToggleBuyMenu(true);
                    if (!string.IsNullOrEmpty(c.value)) Find<ElementBuyMenu>().ShowCategory((ElementCategory)Enum.Parse(typeof(ElementCategory), c.value));
                    break;
                case "tech":
                    GameUI.Instance.ToggleTechMenu(true);
                    TechTreeMenu.Instance.ShowTechTree(string.IsNullOrEmpty(c.value) ? null : (TechNode)c.value, true);
                    break;
                case "focus_tech": TechTreeMenu.Instance.FocusNode((TechNode)c.value); break;
                case "unlock":
                    GamePlayer.Current.AddTech((TechNode)c.value);
                    break;
                case "unlock_all":
                    foreach (var tech in TechNode.Nodes.ToArray()) if (!GamePlayer.Current.HasTech(tech)) GamePlayer.Current.AddTech(tech);
                    break;
                case "resources": GameUI.Instance.ToggleResourceMenu(true); break;
                case "war": GameUI.Instance.ToggleWarEffortMenu(true); break;
                case "forest": GameUI.Instance.ToggleForestCrewMenu(true); break;
                case "deco": GameUI.Instance.ToggleDecoMenu(true); break;
                case "pause":
                    GameUI.Instance.CloseAllExcept(null);
                    Find<InGameMenuUI>().gameObject.SetActive(true);
                    Find<InGameMenuUI>().ShowMainMenu();
                    break;
                case "save_menu": Find<InGameMenuUI>().ShowSaveGame(); break;
                case "ingame_load": Find<InGameMenuUI>().ShowLoadGame(); break;
                case "ingame_options": Find<InGameMenuUI>().ShowOptions(); break;
                case "ingame_keys": Find<InGameMenuUI>().ShowKeyBindings(); break;
                case "resume": Find<InGameMenuUI>().DoResume(); break;
                case "demo_end": GameUI.Instance.CloseAllExcept(null); GameUI.Instance.ShowDemoThanks(true); break;
                case "demo_close": GameUI.Instance.ShowDemoThanks(false); break;
                case "alert": UIAlertWindow.Show("@LGError", "@LGErrorCorrupt"); break;
                case "alert_close": UIAlertWindow.Hide(); break;
                case "save": SaveGame.DoSave(string.IsNullOrEmpty(c.value) ? "한국어 검수" : c.value); break;
                case "return_menu": Find<InGameMenuUI>().DoReturnToMenu(); break;
                case "load_latest": MainMenuUI.Instance.DoContinue(); break;
                case "quit":
                    // 키 설정 창을 먼저 닫아 게임 자체의 종료 객체 파괴 순서와 충돌하지 않게 합니다.
                    if (MainMenuUI.Instance != null) MainMenuUI.Instance.ShowMainMenu();
                    else
                    {
                        var pause = Resources.FindObjectsOfTypeAll<InGameMenuUI>().FirstOrDefault(x => x.gameObject.scene.IsValid());
                        if (pause != null) pause.ShowMainMenu();
                    }
                    Application.Quit();
                    break;
                default:
                    if (!ActAccess(c)) throw new InvalidOperationException("알 수 없는 검수 명령: " + c.action);
                    break;
            }
        }

        private static string Safe(string value)
        {
            foreach (char c in Path.GetInvalidFileNameChars()) value = value.Replace(c, '_');
            return value.Replace('/', '_').Replace('\\', '_');
        }

        private static string ObjectPath(Transform transform)
        {
            var parts = new List<string>();
            while (transform != null) { parts.Add(transform.name); transform = transform.parent; }
            parts.Reverse();
            return string.Join("/", parts);
        }

        private void Capture(Command command)
        {
            string stem = Safe(command.id);
            var rows = new List<TextRow>();
            foreach (TMP_Text text in Resources.FindObjectsOfTypeAll<TMP_Text>())
            {
                if (!text.gameObject.scene.IsValid()) continue;
                var corners = new Vector3[4];
                text.rectTransform.GetWorldCorners(corners);
                var canvas = text.canvas;
                Camera camera = canvas != null && canvas.renderMode != RenderMode.ScreenSpaceOverlay ? canvas.worldCamera : null;
                Vector2 a = RectTransformUtility.WorldToScreenPoint(camera, corners[0]);
                Vector2 b = RectTransformUtility.WorldToScreenPoint(camera, corners[2]);
                bool active = text.isActiveAndEnabled && text.gameObject.activeInHierarchy;
                rows.Add(new TextRow {
                    path = ObjectPath(text.transform), text = text.text, active = active,
                    font = text.font != null ? text.font.name : null,
                    material = text.fontSharedMaterial != null ? text.fontSharedMaterial.name : null,
                    fontSize = text.fontSize, overflow = text.isTextOverflowing,
                    left = a.x, bottom = a.y, width = b.x - a.x, height = b.y - a.y,
                    onScreen = active && b.x > 0 && b.y > 0 && a.x < Screen.width && a.y < Screen.height,
                    characters = text.textInfo.characterCount,
                    visibleCharacters = text.textInfo.characterInfo.Take(text.textInfo.characterCount).Count(x => x.isVisible)
                });
            }
            string imagePath = Path.Combine(output, stem + ".png");
            if (rows.Count == 0) throw new InvalidOperationException("화면 문구 기록이 0행입니다.");
            ScreenCapture.CaptureScreenshot(imagePath);
            var info = new CaptureInfo { id = command.id, action = command.action, utc = DateTime.UtcNow.ToString("O"),
                scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name, image = imagePath,
                width = Screen.width, height = Screen.height };
            // 외부 지원 DLL의 사용자 정의 배열을 Unity 직렬화기가 생략하므로 각 행을 따로 저장합니다.
            string header = JsonUtility.ToJson(info, true);
            int closing = header.LastIndexOf('}');
            string encodedRows = string.Join(",\n", rows.Select(row => JsonUtility.ToJson(row, true)));
            File.WriteAllText(Path.Combine(output, stem + ".json"), header.Substring(0, closing).TrimEnd() +
                ",\n\"texts\": [\n" + encodedRows + "\n]\n}\n");
            CaptureAccess(stem);
        }

        private void WriteRunInfo()
        {
            var process = System.Diagnostics.Process.GetCurrentProcess();
            var info = new RunInfo { utc = DateTime.UtcNow.ToString("O"), pid = process.Id, executable = process.MainModule.FileName,
                dataPath = Application.dataPath, persistentDataPath = Application.persistentDataPath,
                company = Application.companyName, product = Application.productName, graphicsDevice = SystemInfo.graphicsDeviceName,
                unity = Application.unityVersion, mode = config.mode, width = Screen.width, height = Screen.height,
                windowX = Screen.mainWindowPosition.x, windowY = Screen.mainWindowPosition.y,
                monitorWidth = Screen.mainWindowDisplayInfo.width, monitorHeight = Screen.mainWindowDisplayInfo.height,
                fullScreen = Screen.fullScreen, steamInitialized = SteamManager.Initialized };
            File.WriteAllText(Path.Combine(output, "runtime.json"), JsonUtility.ToJson(info, true));
        }

        private void Log(string message, string stack, LogType type)
        {
            var row = new LogRow { utc = DateTime.UtcNow.ToString("O"), type = type.ToString(), message = message, stack = stack };
            File.AppendAllText(Path.Combine(output, "messages.jsonl"), JsonUtility.ToJson(row) + "\n");
        }
    }
}
