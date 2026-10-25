#pragma once

#include <cstdint>
#include <istream>
#include <optional>
#include <ostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace aio_sidecar {

using json = nlohmann::json;

inline constexpr std::size_t kHeaderBytes = 8;
inline constexpr std::size_t kMaxJsonBytes = 64ull * 1024 * 1024;
inline constexpr std::size_t kMaxBinBytes = 512ull * 1024 * 1024;

struct Frame {
    json envelope;
    std::vector<std::uint8_t> bin;
};

inline std::uint32_t read_be32(const unsigned char* bytes) {
    return (static_cast<std::uint32_t>(bytes[0]) << 24) |
           (static_cast<std::uint32_t>(bytes[1]) << 16) |
           (static_cast<std::uint32_t>(bytes[2]) << 8) |
           static_cast<std::uint32_t>(bytes[3]);
}

inline void write_be32(unsigned char* bytes, std::uint32_t value) {
    bytes[0] = static_cast<unsigned char>((value >> 24) & 0xff);
    bytes[1] = static_cast<unsigned char>((value >> 16) & 0xff);
    bytes[2] = static_cast<unsigned char>((value >> 8) & 0xff);
    bytes[3] = static_cast<unsigned char>(value & 0xff);
}

/// Reads one frame; returns nullopt at a clean end of stream.
inline std::optional<Frame> read_frame(std::istream& in) {
    char header[kHeaderBytes];
    in.read(header, static_cast<std::streamsize>(kHeaderBytes));
    const auto read_bytes = in.gcount();
    if (read_bytes == 0 && in.eof()) {
        return std::nullopt;
    }
    if (read_bytes != static_cast<std::streamsize>(kHeaderBytes)) {
        throw std::runtime_error("truncated frame header");
    }

    const auto* raw = reinterpret_cast<const unsigned char*>(header);
    const auto json_len = read_be32(raw);
    const auto bin_len = read_be32(raw + 4);
    if (json_len > kMaxJsonBytes) {
        throw std::runtime_error("frame json length exceeds the 64 MiB cap");
    }
    if (bin_len > kMaxBinBytes) {
        throw std::runtime_error("frame binary length exceeds the 512 MiB cap");
    }

    Frame frame;
    if (json_len > 0) {
        std::vector<char> json_bytes(json_len);
        in.read(json_bytes.data(), static_cast<std::streamsize>(json_len));
        if (in.gcount() != static_cast<std::streamsize>(json_len)) {
            throw std::runtime_error("truncated frame json");
        }
        try {
            frame.envelope = json::parse(json_bytes.begin(), json_bytes.end());
        } catch (const json::parse_error& error) {
            throw std::runtime_error(std::string("frame JSON is invalid: ") + error.what());
        }
    } else {
        throw std::runtime_error("frame JSON is empty");
    }

    if (bin_len > 0) {
        frame.bin.resize(bin_len);
        in.read(reinterpret_cast<char*>(frame.bin.data()), static_cast<std::streamsize>(bin_len));
        if (in.gcount() != static_cast<std::streamsize>(bin_len)) {
            throw std::runtime_error("truncated frame binary");
        }
    }
    return frame;
}

/// Writes one frame and flushes it.
inline void write_frame(
    std::ostream& out,
    const json& envelope,
    const std::vector<std::uint8_t>& bin = {}) {
    const std::string text = envelope.dump();
    if (text.size() > kMaxJsonBytes) {
        throw std::runtime_error("envelope json length exceeds the 64 MiB cap");
    }
    if (bin.size() > kMaxBinBytes) {
        throw std::runtime_error("frame binary length exceeds the 512 MiB cap");
    }

    unsigned char header[kHeaderBytes];
    write_be32(header, static_cast<std::uint32_t>(text.size()));
    write_be32(header + 4, static_cast<std::uint32_t>(bin.size()));
    out.write(reinterpret_cast<const char*>(header), static_cast<std::streamsize>(kHeaderBytes));
    out.write(text.data(), static_cast<std::streamsize>(text.size()));
    if (!bin.empty()) {
        out.write(
            reinterpret_cast<const char*>(bin.data()),
            static_cast<std::streamsize>(bin.size()));
    }
    out.flush();
    if (!out) {
        throw std::runtime_error("failed to write sidecar frame");
    }
}

/// Canonical JSON for `schema_hash`: nlohmann's default object is a std::map,
/// so keys are sorted recursively; dump() is compact and keeps UTF-8 raw.
inline std::string canonical_json(const json& value) {
    return value.dump();
}

inline std::string fnv1a64(const std::string& data) {
    std::uint64_t digest = 0xcbf29ce484222325ull;
    for (unsigned char byte : data) {
        digest ^= static_cast<std::uint64_t>(byte);
        digest *= 0x00000100000001b3ull;
    }
    static constexpr char kHex[] = "0123456789abcdef";
    std::string out(16, '0');
    for (int index = 15; index >= 0; --index) {
        out[static_cast<std::size_t>(index)] = kHex[digest & 0x0f];
        digest >>= 4;
    }
    return out;
}

inline std::string schema_hash(const json& descriptor) {
    return fnv1a64(canonical_json(descriptor));
}

}  // namespace aio_sidecar
