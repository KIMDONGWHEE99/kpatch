using Mono.Cecil;
using System.Text.Json;

// 게임 코드를 실행하지 않고 분석용 DLL의 위치 속성만 읽습니다.
IEnumerable<TypeDefinition> Walk(IEnumerable<TypeDefinition> types) {
    foreach (var type in types) { yield return type; foreach (var child in Walk(type.NestedTypes)) yield return child; }
}
object[] Attributes(ICustomAttributeProvider value) => value.CustomAttributes
    .Where(attribute => attribute.AttributeType.Namespace == "Cpp2ILInjected")
    .Select(attribute => (object)new {
        type = attribute.AttributeType.FullName,
        fields = attribute.Fields.ToDictionary(field => field.Name, field => field.Argument.Value)
    }).ToArray();
var rows = new List<object>();
foreach (var path in Directory.GetFiles(args[0], "*.dll").Order()) {
    using var assembly = AssemblyDefinition.ReadAssembly(path);
    foreach (var type in Walk(assembly.MainModule.Types)) rows.Add(new {
        assembly = Path.GetFileName(path), type = type.FullName, baseType = type.BaseType?.FullName,
        fields = type.Fields.Select(field => new {name = field.Name, type = field.FieldType.FullName, attributes = Attributes(field)}).ToArray(),
        methods = type.Methods.Select(method => new {name = method.Name, fullName = method.FullName, attributes = Attributes(method)}).ToArray()
    });
}
File.WriteAllText(args[1], JsonSerializer.Serialize(rows));
Console.WriteLine($"분석한 클래스: {rows.Count}");
