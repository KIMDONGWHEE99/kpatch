using System.Text.Json;
using Mono.Cecil;
using Mono.Cecil.Cil;

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
                "inventory" => Inventory(options),
                "patch" => Patch(options),
                _ => throw new ArgumentException($"지원하지 않는 명령: {options.Command}"),
            };
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"{ex.GetType().Name}: {ex.Message}");
            return 1;
        }
    }

    private static int Patch(Options options)
    {
        var input = Require(options, "input");
        var output = Require(options, "output");
        var translationsPath = Require(options, "translations");
        var reportPath = Require(options, "report");
        var translations = JsonSerializer.Deserialize<Dictionary<string, string>>(
            File.ReadAllText(translationsPath), JsonOptions
        ) ?? throw new InvalidDataException("번역 JSON을 읽지 못했습니다.");

        var resolver = CreateResolver(input);
        using var assembly = AssemblyDefinition.ReadAssembly(input, new ReaderParameters
        {
            InMemory = true,
            ReadSymbols = false,
            AssemblyResolver = resolver,
        });
        var replacementCounts = translations.Keys.ToDictionary(
            key => key, _ => 0, StringComparer.Ordinal
        );
        foreach (var type in AllTypes(assembly.MainModule.Types))
        {
            foreach (var method in type.Methods)
            {
                if (!method.HasBody)
                {
                    continue;
                }
                foreach (var instruction in method.Body.Instructions)
                {
                    if (instruction.OpCode != OpCodes.Ldstr || instruction.Operand is not string source)
                    {
                        continue;
                    }
                    if (!translations.TryGetValue(source, out var target))
                    {
                        continue;
                    }
                    instruction.Operand = target;
                    replacementCounts[source]++;
                }
            }
        }

        var enumFallbackPatched = PatchRuntimeAttributeFallback(assembly.MainModule);
        var secondsSuffixReplacements = PatchSecondsSuffix(assembly.MainModule);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        assembly.Write(output, new WriterParameters { WriteSymbols = false });

        var report = new
        {
            schema_version = 1,
            input,
            output,
            translations = translations.Count,
            replacements = replacementCounts.Values.Sum(),
            unmatched = replacementCounts.Where(row => row.Value == 0).Select(row => row.Key).ToArray(),
            replacement_counts = replacementCounts,
            enum_fallback_patched = enumFallbackPatched,
            seconds_suffix_replacements = secondsSuffixReplacements,
        };
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath))!);
        File.WriteAllText(reportPath, JsonSerializer.Serialize(report, JsonOptions) + "\n");
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            report.translations,
            report.replacements,
            unmatched = report.unmatched.Length,
            report.enum_fallback_patched,
            report.seconds_suffix_replacements,
        }, JsonOptions));
        return 0;
    }

    private static int PatchSecondsSuffix(ModuleDefinition module)
    {
        var type = AllTypes(module.Types).FirstOrDefault(
            candidate => candidate.FullName == "GameMenuPanelWeaponItem"
        );
        var method = type?.Methods.FirstOrDefault(
            candidate => candidate.Name == "UpdateBtn" && candidate.HasBody
        );
        if (method is null)
        {
            throw new InvalidDataException("도구 화면의 초 단위 표시 메서드를 찾지 못했습니다.");
        }
        var replacements = 0;
        foreach (var instruction in method.Body.Instructions)
        {
            if (instruction.OpCode == OpCodes.Ldstr && Equals(instruction.Operand, "s"))
            {
                instruction.Operand = "초";
                replacements++;
            }
        }
        if (replacements != 3)
        {
            throw new InvalidDataException($"초 단위 표시 교체 수가 예상과 다릅니다: {replacements}/3");
        }
        return replacements;
    }

    private static bool PatchRuntimeAttributeFallback(ModuleDefinition module)
    {
        var allTypes = AllTypes(module.Types).ToArray();
        var enumType = allTypes.FirstOrDefault(type => type.FullName == "RuntimeDataAttribute");
        var panelType = allTypes.FirstOrDefault(type => type.FullName == "DebugCurrentWaveDataPanel");
        var enumField = enumType?.Fields.FirstOrDefault(
            field => field.Name == "FinalToolRangeTalentMagnification" && field.HasConstant
        );
        var method = panelType?.Methods.FirstOrDefault(
            candidate => candidate.Name == "GetAttributeName" && candidate.HasBody
        );
        if (enumField?.Constant is null || method is null || method.Body.Instructions.Count == 0)
        {
            return false;
        }

        // 이미 패치된 파일을 다시 처리하더라도 같은 분기를 중복 삽입하지 않는다.
        if (method.Body.Instructions.Any(
            instruction => instruction.OpCode == OpCodes.Ldstr
                && Equals(instruction.Operand, "최종 도구 범위 재능 배율")
        ))
        {
            return true;
        }

        var enumValue = Convert.ToInt32(enumField.Constant);
        var first = method.Body.Instructions[0];
        var processor = method.Body.GetILProcessor();
        processor.InsertBefore(first, Instruction.Create(OpCodes.Ldarg_0));
        processor.InsertBefore(first, Instruction.Create(OpCodes.Ldc_I4, enumValue));
        processor.InsertBefore(first, Instruction.Create(OpCodes.Bne_Un, first));
        processor.InsertBefore(first, Instruction.Create(OpCodes.Ldstr, "최종 도구 범위 재능 배율"));
        processor.InsertBefore(first, Instruction.Create(OpCodes.Ret));
        method.Body.MaxStackSize = Math.Max(method.Body.MaxStackSize, 2);
        return true;
    }

    private static int Inventory(Options options)
    {
        var input = Require(options, "input");
        var output = Require(options, "output");
        var resolver = CreateResolver(input);
        using var assembly = AssemblyDefinition.ReadAssembly(input, new ReaderParameters
        {
            InMemory = true,
            ReadSymbols = false,
            AssemblyResolver = resolver,
        });

        var rows = new List<object>();
        foreach (var type in AllTypes(assembly.MainModule.Types))
        {
            foreach (var method in type.Methods)
            {
                if (!method.HasBody)
                {
                    continue;
                }

                foreach (var instruction in method.Body.Instructions)
                {
                    if (instruction.OpCode != OpCodes.Ldstr || instruction.Operand is not string value)
                    {
                        continue;
                    }

                    rows.Add(new
                    {
                        type = type.FullName,
                        method = method.FullName,
                        offset = instruction.Offset,
                        source = value,
                    });
                }
            }
        }

        var report = new
        {
            schema_version = 1,
            input,
            assembly = assembly.Name.Name,
            occurrences = rows.Count,
            unique_strings = rows.Select(row =>
            {
                var property = row.GetType().GetProperty("source");
                return (string?)property?.GetValue(row) ?? string.Empty;
            }).Distinct(StringComparer.Ordinal).Count(),
            entries = rows,
        };
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllText(output, JsonSerializer.Serialize(report, JsonOptions) + "\n");
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            report.assembly,
            report.occurrences,
            report.unique_strings,
        }, JsonOptions));
        return 0;
    }

    private static IEnumerable<TypeDefinition> AllTypes(IEnumerable<TypeDefinition> roots)
    {
        foreach (var type in roots)
        {
            yield return type;
            foreach (var nested in AllTypes(type.NestedTypes))
            {
                yield return nested;
            }
        }
    }

    private static IAssemblyResolver CreateResolver(string input)
    {
        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(input))!);
        return resolver;
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
}
