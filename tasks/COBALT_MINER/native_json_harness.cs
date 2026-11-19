// 실제 게임을 불러오거나 표시 창을 띄우지 않고 32비트 변환 함수의 호출 규약을 시험합니다.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

class NativeJsonHarness {
    [DllImport("kernel32.dll")] static extern IntPtr VirtualAlloc(IntPtr address, UIntPtr size, uint type, uint protection);
    [DllImport("kernel32.dll")] static extern bool VirtualFree(IntPtr address, UIntPtr size, uint type);
    [DllImport("kernel32.dll")] static extern IntPtr GetModuleHandle(string name);
    [DllImport("kernel32.dll")] static extern IntPtr GetProcAddress(IntPtr module, string name);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int MessageCall(IntPtr hwnd, IntPtr body, IntPtr caption, uint flags);
    static string capturedBody, capturedCaption;
    static IntPtr capturedWindow;
    static uint capturedFlags;
    static string stage = "start";
    static int Capture(IntPtr hwnd, IntPtr body, IntPtr caption, uint flags) {
        capturedBody = Marshal.PtrToStringUni(body);
        capturedCaption = Marshal.PtrToStringUni(caption);
        capturedWindow = hwnd; capturedFlags = flags;
        return 1234;
    }
    static byte[] Hex(string text) {
        byte[] bytes = new byte[text.Length / 2];
        for (int index = 0; index < bytes.Length; index++) bytes[index] = Convert.ToByte(text.Substring(index * 2, 2), 16);
        return bytes;
    }
    static IntPtr Utf8(string text) {
        byte[] bytes = Encoding.UTF8.GetBytes(text + "\0");
        IntPtr address = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, address, bytes.Length); return address;
    }
    static string Render(string text) {
        int number = 0;
        return Regex.Replace(text, "%[dc]", delegate(Match match) {
            return match.Value == "%c" ? "Q" : (++number == 1 ? "12" : "34");
        });
    }
    static int Main(string[] args) {
        try { return Run(args); }
        catch (Exception error) {
            File.WriteAllText(args[1], "FAIL stage=" + stage + " type=" + error.GetType().FullName, Encoding.UTF8);
            Console.WriteLine("FAIL stage=" + stage); return 1;
        }
    }
    static int Run(string[] args) {
        if (IntPtr.Size != 4) throw new Exception("32비트 실행이 필요합니다.");
        var serializer = new JavaScriptSerializer();
        stage = "read-audit";
        var audit = serializer.Deserialize<Dictionary<string, object>>(File.ReadAllText(args[0], Encoding.UTF8));
        var wrapper = (Dictionary<string, object>)audit["wrapper"];
        int rva = Convert.ToInt32(wrapper["rva"]);
        byte[] code = Hex((string)wrapper["bytes"]);
        byte[] candidate = File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(args[0]), "Modules", "Steamworks.mfx"));
        var section = (Dictionary<string, object>)audit["new_section"];
        int offset = Convert.ToInt32(section["file_offset"]);
        for (int index = 0; index < code.Length; index++) if (code[index] != candidate[offset + index]) throw new Exception("후보 코드 불일치");
        IntPtr image = VirtualAlloc(IntPtr.Zero, new UIntPtr((uint)(rva + 4096)), 0x3000, 0x40);
        if (image == IntPtr.Zero) throw new Exception("시험 메모리 할당 실패");
        MessageCall capture = Capture;
        var records = new List<object>();
        try {
            stage = "prepare-imports";
            Marshal.Copy(code, 0, IntPtr.Add(image, rva), code.Length);
            Marshal.WriteIntPtr(IntPtr.Add(image, Convert.ToInt32(wrapper["convert_iat_rva"])), GetProcAddress(GetModuleHandle("kernel32.dll"), "MultiByteToWideChar"));
            Marshal.WriteIntPtr(IntPtr.Add(image, Convert.ToInt32(wrapper["message_iat_rva"])), Marshal.GetFunctionPointerForDelegate(capture));
            MessageCall function = (MessageCall)Marshal.GetDelegateForFunctionPointer(IntPtr.Add(image, rva), typeof(MessageCall));
            stage = "read-translations";
            var translations = (System.Collections.ArrayList)audit["translations"];
            var bodies = new List<string>();
            foreach (Dictionary<string, object> row in translations) bodies.Add(Render((string)row["translation"]));
            bodies.Add(""); bodies.Add(new string('X', 127)); bodies.Add("한글 Á 😀");
            string caption = (string)((Dictionary<string, object>)translations[0])["translation"];
            foreach (string text in bodies) {
                stage = "case-" + records.Count;
                IntPtr body = Utf8(text), title = Utf8(caption);
                try {
                    int returned = function(new IntPtr(0x1234), body, title, 0x34);
                    bool passed = returned == 1234 && capturedWindow.ToInt32() == 0x1234 && capturedFlags == 0x34 && capturedBody == text && capturedCaption == caption;
                    records.Add(new { expected = text, actual = capturedBody, caption = capturedCaption, returned = returned, passed = passed });
                    if (!passed) throw new Exception("Unicode 경계 시험 실패");
                } finally { Marshal.FreeHGlobal(body); Marshal.FreeHGlobal(title); }
            }
            GC.KeepAlive(capture); GC.KeepAlive(function);
            File.WriteAllText(args[1], serializer.Serialize(new { status = "PASS", architecture = "x86", tests = records.Count, records = records, game_loaded = false, display_opened = false }), Encoding.UTF8);
            Console.WriteLine("PASS: " + records.Count + " Unicode boundary cases; no game or display window.");
            return 0;
        } finally { VirtualFree(image, UIntPtr.Zero, 0x8000); }
    }
}
