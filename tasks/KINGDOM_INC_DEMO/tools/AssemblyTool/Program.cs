using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;
using System.Security.Cryptography;

// 게임 코드를 실행하지 않고 검수 사본의 두 메서드 변경과 나머지 구조 보존을 검사합니다.
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(args[1]));
using var original = AssemblyDefinition.ReadAssembly(args[1], new ReaderParameters { AssemblyResolver = resolver });
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> list) {
    foreach (var type in list) { yield return type; foreach (var child in Walk(type.NestedTypes)) yield return child; }
}
var types = Walk(original.MainModule.Types).ToArray();
var methods = types.SelectMany(t => t.Methods).ToArray();
const string entryName = "System.Void Assets.Behaviour.Util.Bootstrap::InitializeGame()";
const string steamName = "System.Void SteamManager::Awake()";
const string qaName = "System.Void KoreanQA.Bootstrap::Initialize()";
var jsonOptions = new JsonSerializerOptions { WriteIndented = true };
string Hash(byte[] data) => Convert.ToHexString(SHA256.HashData(data));
object[] Attr(ICustomAttributeProvider value) => value.CustomAttributes.Select(a => (object)new {
    type = a.AttributeType.FullName, blob = Convert.ToBase64String(a.GetBlob())
}).ToArray();
string TypeMetadata(TypeDefinition t) => JsonSerializer.Serialize(new {
    t.FullName, t.Attributes, baseType = t.BaseType?.FullName, t.ClassSize, t.PackingSize,
    attributes = Attr(t), interfaces = t.Interfaces.Select(i => i.InterfaceType.FullName),
    generics = t.GenericParameters.Select(g => new { g.Name, g.Attributes, constraints = g.Constraints.Select(c => c.ConstraintType.FullName) }),
    fields = t.Fields.Select(f => new { f.Name, f.Attributes, type = f.FieldType.FullName, constant = f.HasConstant ? f.Constant?.ToString() : null,
        data = Hash(f.InitialValue ?? Array.Empty<byte>()), f.Offset, attributes = Attr(f) }),
    properties = t.Properties.Select(p => new { p.Name, p.Attributes, type = p.PropertyType.FullName, get = p.GetMethod?.FullName, set = p.SetMethod?.FullName, attributes = Attr(p) }),
    events = t.Events.Select(e => new { e.Name, e.Attributes, type = e.EventType.FullName, add = e.AddMethod?.FullName, remove = e.RemoveMethod?.FullName, attributes = Attr(e) })
});
string MethodMetadata(MethodDefinition m) => JsonSerializer.Serialize(new {
    m.FullName, m.Attributes, m.ImplAttributes, m.SemanticsAttributes, m.CallingConvention, m.HasBody,
    attributes = Attr(m), returnAttributes = Attr(m.MethodReturnType),
    parameters = m.Parameters.Select(p => new { p.Name, p.Attributes, type = p.ParameterType.FullName, constant = p.HasConstant ? p.Constant?.ToString() : null, attributes = Attr(p) }),
    generics = m.GenericParameters.Select(g => new { g.Name, g.Attributes, constraints = g.Constraints.Select(c => c.ConstraintType.FullName) })
});
string Operand(Instruction i, MethodDefinition method, int shift) => i.Operand switch {
    Instruction target => "branch:" + (method.Body.Instructions.IndexOf(target) - shift),
    Instruction[] targets => "switch:" + string.Join(",", targets.Select(x => method.Body.Instructions.IndexOf(x) - shift)),
    _ => i.Operand?.ToString() ?? ""
};
string Handlers(MethodDefinition m, int shift) {
    int Pos(Instruction? i) => i == null ? -1 : m.Body.Instructions.IndexOf(i) - shift;
    return JsonSerializer.Serialize(m.Body.ExceptionHandlers.Select(h => new { h.HandlerType, type = h.CatchType?.FullName,
        ts = Pos(h.TryStart), te = Pos(h.TryEnd), hs = Pos(h.HandlerStart), he = Pos(h.HandlerEnd), fs = Pos(h.FilterStart) }));
}
if (args[0] == "qa") {
    using var support = AssemblyDefinition.ReadAssembly(args[3]);
    var entry = Walk(support.MainModule.Types).SelectMany(t => t.Methods).Single(m => m.FullName == qaName);
    var bootstrap = methods.Single(m => m.FullName == entryName);
    if (bootstrap.Body.Instructions.Any(i => i.Operand?.ToString() == qaName)) throw new Exception("검수 진입점 중복");
    bootstrap.Body.GetILProcessor().InsertBefore(bootstrap.Body.Instructions[0],
        Instruction.Create(OpCodes.Call, original.MainModule.ImportReference(entry)));
    var steam = methods.Single(m => m.FullName == steamName);
    steam.Body = new MethodBody(steam);
    steam.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
    original.Write(args[2]);
} else if (args[0] == "verify-qa") {
    using var candidate = AssemblyDefinition.ReadAssembly(args[2], new ReaderParameters { AssemblyResolver = resolver });
    var otherTypes = Walk(candidate.MainModule.Types).ToArray();
    if (types.Length != otherTypes.Length) throw new Exception("검수 형식 수 변경");
    if (JsonSerializer.Serialize(Attr(original)) != JsonSerializer.Serialize(Attr(candidate))) throw new Exception("어셈블리 특성 변경");
    if (original.Name.FullName != candidate.Name.FullName || original.MainModule.Kind != candidate.MainModule.Kind ||
        original.MainModule.Architecture != candidate.MainModule.Architecture) throw new Exception("어셈블리 구조 변경");
    var beforeRefs = original.MainModule.AssemblyReferences.Select(r => r.FullName).ToArray();
    var afterRefs = candidate.MainModule.AssemblyReferences.Where(r => r.Name != "KoreanQA").Select(r => r.FullName).ToArray();
    if (!beforeRefs.SequenceEqual(afterRefs) || candidate.MainModule.AssemblyReferences.Count(r => r.Name == "KoreanQA") != 1)
        throw new Exception("검수 외 어셈블리 참조 변경");
    if (original.MainModule.Resources.Count != candidate.MainModule.Resources.Count) throw new Exception("내장 자산 수 변경");
    for (int i = 0; i < original.MainModule.Resources.Count; i++) {
        var a = original.MainModule.Resources[i]; var b = candidate.MainModule.Resources[i];
        if (a.Name != b.Name || a.Attributes != b.Attributes || a.ResourceType != b.ResourceType) throw new Exception("내장 자산 메타데이터 변경");
        if (a is EmbeddedResource ea && b is EmbeddedResource eb && Hash(ea.GetResourceData()) != Hash(eb.GetResourceData())) throw new Exception("내장 자산 내용 변경");
    }
    int checkedMethods = 0;
    for (int t = 0; t < types.Length; t++) {
        var aType = types[t]; var bType = otherTypes[t];
        if (TypeMetadata(aType) != TypeMetadata(bType) || aType.Methods.Count != bType.Methods.Count) throw new Exception("검수 외 형식 변경: " + aType.FullName);
        for (int n = 0; n < aType.Methods.Count; n++) {
            var a = aType.Methods[n]; var b = bType.Methods[n];
            if (MethodMetadata(a) != MethodMetadata(b)) throw new Exception("메서드 정의 변경: " + a.FullName);
            checkedMethods++;
            if (!a.HasBody) continue;
            if (a.FullName == steamName) {
                if (b.Body.Instructions.Count != 1 || b.Body.Instructions[0].OpCode != OpCodes.Ret || b.Body.Variables.Count != 0 || b.Body.ExceptionHandlers.Count != 0)
                    throw new Exception("Steam 격리 내용 불일치");
                continue;
            }
            int shift = a.FullName == entryName ? 1 : 0;
            if (shift == 1 && (b.Body.Instructions[0].OpCode != OpCodes.Call || b.Body.Instructions[0].Operand?.ToString() != qaName)) throw new Exception("검수 진입 호출 불일치");
            if (a.Body.Instructions.Count + shift != b.Body.Instructions.Count || a.Body.InitLocals != b.Body.InitLocals ||
                !a.Body.Variables.Select(v => v.VariableType.FullName).SequenceEqual(b.Body.Variables.Select(v => v.VariableType.FullName)) ||
                Handlers(a, 0) != Handlers(b, shift)) throw new Exception("검수 외 본문 구조 변경: " + a.FullName);
            for (int i = 0; i < a.Body.Instructions.Count; i++) {
                var ai = a.Body.Instructions[i]; var bi = b.Body.Instructions[i + shift];
                if (ai.OpCode != bi.OpCode || Operand(ai, a, 0) != Operand(bi, b, shift)) throw new Exception("검수 외 명령 변경: " + a.FullName + " #" + i);
            }
        }
    }
    File.WriteAllText(args[3], JsonSerializer.Serialize(new { status = "PASS", methods = checkedMethods, types = types.Length,
        allowed = new[] { entryName + " 진입 호출 1개", steamName + " 즉시 반환" }, source_sha256 = Hash(File.ReadAllBytes(args[1])),
        qa_sha256 = Hash(File.ReadAllBytes(args[2])) }, jsonOptions));
    Console.WriteLine($"검수 경계 일치: 형식 {types.Length}, 메서드 {checkedMethods}, 허용 변경 두 곳");
} else if (args[0] == "dump") {
    File.WriteAllText(args[2], JsonSerializer.Serialize(methods.Where(m => m.HasBody).SelectMany(m =>
        m.Body.Instructions.Where(i => i.OpCode == OpCodes.Ldstr).Select(i => new { method = m.FullName, offset = i.Offset, source = (string)i.Operand })), jsonOptions));
} else { throw new Exception("지원하지 않는 작업"); }
