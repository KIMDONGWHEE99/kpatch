using Mono.Cecil;
using System.Text.Json;

// 게임 코드를 실행하지 않고 분석용 DLL에서 위치와 필드 구조만 읽습니다.
var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(args[0]);
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> types) {
    foreach (var t in types) { yield return t; foreach (var c in Walk(t.NestedTypes)) yield return c; }
}
object[] Attr(ICustomAttributeProvider value) => value.CustomAttributes.Select(a => (object)new {
    type = a.AttributeType.FullName,
    fields = a.Fields.ToDictionary(f => f.Name, f => f.Argument.Value),
    arguments = a.ConstructorArguments.Select(x => x.Value?.ToString())
}).ToArray();
var rows = new List<object>();
foreach (var file in Directory.GetFiles(args[0], "*.dll")) {
    using var assembly = AssemblyDefinition.ReadAssembly(file, new ReaderParameters { AssemblyResolver = resolver });
    foreach (var type in Walk(assembly.MainModule.Types)) rows.Add(new {
        assembly = Path.GetFileName(file), type = type.FullName, baseType = type.BaseType?.FullName,
        isEnum = type.IsEnum, attributes = Attr(type),
        fields = type.Fields.Select(f => new {name=f.Name,type=f.FieldType.FullName,isStatic=f.IsStatic,isPublic=f.IsPublic,isNotSerialized=f.IsNotSerialized,constant=f.HasConstant?f.Constant:null,attributes=Attr(f)}),
        methods = type.Methods.Select(m => new {name=m.Name,fullName=m.FullName,attributes=Attr(m)})
    });
}
File.WriteAllText(args[1], JsonSerializer.Serialize(rows,new JsonSerializerOptions {WriteIndented=true}));
Console.WriteLine($"분석한 클래스: {rows.Count}");
