using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;
// 원본 코드를 실행하지 않고 허용된 문자열 위치만 바꿉니다.
var resolver=new DefaultAssemblyResolver();resolver.AddSearchDirectory(Path.GetDirectoryName(args[1]));
using var assembly=AssemblyDefinition.ReadAssembly(args[1],new ReaderParameters{AssemblyResolver=resolver});
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> ts){foreach(var t in ts){yield return t;foreach(var n in Walk(t.NestedTypes))yield return n;}}
var allMethods=Walk(assembly.MainModule.Types).SelectMany(t=>t.Methods).ToArray();
if(args[0]=="dumpall"){
 var rows=allMethods.Where(m=>m.HasBody).SelectMany(m=>m.Body.Instructions.Where(i=>i.OpCode==OpCodes.Ldstr).Select(i=>new {method=m.FullName,token=m.MetadataToken.ToInt32(),offset=i.Offset,source=(string)i.Operand,context=m.Body.Instructions.Skip(Math.Max(0,m.Body.Instructions.IndexOf(i)-2)).Take(14).Select(j=>j.ToString()).ToArray()}));
 File.WriteAllText(args[2],JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));return;
}
var methods=allMethods.ToDictionary(m=>m.FullName);
if(args[0]=="verify_isolation"){
 using var isolated=AssemblyDefinition.ReadAssembly(args[2]);var im=Walk(isolated.MainModule.Types).SelectMany(t=>t.Methods).ToDictionary(m=>m.FullName);
 if(!methods.Keys.ToHashSet().SetEquals(im.Keys))throw new Exception("검수 메서드 집합 불일치");int changed=0;
 foreach(var pair in methods){var a=pair.Value;var b=im[pair.Key];if(a.Attributes!=b.Attributes||a.HasBody!=b.HasBody)throw new Exception(pair.Key);if(!a.HasBody)continue;
  if(a.DeclaringType.Name=="SteamHelper"&&a.Name=="Initialize"){if(b.Body.Instructions.Count!=2||b.Body.Instructions[0].OpCode!=OpCodes.Call||b.Body.Instructions[0].Operand.ToString()!="System.Void KoreanQA.Bootstrap::Start()"||b.Body.Instructions[1].OpCode!=OpCodes.Ret)throw new Exception("검수 진입점 경계 오류");changed++;continue;}
  if(!a.Body.Instructions.Select(x=>x.ToString()).SequenceEqual(b.Body.Instructions.Select(x=>x.ToString())))throw new Exception(pair.Key);
 }
 if(changed!=1)throw new Exception("검수 변경 메서드 수 오류");Console.WriteLine("검수 코드 경계 통과: SteamHelper.Initialize 1개만 변경");return;
}
if(args[0]=="dump"){
 var rows=methods.Values.Where(m=>m.HasBody).SelectMany(m=>m.Body.Instructions.Where(i=>i.OpCode==OpCodes.Ldstr).Select(i=>new {method=m.FullName,offset=i.Offset,source=(string)i.Operand,context=m.Body.Instructions.Skip(Math.Max(0,m.Body.Instructions.IndexOf(i)-2)).Take(8).Select(j=>j.ToString()).ToArray()}));
 File.WriteAllText(args[2],JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));
 Console.WriteLine("코드 문자열 추출 완료");
}else if(args[0]=="isolate"){
 var m=methods.Values.Single(m=>m.DeclaringType.Name=="SteamHelper"&&m.Name=="Initialize");
 m.Body.Instructions.Clear();m.Body.ExceptionHandlers.Clear();m.Body.Variables.Clear();m.Body.GetILProcessor().Append(Instruction.Create(OpCodes.Ret));
 if(args.Length>3){using var support=AssemblyDefinition.ReadAssembly(args[3]);var entry=support.MainModule.Types.Single(t=>t.FullName=="KoreanQA.Bootstrap").Methods.Single(m=>m.Name=="Start");m.Body.GetILProcessor().InsertBefore(m.Body.Instructions[0],Instruction.Create(OpCodes.Call,assembly.MainModule.ImportReference(entry)));}
 assembly.Write(args[2]);Console.WriteLine("검수 사본 Steam 초기화 격리");
}else if(args[0]=="patch"||args[0]=="literal_patch"){
 using var doc=JsonDocument.Parse(File.ReadAllText(args[3]));
 foreach(var r in doc.RootElement.EnumerateArray()){
  var m=methods[r.GetProperty("method").GetString()!];var i=m.Body.Instructions.Single(i=>i.Offset==r.GetProperty("offset").GetInt32());
  if(i.OpCode!=OpCodes.Ldstr||(string)i.Operand!=r.GetProperty("source").GetString())throw new Exception("원문 위치 불일치");
  i.Operand=r.GetProperty("target").GetString();
 }
 if(args[0]=="literal_patch"){assembly.Write(args[2]);Console.WriteLine("보조 화면 문자열 변경 완료");return;}
 // 저장에 쓰는 이름·열거형을 보존하고 실제 표시 지점에만 변환을 추가합니다.
 using var labels=JsonDocument.Parse(File.ReadAllText(args[4]));
 var helper=new TypeDefinition("","KoreanPatchText",TypeAttributes.Public|TypeAttributes.Abstract|TypeAttributes.Sealed,assembly.MainModule.TypeSystem.Object);assembly.MainModule.Types.Add(helper);
 var label=new MethodDefinition("Label",MethodAttributes.Public|MethodAttributes.Static,assembly.MainModule.TypeSystem.String);label.Parameters.Add(new ParameterDefinition(assembly.MainModule.TypeSystem.String));helper.Methods.Add(label);
 var equality=new MethodReference("op_Equality",assembly.MainModule.TypeSystem.Boolean,assembly.MainModule.TypeSystem.String){HasThis=false};equality.Parameters.Add(new ParameterDefinition(assembly.MainModule.TypeSystem.String));equality.Parameters.Add(new ParameterDefinition(assembly.MainModule.TypeSystem.String));
 var il=label.Body.GetILProcessor();
 foreach(var pair in labels.RootElement.EnumerateObject()){
  var next=Instruction.Create(OpCodes.Nop);il.Append(Instruction.Create(OpCodes.Ldarg_0));il.Append(Instruction.Create(OpCodes.Ldstr,pair.Name));il.Append(Instruction.Create(OpCodes.Call,equality));il.Append(Instruction.Create(OpCodes.Brfalse,next));il.Append(Instruction.Create(OpCodes.Ldstr,pair.Value.GetString()!));il.Append(Instruction.Create(OpCodes.Ret));il.Append(next);
 }
 il.Append(Instruction.Create(OpCodes.Ldarg_0));il.Append(Instruction.Create(OpCodes.Ret));
 var boxed=new MethodDefinition("ObjectLabel",MethodAttributes.Public|MethodAttributes.Static,assembly.MainModule.TypeSystem.String);boxed.Parameters.Add(new ParameterDefinition(assembly.MainModule.TypeSystem.Object));helper.Methods.Add(boxed);
 var toString=new MethodReference("ToString",assembly.MainModule.TypeSystem.String,assembly.MainModule.TypeSystem.Object){HasThis=true};var bi=boxed.Body.GetILProcessor();bi.Append(Instruction.Create(OpCodes.Ldarg_0));bi.Append(Instruction.Create(OpCodes.Callvirt,toString));bi.Append(Instruction.Create(OpCodes.Call,label));bi.Append(Instruction.Create(OpCodes.Ret));
 var calls=new List<object>();
 foreach(var m in methods.Values.Where(m=>m.HasBody))foreach(var instruction in m.Body.Instructions.ToArray()){
  MethodDefinition? converter=null;string owner=m.DeclaringType.Name;
  if(instruction.OpCode==OpCodes.Ldfld&&instruction.Operand.ToString()=="System.String AbilityData::Name"&&new[]{"UIAbilitiesWindowElement","UIAbilityDescription"}.Contains(owner))converter=label;
  if(instruction.OpCode==OpCodes.Callvirt&&instruction.Operand.ToString()=="System.String System.Object::ToString()"&&((owner=="DialogManager"&&m.Name=="RenderCurrentDialogCharacter")||(owner=="StatusesSystem"&&m.Name=="AddStatus")))converter=label;
  if(instruction.OpCode==OpCodes.Box&&((owner=="InventoryItem"&&m.Name=="CompareMainStat"&&instruction.Operand.ToString()=="ItemMainStat")||(owner=="StageRewardsManager"&&m.Name=="AddReward"&&instruction.Operand.ToString()!.Contains("UnlockableType"))))converter=boxed;
  if(converter!=null){m.Body.GetILProcessor().InsertAfter(instruction,Instruction.Create(OpCodes.Call,converter));calls.Add(new{method=m.FullName,offset=instruction.Offset,converter=converter.Name});}
 }
 if(calls.Count!=7)throw new Exception($"표시 변환 위치 수 불일치: {calls.Count}");
 File.WriteAllText(args[2]+".labels.json",JsonSerializer.Serialize(calls,new JsonSerializerOptions{WriteIndented=true}));
 assembly.Write(args[2]);Console.WriteLine("문자열 변경 완료");
}else if(args[0]=="verify"||args[0]=="literal_verify"){
 using var other=AssemblyDefinition.ReadAssembly(args[2]);var candidate=Walk(other.MainModule.Types).SelectMany(t=>t.Methods).ToDictionary(m=>m.FullName);
 using var doc=JsonDocument.Parse(File.ReadAllText(args[3]));var expected=doc.RootElement.EnumerateArray().ToDictionary(r=>(r.GetProperty("method").GetString()!,r.GetProperty("offset").GetInt32()),r=>r.GetProperty("target").GetString());int count=0;
 bool literalsOnly=args[0]=="literal_verify";
 if(methods.Count+(literalsOnly?0:2)!=candidate.Count)throw new Exception("메서드 개수 불일치");
 int added=0;
 foreach(var c in candidate.Values.Where(m=>m.HasBody&&m.DeclaringType.Name!="KoreanPatchText"))foreach(var i in c.Body.Instructions.ToArray())if(i.OpCode==OpCodes.Call&&i.Operand is MethodReference mr&&mr.DeclaringType.Name=="KoreanPatchText"){
  bool ok=(new[]{"UIAbilitiesWindowElement","UIAbilityDescription"}.Contains(c.DeclaringType.Name)&&i.Previous.Operand?.ToString()=="System.String AbilityData::Name")||(c.DeclaringType.Name=="DialogManager"&&c.Name=="RenderCurrentDialogCharacter")||(c.DeclaringType.Name=="StatusesSystem"&&c.Name=="AddStatus")||(c.DeclaringType.Name=="InventoryItem"&&c.Name=="CompareMainStat")||(c.DeclaringType.Name=="StageRewardsManager"&&c.Name=="AddReward");
  if(!ok)throw new Exception("허용되지 않은 표시 변환");c.Body.Instructions.Remove(i);added++;
 }
 if(added!=(literalsOnly?0:7))throw new Exception("표시 변환 개수 불일치");
 var originalTypes=Walk(assembly.MainModule.Types).ToArray();var otherTypes=Walk(other.MainModule.Types).Where(t=>t.Name!="KoreanPatchText").ToArray();
 if(originalTypes.Length!=otherTypes.Length)throw new Exception("타입 수 불일치");
 for(int ti=0;ti<originalTypes.Length;ti++){
  var a=originalTypes[ti];var b=otherTypes[ti];
  if(a.FullName!=b.FullName||a.Attributes!=b.Attributes||a.BaseType?.FullName!=b.BaseType?.FullName||a.Fields.Count!=b.Fields.Count)throw new Exception("타입 경계 불일치");
  for(int fi=0;fi<a.Fields.Count;fi++){var x=a.Fields[fi];var y=b.Fields[fi];if(x.FullName!=y.FullName||x.Attributes!=y.Attributes||!Equals(x.Constant,y.Constant)||!x.InitialValue.SequenceEqual(y.InitialValue))throw new Exception("필드 경계 불일치");}
 }
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

