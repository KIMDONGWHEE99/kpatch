// 검수 프로세스에만 적용하는 저장·Steam 격리와 관측 코드. 배포하지 않는다.
// @@CONFIG@@ 자리에는 prepare_qa.py가 검수 경로를 넣는다.
const config = /*@@CONFIG@@*/ null;
if (!config) throw new Error('검수 경로가 지정되지 않았습니다.');
const pins = [];
const hooks = new Set();
const seen = new Set();
const events = [];
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
  if (lower === 'kernel32.dll' || lower === 'kernelbase.dll') {
    for (const suffix of ['W', 'A']) {
      const wide = suffix === 'W';
      attach(module, 'CreateFile' + suffix, {
        onEnter(args) {
          const path = read(args[0], wide);
          const access = args[1].toUInt32();
          const disposition = args[4].toUInt32();
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
    attach(module, 'CreateWindowExW', {onEnter(args) {
      const style = args[3].toUInt32();
      this.details = {style, width:args[6].toInt32(),height:args[7].toInt32()};
      if (config.resizeWindow && (style & 0x40000000) === 0 && args[6].toInt32() >= 2000) {
        log('qa_window_size', {old_width: args[6].toInt32(), old_height: args[7].toInt32(), width: 1280, height: 750});
        args[4] = ptr(40); args[5] = ptr(40); args[6] = ptr(1280); args[7] = ptr(750);
      }
    }, onLeave(result) { log('window_created', {...this.details,hwnd:result.toString(),last_error:this.lastError}); }});
    attach(module, 'CreateWindowExA', {onEnter(args) {this.details={style:args[3].toUInt32(),width:args[6].toInt32(),height:args[7].toInt32()};},onLeave(result) {log('window_created_a',{...this.details,hwnd:result.toString(),last_error:this.lastError});}});
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
  try {trace=Thread.backtrace(details.context,Backtracer.ACCURATE).map(p=>{const m=Process.findModuleByAddress(p);return m?m.name+'+'+p.sub(m.base):p.toString();});}catch(_){}
  const module=Process.findModuleByAddress(details.address);
  log('native_exception', {type:details.type,address:details.address.toString(),module:module?module.name:null,offset:module?details.address.sub(module.base).toString():null,memory:details.memory,trace}); return false;
});
const kernel = Process.getModuleByName('kernel32.dll');
const setDir = new NativeFunction(kernel.getExportByName('SetCurrentDirectoryW'), 'int', ['pointer'], 'stdcall');
const setEnv = new NativeFunction(kernel.getExportByName('SetEnvironmentVariableW'), 'int', ['pointer','pointer'], 'stdcall');
if (!setDir(alloc(gameRoot, true))) throw new Error('검수 작업 폴더를 설정하지 못했습니다.');
for (const [key, value] of Object.entries({TEMP: config.temp, TMP: config.temp})) {
  if (!setEnv(alloc(key, true), alloc(value, true))) throw new Error('검수 환경값 설정 실패: ' + key);
}
log('guard_ready', {pid: Process.id, platform: Process.platform, architecture: Process.arch, modules: Process.enumerateModules().filter(m => m.name.toLowerCase() === 'thog.exe').map(m => ({name:m.name,path:m.path,base:m.base.toString()})), root:config.root, hooks:hooks.size});
rpc.exports = {summary() { return {events, hooks: hooks.size, pid: Process.id}; }};
