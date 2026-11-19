using System.Buffers.Binary;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using UnityEngine.AddressableAssets.ResourceLocators;
using UnityEngine.ResourceManagement.ResourceLocations;
using UnityEngine.ResourceManagement.ResourceProviders;

internal static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static int Main(string[] args)
    {
        try
        {
            var options = ParseArgs(args);
            return options.Command switch
            {
                "inspect" => Inspect(options),
                "patch" => Patch(options),
                _ => throw new ArgumentException($"지원하지 않는 명령: {options.Command}"),
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 1;
        }
    }

    private static int Inspect(Options options)
    {
        var input = Require(options, "input");
        var rows = ReadBundleOptions(input);
        Console.WriteLine(JsonSerializer.Serialize(rows, JsonOptions));
        return 0;
    }

    private static int Patch(Options options)
    {
        var input = Require(options, "input");
        var output = Require(options, "output");
        var sourceBundleDir = Require(options, "source-bundle-dir");
        var overlayBundleDir = Require(options, "overlay-bundle-dir");
        var reportPath = Require(options, "report");

        var sourceOptions = ReadBundleOptions(input);
        var overlayFiles = Directory.GetFiles(overlayBundleDir, "*.bundle")
            .ToDictionary(Path.GetFileName, StringComparer.OrdinalIgnoreCase);
        if (overlayFiles.Count == 0)
        {
            throw new InvalidDataException("수정된 Addressables 묶음 파일이 없습니다.");
        }

        var catalog = File.ReadAllBytes(input);
        var changes = new List<object>();
        foreach (var row in sourceOptions)
        {
            if (!overlayFiles.TryGetValue(row.FileName, out var overlayPath))
            {
                continue;
            }
            var sourceBundlePath = Path.Combine(sourceBundleDir, row.FileName);
            if (!File.Exists(sourceBundlePath))
            {
                throw new FileNotFoundException("원본 Addressables 묶음이 없습니다.", sourceBundlePath);
            }
            var actualSourceSize = new FileInfo(sourceBundlePath).Length;
            if (actualSourceSize != row.BundleSize)
            {
                throw new InvalidDataException(
                    $"카탈로그의 원본 크기가 실제 파일과 다릅니다: {row.FileName} " +
                    $"{row.BundleSize}/{actualSourceSize}"
                );
            }

            var newSizeLong = new FileInfo(overlayPath).Length;
            if (newSizeLong > uint.MaxValue)
            {
                throw new InvalidDataException($"묶음 파일이 너무 큽니다: {row.FileName}");
            }
            var newSize = (uint)newSizeLong;
            var pair = new byte[8];
            BinaryPrimitives.WriteUInt32LittleEndian(pair.AsSpan(0, 4), row.Crc);
            BinaryPrimitives.WriteUInt32LittleEndian(pair.AsSpan(4, 4), row.BundleSize);
            var matches = FindAll(catalog, pair)
                .Where(index => index >= 8 && index + 12 <= catalog.Length)
                .ToArray();
            if (matches.Length != 1)
            {
                throw new InvalidDataException(
                    $"카탈로그 옵션 위치가 하나가 아닙니다: {row.FileName} ({matches.Length})"
                );
            }
            var position = matches[0];
            BinaryPrimitives.WriteUInt32LittleEndian(catalog.AsSpan(position, 4), 0u);
            BinaryPrimitives.WriteUInt32LittleEndian(catalog.AsSpan(position + 4, 4), newSize);
            changes.Add(new
            {
                file = row.FileName,
                internal_id = row.InternalId,
                option_offset = position - 8,
                old_crc = row.Crc,
                new_crc = 0,
                old_size = row.BundleSize,
                new_size = newSize,
                hash_preserved = row.Hash,
                modified_file_crc32 = Crc32(overlayPath),
            });
        }

        if (changes.Count != overlayFiles.Count)
        {
            var known = sourceOptions.Select(row => row.FileName).ToHashSet(StringComparer.OrdinalIgnoreCase);
            var missing = overlayFiles.Keys.Where(name => !known.Contains(name)).ToArray();
            throw new InvalidDataException(
                $"수정 묶음과 카탈로그 항목 수가 다릅니다: {changes.Count}/{overlayFiles.Count}; " +
                $"카탈로그에 없는 파일: {string.Join(", ", missing)}"
            );
        }

        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllBytes(output, catalog);
        var reopened = ReadBundleOptions(output);
        foreach (var overlay in overlayFiles)
        {
            var option = reopened.Single(row => string.Equals(row.FileName, overlay.Key, StringComparison.OrdinalIgnoreCase));
            if (option.Crc != 0 || option.BundleSize != new FileInfo(overlay.Value).Length)
            {
                throw new InvalidDataException($"수정 카탈로그 재검사 실패: {overlay.Key}");
            }
        }

        var report = new
        {
            schema_version = 1,
            input,
            output,
            catalog_size_preserved = new FileInfo(input).Length == new FileInfo(output).Length,
            source_sha256 = Sha256(input),
            output_sha256 = Sha256(output),
            bundle_option_count = sourceOptions.Count,
            modified_bundle_count = changes.Count,
            modified_bundles = changes,
            reopened = true,
        };
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath))!);
        File.WriteAllText(reportPath, JsonSerializer.Serialize(report, JsonOptions) + "\n");
        Console.WriteLine(JsonSerializer.Serialize(report, JsonOptions));
        return 0;
    }

    private static List<BundleOptionRow> ReadBundleOptions(string path)
    {
        var load = typeof(ContentCatalogData).GetMethod(
            "LoadFromFile",
            BindingFlags.Static | BindingFlags.NonPublic
        ) ?? throw new MissingMethodException("ContentCatalogData.LoadFromFile");
        var catalog = (ContentCatalogData?)load.Invoke(null, new object[] { path, false })
            ?? throw new InvalidDataException("카탈로그를 열지 못했습니다.");
        var createLocator = typeof(ContentCatalogData).GetMethod(
            "CreateCustomLocator",
            BindingFlags.Instance | BindingFlags.NonPublic
        ) ?? throw new MissingMethodException("ContentCatalogData.CreateCustomLocator");
        var locator = (IResourceLocator?)createLocator.Invoke(catalog, new object?[] { "", null })
            ?? throw new InvalidDataException("카탈로그 위치 목록을 만들지 못했습니다.");

        var rows = new Dictionary<string, BundleOptionRow>(StringComparer.Ordinal);
        foreach (var key in locator.Keys)
        {
            if (!locator.Locate(key, null, out var locations) || locations is null)
            {
                continue;
            }
            foreach (var location in locations)
            {
                if (location.Data is not AssetBundleRequestOptions option)
                {
                    continue;
                }
                var id = location.InternalId;
                rows.TryAdd(
                    id,
                    new BundleOptionRow(
                        id,
                        Path.GetFileName(id.Replace('\\', '/')),
                        option.BundleName,
                        option.Hash,
                        option.Crc,
                        checked((uint)option.BundleSize),
                        location.ProviderId
                    )
                );
            }
        }
        return rows.Values.OrderBy(row => row.FileName, StringComparer.OrdinalIgnoreCase).ToList();
    }

    private static IEnumerable<int> FindAll(byte[] haystack, byte[] needle)
    {
        for (var index = 0; index <= haystack.Length - needle.Length; index++)
        {
            if (haystack.AsSpan(index, needle.Length).SequenceEqual(needle))
            {
                yield return index;
            }
        }
    }

    private static string Sha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static uint Crc32(string path)
    {
        var table = new uint[256];
        for (uint i = 0; i < table.Length; i++)
        {
            var value = i;
            for (var bit = 0; bit < 8; bit++)
            {
                value = (value & 1) != 0 ? 0xEDB88320u ^ (value >> 1) : value >> 1;
            }
            table[i] = value;
        }
        var crc = 0xFFFFFFFFu;
        using var stream = File.OpenRead(path);
        var buffer = new byte[1024 * 1024];
        int read;
        while ((read = stream.Read(buffer, 0, buffer.Length)) > 0)
        {
            for (var i = 0; i < read; i++)
            {
                crc = table[(crc ^ buffer[i]) & 0xFF] ^ (crc >> 8);
            }
        }
        return crc ^ 0xFFFFFFFFu;
    }

    private static Options ParseArgs(string[] args)
    {
        if (args.Length == 0)
        {
            throw new ArgumentException("명령이 필요합니다.");
        }
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var index = 1; index < args.Length; index += 2)
        {
            if (index + 1 >= args.Length || !args[index].StartsWith("--", StringComparison.Ordinal))
            {
                throw new ArgumentException($"잘못된 인수: {args[index]}");
            }
            values[args[index][2..]] = args[index + 1];
        }
        return new Options(args[0].ToLowerInvariant(), values);
    }

    private static string Require(Options options, string name)
    {
        if (!options.Values.TryGetValue(name, out var value) || string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException($"--{name} 인수가 필요합니다.");
        }
        return value;
    }

    private sealed record Options(string Command, Dictionary<string, string> Values);
    private sealed record BundleOptionRow(
        string InternalId,
        string FileName,
        string BundleName,
        string Hash,
        uint Crc,
        uint BundleSize,
        string ProviderId
    );
}
