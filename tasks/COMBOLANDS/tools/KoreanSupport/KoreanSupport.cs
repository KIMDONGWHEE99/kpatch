using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using TMPro;

namespace CombolandsKorean
{
    // 원본 그림 파일은 보존하고, 그림에 포함된 기능 안내만 한국어 UI로 표시합니다.
    public sealed class KoreanSupport : MonoBehaviour
    {
        private static bool initialized;
        private readonly List<Image> loadingImages = new List<Image>();
        public static void Initialize()
        {
            if (initialized) return;
            initialized = true;
            var owner = new GameObject("Combolands Korean UI");
            DontDestroyOnLoad(owner);
            owner.AddComponent<KoreanSupport>();
        }
        private void Awake()
        {
            SceneManager.sceneLoaded += SceneLoaded;
            Refresh();
        }
        private void OnDestroy() { SceneManager.sceneLoaded -= SceneLoaded; }
        private void SceneLoaded(Scene scene, LoadSceneMode mode) { Refresh(); StartCoroutine(RefreshLater()); }
        private IEnumerator RefreshLater() { yield return null; Refresh(); }
        private void LateUpdate()
        {
            for (int i = loadingImages.Count - 1; i >= 0; --i)
                if (!loadingImages[i]) loadingImages.RemoveAt(i); else loadingImages[i].enabled = false;
        }
        private void Refresh()
        {
            foreach (var image in Resources.FindObjectsOfTypeAll<Image>())
            {
                if (!image.gameObject.scene.IsValid() || !image.sprite || image.transform.Find("Korean Label")) continue;
                string name = image.sprite.name;
                if (name.StartsWith("LoadingSequence-Sheet_", StringComparison.Ordinal))
                {
                    AddLabel(image, "불러오는 중…", new Rect(0.05f, 0.25f, 0.9f, 0.5f), null, 18f);
                    image.enabled = false; loadingImages.Add(image);
                }
                else if (name == "ShopBorder")
                    AddLabel(image, "상점", new Rect(10f/334f, 87f/180f, 43f/334f, 22f/180f), new Color32(130,87,59,255), 9f);
                else if (name == "ShopBroken")
                    AddLabel(image, "휴점", new Rect(49f/333f, 30f/208f, 42f/333f, 22f/208f), new Color32(116,86,61,255), 9f);
                else if (name == "CrownDemo")
                {
                    AddLabel(image, "체험판", new Rect(0f,0f,1f,1f), null, 12f);
                    image.enabled = false;
                }
                else if (name == "AutoCompleteIcon" || name == "EndlessIcon")
                    TranslateMechanicImage(image);
            }
        }
        // 해금 팝업은 실행 중 새로 만들어지므로 그림을 지정하는 순간 번역합니다.
        public static void SetMechanicSprite(Image image, Sprite sprite)
        {
            image.sprite = sprite;
            TranslateMechanicImage(image);
        }
        private static void TranslateMechanicImage(Image image)
        {
            if (!image || !image.sprite || image.transform.Find("Korean Label")) return;
            string value = image.sprite.name == "AutoCompleteIcon" ? "자동 완료" : image.sprite.name == "EndlessIcon" ? "무한 모드" : null;
            if (value == null) return;
            AddLabel(image, value, new Rect(0f,0f,1f,1f), null, 14f);
            image.enabled = false;
        }
        private static void AddLabel(Image image, string value, Rect region, Color? background, float size)
        {
            var owner = new GameObject("Korean Label", typeof(RectTransform));
            var rect = (RectTransform)owner.transform;
            rect.SetParent(image.transform, false);
            rect.anchorMin = region.min; rect.anchorMax = region.max;
            rect.offsetMin = Vector2.zero; rect.offsetMax = Vector2.zero;
            if (background.HasValue)
            {
                var panel = owner.AddComponent<Image>(); panel.color = background.Value; panel.raycastTarget = false;
            }
            var textOwner = new GameObject("Text", typeof(RectTransform));
            var textRect = (RectTransform)textOwner.transform; textRect.SetParent(rect,false);
            textRect.anchorMin=Vector2.zero; textRect.anchorMax=Vector2.one;
            textRect.offsetMin=Vector2.zero; textRect.offsetMax=Vector2.zero;
            var text = textOwner.AddComponent<TextMeshProUGUI>();
            text.font=TMP_Settings.defaultFontAsset; text.text=value; text.color=Color.white;
            text.fontSize=size; text.fontSizeMax=size; text.fontSizeMin=size*0.6f;
            text.enableAutoSizing=true; text.textWrappingMode=TextWrappingModes.NoWrap;
            text.alignment=TextAlignmentOptions.Center; text.raycastTarget=false;
        }
        // 개발·예비 화면에서 enum 이름을 직접 표시할 때도 기존 번역 조회를 사용합니다.
        public static string CategoryName(string value)
        {
            if (Enum.TryParse<Entities.GamePieceCategory>(value, out var category) &&
                Framework.ScriptableObjectSingleton<Interaction.StringLookup>.Instance.GetNameForCategory(category,out var translated)) return translated;
            return value;
        }
    }
}
