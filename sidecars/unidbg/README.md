# Unidbg Sidecar

Standalone Java daemon wrapping the `unidbg` library:
- Simulates ARM32/ARM64 CPU and Android Dalvik/ART runtime.
- Loads target `.so` native libraries extracted from APKs.
- Exposes a local RPC (HTTP/gRPC/Unix Socket) to execute native JNI functions (e.g. `signRequest()`).
