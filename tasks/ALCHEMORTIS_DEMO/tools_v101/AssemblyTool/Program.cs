using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;

// 게임 코드를 실행하지 않고 메서드별 문자열을 조사·수정합니다.
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(args[1]));
using var assembly = AssemblyDefinition.ReadAssembly(args[1], new ReaderParameters { AssemblyResolver = resolver });
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> source) { foreach (var t in source) { yield return t; foreach (var n in Walk(t.NestedTypes)) yield return n; } }
var methods = Walk(assembly.MainModule.Types).SelectMany(t => t.Methods).ToArray();
var jsonOptions = new JsonSerializerOptions { WriteIndented = true };
if (args[0] == "dump") {
    var strings = methods.Where(m => m.HasBody).SelectMany(m => m.Body.Instructions.Where(i => i.OpCode == OpCodes.Ldstr).Select(i => new { method = m.FullName, offset = i.Offset, instruction_index = m.Body.Instructions.IndexOf(i), source = (string)i.Operand, context = m.Body.Instructions.Skip(Math.Max(0, m.Body.Instructions.IndexOf(i) - 2)).Take(7).Select(x => x.ToString()).ToArray() }));
    File.WriteAllText(args[2], JsonSerializer.Serialize(strings, jsonOptions));
    File.WriteAllText(args[2] + ".il.json", JsonSerializer.Serialize(methods.Where(m => m.HasBody && (m.DeclaringType.FullName.Contains("VisualUtilities") || m.DeclaringType.FullName.Contains("LanguageSelectionDialog"))).Select(m => new { method = m.FullName, instructions = m.Body.Instructions.Select(i => i.ToString()) }), jsonOptions));
    string Operand(Instruction i, MethodDefinition m) => i.Operand switch {
        null => "", Instruction target => "branch:" + m.Body.Instructions.IndexOf(target),
        Instruction[] targets => "switch:" + string.Join(",", targets.Select(t => m.Body.Instructions.IndexOf(t))),
        _ => i.Operand.ToString() ?? ""
    };
    var snapshot = new {
        types = Walk(assembly.MainModule.Types).Select(t => new { name=t.FullName, attributes=t.Attributes.ToString(), fields=t.Fields.Select(f => new { name=f.FullName, attributes=f.Attributes.ToString(), constant=f.Constant?.ToString() }), properties=t.Properties.Select(p => p.FullName), custom=t.CustomAttributes.Select(a=>a.ToString()) }),
        methods = methods.Select(m => new { method=m.FullName, attributes=m.Attributes.ToString(), custom=m.CustomAttributes.Select(a=>a.ToString()), locals=m.HasBody ? m.Body.Variables.Select(v=>v.VariableType.FullName).ToArray() : Array.Empty<string>(), instructions=m.HasBody ? m.Body.Instructions.Select(i=>new { opcode=i.OpCode.ToString(),operand=Operand(i,m) }).ToArray() : null })
    };
    File.WriteAllText(args[2] + ".snapshot.json", JsonSerializer.Serialize(snapshot, jsonOptions));
    object Argument(CustomAttributeArgument a) => new { type=a.Type.FullName, value=a.Value is CustomAttributeArgument[] items ? (object)items.Select(Argument).ToArray() : a.Value?.ToString() };
    var metadata=new List<object>();
    void Attributes(string owner,ICustomAttributeProvider provider) {
        foreach(var attribute in provider.CustomAttributes)metadata.Add(new { owner, constructor=attribute.Constructor.FullName, arguments=attribute.ConstructorArguments.Select(Argument), fields=attribute.Fields.Select(a=>new {a.Name,argument=Argument(a.Argument)}), properties=attribute.Properties.Select(a=>new {a.Name,argument=Argument(a.Argument)}) });
    }
    Attributes("assembly",assembly); Attributes("module",assembly.MainModule);
    foreach(var type in Walk(assembly.MainModule.Types)) {
        Attributes(type.FullName,type);
        foreach(var field in type.Fields)Attributes(field.FullName,field);
        foreach(var property in type.Properties)Attributes(property.FullName,property);
        foreach(var method in type.Methods) {
            Attributes(method.FullName,method); Attributes(method.FullName+" return",method.MethodReturnType);
            foreach(var parameter in method.Parameters)Attributes(method.FullName+" parameter "+parameter.Name,parameter);
        }
    }
    File.WriteAllText(args[2]+".attributes.json",JsonSerializer.Serialize(metadata,jsonOptions));
    File.WriteAllText(args[2]+".enums.json",JsonSerializer.Serialize(Walk(assembly.MainModule.Types).Where(t=>t.IsEnum).Select(t=>new {name=t.FullName,values=t.Fields.Where(f=>f.IsLiteral).Select(f=>new {f.Name,value=f.Constant})}),jsonOptions));
    Console.WriteLine("문자열·글꼴·언어 선택 명령 추출 완료");
} else if (args[0] == "qa_runner") {
    using var helper = AssemblyDefinition.ReadAssembly(args[3]);
    var start = helper.MainModule.Types.Single(t=>t.FullName=="KoreanQa.Runner").Methods.Single(m=>m.Name=="Start");
    var ready = methods.Single(m=>m.FullName=="System.Void Game.Autoload.VisualUtilities::_Ready()");
    var last = ready.Body.Instructions.Last();
    if(last.OpCode!=OpCodes.Ret)throw new Exception("검수 연결 위치 변경");
    ready.Body.GetILProcessor().InsertBefore(last,Instruction.Create(OpCodes.Call,assembly.MainModule.ImportReference(start)));
    assembly.Write(args[2]);
} else if (args[0] == "qa") {
    var targets = new[] { "System.Void SentryAutoInit::Init()", "System.Void Game.Steam.SteamService::UnlockAchievement(System.String)", "System.Void Game.Steam.SteamService::OpenWebOverlay(System.String)" };
    foreach (var name in targets) {
        var m = methods.Single(m => m.FullName == name);
        m.Body.Instructions.Clear(); m.Body.ExceptionHandlers.Clear(); m.Body.Variables.Clear();
        m.Body.GetILProcessor().Append(Instruction.Create(OpCodes.Ret));
    }
    assembly.Write(args[2]);
    File.WriteAllText(args[2] + ".changes.json", JsonSerializer.Serialize(targets, jsonOptions));
} else if (args[0] == "patch") {
    var references = assembly.MainModule.GetMemberReferences().OfType<MethodReference>().ToArray();
    var toName=references.First(m=>m.FullName=="Godot.StringName Godot.StringName::op_Implicit(System.String)");
    var toString=references.First(m=>m.FullName=="System.String Godot.StringName::op_Implicit(Godot.StringName)");
    var translate=references.First(m=>m.FullName=="Godot.StringName Godot.TranslationServer::Translate(Godot.StringName,Godot.StringName)");
    var modified=new HashSet<MethodDefinition>();
    using var doc = JsonDocument.Parse(File.ReadAllText(args[3]));
    foreach (var r in doc.RootElement.EnumerateArray()) {
        var m = methods.Single(m => m.FullName == r.GetProperty("method").GetString());
        var i = m.Body.Instructions.Single(i => i.Offset == r.GetProperty("offset").GetInt32());
        if (i.OpCode != OpCodes.Ldstr || (string)i.Operand != r.GetProperty("source").GetString()) throw new Exception("원본 위치 불일치");
        if(r.TryGetProperty("translate",out var isTranslation) && isTranslation.GetBoolean()) {
            var additional=new[]{Instruction.Create(OpCodes.Call,toName),Instruction.Create(OpCodes.Ldnull),Instruction.Create(OpCodes.Call,translate),Instruction.Create(OpCodes.Call,toString)};
            var previous=i;
            foreach(var extra in additional){m.Body.GetILProcessor().InsertAfter(previous,extra);previous=extra;}
            modified.Add(m);
        } else i.Operand = r.GetProperty("target").GetString();
    }
    // 한국어에서만 실행 중 삽입되는 용어의 기본 표시를 번역합니다.
    var format=methods.Single(m=>m.FullName=="System.String Game.Util.Keyword::Format(System.Boolean,System.Boolean,System.Boolean,System.String)");
    var entry=format.Body.Instructions[0];
    var getLocale=assembly.MainModule.ImportReference(translate.DeclaringType.Resolve().Methods.Single(m=>m.Name=="GetLocale" && !m.HasParameters));
    var startsWith=new MethodReference("StartsWith",assembly.MainModule.TypeSystem.Boolean,assembly.MainModule.TypeSystem.String){HasThis=true};
    startsWith.Parameters.Add(new ParameterDefinition(assembly.MainModule.TypeSystem.String));
    var getLocalized=methods.Single(m=>m.FullName=="System.String Game.Util.Keyword::get_WordLocalized()");
    var prefix=new[]{Instruction.Create(OpCodes.Ldarg,format.Parameters[3]),Instruction.Create(OpCodes.Brtrue,entry),Instruction.Create(OpCodes.Call,getLocale),Instruction.Create(OpCodes.Ldstr,"ko"),Instruction.Create(OpCodes.Callvirt,startsWith),Instruction.Create(OpCodes.Brfalse,entry),Instruction.Create(OpCodes.Ldarg_0),Instruction.Create(OpCodes.Call,getLocalized),Instruction.Create(OpCodes.Starg,format.Parameters[3])};
    foreach(var i in prefix)format.Body.GetILProcessor().InsertBefore(entry,i);
    modified.Add(format);
    // 보관함 그림에 포함된 영문을 한국어 전용 UI로 덮습니다. 원본 그림은 유지합니다.
    var inventory=methods.Single(m=>m.FullName=="System.Void Game.Gameplay.PlayerInventory::_Ready()");
    var frame=inventory.DeclaringType.Fields.Single(f=>f.Name=="frame");
    var loadScene=methods.Where(m=>m.HasBody).SelectMany(m=>m.Body.Instructions).Select(i=>i.Operand).OfType<MethodReference>().First(m=>m.FullName=="!!0 Godot.GD::Load<Godot.PackedScene>(System.String)");
    var instantiate=references.First(m=>m.FullName=="Godot.Node Godot.PackedScene::Instantiate(Godot.PackedScene/GenEditState)");
    var addChild=references.First(m=>m.FullName=="System.Void Godot.Node::AddChild(Godot.Node,System.Boolean,Godot.Node/InternalMode)");
    var inventoryPrefix=new[]{Instruction.Create(OpCodes.Ldarg_0),Instruction.Create(OpCodes.Ldfld,frame),Instruction.Create(OpCodes.Ldstr,"res://korean_patch/inventory_labels.tscn"),Instruction.Create(OpCodes.Call,loadScene),Instruction.Create(OpCodes.Ldc_I4_0),Instruction.Create(OpCodes.Callvirt,instantiate),Instruction.Create(OpCodes.Ldc_I4_0),Instruction.Create(OpCodes.Ldc_I4_0),Instruction.Create(OpCodes.Callvirt,addChild)};
    var inventoryEntry=inventory.Body.Instructions[0];
    foreach(var i in inventoryPrefix)inventory.Body.GetILProcessor().InsertBefore(inventoryEntry,i);
    modified.Add(inventory);
    // 명령 추가로 분기 거리가 늘어도 기존 분기 목적지는 그대로 유지합니다.
    var longBranches=new Dictionary<OpCode,OpCode>{{OpCodes.Br_S,OpCodes.Br},{OpCodes.Brtrue_S,OpCodes.Brtrue},{OpCodes.Brfalse_S,OpCodes.Brfalse},{OpCodes.Beq_S,OpCodes.Beq},{OpCodes.Bne_Un_S,OpCodes.Bne_Un},{OpCodes.Bge_S,OpCodes.Bge},{OpCodes.Bge_Un_S,OpCodes.Bge_Un},{OpCodes.Bgt_S,OpCodes.Bgt},{OpCodes.Bgt_Un_S,OpCodes.Bgt_Un},{OpCodes.Ble_S,OpCodes.Ble},{OpCodes.Ble_Un_S,OpCodes.Ble_Un},{OpCodes.Blt_S,OpCodes.Blt},{OpCodes.Blt_Un_S,OpCodes.Blt_Un},{OpCodes.Leave_S,OpCodes.Leave}};
    foreach(var m in modified)foreach(var i in m.Body.Instructions)if(longBranches.TryGetValue(i.OpCode,out var longer))i.OpCode=longer;
    // 기존 일곱 언어를 보존하고 한국어 항목과 기존 한글 지원 글꼴 연결을 추가합니다.
    Instruction Clone(Instruction i) {
        var n = Instruction.Create(OpCodes.Nop); n.OpCode = i.OpCode; n.Operand = i.Operand; return n;
    }
    var language = methods.Single(m => m.FullName == "System.Void Game.UI.LanguageSelectionDialog::.cctor()");
    if (language.Body.Instructions[0].OpCode != OpCodes.Ldc_I4_7) throw new Exception("언어 배열 구조 변경");
    language.Body.Instructions[0].OpCode = OpCodes.Ldc_I4_8;
    var option = language.Body.Instructions.Where(i => i.Offset >= 6 && i.Offset <= 46).Select(Clone).ToArray();
    option[1].OpCode = OpCodes.Ldc_I4_7;
    option.Single(i => i.OpCode == OpCodes.Ldstr && (string)i.Operand == "en-US").Operand = "ko-KR";
    var names = option.Where(i => i.OpCode == OpCodes.Ldstr && (string)i.Operand == "English").ToArray();
    names[0].Operand = "Korean"; names[1].Operand = "한국어";
    var beforeOption = language.Body.Instructions.Single(i => i.Offset == 0x125);
    foreach (var i in option) language.Body.GetILProcessor().InsertBefore(beforeOption, i);
    var fonts = methods.Single(m => m.FullName == "System.Void Game.Autoload.VisualUtilities::.cctor()");
    var fontPair = fonts.Body.Instructions.Where(i => i.Offset >= 0x1bc && i.Offset <= 0x1c7).Select(Clone).ToArray();
    fontPair.Single(i => i.OpCode == OpCodes.Ldstr).Operand = "ko";
    var beforeFonts = fonts.Body.Instructions.Single(i => i.Offset == 0x1cc);
    foreach (var i in fontPair) fonts.Body.GetILProcessor().InsertBefore(beforeFonts, i);
    assembly.Write(args[2]);
}
