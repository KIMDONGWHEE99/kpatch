// 실행 중인 검수 게임 창만 읽어 캡처합니다. 포커스·위치·입력은 변경하지 않습니다.
const captureConfig = /*@@CAPTURE@@*/ null;
if (!captureConfig) throw new Error('캡처 대상이 지정되지 않았습니다.');
const u = Process.getModuleByName('user32.dll');
const g = Process.getModuleByName('gdi32.dll');
const k = Process.getModuleByName('kernel32.dll');
const native = (module, name, result, args) => new NativeFunction(module.getExportByName(name), result, args, 'stdcall');
const getClient = native(u, 'GetClientRect', 'int', ['pointer','pointer']);
const printWindow = native(u, 'PrintWindow', 'int', ['pointer','pointer','uint']);
const createDC = native(g, 'CreateCompatibleDC', 'pointer', ['pointer']);
const createDIB = native(g, 'CreateDIBSection', 'pointer', ['pointer','pointer','uint','pointer','pointer','uint']);
const selectObject = native(g, 'SelectObject', 'pointer', ['pointer','pointer']);
const deleteObject = native(g, 'DeleteObject', 'int', ['pointer']);
const deleteDC = native(g, 'DeleteDC', 'int', ['pointer']);
const hwnd = ptr(captureConfig.hwnd);
const owner = Memory.alloc(4);
native(u, 'GetWindowThreadProcessId', 'uint', ['pointer','pointer'])(hwnd, owner);
if (owner.readU32() !== Process.id) throw new Error('현재 검수 프로세스의 창만 캡처할 수 있습니다.');
const rect = Memory.alloc(16);
const getRect = captureConfig.includeFrame ? native(u, 'GetWindowRect', 'int', ['pointer','pointer']) : getClient;
if (!getRect(hwnd, rect)) throw new Error('창 크기 조회 실패');
const width = rect.add(8).readS32() - rect.readS32();
const height = rect.add(12).readS32() - rect.add(4).readS32();
if (width !== (captureConfig.expectedWidth || 1920) || height !== (captureConfig.expectedHeight || 1080) || width < 16 || height < 16 || width > 4096 || height > 4096) throw new Error('예상한 검수 해상도와 다릅니다.');
const info = Memory.alloc(40);
info.writeByteArray(new Uint8Array(40));
info.writeU32(40); info.add(4).writeS32(width); info.add(8).writeS32(-height);
info.add(12).writeU16(1); info.add(14).writeU16(32); info.add(20).writeU32(width * height * 4);
const pointer = Memory.alloc(Process.pointerSize);
const dc = createDC(ptr(0));
const bitmap = createDIB(dc, info, 0, pointer, ptr(0), 0);
if (dc.isNull() || bitmap.isNull()) throw new Error('캡처용 메모리 생성 실패');
const old = selectObject(dc, bitmap);
try {
  const success = printWindow(hwnd, dc, captureConfig.includeFrame ? 2 : 3);
  if (!success) throw new Error('PrintWindow 실패');
  const header = new ArrayBuffer(54);
  const bytes = new Uint8Array(header); const view = new DataView(header);
  bytes[0] = 66; bytes[1] = 77;
  view.setUint32(2, 54 + width * height * 4, true); view.setUint32(10, 54, true);
  bytes.set(new Uint8Array(info.readByteArray(40)), 14);
  // Frida File의 Windows 경로 인코딩 제한을 피하고 유니코드 파일 API를 사용합니다.
  const createFile = native(k, 'CreateFileW', 'pointer', ['pointer','uint','uint','pointer','uint','uint','pointer']);
  const writeFile = native(k, 'WriteFile', 'int', ['pointer','pointer','uint','pointer','pointer']);
  const closeFile = native(k, 'CloseHandle', 'int', ['pointer']);
  const file = createFile(Memory.allocUtf16String(captureConfig.output), 0x40000000, 1, ptr(0), 1, 0x80, ptr(0));
  if (file.equals(ptr(-1))) throw new Error('캡처 파일 열기 실패');
  const headerMemory = Memory.alloc(54); headerMemory.writeByteArray(header);
  const written = Memory.alloc(4);
  try {
    if (!writeFile(file, headerMemory, 54, written, ptr(0)) || written.readU32() !== 54) throw new Error('BMP 헤더 쓰기 실패');
    if (!writeFile(file, pointer.readPointer(), width * height * 4, written, ptr(0)) || written.readU32() !== width * height * 4) throw new Error('BMP 픽셀 쓰기 실패');
  } finally { closeFile(file); }
  send({kind:'qa_printwindow_capture',pid:Process.id,hwnd:hwnd.toString(),width,height,output:captureConfig.output,api_success:success,
        limitation:'API 성공은 화면 판독 PASS가 아닙니다. 실제 내용·가림 여부를 별도 확인해야 합니다.'});
} finally {
  selectObject(dc, old); deleteObject(bitmap); deleteDC(dc);
}
