# Headless Reverse Clients Directory

Contains target-specific client implementations powered by `libs/web-re-toolkit`:
- Each client wraps target JS logic (placed in `assets/`) and runs inside an embedded V8 realm (`wre-live`).
- Native browser fingerprints and environment profiles are provided by `wre-sandbox` and `wre-env`.
- Can be compiled into a standalone binary or exported as a multi-language SDK via `wre-codegen`.
