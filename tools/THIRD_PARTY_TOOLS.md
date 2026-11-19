# Git에 넣지 않는 외부 도구 목록

작성: 2026-11-19 · 대상: `.gitignore`로 제외한 외부 도구 바이너리

아래 도구는 용량이 크거나 실행 파일이어서 Git에 넣지 않는다. 파일은 이 폴더에 그대로 있다. 폴더를 새로 만들거나 도구를 잃었을 때 같은 버전을 다시 구할 수 있도록 이름·버전·해시를 적어 둔다. 해시는 SHA-256이다.

## tools/python_deps

Python 3.10(64비트 Windows)용으로 받아 둔 패키지다. 도구 스크립트가 `sys.path`에 이 폴더를 넣어 쓴다. `__pycache__`를 뺀 파일 921개, 64,589,191바이트.

| 패키지 | 버전 |
|---|---|
| archspec | 0.2.6 |
| astc_encoder_py | 0.1.12 |
| attrs | 26.1.0 |
| brotli | 1.2.0 |
| etcpak | 0.9.15 |
| fmod_toolkit | 0.1.3 |
| fonttools | 4.64.0 |
| fsspec | 2026.7.0 |
| lz4 | 4.4.5 |
| pillow | 12.3.0 |
| pyfmodex | 0.7.2 |
| texture2ddecoder | 1.0.6 |
| tpk_ar | 0.2.4 |
| typetreegeneratorapi | 0.0.10 |
| typing_extensions | 4.16.0 |
| unitypy | 1.25.3 |

폴더 전체 지문: `ad1b40aa3727b21cf223ad0058c1717f1ec307d00191d57bfc41606cce0576e2`. 파일마다 "상대 경로, 공백, 파일 SHA-256"을 한 줄로 적고 경로 순으로 정렬해 줄바꿈으로 이은 문자열의 SHA-256이다. `__pycache__`는 뺀다.

## tools/gdre_2.6.4

Godot RE Tools 2.6.4. Godot 게임의 PCK를 풀고 다시 묶을 때 쓴다.

| 파일 | 크기(바이트) | SHA-256 |
|---|---|---|
| `GDRE_tools-v2.6.4-windows.zip` | 42,467,872 | `62e06406a08da639e81afb14dcb071beb738be275469e8e980516957b5ebec47` |
| `bin/gdre_tools.exe` | 91,409,408 | `88d6fbccfb7e5bacca7d248c5171fe66bbef15d78e0d7f6287c2f44e78aa9eaf` |
| `bin/gdre_tools.pck` | 6,159,276 | `3703ed2ebdfa1027a47cdaf181b53f4ee9164656b426017b06aa0f31b1401554` |
| `bin/GodotMonoDecompNativeAOT.dll` | 25,230,848 | `ab0bf70684bf8752298323787e2cea0da829948ef3707abb4973aef320dd9bff` |

## tasks 안의 외부 실행 파일

`*.exe`, `*.dll` 규칙으로 제외된다.

| 위치 | 도구 |
|---|---|
| `tasks/TFC2/tools/third_party/Cpp2IL-2022.1.0-pre-release.21/` | Cpp2IL 2022.1.0-pre-release.21 (`Cpp2IL.exe`와 플러그인 DLL 1개) |
| `tasks/SUPERREAP_DEMO/tools/third_party/xdelta3-3.2.0/` | xdelta3 3.2.0 (`xdelta3.exe`, `xdelta3decode.exe`) |

## 그 밖에 제외되는 것

- `tasks/**/bin/`, `tasks/**/obj/`: C# 도구의 빌드 산출물. 소스(`.cs`, `.csproj`)는 Git에 있으므로 다시 빌드할 수 있다. 일부 `bin`에는 게임에서 온 DLL이 들어 있어 커밋하지 않는다.
- 글꼴(`tasks/*/third_party`의 `.ttf`)은 라이선스 파일과 함께 Git에 넣는다.
