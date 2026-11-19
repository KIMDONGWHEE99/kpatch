using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using TMPro;
using UnityEngine;

namespace KoreanQA
{
    [Serializable] public class FontCheckRow
    {
        public string name, status, populationMode, sourceFont, material, shader, fallbacks;
        public string directMissing, fallbackMissing, addMissing, atlasDescription, error;
        public int instance, requested, directMissingCount, fallbackMissingCount;
        public int atlasCountBefore, atlasCountAfter, characterCountBefore, characterCountAfter;
        public int atlasWidth, atlasHeight, atlasPadding, materialTextureWidth, materialTextureHeight;
        public bool dynamic, addSucceeded, fallbackSucceeded, multiAtlas, shaderSupported, materialUsesFirstAtlas;
        public float textureWidthProperty, textureHeightProperty, gradientScale;
    }

    [Serializable] public class FontCheckHeader
    {
        public string id, status, utc, sourceFile, sourceSha256, inputFormat, requiredFonts, ignoredControls;
        public int inputScalars, requestedScalars, checkedFonts;
    }

    public sealed partial class Driver
    {
        private void CheckFonts(Command command)
        {
            string path = Path.GetFullPath(command.value);
            byte[] raw = File.ReadAllBytes(path);
            string contents = File.ReadAllText(path, Encoding.UTF8);
            bool jsonInput = string.Equals(Path.GetExtension(path), ".json", StringComparison.OrdinalIgnoreCase);
            if (jsonInput && !Regex.IsMatch(contents.Trim(), @"^\[\s*(?:\d+\s*(?:,\s*\d+\s*)*)?\]$"))
                throw new ArgumentException("JSON 문자표는 유니코드 정수의 배열이어야 합니다.");
            var allScalars = (jsonInput ? Regex.Matches(contents, @"\d+").Cast<Match>().Select(x => uint.Parse(x.Value)) : Scalars(contents))
                .Distinct().OrderBy(x => x).ToArray();
            if (allScalars.Any(x => x > 0x10FFFF || x >= 0xD800 && x <= 0xDFFF))
                throw new ArgumentException("문자표에 잘못된 유니코드 값이 있습니다.");
            var scalars = allScalars.Where(x => x != 9 && x != 10 && x != 13 && x != 0xFEFF).ToArray();
            if (scalars.Length == 0) throw new InvalidOperationException("검사할 문자가 없습니다.");
            string text = string.Concat(scalars.Select(x => char.ConvertFromUtf32((int)x)));
            // 공용 정적 폰트의 폴백과 첫 메뉴의 두 폰트를 모두 실제 게임 자산에서 수집합니다.
            var fonts = UnityEngine.Resources.LoadAll<TMP_FontAsset>("").Concat(UnityEngine.Resources.FindObjectsOfTypeAll<TMP_FontAsset>())
                .GroupBy(x => x.GetInstanceID()).Select(x => x.First()).ToArray();
            string[] required = { "LiberationSans SDF - Fallback", "LiberationSans SDF", "pixel16", "pixel16 NN" };
            var rows = new List<FontCheckRow>();
            foreach (string name in required)
            {
                var matches = fonts.Where(x => x.name == name).ToArray();
                if (matches.Length != 1)
                {
                    rows.Add(new FontCheckRow { name = name, status = "FAIL", error = "필수 폰트 검색 수: " + matches.Length });
                    continue;
                }
                var font = matches[0];
                var row = new FontCheckRow { name = name, instance = font.GetInstanceID(), requested = scalars.Length, status = "FAIL" };
                rows.Add(row);
                try
                {
                    row.populationMode = font.atlasPopulationMode.ToString();
                    row.dynamic = font.atlasPopulationMode != AtlasPopulationMode.Static;
                    row.sourceFont = font.sourceFontFile != null ? font.sourceFontFile.name : null;
                    row.multiAtlas = font.isMultiAtlasTexturesEnabled;
                    row.atlasWidth = font.atlasWidth;
                    row.atlasHeight = font.atlasHeight;
                    row.atlasPadding = font.atlasPadding;
                    row.atlasCountBefore = font.atlasTextureCount;
                    row.characterCountBefore = font.characterTable.Count;
                    row.fallbacks = string.Join(" | ", font.fallbackFontAssetTable.Where(x => x != null).Select(x => x.name));
                    uint[] addMissing = new uint[0];
                    // 정적 폰트에는 문자를 추가하지 않고 원래 문자표와 실제 폴백 경로를 검사합니다.
                    if (row.dynamic) row.addSucceeded = font.TryAddCharacters(scalars, out addMissing, true);
                    row.addMissing = Codepoints(addMissing);
                    var directMissing = scalars.Where(x => !font.characterLookupTable.ContainsKey(x)).ToArray();
                    row.directMissing = Codepoints(directMissing);
                    row.directMissingCount = directMissing.Length;
                    row.fallbackSucceeded = font.HasCharacters(text, out uint[] missing, true, true);
                    row.fallbackMissing = Codepoints(missing);
                    row.fallbackMissingCount = missing == null ? 0 : missing.Length;
                    row.atlasCountAfter = font.atlasTextureCount;
                    row.characterCountAfter = font.characterTable.Count;
                    row.atlasDescription = string.Join(" | ", font.atlasTextures.Where(x => x != null)
                        .Select(x => x.name + ":" + x.width + "x" + x.height + ":" + x.format + ":readable=" + x.isReadable));
                    var material = font.material;
                    row.material = material != null ? material.name : null;
                    if (material != null)
                    {
                        row.shader = material.shader != null ? material.shader.name : null;
                        row.shaderSupported = material.shader != null && material.shader.isSupported;
                        var texture = material.mainTexture;
                        row.materialTextureWidth = texture != null ? texture.width : 0;
                        row.materialTextureHeight = texture != null ? texture.height : 0;
                        row.materialUsesFirstAtlas = font.atlasTextures.Length > 0 && texture == font.atlasTextures[0];
                        if (material.HasProperty("_TextureWidth")) row.textureWidthProperty = material.GetFloat("_TextureWidth");
                        if (material.HasProperty("_TextureHeight")) row.textureHeightProperty = material.GetFloat("_TextureHeight");
                        if (material.HasProperty("_GradientScale")) row.gradientScale = material.GetFloat("_GradientScale");
                    }
                    bool materialValid = row.shaderSupported && row.materialUsesFirstAtlas &&
                        row.materialTextureWidth == row.atlasWidth && row.materialTextureHeight == row.atlasHeight;
                    row.status = row.fallbackSucceeded && row.fallbackMissingCount == 0 && materialValid &&
                        (!row.dynamic || row.addSucceeded && row.directMissingCount == 0) ? "PASS" : "FAIL";
                }
                catch (Exception ex) { row.error = ex.ToString(); }
            }
            string hash;
            using (var sha = SHA256.Create()) hash = BitConverter.ToString(sha.ComputeHash(raw)).Replace("-", "").ToLowerInvariant();
            var header = new FontCheckHeader
            {
                id = command.id, utc = DateTime.UtcNow.ToString("O"), status = rows.All(x => x.status == "PASS") ? "PASS" : "FAIL",
                sourceFile = path, sourceSha256 = hash, requiredFonts = string.Join(" | ", required),
                inputFormat = jsonInput ? "unicode_integer_array" : "utf8_text",
                inputScalars = allScalars.Length, requestedScalars = scalars.Length, checkedFonts = rows.Count,
                ignoredControls = Codepoints(allScalars.Except(scalars).ToArray())
            };
            string encoded = JsonUtility.ToJson(header, true);
            File.WriteAllText(Path.Combine(output, Safe(command.id) + ".fonts.json"), encoded.Substring(0, encoded.LastIndexOf('}')).TrimEnd() +
                ",\n\"rows\": [\n" + string.Join(",\n", rows.Select(x => JsonUtility.ToJson(x, true))) + "\n]\n}\n");
            if (header.status != "PASS") throw new InvalidOperationException("글꼴 검사 실패. " + command.id + ".fonts.json 참조");
        }

        private static IEnumerable<uint> Scalars(string text)
        {
            for (int i = 0; i < text.Length; i++)
            {
                if (char.IsHighSurrogate(text[i]) && i + 1 < text.Length && char.IsLowSurrogate(text[i + 1]))
                    yield return (uint)char.ConvertToUtf32(text[i++], text[i]);
                else yield return text[i];
            }
        }

        private static string Codepoints(IEnumerable<uint> codes) =>
            codes == null ? "" : string.Join(" ", codes.Select(x => "U+" + x.ToString("X4")));
    }
}
