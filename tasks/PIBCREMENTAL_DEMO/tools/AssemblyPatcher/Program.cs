using System.Security.Cryptography;
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
            var values = ParseArgs(args);
            var input = Require(values, "input");
            var output = Require(values, "output");
            var translationsPath = Require(values, "translations");
            var reportPath = Require(values, "report");
            var translations = JsonSerializer.Deserialize<Dictionary<string, string>>(
                File.ReadAllText(translationsPath),
                JsonOptions
            ) ?? throw new InvalidDataException("번역 JSON을 읽지 못했습니다.");

            var replacementCounts = translations.Keys.ToDictionary(
                key => key,
                _ => 0,
                StringComparer.Ordinal
            );
            using (var assembly = ReadAssembly(input))
            {
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
                var unmatched = replacementCounts.Where(row => row.Value == 0).Select(row => row.Key).ToArray();
                if (unmatched.Length != 0)
                {
                    throw new InvalidDataException(
                        $"어셈블리에서 찾지 못한 번역 원문: {string.Join(", ", unmatched)}"
                    );
                }
                InjectKoreanFontBootstrap(assembly, Path.GetDirectoryName(Path.GetFullPath(input))!);
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
                assembly.Write(output, new WriterParameters { WriteSymbols = false });
            }

            var reopenedOccurrences = new Dictionary<string, int>(StringComparer.Ordinal);
            var fontBootstrapVerified = false;
            var fontBootstrapCallSites = 0;
            using (var reopened = ReadAssembly(output))
            {
                var bootstrapType = reopened.MainModule.Types.SingleOrDefault(
                    type => type.Name == "PibcrementalKoreanFontBootstrap"
                );
                var bootstrapMethod = bootstrapType?.Methods.SingleOrDefault(
                    method => method.Name == "Initialize" && method.IsStatic
                );
                fontBootstrapVerified = bootstrapMethod is not null
                    && bootstrapMethod.CustomAttributes.Any(
                        attribute => attribute.AttributeType.FullName
                            == "UnityEngine.RuntimeInitializeOnLoadMethodAttribute"
                    )
                    && bootstrapMethod.Body.Instructions.Any(
                        instruction => instruction.OpCode == OpCodes.Ldstr
                            && Equals(instruction.Operand, "[Pibcremental Korean Patch] Korean font fallback ready.")
                    );
                fontBootstrapCallSites = reopened.MainModule.Types
                    .Where(type => type.Name is "GameManager" or "SteamManager")
                    .SelectMany(type => type.Methods)
                    .Where(method => method.Name == "Awake" && method.HasBody)
                    .SelectMany(method => method.Body.Instructions)
                    .Count(
                        instruction => instruction.OpCode == OpCodes.Call
                            && instruction.Operand is MethodReference reference
                            && reference.DeclaringType.Name == "PibcrementalKoreanFontBootstrap"
                            && reference.Name == "Initialize"
                    );
                foreach (var type in AllTypes(reopened.MainModule.Types))
                {
                    foreach (var method in type.Methods.Where(method => method.HasBody))
                    {
                        foreach (var instruction in method.Body.Instructions)
                        {
                            if (instruction.OpCode == OpCodes.Ldstr && instruction.Operand is string value)
                            {
                                reopenedOccurrences[value] = reopenedOccurrences.GetValueOrDefault(value) + 1;
                            }
                        }
                    }
                }
            }
            if (!fontBootstrapVerified)
            {
                throw new InvalidDataException("런타임 한글 글꼴 초기화 코드 재검증에 실패했습니다.");
            }
            if (fontBootstrapCallSites != 2)
            {
                throw new InvalidDataException(
                    $"런타임 한글 글꼴 호출 지점 수가 예상과 다릅니다: {fontBootstrapCallSites}/2"
                );
            }
            var sourceRemaining = translations.Keys
                .Where(source => reopenedOccurrences.GetValueOrDefault(source) > 0)
                .ToDictionary(source => source, source => reopenedOccurrences[source], StringComparer.Ordinal);
            if (sourceRemaining.Count != 0)
            {
                throw new InvalidDataException(
                    $"수정 어셈블리에 대상 원문이 남았습니다: {string.Join(", ", sourceRemaining.Keys)}"
                );
            }

            var report = new
            {
                schema_version = 1,
                input,
                output,
                translations = translations.Count,
                replacements = replacementCounts.Values.Sum(),
                replacement_counts = replacementCounts,
                source_remaining = sourceRemaining,
                runtime_font_bootstrap = fontBootstrapVerified,
                runtime_font_bootstrap_call_sites = fontBootstrapCallSites,
                source_sha256 = Sha256(input),
                output_sha256 = Sha256(output),
                reopened = true,
            };
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath))!);
            File.WriteAllText(reportPath, JsonSerializer.Serialize(report, JsonOptions) + "\n");
            Console.WriteLine(JsonSerializer.Serialize(report, JsonOptions));
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.ToString());
            return 1;
        }
    }

    private static void InjectKoreanFontBootstrap(AssemblyDefinition assembly, string managedDirectory)
    {
        var module = assembly.MainModule;
        if (module.Types.Any(type => type.Name == "PibcrementalKoreanFontBootstrap"))
        {
            throw new InvalidDataException("런타임 한글 글꼴 초기화 형식이 이미 있습니다.");
        }

        using var core = AssemblyDefinition.ReadAssembly(
            Path.Combine(managedDirectory, "UnityEngine.CoreModule.dll")
        );
        using var textMeshPro = AssemblyDefinition.ReadAssembly(
            Path.Combine(managedDirectory, "Unity.TextMeshPro.dll")
        );
        using var textRendering = AssemblyDefinition.ReadAssembly(
            Path.Combine(managedDirectory, "UnityEngine.TextRenderingModule.dll")
        );

        var objectDefinition = core.MainModule.GetType("UnityEngine.Object");
        var fontDefinition = textRendering.MainModule.GetType("UnityEngine.Font");
        var resourcesDefinition = core.MainModule.GetType("UnityEngine.Resources");
        var debugDefinition = core.MainModule.GetType("UnityEngine.Debug");
        var runtimeAttributeDefinition = core.MainModule.GetType(
            "UnityEngine.RuntimeInitializeOnLoadMethodAttribute"
        );
        var runtimeLoadTypeDefinition = core.MainModule.GetType("UnityEngine.RuntimeInitializeLoadType");
        var fontAssetDefinition = textMeshPro.MainModule.GetType("TMPro.TMP_FontAsset");
        var settingsDefinition = textMeshPro.MainModule.GetType("TMPro.TMP_Settings");

        var objectType = module.ImportReference(objectDefinition);
        var fontType = module.ImportReference(fontDefinition);
        var fontAssetType = module.ImportReference(fontAssetDefinition);
        var runtimeLoadType = module.ImportReference(runtimeLoadTypeDefinition);

        var getBuiltinResourceDefinition = resourcesDefinition.Methods.Single(
            method => method.Name == "GetBuiltinResource"
                && method.IsStatic
                && method.HasGenericParameters
                && method.Parameters.Count == 1
        );
        var getBuiltinResource = new GenericInstanceMethod(
            module.ImportReference(getBuiltinResourceDefinition)
        );
        getBuiltinResource.GenericArguments.Add(fontType);
        var createFontAsset = module.ImportReference(
            fontAssetDefinition.Methods.Single(
                method => method.Name == "CreateFontAsset"
                    && method.IsStatic
                    && method.Parameters.Count == 1
                    && method.Parameters[0].ParameterType.FullName == "UnityEngine.Font"
            )
        );
        var setName = module.ImportReference(
            objectDefinition.Methods.Single(
                method => method.Name == "set_name" && method.Parameters.Count == 1
            )
        );
        var setMultiAtlas = module.ImportReference(
            fontAssetDefinition.Methods.Single(
                method => method.Name == "set_isMultiAtlasTexturesEnabled"
                    && method.Parameters.Count == 1
            )
        );
        var getFallbacks = module.ImportReference(
            settingsDefinition.Methods.Single(
                method => method.Name == "get_fallbackFontAssets" && method.Parameters.Count == 0
            )
        );
        var setModernHangul = module.ImportReference(
            settingsDefinition.Methods.Single(
                method => method.Name == "set_useModernHangulLineBreakingRules"
                    && method.Parameters.Count == 1
            )
        );
        var dontDestroy = module.ImportReference(
            objectDefinition.Methods.Single(
                method => method.Name == "DontDestroyOnLoad"
                    && method.IsStatic
                    && method.Parameters.Count == 1
            )
        );
        var log = module.ImportReference(
            debugDefinition.Methods.Single(
                method => method.Name == "Log"
                    && method.IsStatic
                    && method.Parameters.Count == 1
                    && method.Parameters[0].ParameterType.FullName == "System.Object"
            )
        );
        var logError = module.ImportReference(
            debugDefinition.Methods.Single(
                method => method.Name == "LogError"
                    && method.IsStatic
                    && method.Parameters.Count == 1
                    && method.Parameters[0].ParameterType.FullName == "System.Object"
            )
        );

        var listType = getFallbacks.ReturnType;
        var listAdd = module.ImportReference(
            AllTypes(textMeshPro.MainModule.Types)
                .SelectMany(type => type.Methods)
                .Where(method => method.HasBody)
                .SelectMany(method => method.Body.Instructions)
                .Select(instruction => instruction.Operand)
                .OfType<MethodReference>()
                .First(
                    reference => reference.Name == "Add"
                        && reference.DeclaringType is GenericInstanceType genericType
                        && genericType.GenericArguments.Count == 1
                        && genericType.GenericArguments[0].FullName == "TMPro.TMP_FontAsset"
                )
        );

        var bootstrapType = new TypeDefinition(
            string.Empty,
            "PibcrementalKoreanFontBootstrap",
            TypeAttributes.NotPublic
                | TypeAttributes.Abstract
                | TypeAttributes.Sealed
                | TypeAttributes.BeforeFieldInit
                | TypeAttributes.Class,
            module.TypeSystem.Object
        );
        var initializedField = new FieldDefinition(
            "s_Initialized",
            FieldAttributes.Private | FieldAttributes.Static,
            module.TypeSystem.Boolean
        );
        bootstrapType.Fields.Add(initializedField);
        var initialize = new MethodDefinition(
            "Initialize",
            MethodAttributes.Assembly | MethodAttributes.Static | MethodAttributes.HideBySig,
            module.TypeSystem.Void
        );
        bootstrapType.Methods.Add(initialize);
        module.Types.Add(bootstrapType);

        var runtimeAttributeConstructor = runtimeAttributeDefinition.Methods.Single(
            method => method.IsConstructor
                && method.Parameters.Count == 1
                && method.Parameters[0].ParameterType.FullName
                    == "UnityEngine.RuntimeInitializeLoadType"
        );
        var runtimeAttribute = new CustomAttribute(
            module.ImportReference(runtimeAttributeConstructor)
        );
        // BeforeSceneLoad(1): 장면의 UI가 Awake를 실행하기 전에 폴백 글꼴을 준비합니다.
        runtimeAttribute.ConstructorArguments.Add(
            new CustomAttributeArgument(runtimeLoadType, 1)
        );
        initialize.CustomAttributes.Add(runtimeAttribute);

        initialize.Body.InitLocals = true;
        var fontVariable = new VariableDefinition(fontType);
        var fontAssetVariable = new VariableDefinition(fontAssetType);
        var fallbackListVariable = new VariableDefinition(listType);
        initialize.Body.Variables.Add(fontVariable);
        initialize.Body.Variables.Add(fontAssetVariable);
        initialize.Body.Variables.Add(fallbackListVariable);

        var il = initialize.Body.GetILProcessor();
        var haveFont = Instruction.Create(OpCodes.Ldloc, fontVariable);
        var haveFontAsset = Instruction.Create(OpCodes.Ldloc, fontAssetVariable);
        var beginInitialization = Instruction.Create(OpCodes.Ldstr, "LegacyRuntime.ttf");

        il.Emit(OpCodes.Ldsfld, initializedField);
        il.Emit(OpCodes.Brfalse, beginInitialization);
        il.Emit(OpCodes.Ret);
        il.Append(beginInitialization);
        il.Emit(OpCodes.Call, getBuiltinResource);
        il.Emit(OpCodes.Stloc, fontVariable);
        il.Emit(OpCodes.Ldloc, fontVariable);
        il.Emit(OpCodes.Brtrue, haveFont);
        il.Emit(OpCodes.Ldstr, "[Pibcremental Korean Patch] Unable to load embedded Korean font.");
        il.Emit(OpCodes.Call, logError);
        il.Emit(OpCodes.Ret);

        il.Append(haveFont);
        il.Emit(OpCodes.Call, createFontAsset);
        il.Emit(OpCodes.Stloc, fontAssetVariable);
        il.Emit(OpCodes.Ldloc, fontAssetVariable);
        il.Emit(OpCodes.Brtrue, haveFontAsset);
        il.Emit(OpCodes.Ldstr, "[Pibcremental Korean Patch] Unable to create Korean TMP font asset.");
        il.Emit(OpCodes.Call, logError);
        il.Emit(OpCodes.Ret);

        il.Append(haveFontAsset);
        il.Emit(OpCodes.Ldstr, "Noto Sans KR Runtime");
        il.Emit(OpCodes.Callvirt, setName);
        il.Emit(OpCodes.Ldloc, fontAssetVariable);
        il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Callvirt, setMultiAtlas);
        il.Emit(OpCodes.Call, getFallbacks);
        il.Emit(OpCodes.Stloc, fallbackListVariable);
        il.Emit(OpCodes.Ldloc, fallbackListVariable);
        il.Emit(OpCodes.Ldloc, fontAssetVariable);
        il.Emit(OpCodes.Callvirt, listAdd);
        il.Emit(OpCodes.Ldloc, fontAssetVariable);
        il.Emit(OpCodes.Call, dontDestroy);
        il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Call, setModernHangul);
        il.Emit(OpCodes.Ldc_I4_1);
        il.Emit(OpCodes.Stsfld, initializedField);
        il.Emit(OpCodes.Ldstr, "[Pibcremental Korean Patch] Korean font fallback ready.");
        il.Emit(OpCodes.Call, log);
        il.Emit(OpCodes.Ret);

        foreach (var typeName in new[] { "GameManager", "SteamManager" })
        {
            var targetType = module.Types.Single(type => type.Name == typeName);
            var awake = targetType.Methods.Single(
                method => method.Name == "Awake" && !method.IsStatic && method.HasBody
            );
            awake.Body.GetILProcessor().InsertBefore(
                awake.Body.Instructions[0],
                Instruction.Create(OpCodes.Call, initialize)
            );
        }
    }

    private static AssemblyDefinition ReadAssembly(string path)
    {
        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        return AssemblyDefinition.ReadAssembly(path, new ReaderParameters
        {
            InMemory = true,
            ReadSymbols = false,
            AssemblyResolver = resolver,
        });
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

    private static string Sha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static Dictionary<string, string> ParseArgs(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var index = 0; index < args.Length; index += 2)
        {
            if (index + 1 >= args.Length || !args[index].StartsWith("--", StringComparison.Ordinal))
            {
                throw new ArgumentException($"잘못된 인수: {args[index]}");
            }
            values[args[index][2..]] = args[index + 1];
        }
        return values;
    }

    private static string Require(Dictionary<string, string> values, string name)
    {
        if (!values.TryGetValue(name, out var value) || string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException($"--{name} 인수가 필요합니다.");
        }
        return value;
    }
}
