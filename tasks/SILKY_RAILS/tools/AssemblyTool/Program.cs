using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;
// 원본 코드를 실행하지 않고 허용된 문자열 위치만 바꿉니다.
var resolver=new DefaultAssemblyResolver();resolver.AddSearchDirectory(Path.GetDirectoryName(args[1]));
using var assembly=AssemblyDefinition.ReadAssembly(args[1],new ReaderParameters{AssemblyResolver=resolver});
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> ts){foreach(var t in ts){yield return t;foreach(var n in Walk(t.NestedTypes))yield return n;}}
var methods=Walk(assembly.MainModule.Types).SelectMany(t=>t.Methods).ToDictionary(m=>m.FullName);
if(args[0]=="patch"){
 using var doc=JsonDocument.Parse(File.ReadAllText(args[3]));
 foreach(var r in doc.RootElement.EnumerateArray()){
  var m=methods[r.GetProperty("method").GetString()!];var i=m.Body.Instructions.Single(i=>i.Offset==r.GetProperty("offset").GetInt32());
  if(i.OpCode!=OpCodes.Ldstr||(string)i.Operand!=r.GetProperty("source").GetString())throw new Exception("원문 위치 불일치");
  i.Operand=r.GetProperty("target").GetString();
 }
 assembly.Write(args[2]);Console.WriteLine("문자열 변경 완료");
}else if(args[0]=="verify"){
 using var other=AssemblyDefinition.ReadAssembly(args[2]);var candidate=Walk(other.MainModule.Types).SelectMany(t=>t.Methods).ToDictionary(m=>m.FullName);
 using var doc=JsonDocument.Parse(File.ReadAllText(args[3]));var expected=doc.RootElement.EnumerateArray().ToDictionary(r=>(r.GetProperty("method").GetString()!,r.GetProperty("offset").GetInt32()),r=>r.GetProperty("target").GetString());int count=0;
 if(methods.Count!=candidate.Count)throw new Exception("메서드 개수 불일치");
 string Operand(Instruction i,MethodDefinition m)=>i.Operand switch{Instruction b=>"branch:"+m.Body.Instructions.IndexOf(b),Instruction[] bs=>"switch:"+string.Join(",",bs.Select(b=>m.Body.Instructions.IndexOf(b))),_=>i.Operand?.ToString()??""};
 foreach(var (name,m) in methods){var c=candidate[name];if(m.Attributes!=c.Attributes||m.HasBody!=c.HasBody)throw new Exception(name);if(!m.HasBody)continue;if(m.Body.Instructions.Count!=c.Body.Instructions.Count||m.Body.Variables.Count!=c.Body.Variables.Count)throw new Exception(name);
  for(int j=0;j<m.Body.Instructions.Count;j++){var a=m.Body.Instructions[j];var b=c.Body.Instructions[j];if(expected.TryGetValue((name,a.Offset),out var t)){if(b.OpCode!=OpCodes.Ldstr||(string)b.Operand!=t)throw new Exception(name);count++;}else if(a.OpCode!=b.OpCode||Operand(a,m)!=Operand(b,c))throw new Exception(name);}
 }
 if(count!=expected.Count)throw new Exception("변경 개수 불일치");Console.WriteLine($"메서드 {methods.Count}, 번역 {count}, 그 외 명령 동일");
}else if(args[0]=="qa"||args[0]=="qasdk"){
 var changed=new List<string>();
 foreach(var m in methods.Values.Where(m=>(m.DeclaringType.Name=="SteamManager"&&m.Name=="Awake")||(m.DeclaringType.Name=="AnalyticsManager"&&m.Name=="Awake")||(m.DeclaringType.FullName=="GameAnalyticsSDK.GameAnalytics" && new[]{"Awake","OnEnable","OnApplicationQuit","OnDestroy"}.Contains(m.Name)))){m.Body.Instructions.Clear();m.Body.ExceptionHandlers.Clear();m.Body.Variables.Clear();m.Body.GetILProcessor().Append(Instruction.Create(OpCodes.Ret));changed.Add(m.FullName);}
 if(changed.Count!=(args[0]=="qa"?2:4))throw new Exception("격리 대상 불일치");assembly.Write(args[2]);File.WriteAllText(args[3],JsonSerializer.Serialize(changed));Console.WriteLine("검수 사본 Steam 및 분석 서비스 초기화 차단");
}

