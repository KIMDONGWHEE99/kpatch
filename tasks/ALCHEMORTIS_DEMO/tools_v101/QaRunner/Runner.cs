using Godot;
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Threading.Tasks;
using Game.Data;
using Game.Data.Card;
using Game.UI.CardInspector;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Reflection;

namespace KoreanQa;

// 배포 후보에는 들어가지 않는 실제 그래픽 검수용 도구입니다.
public static class Runner {
    static SceneTree tree = null!;
    static string output = "";
    static readonly JsonSerializerOptions json = new() { WriteIndented = true };
    static int last = -1;
    public static async void Start() {
        try {
            tree = (SceneTree)Engine.GetMainLoop();
            output = ProjectSettings.GetSetting("korean_qa/output").AsString();
            await Delay(2);
            Write("runner_ready.json", new { engine=Engine.GetVersionInfo().ToString(), display=DisplayServer.GetName(), candidate=ProjectSettings.GetSetting("korean_qa/candidate").AsString() });
            while (true) {
                await Delay(.15);
                string path = Path.Combine(output,"command.json");
                if (!System.IO.File.Exists(path)) continue;
                using var document = JsonDocument.Parse(System.IO.File.ReadAllText(path));
                var command = document.RootElement;
                int serial=command.GetProperty("serial").GetInt32();
                if (serial==last) continue;
                last=serial;
                try {
                    string operation=command.GetProperty("operation").GetString()!;
                    if (operation=="inventory") Inventory();
                    else if (operation=="catalog") Catalog();
                    else if (operation=="update_samples") {
                        // 새 게임 문구의 실제 서식 처리와 원래 카드 설명창을 확인합니다.
                        var stored=new Game.Data.Ability.Composed.AlchemyStoredCardModel();
                        var zero=new Game.Data.Ability.Composed.AlchemyZeroCost();
                        BaseCard reference=CardFactory.CreateCardFromId("skeleton_warrior",true);
                        stored.SetStoredCardModel(reference.ToSaveModel());
                        BaseCard card=CardFactory.CreateCardFromId("bagged",true);
                        card.AddComposedAbilities(new Game.Data.Ability.Composed.BaseComposedAbility[]{stored,zero});
                        string prefix=Game.Util.DescriptionUtils.FormatDescription(TranslationServer.Translate("ABILITY_COPY_PREFIX"),reference.DisplayName);
                        zero.SetDescriptionPrefixFunc(()=>"("+prefix+")");
                        Write("update_samples.json",new { stored=stored.GetDescription(),zero=zero.GetDescription(),prefix });
                        var inspector=GD.Load<PackedScene>("res://scenes/ui/card_inspector/CardInspector.tscn").Instantiate<CardInspector>();
                        tree.Root.AddChild(inspector);inspector.SetBaseCard(card);
                        await Delay(.7);await Capture("update_ability_inspector");
                        inspector.PlayOut();await Delay(.4);card.Destroy();reference.Destroy();
                    }
                    else if (operation=="locale") TranslationServer.SetLocale(command.GetProperty("locale").GetString()!);
                    else if (operation=="quit") {Write("done_"+serial+".json",new{status="PASS"});tree.Quit();return;}
                    else if (operation=="capture") await Capture(command.GetProperty("label").GetString()!);
                    else if (operation=="scene") {
                        var error=tree.ChangeSceneToFile(command.GetProperty("path").GetString()!);
                        if (error!=Error.Ok) throw new Exception(error.ToString());
                        await Delay(3);
                        await Capture(command.GetProperty("label").GetString()!);
                    } else if (operation=="cards") {
                        foreach (var id in command.GetProperty("ids").EnumerateArray()) {
                            BaseCard card=CardFactory.CreateCardFromId(id.GetString()!,true);
                            card.SetTierCapped(command.TryGetProperty("tier",out var tier) ? tier.GetInt32() : 5);
                            var inspector=GD.Load<PackedScene>("res://scenes/ui/card_inspector/CardInspector.tscn").Instantiate<CardInspector>();
                            tree.Root.AddChild(inspector);
                            inspector.SetBaseCard(card);
                            await Delay(.6);
                            string name="card_"+id.GetString();
                            await Capture(name);
                            foreach(var scroll in Walk(inspector).OfType<ScrollContainer>()) scroll.ScrollVertical=100000;
                            await Delay(.2);
                            await Capture(name+"_bottom");
                            inspector.PlayOut();
                            await Delay(.4);
                            card.Destroy();
                        }
                    } else if (operation=="font") {
                        Game.Autoload.VisualUtilities.SetHighResolutionEnabled(command.GetProperty("highres").GetBoolean());
                        Game.Autoload.VisualUtilities.SetHighResolutionFontEnabled(command.GetProperty("readable").GetBoolean());
                    } else if (operation=="call") {
                        Node target=tree.Root.GetNode(command.GetProperty("path").GetString()!);
                        string method=command.GetProperty("method").GetString()!;
                        target.Call(method);
                        await Delay(1);
                        await Capture(command.GetProperty("label").GetString()!);
                    } else throw new Exception("지원하지 않는 검수 명령");
                    Write("done_"+serial+".json",new { serial,operation,status="PASS" });
                } catch(Exception exception) { Write("done_"+serial+".json",new {serial,status="FAIL",error=exception.ToString()}); }
            }
        } catch(Exception exception) { if(output.Length>0) Write("runner_error.json",new { error=exception.ToString() }); }
    }
    static async Task Delay(double seconds) => await tree.ToSignal(tree.CreateTimer(seconds),Godot.Timer.SignalName.Timeout);
    static void Write(string name,object data) => System.IO.File.WriteAllText(Path.Combine(output,name),JsonSerializer.Serialize(data,json));
    static IEnumerable<Node> Walk(Node node) { yield return node; foreach(Node child in node.GetChildren()) foreach(Node descendant in Walk(child)) yield return descendant; }
    static async Task Capture(string label) {
        if (!Regex.IsMatch(label,"^[a-zA-Z0-9_-]+$")) throw new Exception("잘못된 캡처 이름");
        var rows=new List<object>();
        foreach(var node in Walk(tree.Root)) {
            if(node is not Control control || !control.IsVisibleInTree()) continue;
            string? text=node switch {Label l=>l.Text,RichTextLabel r=>r.Text,Button b=>b.Text,_=>null};
            if(text==null) continue;
            string rendered=node is RichTextLabel rich ? rich.GetParsedText() : node.Tr(text);
            var font=control.GetThemeFont(node is RichTextLabel ? "normal_font" : "font");
            var missing=rendered.EnumerateRunes().Where(c=>!char.IsWhiteSpace((char)c.Value)&&!font.HasChar(c.Value)).Select(c=>c.ToString()).Distinct().ToArray();
            var rect=control.GetGlobalRect();
            rows.Add(new { path=node.GetPath().ToString(),text,rendered,rect=new[]{rect.Position.X,rect.Position.Y,rect.Size.X,rect.Size.Y},font=font.ResourcePath,font_size=control.GetThemeFontSize(node is RichTextLabel?"normal_font_size":"font_size"),missing,content_height=node is RichTextLabel rt?rt.GetContentHeight():-1 });
        }
        Write(label+".json",rows);
        await tree.ToSignal(RenderingServer.Singleton,RenderingServer.SignalName.FramePostDraw);
        var error=tree.Root.GetTexture().GetImage().SavePng(Path.Combine(output,label+".png"));
        if(error!=Error.Ok)throw new Exception(error.ToString());
    }
    static void Inventory() {
        var cards=new List<object>(); var errors=new List<object>();
        foreach(string id in CardRegistry.AllIds) {
            BaseCard? card=null;
            try {
                card=CardFactory.CreateCardFromId(id,true);
                var tiers=new List<object>();
                foreach(int tier in new[]{1,2,3,4,5}) {
                    card.SetTierCapped(tier);
                    tiers.Add(new {tier,descriptions=card.GetAllComposedAbilities().Select(a=>new {a.Key,a.DescriptionTranslationKey,source=a.GetDescriptionForTranslationComment(),translated=a.GetDescription(),a.IsHidden}).ToArray()});
                }
                cards.Add(new {id,name=card.DisplayName,flavor=card.CardDefinitionResource.LocalizedFlavorText,tags=card.GetTags().ToString(),tiers});
            } catch(Exception e) {errors.Add(new{id,error=e.ToString()});}
            finally {card?.Destroy();}
        }
        Write("runtime_card_inventory.json",new {cards,errors,locale=TranslationServer.GetLocale(),Game.Util.GameDebug.IsCheatsBuild,Game.Util.GameDebug.IsDebugBuild,Game.Util.GameDebug.IsDemoBuild});
    }
    static void Catalog() {
        var rows=new List<object>();var errors=new List<object>();
        void Add(string category,string id,Func<object> get) {try {rows.Add(new {category,id,value=get()});} catch(Exception e){errors.Add(new {category,id,error=e.ToString()});}}
        foreach(var id in Game.Data.Artifact.ArtifactRegistry.AllIds) Add("artifact",id,()=> {
            var artifact=Game.Data.Artifact.ArtifactFactory.CreateArtifactFromId(id);
            try{return new {name=artifact.ArtifactResource.LocalizedName,description=artifact.GetDescription()};} finally{artifact.Dispose();}
        });
        foreach(var id in Game.Data.Enchant.EnchantFactory.AllIds) Add("enchant",id,()=>Game.Data.Enchant.EnchantFactory.FromId(id).GetDescription());
        foreach(var effect in Game.Data.MapNodeEffect.MapNodeEffectFactory.AllMapNodeEffects) Add("map_effect",effect.EffectId,()=>effect is Game.Data.MapNodeEffect.AutomaticCardRewardMapNodeEffect ? new Game.Data.MapNodeEffect.AutomaticCardRewardMapNodeEffect("skeleton_warrior").GetDescription() : effect.GetDescription());
        foreach(var id in Game.Data.BoardEffect.BoardEffectFactory.AllIds) Add("board_effect",id,()=> {
            var effect=Game.Data.BoardEffect.BoardEffectFactory.FromId(id);
            try{return new {directions=new[]{Vector2I.Up,Vector2I.Down,Vector2I.Left,Vector2I.Right}.Select(direction=>effect.GetGrowBoardTooltipBBCode(direction)).ToArray()};}finally{effect.Dispose();}
        });
        foreach(var tier in Game.Data.DifficultyTiers.Tiers)Add("difficulty",tier.Id,()=>new{name=TranslationServer.Translate(tier.NameTranslationKey).ToString(),description=tier.GetDescription()});
        foreach(var keyword in Game.Util.Keyword.AllRegistered.SelectMany(x=>new[]{x}.Concat(x.Variants)))Add("keyword",keyword.Id,()=>keyword.WordLocalized);
        foreach(var id in Game.Data.Character.CharacterRegistry.AllIds)Add("character",id,()=>ReadLocalized(Game.Data.Character.CharacterRegistry.FromId(id)));
        foreach(var resource in Game.Data.EventConfiguration.LoreRegistry.AllLore)Add("lore",resource.ResourcePath,()=>ReadLocalized(resource));
        foreach(var resource in Game.Data.Unlock.UnlockRegistry.AllUnlockResources)Add("unlock",resource.ResourcePath,()=>ReadLocalized(resource));
        Write("runtime_catalog.json",new {rows,errors,locale=TranslationServer.GetLocale()});
    }
    static object ReadLocalized(object resource) {
        var values=new Dictionary<string,string>();
        foreach(var property in resource.GetType().GetProperties(BindingFlags.Public|BindingFlags.Instance)) {
            if(property.PropertyType!=typeof(string)||property.GetIndexParameters().Length!=0)continue;
            if(property.Name.Contains("Localized"))values[property.Name]=(string?)property.GetValue(resource)??"";
            if(property.Name.EndsWith("TranslationKey")) {string key=(string?)property.GetValue(resource)??"";values[property.Name]=TranslationServer.Translate(key).ToString();}
        }
        return values;
    }
}
