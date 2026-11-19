// 검수 프로세스에만 적용하는 저장·Steam 격리와 관측 코드. 배포하지 않는다.
// 전체화면·입력 간섭을 막는 검수 전용 코드이며 정식 후보에는 포함하지 않습니다.
const config = /*@@CONFIG@@*/ null;
if (!config) throw new Error('검수 경로가 지정되지 않았습니다.');
const pins = [];
const hooks = new Set();
const seen = new Set();
const events = [];
const gameWindows = new Set();
const clientWidth = config.clientWidth || 1920;
const clientHeight = config.clientHeight || 1080;
if (!Number.isInteger(clientWidth) || !Number.isInteger(clientHeight) || clientWidth < 640 || clientWidth > 2560 || clientHeight < 360 || clientHeight > 1440) throw new Error('검수 창 크기 범위 오류');
let windowWidth = clientWidth + 16;
let windowHeight = clientHeight + 39;
const framedStyle = value => ((value & ~0x81000000) | 0x00cf0000) >>> 0;
const framedExStyle = value => (((value & ~0x08000008) | (config.automatic ? 0x08000000 : 0))) >>> 0;
const getAttributes = new NativeFunction(Process.getModuleByName('kernel32.dll').getExportByName('GetFileAttributesW'), 'uint', ['pointer'], 'stdcall');
const allowedRoot = config.root.replace(/\//g, '\\').toLowerCase() + '\\';
const gameRoot = config.game.replace(/\//g, '\\');
const profilePath = config.profile.replace(/\//g, '\\');
function log(kind, data) {
  const key = kind + JSON.stringify(data);
  if (seen.has(key)) return;
  seen.add(key);
  const row = {kind, ...data};
  events.push(row);
  send(row);
}
function read(ptrValue, wide) {
  if (ptrValue.isNull()) return '';
  return wide ? ptrValue.readUtf16String() : ptrValue.readAnsiString();
}
function alloc(value, wide) {
  const p = wide ? Memory.allocUtf16String(value) : Memory.allocAnsiString(value);
  pins.push(p);
  return p;
}
function fullPath(path) {
  let value = path.replace(/\//g, '\\').replace(/^\\\\\?\\/, '');
  if (!/^[a-z]:\\/i.test(value) && !value.startsWith('\\\\')) value = gameRoot + '\\' + value;
  const parts = [];
  for (const part of value.split('\\')) {
    if (part === '..') parts.pop();
    else if (part !== '.') parts.push(part);
  }
  return parts.join('\\').toLowerCase();
}
function allowed(path) { return (fullPath(path) + '\\').startsWith(allowedRoot); }
function address(module, name) { try { return module.findExportByName(name); } catch (_) { return null; } }
function attach(module, name, callbacks) {
  const target = address(module, name);
  if (!target || hooks.has(target.toString())) return;
  hooks.add(target.toString());
  Interceptor.attach(target, callbacks);
}
function replace(module, name, result, args, body, abi) {
  const target = address(module, name);
  if (!target || hooks.has(target.toString())) return;
  hooks.add(target.toString());
  const fn = new NativeCallback(body, result, args, abi || 'stdcall');
  pins.push(fn);
  Interceptor.replace(target, fn);
}
Process.attachModuleObserver({onAdded(module) {
  const lower = module.name.toLowerCase();
  log('loaded_module', {name:module.name,path:module.path});
  if (lower === 'ntdll.dll') {
    attach(module, 'NtTerminateProcess', {onEnter(args) {log('native_exit', {handle:args[0].toString(),code:args[1].toUInt32()});}});
  }
  if (lower === 'kernel32.dll' || lower === 'kernelbase.dll') {
    for (const suffix of ['W', 'A']) {
      const wide = suffix === 'W';
      attach(module, 'CreateFile' + suffix, {
        onEnter(args) {
          const path = read(args[0], wide);
          const access = args[1].toUInt32();
          const disposition = args[4].toUInt32();
          // 접근성 도구가 이 게임과 통신하는 파이프는 저장 파일이 아닙니다.
          // 자기 프로세스의 UIA 연결과 기존 파이프 열기만 허용합니다.
          const pipePrefix = '\\\\.\\PIPE\\UIA_PIPE_' + Process.id + '_';
          if (disposition === 3 && path.toUpperCase().startsWith(pipePrefix.toUpperCase()) && /^[0-9a-f]+$/i.test(path.slice(pipePrefix.length))) {
            log('allowed_accessibility_pipe', {path, access, disposition});
            return;
          }
          if ((access & 0x400d0116) !== 0 || disposition !== 3) {
            if (!allowed(path)) {
              log('blocked_file_write', {path, access, disposition});
              this.path = alloc(config.root + '\\denied\\outside-write-denied', wide);
              args[0] = this.path;
            } else log('allowed_file_write', {path, access, disposition});
          }
        }
      });
      for (const name of ['CreateDirectory', 'DeleteFile', 'RemoveDirectory']) {
        attach(module, name + suffix, {onEnter(args) {
          const path = read(args[0], wide);
          const ancestor = name === 'CreateDirectory' && allowedRoot.startsWith(fullPath(path).replace(/\\$/, '') + '\\');
          const attrs = name === 'CreateDirectory' ? getAttributes(Memory.allocUtf16String(path)) : 0xffffffff;
          const existingDirectory = attrs !== 0xffffffff && (attrs & 16) !== 0;
          if (!allowed(path) && !ancestor && !existingDirectory) {
            log('blocked_path_mutation', {api: name + suffix, path});
            this.path = alloc(config.root + '\\denied\\outside-path-denied', wide);
            args[0] = this.path;
          }
        }});
      }
      for (const [name, filenameIndex] of [['GetPrivateProfileString', 5], ['GetPrivateProfileInt', 3], ['GetPrivateProfileSection', 3], ['WritePrivateProfileString', 3], ['WritePrivateProfileSection', 2]]) {
        attach(module, name + suffix, {onEnter(args) {
          const original = read(args[filenameIndex], wide);
          const basename = original.split(/[\\/]/).pop() || 'default.ini';
          // 게임 저장 이름만 바꾸고 Windows 자체 설정 읽기는 보존한다.
          if (!name.startsWith('Write') && basename.toLowerCase() !== 'saveprofile.ini') return;
          const path = profilePath + '\\' + basename;
          this.path = alloc(path, wide);
          args[filenameIndex] = this.path;
          log('profile_redirect', {api: name + suffix, original, path});
        }});
      }
      replace(module, 'CreateProcess' + suffix, 'int', ['pointer','pointer','pointer','pointer','int','uint','pointer','pointer','pointer','pointer'], function () {
        this.lastError = 5; log('blocked_child_process', {api: 'CreateProcess' + suffix}); return 0;
      });
    }
    attach(module, 'ExitProcess', {onEnter(args) { log('exit_process', {code:args[0].toUInt32()}); }});
    attach(module, 'TerminateProcess', {onEnter(args) { log('terminate_process', {handle:args[0].toString(),code:args[1].toUInt32()}); }});
  }
  if (lower === 'steam_api.dll') {
    replace(module, 'SteamAPI_Init', 'int', [], () => { log('steam_init_disabled', {}); return 0; }, 'mscdecl');
    replace(module, 'SteamAPI_RestartAppIfNecessary', 'int', ['uint'], () => 0, 'mscdecl');
  }
  if (lower === 'steamworks.mfx') {
    try {
      const target = module.base.add(0x60234).readPointer();
      const owner = Process.findModuleByAddress(target);
      log('steam_init_import', {address:target.toString(),owner:owner ? owner.path : null});
      if (!hooks.has(target.toString()) && owner) {
        const fn = new NativeCallback(() => {log('steam_init_disabled', {source:'import_table'}); return 0;}, 'int', [], 'mscdecl');
        pins.push(fn); hooks.add(target.toString()); Interceptor.replace(target, fn);
      }
    } catch (error) {
      log('steam_import_error', {message:String(error)});
      const terminate = new NativeFunction(Process.getModuleByName('kernel32.dll').getExportByName('TerminateProcess'), 'int', ['pointer','uint'], 'stdcall');
      terminate(ptr(-1), 91);
    }
  }
  if (lower === 'advapi32.dll') {
    for (const suffix of ['W', 'A']) {
      replace(module, 'RegSetValueEx' + suffix, 'long', ['pointer','pointer','uint','uint','pointer','uint'], () => { log('registry_write_disabled', {}); return 5; });
    }
  }
  if (lower === 'shell32.dll') {
    for (const suffix of ['W', 'A']) {
      replace(module, 'ShellExecute' + suffix, 'pointer', ['pointer','pointer','pointer','pointer','pointer','int'], function (_, operation, file) {
        log('blocked_shell_launch', {file:read(file, suffix === 'W')}); this.lastError = 5; return ptr(31);
      });
      replace(module, 'ShellExecuteEx' + suffix, 'int', ['pointer'], function () { log('blocked_shell_launch', {api:'ShellExecuteEx' + suffix}); this.lastError = 5; return 0; });
    }
  }
  if (lower === 'user32.dll') {
    const foreground = new NativeFunction(module.getExportByName('GetForegroundWindow'), 'pointer', [], 'stdcall');
    const isSelected = () => gameWindows.has(foreground().toString());
    const adjust = new NativeFunction(module.getExportByName('AdjustWindowRectEx'), 'int', ['pointer','uint','int','uint'], 'stdcall');
    // 직접 선택한 게임의 입력만 허용하고 다른 앱에서 누르는 키는 받지 않습니다.
    for (const name of ['GetAsyncKeyState', 'GetKeyState']) {
      const original = new NativeFunction(module.getExportByName(name), 'int', ['int'], 'stdcall');
      replace(module, name, 'int', ['int'], key => isSelected() ? original(key) : 0);
    }
    const keyboard = new NativeFunction(module.getExportByName('GetKeyboardState'), 'int', ['pointer'], 'stdcall');
    replace(module, 'GetKeyboardState', 'int', ['pointer'], p => {if(isSelected()) return keyboard(p); p.writeByteArray(new Uint8Array(256));return 1;});
    for (const name of ['SetFocus', 'SetActiveWindow']) {
      const original = new NativeFunction(module.getExportByName(name), 'pointer', ['pointer'], 'stdcall');
      replace(module, name, 'pointer', ['pointer'], p => isSelected() ? original(p) : ptr(0));
    }
    for (const suffix of ['W', 'A']) {
      attach(module, 'CreateWindowEx' + suffix, {onEnter(args) {
        this.main = (args[3].toUInt32() & 0x40000000) === 0 && args[6].toInt32() >= 600;
        if (this.main) {
          if (config.automatic) args[2] = alloc('Cobalt Miner - 자동 검수', suffix === 'W');
          const exStyle = framedExStyle(args[0].toUInt32());
          const style = framedStyle(args[3].toUInt32());
          const rect = Memory.alloc(16); rect.writeS32(0); rect.add(4).writeS32(0); rect.add(8).writeS32(clientWidth); rect.add(12).writeS32(clientHeight);
          if (!adjust(rect, style, 0, exStyle)) throw new Error('테두리 크기 계산 실패');
          windowWidth = rect.add(8).readS32() - rect.readS32();
          windowHeight = rect.add(12).readS32() - rect.add(4).readS32();
          args[0] = ptr(exStyle); args[3] = ptr(style);
          args[4] = ptr(8); args[5] = ptr(8); args[6] = ptr(windowWidth); args[7] = ptr(windowHeight);
        }
      }, onLeave(result) {
        if (this.main) { gameWindows.add(result.toString()); log('qa_window_created', {hwnd:result.toString(),x:8,y:8,width:windowWidth,height:windowHeight,client_width:clientWidth,client_height:clientHeight,bordered:true,manual_selection:!config.automatic}); }
      }});
      for (const name of ['SetWindowLong', 'SetWindowLongPtr']) {
        attach(module, name + suffix, {onEnter(args) {
          if (!gameWindows.has(args[0].toString())) return;
          if (args[1].toInt32() === -16) args[2] = ptr(framedStyle(args[2].toUInt32()));
          if (args[1].toInt32() === -20) args[2] = ptr(framedExStyle(args[2].toUInt32()));
        }});
      }
      if (config.automatic) attach(module, 'SetWindowText' + suffix, {onEnter(args) {
        if (gameWindows.has(args[0].toString())) args[1] = alloc('Cobalt Miner - 자동 검수', suffix === 'W');
      }});
      replace(module, 'ChangeDisplaySettings' + suffix, 'long', ['pointer','uint'], () => -1);
      replace(module, 'ChangeDisplaySettingsEx' + suffix, 'long', ['pointer','pointer','pointer','uint','pointer'], () => -1);
    }
    attach(module, 'SetWindowPos', {onEnter(args) {
      if (gameWindows.has(args[0].toString())) {
        args[2]=ptr(8); args[3]=ptr(8); args[4]=ptr(windowWidth); args[5]=ptr(windowHeight);
        if (config.automatic) {args[1]=ptr(1); args[6]=ptr((args[6].toUInt32() | 0x10) & ~7);}
        else args[6]=ptr((args[6].toUInt32() | 0x14) & ~3);
      }
    }});
    attach(module, 'MoveWindow', {onEnter(args) {
      if (gameWindows.has(args[0].toString())) {args[1]=ptr(8); args[2]=ptr(8); args[3]=ptr(windowWidth); args[4]=ptr(windowHeight);}
    }});
    attach(module, 'ShowWindow', {onEnter(args) { if (![0,6,7].includes(args[1].toInt32())) args[1]=ptr(4); }});
    replace(module, 'SetForegroundWindow', 'int', ['pointer'], () => 0);
    replace(module, 'BringWindowToTop', 'int', ['pointer'], () => 0);
    replace(module, 'SetCursorPos', 'int', ['int','int'], () => 1);
    replace(module, 'ClipCursor', 'int', ['pointer'], () => 1);
    replace(module, 'ShowCursor', 'int', ['int'], () => 0);
    attach(module, 'DrawTextW', {onEnter(args) {
      const count = args[2].toInt32();
      if (count > 10000) return;
      const value = count >= 0 ? args[1].readUtf16String(count) : args[1].readUtf16String();
      if (value && /[A-Za-z\uac00-\ud7a3]/.test(value)) log('draw_text', {value});
    }});
  }
}});
Process.setExceptionHandler(details => {
  // 출력 디버그 문자열 등 정상 알림은 제외하고 실제 메모리 오류만 기록한다.
  if (details.type !== 'access-violation' && details.type !== 'illegal-instruction') return false;
  let trace=[];
  try {trace=Thread.backtrace(details.context,Backtracer.ACCURATE).slice(0,24).map(address=>{const owner=Process.findModuleByAddress(address);return {address:address.toString(),module:owner?owner.name:null,offset:owner?address.sub(owner.base).toString():null};});}catch(_){}
  const module=Process.findModuleByAddress(details.address);
  log('native_exception', {type:details.type,address:details.address.toString(),module:module?module.name:null,offset:module?details.address.sub(module.base).toString():null,memory:details.memory,trace}); return false;
});
const kernel = Process.getModuleByName('kernel32.dll');
// 검수 스레드가 살아 있는 동안만 화면·시스템 절전을 방지합니다.
// Windows 설정을 저장하지 않으며 프로세스 종료 때 요청이 해제됩니다.
const executionState = new NativeFunction(kernel.getExportByName('SetThreadExecutionState'), 'uint', ['uint'], 'stdcall');
const priorExecutionState = executionState(0x80000003);
if (!priorExecutionState) throw new Error('검수 중 화면 절전 방지 요청 실패');
log('qa_display_awake', {pid:Process.id,requested:0x80000003,previous:priorExecutionState,scope:'검수 스레드 수명'});
const setDir = new NativeFunction(kernel.getExportByName('SetCurrentDirectoryW'), 'int', ['pointer'], 'stdcall');
const setEnv = new NativeFunction(kernel.getExportByName('SetEnvironmentVariableW'), 'int', ['pointer','pointer'], 'stdcall');
if (!setDir(alloc(gameRoot, true))) throw new Error('검수 작업 폴더를 설정하지 못했습니다.');
for (const [key, value] of Object.entries({TEMP: config.temp, TMP: config.temp})) {
  if (!setEnv(alloc(key, true), alloc(value, true))) throw new Error('검수 환경값 설정 실패: ' + key);
}
log('guard_ready', {pid: Process.id, platform: Process.platform, architecture: Process.arch, modules: Process.enumerateModules().filter(m => m.name.toLowerCase() === 'cobalt miner.exe').map(m => ({name:m.name,path:m.path,base:m.base.toString()})), root:config.root, hooks:hooks.size});
rpc.exports = {summary() { return {events, hooks: hooks.size, pid: Process.id}; }};
