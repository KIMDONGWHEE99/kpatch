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
            var reportPath = Require(values, "report");

            string methodFullName;
            using (var assembly = ReadAssembly(input))
            {
                var targetType = assembly.MainModule.Types.Single(
                    type => type.Name == "CS_FinalQuestPanel"
                );
                var pibsField = targetType.Fields.Single(
                    field => field.Name == "requiredPibsPerBuilding"
                );
                var costumesField = targetType.Fields.Single(
                    field => field.Name == "requiredCostumesPerBuilding"
                );
                if (pibsField.FieldType.MetadataType != MetadataType.Int32
                    || costumesField.FieldType.MetadataType != MetadataType.Int32)
                {
                    throw new InvalidDataException("데모 완료 조건 필드 형식이 int가 아닙니다.");
                }

                var targetMethod = targetType.Methods.Single(
                    method => method.Name == "CheckAllQuests" && method.HasBody
                );
                methodFullName = targetMethod.FullName;
                var first = targetMethod.Body.Instructions[0];
                var il = targetMethod.Body.GetILProcessor();
                il.InsertBefore(first, Instruction.Create(OpCodes.Ldarg_0));
                il.InsertBefore(first, Instruction.Create(OpCodes.Ldc_I4_0));
                il.InsertBefore(first, Instruction.Create(OpCodes.Stfld, pibsField));
                il.InsertBefore(first, Instruction.Create(OpCodes.Ldarg_0));
                il.InsertBefore(first, Instruction.Create(OpCodes.Ldc_I4_0));
                il.InsertBefore(first, Instruction.Create(OpCodes.Stfld, costumesField));

                // 검수 저장 데이터의 진행이 Steam 통계·도전 과제에 전송되지 않게 합니다.
                var steamInitialize = assembly.MainModule.Types
                    .Single(type => type.Name == "SteamManager")
                    .Methods.Single(method => method.Name == "InitializeSteam");
                steamInitialize.Body = new MethodBody(steamInitialize);
                steamInitialize.Body.GetILProcessor().Emit(OpCodes.Ret);

                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
                assembly.Write(output, new WriterParameters { WriteSymbols = false });
            }

            var verified = false;
            using (var reopened = ReadAssembly(output))
            {
                var targetType = reopened.MainModule.Types.Single(
                    type => type.Name == "CS_FinalQuestPanel"
                );
                var method = targetType.Methods.Single(
                    item => item.Name == "CheckAllQuests" && item.HasBody
                );
                var instructions = method.Body.Instructions.Take(6).ToArray();
                verified = instructions.Length == 6
                    && instructions[0].OpCode == OpCodes.Ldarg_0
                    && instructions[1].OpCode == OpCodes.Ldc_I4_0
                    && instructions[2].OpCode == OpCodes.Stfld
                    && instructions[2].Operand is FieldReference pibs
                    && pibs.Name == "requiredPibsPerBuilding"
                    && instructions[3].OpCode == OpCodes.Ldarg_0
                    && instructions[4].OpCode == OpCodes.Ldc_I4_0
                    && instructions[5].OpCode == OpCodes.Stfld
                    && instructions[5].Operand is FieldReference costumes
                    && costumes.Name == "requiredCostumesPerBuilding";
            }
            if (!verified)
            {
                throw new InvalidDataException("검수용 완료 조건 코드 재검증에 실패했습니다.");
            }

            var report = new
            {
                schema_version = 1,
                qa_only = true,
                distributed_candidate_modified = false,
                input,
                output,
                method = methodFullName,
                required_pibs_runtime_override = 0,
                required_costumes_runtime_override = 0,
                steam_initialization_disabled_for_qa = true,
                input_sha256 = Sha256(input),
                output_sha256 = Sha256(output),
                reopened = true,
            };
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath))!);
            File.WriteAllText(reportPath, JsonSerializer.Serialize(report, JsonOptions) + "\n");
            Console.WriteLine(JsonSerializer.Serialize(report, JsonOptions));
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception.ToString());
            return 1;
        }
    }

    private static AssemblyDefinition ReadAssembly(string path)
    {
        var directory = Path.GetDirectoryName(Path.GetFullPath(path))!;
        return AssemblyDefinition.ReadAssembly(
            path,
            new ReaderParameters
            {
                ReadWrite = false,
                InMemory = true,
                AssemblyResolver = new DefaultAssemblyResolverWithDirectory(directory),
            }
        );
    }

    private static Dictionary<string, string> ParseArgs(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var index = 0; index < args.Length; index += 2)
        {
            if (index + 1 >= args.Length || !args[index].StartsWith("--", StringComparison.Ordinal))
            {
                throw new ArgumentException("인수는 --이름 값 쌍이어야 합니다.");
            }
            values[args[index][2..]] = args[index + 1];
        }
        return values;
    }

    private static string Require(Dictionary<string, string> values, string name)
    {
        return values.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value)
            ? value
            : throw new ArgumentException($"필수 인수가 없습니다: --{name}");
    }

    private static string Sha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream));
    }
}

internal sealed class DefaultAssemblyResolverWithDirectory : DefaultAssemblyResolver
{
    internal DefaultAssemblyResolverWithDirectory(string directory)
    {
        AddSearchDirectory(directory);
    }
}
