using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;

// 검수 사본에서만 Steam 연결을 끄고, 정식 후보는 검토한 문구 위치만 수정합니다.
var mode = args[0];
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1])));
using var assembly = AssemblyDefinition.ReadAssembly(args[1], new ReaderParameters { AssemblyResolver = resolver });
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> types) {
    foreach (var type in types) { yield return type; foreach (var child in Walk(type.NestedTypes)) yield return child; }
}
var methods = Walk(assembly.MainModule.Types).SelectMany(t => t.Methods).ToArray();
if (mode == "catalog") {
    // 규칙 목록만 읽으며 게임 장면이나 저장 코드는 실행하지 않습니다.
    var runtime = System.Reflection.Assembly.LoadFrom(Path.GetFullPath(args[1]));
    var type = runtime.GetType("Game.Sim.Crafting.Workbench")!;
    var recipes = (System.Collections.IEnumerable)type.GetField("AllRecipes")!.GetValue(null)!;
    object? Property(object value,string name) => value.GetType().GetProperty(name)?.GetValue(value);
    var rows = new List<object>();
    foreach (var recipe in recipes) rows.Add(new { name=Property(recipe!,"Name"), description=Property(recipe!,"Description"), effect=Property(recipe!,"Effect")?.GetType().Name });
    var enums = Walk(assembly.MainModule.Types).Where(t => t.IsEnum).Select(t => new {type=t.FullName,values=t.Fields.Where(f=>f.HasConstant).Select(f=>new {name=f.Name,value=f.Constant})});
    var constants = Walk(assembly.MainModule.Types).SelectMany(t=>t.Fields).Where(f=>f.HasConstant && f.Constant is string).Select(f=>new {field=f.FullName,text=f.Constant});
    File.WriteAllText(args[2],JsonSerializer.Serialize(new {recipes=rows,enums,constants},new JsonSerializerOptions{WriteIndented=true}));
    return;
}
if (mode == "qa") {
    var init = methods.Single(m => m.FullName == "System.Void Game.Steam.SteamworksSteamService::Init()");
    init.Body = new MethodBody(init);
    init.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
    if (args.Length > 3) {
        // 배포본에서 비활성화된 제작사 검사 진입점을 검수 사본에만 엽니다.
        var parse = methods.Single(m => m.FullName == "System.String Game.AutoTestDriver::ParseMode()");
        parse.Body = new MethodBody(parse);
        parse.Body.Instructions.Add(Instruction.Create(OpCodes.Ldstr, args[3]));
        parse.Body.Instructions.Add(Instruction.Create(OpCodes.Ret));
        var main = methods.Single(m => m.FullName == "System.Void Game.Main::_Ready()");
        foreach (var ins in main.Body.Instructions) {
            if (ins.Operand is MethodReference mr && mr.FullName == "System.Void Godot.DisplayServer::WindowSetMode(Godot.DisplayServer/WindowMode,System.Int32)") {
                var value = ins.Previous.Previous.Previous;
                if (value.OpCode == OpCodes.Ldc_I4_1) { value.OpCode = OpCodes.Ldc_I4_0; value.Operand = null; }
            }
        }
        if (args[3] == "ui-layout") {
            // 실제 한국어만 순회합니다. 원래의 의사 번역 스트레스 검사는 별도 이력으로 남깁니다.
            var cctor = methods.Single(m => m.FullName == "System.Void Game.AutoTestDriver::.cctor()");
            if (cctor.Body.Instructions[0].OpCode != OpCodes.Ldc_I4_2 || (string)cctor.Body.Instructions[8].Operand != "pseudo") throw new Exception("검사 언어 초기화 위치 불일치");
            cctor.Body.Instructions[0].OpCode = OpCodes.Ldc_I4_1;
            for (int i=6; i<=9; i++) { cctor.Body.Instructions[i].OpCode=OpCodes.Nop; cctor.Body.Instructions[i].Operand=null; }
            var tick = methods.Single(m => m.FullName == "System.Void Game.AutoTestDriver::TickUiLayout()");
            var type = tick.DeclaringType;
            var first = tick.Body.Instructions[0];
            var il = tick.Body.GetILProcessor();
            void Add(Instruction i) => il.InsertBefore(first, i);
            foreach (var pair in new[] { ("_uiPhase", 2), ("_uiFontIdx", 0), ("_uiLocaleIdx", 0) }) {
                Add(Instruction.Create(OpCodes.Ldarg_0));
                Add(Instruction.Create(OpCodes.Ldfld, type.Fields.Single(f => f.Name == pair.Item1)));
                Add(Instruction.Create(OpCodes.Ldc_I4, pair.Item2));
                Add(Instruction.Create(OpCodes.Bne_Un, first));
            }
            var concat = assembly.MainModule.ImportReference(typeof(string).GetMethod("Concat", new[] { typeof(object), typeof(object), typeof(object) })!);
            Add(Instruction.Create(OpCodes.Ldarg_0));
            Add(Instruction.Create(OpCodes.Ldstr, "korean-qa-"));
            Add(Instruction.Create(OpCodes.Ldarg_0));
            Add(Instruction.Create(OpCodes.Ldfld, type.Fields.Single(f => f.Name == "_frame")));
            Add(Instruction.Create(OpCodes.Box, assembly.MainModule.TypeSystem.Int32));
            Add(Instruction.Create(OpCodes.Ldstr, ".png"));
            Add(Instruction.Create(OpCodes.Call, concat));
            Add(Instruction.Create(OpCodes.Call, methods.Single(m => m.FullName == "System.Void Game.AutoTestDriver::SaveScreenshot(System.String)")));
        }
        else {
            // 대표 진행 검사에서 실제 렌더링 결과를 일정 간격으로 보관합니다.
            var tick = methods.Single(m => m.FullName == "System.Void Game.AutoTestDriver::_Process(System.Double)");
            var frame = tick.DeclaringType.Fields.Single(f => f.Name == "_frame");
            var first = tick.Body.Instructions[0]; var il = tick.Body.GetILProcessor();
            void Add(Instruction i) => il.InsertBefore(first, i);
            Add(Instruction.Create(OpCodes.Ldarg_0)); Add(Instruction.Create(OpCodes.Ldfld, frame));
            Add(Instruction.Create(OpCodes.Ldc_I4, 15)); Add(Instruction.Create(OpCodes.Rem)); Add(Instruction.Create(OpCodes.Brtrue, first));
            var concat = assembly.MainModule.ImportReference(typeof(string).GetMethod("Concat", new[] { typeof(object), typeof(object), typeof(object) })!);
            Add(Instruction.Create(OpCodes.Ldarg_0)); Add(Instruction.Create(OpCodes.Ldstr,args[3]+"-"));
            Add(Instruction.Create(OpCodes.Ldarg_0)); Add(Instruction.Create(OpCodes.Ldfld,frame));
            Add(Instruction.Create(OpCodes.Box,assembly.MainModule.TypeSystem.Int32));
            Add(Instruction.Create(OpCodes.Ldstr,".png")); Add(Instruction.Create(OpCodes.Call,concat));
            Add(Instruction.Create(OpCodes.Call,methods.Single(m => m.FullName == "System.Void Game.AutoTestDriver::SaveScreenshot(System.String)")));
        }
    }
} else if (mode == "patch") {
    var rows = JsonDocument.Parse(File.ReadAllText(args[3])).RootElement.EnumerateArray();
    foreach (var row in rows) {
        var method = methods.Single(m => m.FullName == row.GetProperty("method").GetString());
        var ins = method.Body.Instructions.Single(i => i.Offset == row.GetProperty("offset").GetInt32());
        if (ins.OpCode != OpCodes.Ldstr || (string)ins.Operand != row.GetProperty("source").GetString()) throw new Exception("원문 위치 불일치");
        ins.Operand = row.GetProperty("target").GetString();
    }
    // 글자 크기 조절 모드에서도 함께 배포하는 한글 글꼴을 사용합니다.
    var systemFont = methods.Single(m => m.FullName == "Godot.SystemFont Game.UI.Framework.BoreworksTheme::BuildSystemFont(System.Boolean)");
    var loadFont = methods.Single(m => m.FullName == "Godot.Font Game.UI.Framework.BoreworksTheme::TryLoadFontWithFallback(System.String)");
    var oldReferences = methods.Where(m => m.HasBody).SelectMany(m => m.Body.Instructions)
        .Where(i => i.Operand is MethodReference mr && mr.FullName == systemFont.FullName).ToArray();
    systemFont.ReturnType = loadFont.ReturnType;
    systemFont.Body = new MethodBody(systemFont);
    var regular = Instruction.Create(OpCodes.Ldstr, "res://Art/Assets/UI/Fonts/PixelOperator.ttf");
    var call = Instruction.Create(OpCodes.Call, loadFont);
    var il = systemFont.Body.GetILProcessor();
    il.Append(Instruction.Create(OpCodes.Ldarg_0));
    il.Append(Instruction.Create(OpCodes.Brfalse, regular));
    il.Append(Instruction.Create(OpCodes.Ldstr, "res://Art/Assets/UI/Fonts/PixelOperator-Bold.ttf"));
    il.Append(Instruction.Create(OpCodes.Br, call));
    il.Append(regular); il.Append(call); il.Append(Instruction.Create(OpCodes.Ret));
    foreach (var reference in oldReferences) reference.Operand = systemFont;
    // 적재함 가득 참 안내도 UI와 같은 글꼴로 그립니다.
    var labelFont = methods.Single(m => m.FullName == "Godot.Font Game.UI.Framework.BoreworksTheme::get_LabelFont()");
    int replaced = 0;
    foreach (var method in methods.Where(m => m.HasBody && m.DeclaringType.FullName == "Game.PlayerNode")) {
        foreach (var instruction in method.Body.Instructions) {
            if (instruction.Operand is MethodReference mr && mr.FullName == "Godot.Font Godot.ThemeDB::get_FallbackFont()") {
                instruction.Operand = labelFont; replaced++;
            }
        }
    }
    if (replaced != 1 || oldReferences.Length != 2) throw new Exception("글꼴 사용 위치 수 불일치");
} else { throw new Exception("지원하지 않는 모드"); }
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[2]))!);
assembly.Write(args[2]);
