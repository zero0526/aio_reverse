# Frida Instrumentation Scripts

Target-side JavaScript hooks injected via Frida:
- `ssl_unpinning.js`: Universal SSL pinning bypass for Android & iOS (TrustManager, OkHttp3, BoringSSL).
- `cipher_monitor.js`: Hooks `javax.crypto.Cipher`, `Mac.getInstance`, KeyStore to dump keys, IVs, and plaintext.
