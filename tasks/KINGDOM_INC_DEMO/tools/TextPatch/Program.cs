using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;
// 원본 코드의 표시 문자열 네 곳만 변경하고 모든 메서드를 별도로 비교합니다.
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> types) {
    foreach(var t in types) { yield return t; foreach(var n in Walk(t.NestedTypes)) yield return n; }
}
using var original=AssemblyDefinition.ReadAssembly(args[1]);
using var document=JsonDocument.Parse(File.ReadAllText(args[3]));
var expected=document.RootElement.EnumerateArray().ToDictionary(
    r=>(r.GetProperty("method").GetString()!,r.GetProperty("offset").GetInt32()),
    r=>(source:r.GetProperty("source").GetString()!,target:r.GetProperty("expected").GetString()!));
var all=Walk(original.MainModule.Types).SelectMany(t=>t.Methods).ToArray();
if(args[0]=="patch") {
    int changed=0;
    foreach(var m in all.Where(m=>m.HasBody)) foreach(var i in m.Body.Instructions)
        if(expected.TryGetValue((m.FullName,i.Offset),out var e)) {
            if(i.OpCode!=OpCodes.Ldstr || (string)i.Operand!=e.source) throw new Exception("원문 위치 불일치");
            i.Operand=e.target; changed++;
        }
    if(changed!=expected.Count) throw new Exception("변경 위치 누락");
    original.Write(args[2]); Console.WriteLine($"표시 문자열 {changed}곳 변경"); return;
}
if(args[0]!="verify") throw new Exception("알 수 없는 명령");
using var candidate=AssemblyDefinition.ReadAssembly(args[2]);
var otherTypes=Walk(candidate.MainModule.Types).ToArray();
var oldTypes=Walk(original.MainModule.Types).ToArray();
if(oldTypes.Length!=otherTypes.Length) throw new Exception("형식 수 변경");
if(!original.MainModule.AssemblyReferences.Select(r=>r.FullName).SequenceEqual(candidate.MainModule.AssemblyReferences.Select(r=>r.FullName))) throw new Exception("참조 변경");
string Meta(TypeDefinition t)=>JsonSerializer.Serialize(new{
    t.FullName,t.Attributes,baseType=t.BaseType?.FullName,t.ClassSize,t.PackingSize,
    fields=t.Fields.Select(f=>new{f.FullName,f.Attributes,f.Constant,data=Convert.ToBase64String(f.InitialValue)}),
    properties=t.Properties.Select(p=>new{p.FullName,p.Attributes,get=p.GetMethod?.FullName,set=p.SetMethod?.FullName}),
    attributes=t.CustomAttributes.Select(a=>Convert.ToBase64String(a.GetBlob()))
});
string Operand(Instruction i,MethodDefinition m)=>i.Operand switch{
    Instruction b=>"branch:"+m.Body.Instructions.IndexOf(b),
    Instruction[] bs=>"switch:"+string.Join(",",bs.Select(b=>m.Body.Instructions.IndexOf(b))),
    _=>i.Operand?.ToString()??""
};
int checkedMethods=0,checkedStrings=0;
for(int ti=0;ti<oldTypes.Length;ti++){
    var at=oldTypes[ti];var bt=otherTypes[ti];
    if(Meta(at)!=Meta(bt)||at.Methods.Count!=bt.Methods.Count) throw new Exception("형식 경계 변경:"+at.FullName);
    for(int mi=0;mi<at.Methods.Count;mi++){
        var a=at.Methods[mi];var b=bt.Methods[mi];checkedMethods++;
        if(a.FullName!=b.FullName||a.Attributes!=b.Attributes||a.ImplAttributes!=b.ImplAttributes||a.HasBody!=b.HasBody) throw new Exception("메서드 정의 변경");
        if(!a.HasBody) continue;
        if(a.Body.Instructions.Count!=b.Body.Instructions.Count || a.Body.InitLocals!=b.Body.InitLocals ||
           !a.Body.Variables.Select(v=>v.VariableType.FullName).SequenceEqual(b.Body.Variables.Select(v=>v.VariableType.FullName))) throw new Exception("메서드 구조 변경");
        string Handlers(MethodDefinition m)=>JsonSerializer.Serialize(m.Body.ExceptionHandlers.Select(h=>new{
            h.HandlerType,type=h.CatchType?.FullName,
            ts=m.Body.Instructions.IndexOf(h.TryStart),te=m.Body.Instructions.IndexOf(h.TryEnd),
            hs=m.Body.Instructions.IndexOf(h.HandlerStart),he=m.Body.Instructions.IndexOf(h.HandlerEnd),
            fs=m.Body.Instructions.IndexOf(h.FilterStart)}));
        if(Handlers(a)!=Handlers(b)) throw new Exception("예외처리 경계 변경");
        for(int j=0;j<a.Body.Instructions.Count;j++){
            var x=a.Body.Instructions[j];var y=b.Body.Instructions[j];
            if(expected.TryGetValue((a.FullName,x.Offset),out var e)){
                if(x.OpCode!=OpCodes.Ldstr||(string)x.Operand!=e.source||y.OpCode!=OpCodes.Ldstr||(string)y.Operand!=e.target) throw new Exception("번역 불일치");
                checkedStrings++;
            } else if(x.OpCode!=y.OpCode||Operand(x,a)!=Operand(y,b)) throw new Exception("허용 밖 코드 변경:"+a.FullName);
        }
    }
}
if(checkedStrings!=expected.Count) throw new Exception("번역 개수 불일치");
Console.WriteLine(JsonSerializer.Serialize(new{status="PASS",types=oldTypes.Length,methods=checkedMethods,translations=checkedStrings}));
