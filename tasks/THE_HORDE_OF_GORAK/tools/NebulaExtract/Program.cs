using Nebula;
using Nebula.Core.FileReaders;
using Nebula.Core.Memory;
using Nebula.Core.Utilities;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using System.Reflection;
using System.Security.Cryptography;
using System.Drawing.Imaging;

// 게임을 실행하지 않고 Nebula의 읽기 도구로 구조와 미디어를 추출합니다.
if (args.Length < 2 || args.Length > 3) throw new ArgumentException("입력 DAT와 새 출력 폴더, 선택적으로 metadata-only를 지정하세요.");
var metadataOnly = args.Length == 3 && args[2] == "metadata-only";
var input = Path.GetFullPath(args[0]);
var output = Path.GetFullPath(args[1]);
if (Directory.Exists(output)) throw new IOException("기존 출력은 덮어쓰지 않습니다.");
Directory.CreateDirectory(output);
Directory.SetCurrentDirectory(output);
var errors = new List<object>();
string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
var settings = new JsonSerializerSettings {
    Formatting = Formatting.Indented, ReferenceLoopHandling = ReferenceLoopHandling.Ignore,
    ContractResolver = new EvidenceResolver(), Converters = { new BytesEvidenceConverter() }
};
void Save(string path, object? value) => File.WriteAllText(path, JsonConvert.SerializeObject(value, settings));
Save("input.json", new { input, sha256 = Hash(File.ReadAllBytes(input)), tool = "NebulaFD", commit = "a24d4d1da78c35412413faac750e07ff7d603a8a", started = DateTimeOffset.Now });
var fileReader = new CCNFileReader();
NebulaCore.CurrentReader = fileReader;
NebulaCore.FilePath = input;
Parameters.Inst.ignore_sounds = false;
Parameters.Inst.dump_all_chunks = false;
Parameters.Inst.dump_unk_chunks = false;
try {
    using var reader = new ByteReader(input, FileMode.Open);
    fileReader.CheckUnpacked(reader);
    fileReader.LoadGame(reader, input);
} catch (Exception ex) {
    errors.Add(new { stage = "parse", error = ex.ToString(), status = "UNKNOWN" });
    Save("errors.json", errors);
    Logger.Save();
    throw;
}
var package = NebulaCore.PackageData;
Save("package.json", package);
Directory.CreateDirectory("frames");
var frames = new List<object>();
for (int fi=0; fi<package.Frames.Count; fi++) {
    var frame = package.Frames[fi];
    var entries = new List<object>();
    for (int ei=0; ei<frame.FrameEvents.Events.Count; ei++) {
        var ev = frame.FrameEvents.Events[ei];
        foreach (var kind in new[] { "Conditions", "Actions" }) {
            var values = kind == "Conditions" ? ev.Conditions.Cast<Nebula.Core.Data.Chunks.FrameChunks.Events.ACEventBase>().ToArray() : ev.Actions.Cast<Nebula.Core.Data.Chunks.FrameChunks.Events.ACEventBase>().ToArray();
            for (int ai=0; ai<values.Length; ai++) {
                var item=values[ai]; string? display=null;
                try {
                    display=item.ToString();
                    if (display is null || display.Contains("[ERROR]") || display.Contains("Unknown"))
                        errors.Add(new {stage="event_description_unimplemented",fi,ei,kind,ai,error=display,status="UNKNOWN"});
                } catch(Exception ex) { errors.Add(new {stage="event_description",fi,ei,kind,ai,error=ex.Message,status="UNKNOWN"}); }
                entries.Add(new { frame=fi,ev=ei,kind,index=ai,item.ObjectType,item.Num,item.ObjectInfo,display,parameters=item.Parameters });
            }
        }
    }
    Save($"frames/{fi:D2}.json",entries);
    frames.Add(new { index=fi,frame.FrameName,frame.Handle,events=frame.FrameEvents.Events.Count,instances=frame.FrameInstances });
}
Save("frames.json",frames);
Directory.CreateDirectory("images");
var media = new List<object>();
foreach (var entry in package.ImageBank.Images.OrderBy(x=>x.Key)) {
    var im=entry.Value;
    try {
        var path=$"images/{entry.Key:D5}.png";
        if (!metadataOnly) { im.GetBitmap().Save(path,ImageFormat.Png); im.DisposeBmp(); }
        media.Add(new {handle=entry.Key,im.Width,im.Height,im.GraphicMode,source_sha256=Hash(im.ImageData),path=metadataOnly?null:path,sha256=metadataOnly?null:Hash(File.ReadAllBytes(path)),status="UNKNOWN"});
    } catch(Exception ex) { errors.Add(new {stage="image",handle=entry.Key,error=ex.ToString(),status="UNKNOWN"}); }
}
Save("media.json",media);
Directory.CreateDirectory("fonts");
var fonts = new List<object>();
for (int i=0;i<package.TrueTypeFontBank.Fonts.Count;i++) {
    var font=package.TrueTypeFontBank.Fonts[i]; var path=$"fonts/{i:D2}.ttf";
    File.WriteAllBytes(path,font.FontData);
    fonts.Add(new {index=i,font.Name,path,sha256=Hash(font.FontData),size=font.FontData.Length});
}
Save("fonts.json",new {embedded=fonts,logical=package.FontBank});
Directory.CreateDirectory("extension_blobs");
var blobs=new List<object>();
foreach (var entry in package.FrameItems.Items.OrderBy(x=>x.Key)) {
    if (entry.Value.Properties is Nebula.Core.Data.Chunks.ObjectChunks.ObjectCommon.ObjectCommon common) {
        var data=common.ObjectExtension.ExtensionData;
        if (data.Length==0) continue;
        var path=$"extension_blobs/{entry.Key:D4}.bin"; File.WriteAllBytes(path,data);
        blobs.Add(new {handle=entry.Key,entry.Value.Name,path,sha256=Hash(data),size=data.Length,status="UNKNOWN"});
    }
}
Save("extension_blobs.json",blobs);
Save("errors.json",errors);
Save("summary.json",new {frames=frames.Count,objects=package.FrameItems.Items.Count,images=media.Count,fonts=fonts.Count,logical_fonts=package.FontBank.Fonts.Count,sounds=package.SoundBank.Sounds.Count,errors=errors.Count,completed=DateTimeOffset.Now});
Logger.Save();
Console.WriteLine(File.ReadAllText("summary.json"));

sealed class EvidenceResolver : DefaultContractResolver {
    protected override IList<JsonProperty> CreateProperties(Type type,MemberSerialization mode) {
        return base.CreateProperties(type,mode).Where(x => x.PropertyName != "Parent" && x.PropertyName != "BitmapCache" && (x.PropertyName != "FrameEvents" || type.Name == "Frame")).ToList();
    }
}
sealed class BytesEvidenceConverter : JsonConverter {
    public override bool CanConvert(Type t) => t == typeof(byte[]);
    public override void WriteJson(JsonWriter writer,object? value,JsonSerializer serializer) {
        var bytes=(byte[]?)value ?? Array.Empty<byte>();
        serializer.Serialize(writer,new { byte_length=bytes.Length,sha256=Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() });
    }
    public override object? ReadJson(JsonReader reader,Type t,object? v,JsonSerializer serializer) => throw new NotSupportedException();
}
