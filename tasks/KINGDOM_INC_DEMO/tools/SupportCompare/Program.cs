using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;
using System.Security.Cryptography;

// 새 명령 분기 외에는 기존 검수 메서드가 그대로인지 독립적으로 비교합니다.
using var before = AssemblyDefinition.ReadAssembly(args[0]);
using var after = AssemblyDefinition.ReadAssembly(args[1]);
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> items) {
    foreach (var item in items) { yield return item; foreach (var child in Walk(item.NestedTypes)) yield return child; }
}
string Op(Instruction i, MethodDefinition m, int shift) => i.Operand switch {
    Instruction target => "branch:" + (m.Body.Instructions.IndexOf(target) - shift),
    Instruction[] targets => "switch:" + string.Join(",", targets.Select(t => m.Body.Instructions.IndexOf(t) - shift)),
    _ => i.Operand?.ToString() ?? ""
};
string[] IL(MethodDefinition m, int shift = 0) => !m.HasBody ? Array.Empty<string>() :
    m.Body.Instructions.Skip(shift).Select(i => i.OpCode.ToString() + " " + Op(i, m, shift)).ToArray();
string[] WithoutInsertion(MethodDefinition m, int start, int count) {
    int Map(Instruction target) {
        int index = m.Body.Instructions.IndexOf(target);
        return index >= start + count ? index - count : index;
    }
    string Operand(Instruction i) => i.Operand switch {
        Instruction target => "branch:" + Map(target),
        Instruction[] targets => "switch:" + string.Join(",", targets.Select(Map)),
        _ => i.Operand?.ToString() ?? ""
    };
    return m.Body.Instructions.Where((i, n) => n < start || n >= start + count)
        .Select(i => i.OpCode + " " + Operand(i)).ToArray();
}
string Structure(MethodDefinition m) => JsonSerializer.Serialize(new {
    m.FullName, m.Attributes, m.ImplAttributes, m.HasBody,
    vars = m.HasBody ? m.Body.Variables.Select(v => v.VariableType.FullName).ToArray() : Array.Empty<string>(),
    handlers = m.HasBody ? m.Body.ExceptionHandlers.Count : 0
});
string Fields(TypeDefinition t) => JsonSerializer.Serialize(t.Fields.Select(f => new { f.Name, type = f.FieldType.FullName, f.Attributes }));
var oldTypes = Walk(before.MainModule.Types).ToDictionary(t => t.FullName);
var newTypes = Walk(after.MainModule.Types).ToDictionary(t => t.FullName);
var oldMethods = oldTypes.Values.SelectMany(t => t.Methods).ToDictionary(m => m.FullName);
var newMethods = newTypes.Values.SelectMany(t => t.Methods).ToDictionary(m => m.FullName);
var issues = new List<string>();
var changed = new List<object>();
int unchanged = 0;
foreach (var pair in oldTypes) {
    if (!newTypes.TryGetValue(pair.Key, out var type) || Fields(pair.Value) != Fields(type))
        issues.Add("기존 형식/필드 변경: " + pair.Key);
}
foreach (var pair in oldMethods) {
    if (!newMethods.TryGetValue(pair.Key, out var method)) { issues.Add("메서드 삭제: " + pair.Key); continue; }
    if (Structure(pair.Value) != Structure(method)) issues.Add("기존 메서드 구조 변경: " + pair.Key);
    var oldIL = IL(pair.Value);
    if (oldIL.SequenceEqual(IL(method))) { unchanged++; continue; }
    if (pair.Key != "System.Boolean KoreanQA.Driver::ActAccess(KoreanQA.Command)") {
        issues.Add("허용하지 않은 기존 메서드 변경: " + pair.Key); continue;
    }
    int shift = method.Body.Instructions.Count - pair.Value.Body.Instructions.Count;
    int insertionStart = shift <= 0 ? -1 : Enumerable.Range(0, method.Body.Instructions.Count - shift + 1)
        .FirstOrDefault(start => oldIL.SequenceEqual(WithoutInsertion(method, start, shift)), -1);
    bool unchangedBody = insertionStart >= 0;
    changed.Add(new { method = pair.Key, insertionStart, addedInstructions = shift,
        originalInstructionsUnchangedOutsideInsertion = unchangedBody,
        insertion = unchangedBody ? method.Body.Instructions.Skip(insertionStart).Take(shift)
            .Select(i => i.OpCode + " " + Op(i, method, 0)).ToArray() : Array.Empty<string>() });
    if (!unchangedBody) issues.Add("ActAccess 기존 분기 본문 변경");
}
string Hash(string p) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(p))).ToLowerInvariant();
var report = new {
    status = issues.Count == 0 ? "PASS" : "FAIL", issues,
    before = new { path = args[0], sha256 = Hash(args[0]) },
    after = new { path = args[1], sha256 = Hash(args[1]) },
    unchangedExistingMethods = unchanged, changedExistingMethods = changed,
    newTypes = newTypes.Keys.Except(oldTypes.Keys).ToArray(),
    newMethods = newMethods.Keys.Except(oldMethods.Keys).ToArray(),
    scope = "기존 검수 DLL 메서드·필드와 새 명령 분기를 비교. 실제 게임 자산·원본 게임 DLL은 수정하지 않음."
};
File.WriteAllText(args[2], JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine(JsonSerializer.Serialize(new { report.status, report.unchangedExistingMethods, report.issues }));
if (issues.Count > 0) Environment.Exit(1);
