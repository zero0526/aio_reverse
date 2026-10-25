# nlohmann/json

- Version: 3.11.3
- Upstream: https://github.com/nlohmann/json
- File: `nlohmann/json.hpp` (single header)
- SHA-256: `9bea4c8066ef4a1c206b2be5a36302f8926f7fdc6087af5d20b417d0cf103ea6`
- License: MIT, see `LICENSE.MIT`

Vendored because the C++ SDK must build without a system JSON package. The
default `nlohmann::json` object uses `std::map`, so keys are sorted and
`json.dump()` matches the canonical JSON used for `schema_hash`.
