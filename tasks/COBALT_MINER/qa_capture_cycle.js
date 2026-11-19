// 검수 게임 자기 창만 1초마다 읽습니다. 창 상태·포커스·입력은 변경하지 않습니다.
(() => {
  const config = /*@@CAPTURE_CYCLE@@*/ null;
  if (!config || typeof config.outputDir !== 'string') throw new Error('outputDir 설정이 필요합니다.');
  const outputDir = config.outputDir.replace(/\//g, '\\').replace(/\\+$/, '');
  if (!/^[A-Za-z]:\\/.test(outputDir) || outputDir.split('\\').includes('..')) throw new Error('절대 증거 경로만 허용합니다.');
  const durationMs = config.durationMs === undefined ? 350000 : config.durationMs;
  const intervalMs = config.intervalMs === undefined ? 1000 : config.intervalMs;
  const maxCaptures = config.maxCaptures === undefined ? 350 : config.maxCaptures;
  if (!Number.isInteger(durationMs) || durationMs < 1000 || durationMs > 350000 || intervalMs !== 1000 ||
      !Number.isInteger(maxCaptures) || maxCaptures < 1 || maxCaptures > 350) throw new Error('최대350초/350장, 간격1초만 허용합니다.');
  const native = (module, name, result, args) => new NativeFunction(module.getExportByName(name), result, args, 'stdcall');
  const kernel = Process.getModuleByName('kernel32.dll');
  const createFile = native(kernel, 'CreateFileW', 'pointer', ['pointer','uint','uint','pointer','uint','uint','pointer']);
  const writeFile = native(kernel, 'WriteFile', 'int', ['pointer','pointer','uint','pointer','pointer']);
  const closeHandle = native(kernel, 'CloseHandle', 'int', ['pointer']);
  const attributes = native(kernel, 'GetFileAttributesW', 'uint', ['pointer']);
  const lastError = native(kernel, 'GetLastError', 'uint', []);
  const queryCounter = native(kernel, 'QueryPerformanceCounter', 'int', ['pointer']);
  const queryFrequency = native(kernel, 'QueryPerformanceFrequency', 'int', ['pointer']);
  const frequencyMemory = Memory.alloc(8);
  if (!queryFrequency(frequencyMemory)) throw new Error('단조 시계 주파수를 읽지 못했습니다.');
  const frequency = Number(frequencyMemory.readS64().toString());
  if (!(frequency > 0)) throw new Error('잘못된 단조 시계 주파수');
  const clock = () => {
    const value = Memory.alloc(8);
    if (!queryCounter(value)) throw new Error('단조 시계를 읽지 못했습니다.');
    return Number(value.readS64().toString()) * 1000 / frequency;
  };
  const directoryAttributes = attributes(Memory.allocUtf16String(outputDir));
  if (directoryAttributes === 0xffffffff || (directoryAttributes & 0x10) === 0) throw new Error('미리 생성한 증거 폴더가 필요합니다.');
  const scriptLoadedUtc = new Date().toISOString();
  const scriptLoadedMono = clock();
  const records = [];
  const attemptedWindows = new Set();
  let api = null, target = null, firstWindowMono = null, firstWindowUtc = null;
  let startMono = null, startUtc = null, interval = null, deadline = null, stopped = false, busy = false;
  let index = 0, attempts = 0, observer = null, userHooked = false, pendingWindow = null;
  let firstWindowBasis = config.hwnd ? 'existing_hwnd_capture_start' : 'observed_CreateWindowEx_return';
  const log = (kind, details) => send({kind, pid: Process.id, ...details});
  const elapsed = now => firstWindowMono === null ? null : Math.round((now - firstWindowMono) * 1000) / 1000;
  function writeParts(path, parts) {
    // CREATE_NEW=1: 같은 이름이 있으면 실패하며 기존 자료를 덮어쓰지 않습니다.
    const file = createFile(Memory.allocUtf16String(path), 0x40000000, 1, ptr(0), 1, 0x80, ptr(0));
    if (file.equals(ptr(-1))) throw new Error('새 파일 생성 실패: ' + path + ' win32=' + lastError());
    const written = Memory.alloc(4);
    try {
      for (const part of parts) {
        if (!writeFile(file, part.pointer, part.size, written, ptr(0)) || written.readU32() !== part.size) {
          throw new Error('파일 쓰기 실패: ' + path + ' win32=' + lastError());
        }
      }
    } finally { closeHandle(file); }
  }
  function writeJson(name, value) {
    const text = JSON.stringify(value, null, 2) + '\n';
    let size = 0;
    for (const character of text) {
      const point = character.codePointAt(0);
      size += point < 0x80 ? 1 : point < 0x800 ? 2 : point < 0x10000 ? 3 : 4;
    }
    writeParts(outputDir + '\\' + name, [{pointer:Memory.allocUtf8String(text), size}]);
  }
  function initializeApis() {
    if (api) return true;
    const user = Process.findModuleByName('user32.dll');
    const gdi = Process.findModuleByName('gdi32.dll');
    const advapi = Process.findModuleByName('advapi32.dll');
    if (!user || !gdi || !advapi) return false;
    api = {
      getClient: native(user, 'GetClientRect', 'int', ['pointer','pointer']),
      getOwner: native(user, 'GetWindowThreadProcessId', 'uint', ['pointer','pointer']),
      isWindow: native(user, 'IsWindow', 'int', ['pointer']),
      isIconic: native(user, 'IsIconic', 'int', ['pointer']),
      print: native(user, 'PrintWindow', 'int', ['pointer','pointer','uint']),
      createDC: native(gdi, 'CreateCompatibleDC', 'pointer', ['pointer']),
      createDIB: native(gdi, 'CreateDIBSection', 'pointer', ['pointer','pointer','uint','pointer','pointer','uint']),
      select: native(gdi, 'SelectObject', 'pointer', ['pointer','pointer']),
      deleteObject: native(gdi, 'DeleteObject', 'int', ['pointer']),
      deleteDC: native(gdi, 'DeleteDC', 'int', ['pointer']),
      cryptAcquire: native(advapi, 'CryptAcquireContextW', 'int', ['pointer','pointer','pointer','uint','uint']),
      cryptCreate: native(advapi, 'CryptCreateHash', 'int', ['pointer','uint','pointer','uint','pointer']),
      cryptUpdate: native(advapi, 'CryptHashData', 'int', ['pointer','pointer','uint','uint']),
      cryptGet: native(advapi, 'CryptGetHashParam', 'int', ['pointer','uint','pointer','pointer','uint']),
      cryptDestroy: native(advapi, 'CryptDestroyHash', 'int', ['pointer']),
      cryptRelease: native(advapi, 'CryptReleaseContext', 'int', ['pointer','uint'])
    };
    return true;
  }
  function sha256(parts) {
    const providerMemory = Memory.alloc(Process.pointerSize);
    const hashMemory = Memory.alloc(Process.pointerSize);
    // VERIFYCONTEXT: 저장 키 컨테이너를 만들지 않고 메모리에서 해시만 계산합니다.
    if (!api.cryptAcquire(providerMemory, ptr(0), ptr(0), 24, 0xf0000000)) throw new Error('SHA256 공급자 생성 실패');
    const provider = providerMemory.readPointer();
    let hash = null;
    try {
      if (!api.cryptCreate(provider, 0x800c, ptr(0), 0, hashMemory)) throw new Error('SHA256 해시 생성 실패');
      hash = hashMemory.readPointer();
      for (const part of parts) if (!api.cryptUpdate(hash, part.pointer, part.size, 0)) throw new Error('SHA256 갱신 실패');
      const value = Memory.alloc(32), length = Memory.alloc(4); length.writeU32(32);
      if (!api.cryptGet(hash, 2, value, length, 0) || length.readU32() !== 32) throw new Error('SHA256 읽기 실패');
      return Array.from(new Uint8Array(value.readByteArray(32)), byte => byte.toString(16).padStart(2, '0')).join('');
    } finally {
      if (hash) api.cryptDestroy(hash);
      api.cryptRelease(provider, 0);
    }
  }
  function ownWindow(hwnd) {
    if (!api.isWindow(hwnd)) return false;
    const owner = Memory.alloc(4); owner.writeU32(0);
    return api.getOwner(hwnd, owner) !== 0 && owner.readU32() === Process.id;
  }
  function captureOne() {
    if (!ownWindow(target)) throw new Error('대상 HWND가 사라졌거나 다른 프로세스로 바뀌었습니다.');
    if (api.isIconic(target)) throw new Error('대상 창이 최소화되어 캡처를 건너뜁니다.');
    const rect = Memory.alloc(16);
    if (!api.getClient(target, rect)) throw new Error('클라이언트 크기 조회 실패');
    const width = rect.add(8).readS32() - rect.readS32();
    const height = rect.add(12).readS32() - rect.add(4).readS32();
    if (width !== (config.expectedWidth || 1920) || height !== (config.expectedHeight || 1080) || width < 640 || width > 2560 || height < 360 || height > 1440) throw new Error('예상 크기와 다른 클라이언트: ' + width + 'x' + height);
    const startedMono = clock(), startedUtc = new Date().toISOString();
    const info = Memory.alloc(40); info.writeByteArray(new Uint8Array(40));
    const pixelBytes = width * height * 4;
    info.writeU32(40); info.add(4).writeS32(width); info.add(8).writeS32(-height);
    info.add(12).writeU16(1); info.add(14).writeU16(32); info.add(20).writeU32(pixelBytes);
    const bits = Memory.alloc(Process.pointerSize); bits.writePointer(ptr(0));
    const dc = api.createDC(ptr(0));
    if (dc.isNull()) throw new Error('메모리 DC 생성 실패');
    let bitmap = null, old = null;
    try {
      bitmap = api.createDIB(dc, info, 0, bits, ptr(0), 0);
      if (bitmap.isNull() || bits.readPointer().isNull()) throw new Error('DIB 생성 실패');
      old = api.select(dc, bitmap);
      if (old.isNull() || old.equals(ptr(-1))) throw new Error('DIB 선택 실패');
      if (!api.print(target, dc, 3)) throw new Error('PrintWindow 실패');
      const header = new Uint8Array(54), view = new DataView(header.buffer);
      header[0] = 66; header[1] = 77;
      view.setUint32(2, 54 + pixelBytes, true); view.setUint32(10, 54, true);
      header.set(new Uint8Array(info.readByteArray(40)), 14);
      const headerMemory = Memory.alloc(54); headerMemory.writeByteArray(header);
      const parts = [{pointer:headerMemory,size:54},{pointer:bits.readPointer(),size:pixelBytes}];
      const digest = sha256(parts);
      const nextIndex = index + 1;
      const path = outputDir + '\\cycle_' + String(nextIndex).padStart(4, '0') + '.bmp';
      writeParts(path, parts);
      index = nextIndex;
      const endedMono = clock();
      return {index,attempt:attempts,hwnd:target.toString(),width,height,output:path,bytes:54+pixelBytes,sha256:digest,
              utc:startedUtc,finished_utc:new Date().toISOString(),elapsed_ms:elapsed(startedMono),
              capture_session_elapsed_ms:Math.round(startedMono-startMono),capture_duration_ms:Math.round(endedMono-startedMono),
              first_window_basis:firstWindowBasis,api_status:'PASS',graphics_review:'NOT_RUN',paragraph_alignment:'NOT_RUN'};
    } finally {
      if (old && !old.isNull() && !old.equals(ptr(-1))) api.select(dc, old);
      if (bitmap && !bitmap.isNull()) api.deleteObject(bitmap);
      api.deleteDC(dc);
    }
  }
  function stop(reason) {
    if (stopped) return;
    stopped = true;
    if (interval !== null) clearInterval(interval);
    if (deadline !== null) clearTimeout(deadline);
    const manifest = {pid:Process.id,hwnd:target ? target.toString() : null,reason,config,script_loaded_utc:scriptLoadedUtc,
      first_window_utc:firstWindowUtc,first_window_basis:firstWindowBasis,capture_started_utc:startUtc,stopped_utc:new Date().toISOString(),
      elapsed_ms:elapsed(clock()),attempts,captures:index,records,interval_ms:intervalMs,duration_ms:durationMs,
      capture_only:true,graphics_review:'NOT_RUN',paragraph_alignment:'NOT_RUN',
      limitation:'시간 일치와 API 성공만으로 문단 PASS를 판정하지 않습니다. 실제 텍스트 또는 고유한 화면 영역과 연결해야 합니다.'};
    try { writeJson('cycle_manifest.json', manifest); }
    catch (error) { log('qa_cycle_manifest_error', {error:String(error),manifest}); }
    log('qa_cycle_stopped', {reason,captures:index,attempts,elapsed_ms:manifest.elapsed_ms,outputDir});
  }
  function tick() {
    if (stopped || busy) return;
    if (clock() - startMono >= durationMs || index >= maxCaptures) { stop('limit'); return; }
    busy = true; attempts += 1;
    try {
      const row = captureOne(); records.push(row); log('qa_cycle_capture', row);
    } catch (error) {
      const row = {attempt:attempts,utc:new Date().toISOString(),elapsed_ms:elapsed(clock()),error:String(error),api_status:'FAIL'};
      records.push(row); log('qa_cycle_capture_error', row);
      // 이름 충돌·쓰기 실패가 계속되면 원본을 덮어쓰지 않고 이 실행을 종료합니다.
      if (String(error).includes('파일') || !ownWindow(target)) stop('capture_error');
    } finally { busy = false; }
  }
  function start(hwnd, basis, createdMono, createdUtc) {
    if (target || stopped || !initializeApis()) return;
    if (!ownWindow(hwnd)) throw new Error('설정된 HWND는 현재 검수 프로세스의 창이 아닙니다.');
    target = hwnd; firstWindowBasis = basis;
    firstWindowMono = createdMono; firstWindowUtc = createdUtc;
    startMono = clock(); startUtc = new Date().toISOString();
    writeJson('cycle_config.json', {pid:Process.id,hwnd:target.toString(),config,script_loaded_utc:scriptLoadedUtc,
      first_window_utc:firstWindowUtc,first_window_basis:firstWindowBasis,start_utc:startUtc,
      note:basis==='existing_hwnd_capture_start'?'이미 열린 창의 실제 생성 시각은 미관측. elapsed는캡처시작기준':'CreateWindowEx 반환을관측한단조시계기준'});
    log('qa_cycle_started', {hwnd:target.toString(),outputDir,durationMs,intervalMs,maxCaptures,first_window_utc:firstWindowUtc,
      first_window_basis:firstWindowBasis,script_to_start_ms:Math.round(startMono-scriptLoadedMono)});
    interval = setInterval(tick, intervalMs);
    deadline = setTimeout(() => stop('duration'), durationMs);
  }
  function hookUser(module) {
    if (userHooked) return;
    userHooked = true;
    for (const suffix of ['W','A']) {
      Interceptor.attach(module.getExportByName('CreateWindowEx'+suffix), {
        onEnter(args) { this.main = (args[3].toUInt32() & 0x40000000) === 0 && args[6].toInt32() >= 600; },
        onLeave(result) {
          if (!this.main || result.isNull() || config.hwnd || target || stopped) return;
          const key = result.toString();
          if (attemptedWindows.has(key)) return;
          attemptedWindows.add(key);
          const mono = clock(), utc = new Date().toISOString();
          // Frida의 retval 객체는 재사용되므로 비동기 콜백에는 포인터 값을 복제합니다.
          const hwnd = ptr(key);
          pendingWindow = {hwnd,mono,utc};
          // 창 생성 함수 내부에서 캡처하지 않고 콜백이 끝난 다음 타이머를 설정합니다.
          setImmediate(() => {
            try { start(hwnd, 'observed_CreateWindowEx_return', mono, utc); }
            catch (error) { log('qa_cycle_window_rejected', {hwnd:key,error:String(error)}); }
          });
        }
      });
    }
  }
  observer = Process.attachModuleObserver({onAdded(module) {
    if (module.name.toLowerCase() === 'user32.dll') hookUser(module);
    if (config.hwnd && !target && initializeApis()) setImmediate(() => {
      if (!target && !stopped) start(ptr(config.hwnd), 'existing_hwnd_capture_start', clock(), new Date().toISOString());
    });
    if (!config.hwnd && pendingWindow && !target && initializeApis()) setImmediate(() => {
      if (!target && !stopped) start(pendingWindow.hwnd, 'observed_CreateWindowEx_return', pendingWindow.mono, pendingWindow.utc);
    });
  }});
  rpc.exports = {
    stop() { stop('rpc'); return {captures:index,attempts}; },
    status() { return {pid:Process.id,hwnd:target?target.toString():null,stopped,captures:index,attempts,first_window_utc:firstWindowUtc,first_window_basis:firstWindowBasis}; }
  };
  log('qa_cycle_ready', {outputDir,durationMs,intervalMs,maxCaptures,mode:config.hwnd?'existing_hwnd':'before_resume'});
})();
