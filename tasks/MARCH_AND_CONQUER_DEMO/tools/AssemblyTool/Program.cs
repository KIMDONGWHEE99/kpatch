using Mono.Cecil;
using Mono.Cecil.Cil;
using System.Text.Json;
// 게임 코드를 실행하지 않고 문자열의 정확한 메서드·명령 위치를 조사합니다.
var resolver=new DefaultAssemblyResolver();resolver.AddSearchDirectory(Path.GetDirectoryName(args[1]));
using var assembly=AssemblyDefinition.ReadAssembly(args[1],new ReaderParameters{AssemblyResolver=resolver});
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> types){foreach(var t in types){yield return t;foreach(var n in Walk(t.NestedTypes))yield return n;}}
var types=Walk(assembly.MainModule.Types).ToArray();
var methods=types.SelectMany(t=>t.Methods).ToArray();
if(args[0]=="dump"){
 var rows=methods.Where(m=>m.HasBody).SelectMany(m=>m.Body.Instructions.Where(i=>i.OpCode==OpCodes.Ldstr).Select(i=>new{method=m.FullName,offset=i.Offset,source=(string)i.Operand,context=m.Body.Instructions.Skip(Math.Max(0,m.Body.Instructions.IndexOf(i)-2)).Take(7).Select(x=>x.ToString()).ToArray()})).ToArray();
 File.WriteAllText(args[2],JsonSerializer.Serialize(rows,new JsonSerializerOptions{WriteIndented=true}));
 File.WriteAllText(args[2]+".types.json",JsonSerializer.Serialize(types.Select(t=>new{name=t.FullName,isEnum=t.IsEnum,fields=t.Fields.Select(f=>new{name=f.Name,type=f.FieldType.FullName,constant=f.HasConstant?f.Constant:null})}),new JsonSerializerOptions{WriteIndented=true}));
 Console.WriteLine($"문자열 {rows.Length}곳, 형식 {types.Length}개");
}else if(args[0]=="qa"){
 using var support=AssemblyDefinition.ReadAssembly(args[3]);
 var entry=support.MainModule.Types.Single(t=>t.FullName=="KoreanQA.Bootstrap").Methods.Single(m=>m.Name=="Start");
 var awake=methods.Single(m=>m.DeclaringType.FullName=="Battles1000.GameTextManager"&&m.Name=="Awake");
 var first=awake.Body.Instructions[0];awake.Body.GetILProcessor().InsertBefore(first,Instruction.Create(OpCodes.Call,assembly.MainModule.ImportReference(entry)));
 assembly.Write(args[2]);
}else if(args[0]=="verify-qa"){
 using var qa=AssemblyDefinition.ReadAssembly(args[2],new ReaderParameters{AssemblyResolver=resolver});
 var qm=Walk(qa.MainModule.Types).SelectMany(t=>t.Methods).ToDictionary(m=>m.FullName);
 if(qm.Count!=methods.Length)throw new Exception("검수 메서드 개수 불일치");
 foreach(var m in methods){
  var other=qm[m.FullName];if(m.Attributes!=other.Attributes||m.HasBody!=other.HasBody)throw new Exception("검수 메서드 구조 불일치");
  if(!m.HasBody)continue;
  int skip=m.DeclaringType.FullName=="Battles1000.GameTextManager"&&m.Name=="Awake"?1:0;
  if(skip==1&&(other.Body.Instructions[0].OpCode!=OpCodes.Call||other.Body.Instructions[0].Operand.ToString()!="System.Void KoreanQA.Bootstrap::Start()"))throw new Exception("검수 진입점 불일치");
  if(m.Body.Instructions.Count+skip!=other.Body.Instructions.Count||m.Body.Variables.Count!=other.Body.Variables.Count)throw new Exception("검수 명령 개수 불일치");
  string Operand(Instruction i,MethodDefinition method,int shift)=>i.Operand switch{Instruction target=>"branch:"+(method.Body.Instructions.IndexOf(target)-shift),Instruction[] targets=>"switch:"+string.Join(",",targets.Select(t=>method.Body.Instructions.IndexOf(t)-shift)),_=>i.Operand?.ToString()??""};
  for(int j=0;j<m.Body.Instructions.Count;j++){var a=m.Body.Instructions[j];var b=other.Body.Instructions[j+skip];if(a.OpCode!=b.OpCode||Operand(a,m,0)!=Operand(b,other,skip))throw new Exception("검수 외 코드 변경");}
 }
 Console.WriteLine($"검수 사본: 메서드 {methods.Length}개 일치, Awake 진입 호출 1개만 추가");
}else if(args[0]=="verify"){
 using var candidate=AssemblyDefinition.ReadAssembly(args[2],new ReaderParameters{AssemblyResolver=resolver});
 var cm=Walk(candidate.MainModule.Types).SelectMany(t=>t.Methods).ToDictionary(m=>m.FullName);
 using var doc=JsonDocument.Parse(File.ReadAllText(args[3]));
 var expected=doc.RootElement.EnumerateArray().ToDictionary(r=>(r.GetProperty("method").GetString()!,r.GetProperty("offset").GetInt32()),r=>r.GetProperty("target").GetString());
 int count=0;
 foreach(var m in methods){
  if(!cm.TryGetValue(m.FullName,out var other)||m.Attributes!=other.Attributes||m.HasBody!=other.HasBody)throw new Exception("메서드 구조 불일치");
  if(!m.HasBody)continue;
  if(m.Body.Instructions.Count!=other.Body.Instructions.Count||m.Body.Variables.Count!=other.Body.Variables.Count)throw new Exception("명령/변수 개수 불일치");
  for(int j=0;j<m.Body.Instructions.Count;j++){
   var a=m.Body.Instructions[j];var b=other.Body.Instructions[j];
   if(expected.TryGetValue((m.FullName,a.Offset),out var text)){if(b.OpCode!=OpCodes.Ldstr||(string)b.Operand!=text)throw new Exception("번역 위치 불일치");count++;continue;}
   if(m.DeclaringType.Name=="GameplayHUD"&&m.Name=="Refresh"&&a.OpCode==OpCodes.Box&&a.Operand.ToString()=="Battles1000.BattleFlowState"){
    if(b.OpCode!=OpCodes.Call||b.Operand.ToString()!="System.String KoreanPatchText::FlowState(System.Int32)")throw new Exception("상태 변환 불일치");continue;
   }
   if(m.DeclaringType.Name=="SkillNodeView"&&m.Name=="Refresh"){
    if(a.OpCode==OpCodes.Constrained&&a.Operand.ToString()=="Battles1000.ProducerBlockReason"){if(b.OpCode!=OpCodes.Nop)throw new Exception("enum 접두 불일치");continue;}
    if(a.OpCode==OpCodes.Ldflda&&a.Next.OpCode==OpCodes.Constrained&&a.Next.Operand.ToString()=="Battles1000.ProducerBlockReason"){if(b.OpCode!=OpCodes.Ldfld||b.Operand.ToString()!=a.Operand.ToString())throw new Exception("enum 필드 불일치");continue;}
    if(a.OpCode==OpCodes.Callvirt&&a.Previous.OpCode==OpCodes.Constrained&&a.Previous.Operand.ToString()=="Battles1000.ProducerBlockReason"){if(b.OpCode!=OpCodes.Call||b.Operand.ToString()!="System.String KoreanPatchText::BlockReason(System.Int32)")throw new Exception("생산 상태 변환 불일치");continue;}
   }
   string Operand(Instruction i,MethodDefinition method)=>i.Operand switch{Instruction target=>"branch:"+method.Body.Instructions.IndexOf(target),Instruction[] targets=>"switch:"+string.Join(",",targets.Select(t=>method.Body.Instructions.IndexOf(t))),_=>i.Operand?.ToString()??""};
   if(a.OpCode!=b.OpCode||Operand(a,m)!=Operand(b,other))throw new Exception($"예상 밖 명령 변경: {m.FullName} {j}");
  }
 }
 if(count!=expected.Count)throw new Exception("번역 개수 불일치");
 Console.WriteLine($"원본 메서드 {methods.Length}개, 번역 {count}곳, enum 표시 2곳 경계 일치");
}else if(args[0]=="patch"){
 using var doc=JsonDocument.Parse(File.ReadAllText(args[3]));
 foreach(var r in doc.RootElement.EnumerateArray()){
  var m=methods.Single(m=>m.FullName==r.GetProperty("method").GetString());
  var i=m.Body.Instructions.Single(i=>i.Offset==r.GetProperty("offset").GetInt32());
  if(i.OpCode!=OpCodes.Ldstr||(string)i.Operand!=r.GetProperty("source").GetString())throw new Exception("원본 위치 불일치");
  i.Operand=r.GetProperty("target").GetString();
 }
 // 저장에 쓰는 enum 식별자를 유지하고, 두 화면 출력 지점에서만 한국어로 변환합니다.
 var labels=new TypeDefinition("","KoreanPatchText",TypeAttributes.Public|TypeAttributes.Abstract|TypeAttributes.Sealed,assembly.MainModule.TypeSystem.Object);
 assembly.MainModule.Types.Add(labels);
 MethodDefinition MakeLabels(string name,string[] values){
  var m=new MethodDefinition(name,MethodAttributes.Public|MethodAttributes.Static,assembly.MainModule.TypeSystem.String);
  m.Parameters.Add(new ParameterDefinition("value",ParameterAttributes.None,assembly.MainModule.TypeSystem.Int32));labels.Methods.Add(m);
  var il=m.Body.GetILProcessor();var branches=values.Select(v=>Instruction.Create(OpCodes.Ldstr,v)).ToArray();
  il.Append(Instruction.Create(OpCodes.Ldarg_0));il.Append(Instruction.Create(OpCodes.Switch,branches));il.Append(Instruction.Create(OpCodes.Ldstr,"알 수 없음"));il.Append(Instruction.Create(OpCodes.Ret));
  foreach(var b in branches){il.Append(b);il.Append(Instruction.Create(OpCodes.Ret));}return m;
 }
 var flow=MakeLabels("FlowState",["대기","준비","출전 대기","전투 중","승리","패배","전환 중"]);
 var blocked=MakeLabels("BlockReason",["없음","금화 부족","마나 부족","배치 공간 부족","미해금","전투 대기"]);
 var hud=methods.Single(m=>m.DeclaringType.FullName=="Battles1000.GameplayHUD"&&m.Name=="Refresh");
 var box=hud.Body.Instructions.Single(i=>i.OpCode==OpCodes.Box&&((TypeReference)i.Operand).FullName=="Battles1000.BattleFlowState");box.OpCode=OpCodes.Call;box.Operand=flow;
 var view=methods.Single(m=>m.DeclaringType.FullName=="Battles1000.SkillNodeView"&&m.Name=="Refresh");
 var constrained=view.Body.Instructions.Single(i=>i.OpCode==OpCodes.Constrained&&((TypeReference)i.Operand).FullName=="Battles1000.ProducerBlockReason");
 if(constrained.Previous.OpCode!=OpCodes.Ldflda||constrained.Next.OpCode!=OpCodes.Callvirt)throw new Exception("예상하지 않은 enum 출력 구조");
 constrained.Previous.OpCode=OpCodes.Ldfld;constrained.Next.OpCode=OpCodes.Call;constrained.Next.Operand=blocked;constrained.OpCode=OpCodes.Nop;constrained.Operand=null;
 assembly.Write(args[2]);
}
