using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;

// 게임의 메서드별 문자열을 기록하고 검수 사본의 저장·Steam 연결만 격리합니다.
try {
var mode = args[0];
var input = Path.GetFullPath(args[1]);
var output = Path.GetFullPath(args[2]);
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(input));
using var assembly = AssemblyDefinition.ReadAssembly(input, new ReaderParameters { AssemblyResolver = resolver });
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> types) {
    foreach (var t in types) { yield return t; foreach(var c in Walk(t.NestedTypes)) yield return c; }
}
var rows = new List<object>();
foreach (var type in Walk(assembly.MainModule.Types)) {
    foreach (var method in type.Methods.Where(m => m.HasBody)) {
        foreach (var ins in method.Body.Instructions) {
            if (ins.OpCode == OpCodes.Ldstr) rows.Add(new { method = method.FullName, offset = ins.Offset, text = ins.Operand });
        }
    }
}
Directory.CreateDirectory(Path.GetDirectoryName(output));
var jsonOptions = new JsonSerializerOptions { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
if (mode == "inventory") { File.WriteAllText(output, JsonSerializer.Serialize(rows, jsonOptions)); return; }
if (mode == "surface") {
    // 표시 코드와 자동 시작점을 찾기 위해 문자열·호출·속성을 원본 위치에 연결합니다.
    var data = new {
        assembly = assembly.Name.FullName,
        references = assembly.MainModule.AssemblyReferences.Select(a=>a.FullName).ToArray(),
        types = Walk(assembly.MainModule.Types).Select(t=>new {
            type=t.FullName, baseType=t.BaseType?.FullName,
            methods=t.Methods.Select(m=>new {
                method=m.FullName, name=m.Name, attributes=m.CustomAttributes.Select(a=>a.AttributeType.FullName).ToArray(),
                literals=m.HasBody ? m.Body.Instructions.Where(i=>i.OpCode==OpCodes.Ldstr).Select(i=>new {offset=i.Offset,text=(string)i.Operand}).ToArray() : [],
                calls=m.HasBody ? m.Body.Instructions.Where(i=>i.Operand is MethodReference).Select(i=>new {offset=i.Offset,op=i.OpCode.Name,target=((MethodReference)i.Operand).FullName,scope=((MethodReference)i.Operand).DeclaringType.Scope.Name}).ToArray() : []
            }).ToArray()
        }).ToArray()
    };
    File.WriteAllText(output,JsonSerializer.Serialize(data,jsonOptions));return;
}
if (mode == "metadata") {
    var data=Walk(assembly.MainModule.Types).Select(t=>new {type=t.FullName,baseType=t.BaseType?.FullName,attributes=t.Attributes.ToString(),fields=t.Fields.Select(f=>new {name=f.FullName,attributes=f.Attributes.ToString(),constant=f.Constant}).ToArray(),methods=t.Methods.Select(m=>new {name=m.FullName,attributes=m.Attributes.ToString(),custom=m.CustomAttributes.Select(a=>a.AttributeType.FullName).ToArray()}).ToArray()}).ToArray();
    File.WriteAllText(output,JsonSerializer.Serialize(data,jsonOptions));return;
}
if (mode == "dump") {
    var methods = Walk(assembly.MainModule.Types).SelectMany(t=>t.Methods).Where(m=>m.HasBody).Select(m=>new {
        method=m.FullName, locals=m.Body.Variables.Select(v=>v.VariableType.FullName).ToArray(),
        instructions=m.Body.Instructions.Select(i=>new {offset=i.Offset, op=i.OpCode.Name, operand=i.Operand is Instruction target ? "IL_"+target.Offset.ToString("X4") : i.Operand is Instruction[] targets ? string.Join(",",targets.Select(t=>"IL_"+t.Offset.ToString("X4"))) : i.Operand?.ToString()}).ToArray(),
        handlers=m.Body.ExceptionHandlers.Select(h=>new {kind=h.HandlerType.ToString(), start=h.TryStart?.Offset,end=h.TryEnd?.Offset,handler=h.HandlerStart?.Offset,handlerEnd=h.HandlerEnd?.Offset}).ToArray()
    });
    File.WriteAllText(output, JsonSerializer.Serialize(methods,jsonOptions)); return;
}
if (mode == "patch") {
    using var document=JsonDocument.Parse(File.ReadAllText(args[3]));
    var changes=document.RootElement.EnumerateArray().ToArray();
    foreach(var row in changes) {
        var method=Walk(assembly.MainModule.Types).SelectMany(t=>t.Methods).Single(m=>m.FullName==row.GetProperty("method").GetString());
        var ins=method.Body.Instructions.Single(i=>i.Offset==row.GetProperty("offset").GetInt32());
        if(ins.OpCode!=OpCodes.Ldstr || (string)ins.Operand!=row.GetProperty("source").GetString()) throw new Exception("코드 원문 위치 불일치");
        ins.Operand=row.GetProperty("target").GetString();
    }
    if(args.Length>4) {
        using var helper=AssemblyDefinition.ReadAssembly(args[4]);
        var support=helper.MainModule.Types.Single(t=>t.FullName=="CombolandsKorean.KoreanSupport");
        var start=Walk(assembly.MainModule.Types).Single(t=>t.FullName=="Shared.SceneOrchestrator").Methods.Single(m=>m.Name=="Start");
        var initialize=assembly.MainModule.ImportReference(support.Methods.Single(m=>m.Name=="Initialize"));
        start.Body.GetILProcessor().InsertBefore(start.Body.Instructions.Last(),Instruction.Create(OpCodes.Call,initialize));
        var category=assembly.MainModule.ImportReference(support.Methods.Single(m=>m.Name=="CategoryName"));
        int count=0;
        foreach(var type in Walk(assembly.MainModule.Types).Where(t=>t.FullName=="Utils.BuildingCategoryVisualization" || t.FullName=="UI.EndingScreens.UnlockScreenGuild"))
        foreach(var method in type.Methods.Where(m=>m.HasBody))
        foreach(var ins in method.Body.Instructions.ToArray()) {
            if(ins.Operand is MethodReference target && target.Name=="set_text" && ins.Previous?.Operand is MethodReference prev && prev.Name=="ToString") {
                method.Body.GetILProcessor().InsertBefore(ins,Instruction.Create(OpCodes.Call,category));count++;
            }
        }
        if(count!=2)throw new Exception("표시 enum 위치 수 불일치: "+count);
        var mechanicImage=assembly.MainModule.ImportReference(support.Methods.Single(m=>m.Name=="SetMechanicSprite"));
        var mechanicInit=Walk(assembly.MainModule.Types).SelectMany(t=>t.Methods).Single(m=>m.FullName=="System.Void UI.EndingScreens.VictoryScreenGenericUnlockPopup::Init(Entities.Data.GameMechanicUnlock)");
        var imageSetter=mechanicInit.Body.Instructions.Single(i=>i.OpCode==OpCodes.Callvirt && i.Operand is MethodReference m && m.FullName=="System.Void UnityEngine.UI.Image::set_sprite(UnityEngine.Sprite)");
        imageSetter.OpCode=OpCodes.Call;imageSetter.Operand=mechanicImage;
    }
    assembly.Write(output); return;
}
if (mode == "qa" || mode == "qa-controls") {
    var changes = new List<string>();
    foreach (var type in Walk(assembly.MainModule.Types)) {
        foreach (var method in type.Methods.Where(m => m.HasBody)) {
            if ((type.FullName == "SteamManager" && method.Name == "Awake") || (type.FullName == "IO.StateSaver" && method.Name == "get_PATH")) {
                method.Body = new MethodBody(method);
                var il = method.Body.GetILProcessor();
                if (method.Name == "get_PATH") il.Append(il.Create(OpCodes.Ldstr, Path.GetFullPath(args[3])));
                il.Append(il.Create(OpCodes.Ret));
                changes.Add(method.FullName);
            }
        }
    }
    if (changes.Count != 2) throw new Exception("검수 격리 메서드 수가 다릅니다.");
    if(mode=="qa-controls") {
        var type=Walk(assembly.MainModule.Types).Single(t=>t.FullName=="Interaction.CheatsHandler");
        var start=type.Methods.Single(m=>m.Name=="Start");
        if(start.Body.Instructions.Count!=1 || start.Body.Instructions[0].OpCode!=OpCodes.Ret)throw new Exception("시험 초기화 구조 변경");
        var il=start.Body.GetILProcessor();var end=start.Body.Instructions[0];
        il.InsertBefore(end,Instruction.Create(OpCodes.Ldarg_0));
        il.InsertBefore(end,Instruction.Create(OpCodes.Ldc_I4_1));
        il.InsertBefore(end,Instruction.Create(OpCodes.Stfld,type.Fields.Single(f=>f.Name=="_cheatsEnabled")));
        var update=type.Methods.Single(m=>m.Name=="Update");int count=0;
        // 화면 자동 검수에서 오른쪽 Shift 인식이 되지 않아 이 검수 사본만 단일 키를 사용합니다.
        foreach(var ins in update.Body.Instructions) {
            if(ins.OpCode==OpCodes.Ldc_I4 && (int)ins.Operand==303 && ins.Next.Operand is MethodReference call && call.FullName=="System.Boolean UnityEngine.Input::GetKey(UnityEngine.KeyCode)") {
                ins.OpCode=OpCodes.Ldc_I4_1;ins.Operand=null;ins.Next.OpCode=OpCodes.Nop;ins.Next.Operand=null;count++;
            }
        }
        if(count!=2)throw new Exception("오른쪽 Shift 검사 수 불일치 "+count);
        changes.Add(start.FullName);changes.Add(update.FullName);
    }
    assembly.Write(output);
    File.WriteAllText(output + ".qa.json", JsonSerializer.Serialize(changes,jsonOptions));
    return;
}
throw new Exception("알 수 없는 실행 방식입니다.");
} catch(Exception exception) {
    Console.Error.WriteLine(exception);
    Environment.ExitCode=1;
}
