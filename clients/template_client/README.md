# Template Client Workflow

1. Place your reversed JS files into `assets/` (e.g. `assets/encode.js`).
2. Implement your client operations in `src/lib.rs` using `wre_live::mount` and `wre_client::Client`.
3. Build the client into a standalone binary (`dist/bin/`) or generate SDKs (`dist/packages/`).
