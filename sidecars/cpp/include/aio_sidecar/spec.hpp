#pragma once

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_set>
#include <vector>

#include "error.hpp"

namespace aio_sidecar {

inline constexpr int kProtocol = 1;
inline constexpr const char* kBundle = "aio";
inline constexpr const char* kHostVersion = "0.1.0";

inline constexpr std::string_view kBaseOps[] = {
    "hello", "describe", "targets", "metrics", "open",
    "close", "health", "warmup", "shutdown", "diag",
};

inline bool is_base_op(const std::string& name) {
    return std::any_of(std::begin(kBaseOps), std::end(kBaseOps),
                       [&](std::string_view candidate) { return candidate == name; });
}

struct OpSpec {
    std::string name;
    std::optional<std::uint64_t> deadline_ms;
};

struct Descriptor {
    json value;
    std::string id;
    std::vector<OpSpec> ops;

    static Descriptor parse(const json& value) {
        if (!value.is_object()) {
            throw SidecarError::make(
                ErrorKind::Internal, "engine.describe() must return a JSON object");
        }
        const auto& id_value = value.at("id");
        if (!id_value.is_string() || id_value.get<std::string>().empty()) {
            throw SidecarError::make(
                ErrorKind::Internal, "engine descriptor requires a non-empty string id");
        }
        Descriptor descriptor;
        descriptor.value = value;
        descriptor.id = id_value.get<std::string>();

        if (!value.contains("ops") || !value.at("ops").is_array()) {
            throw SidecarError::make(
                ErrorKind::Internal,
                "engine \"" + descriptor.id + "\" descriptor requires an ops array");
        }
        std::unordered_set<std::string> seen;
        for (const auto& raw_op : value.at("ops")) {
            if (!raw_op.is_object() || !raw_op.contains("name") ||
                !raw_op.at("name").is_string() ||
                raw_op.at("name").get<std::string>().empty()) {
                throw SidecarError::make(
                    ErrorKind::Internal,
                    "engine \"" + descriptor.id + "\" has an op without a name");
            }
            OpSpec spec;
            spec.name = raw_op.at("name").get<std::string>();
            if (!seen.insert(spec.name).second) {
                throw SidecarError::make(
                    ErrorKind::Internal,
                    "engine \"" + descriptor.id + "\" declares op \"" + spec.name +
                        "\" twice");
            }
            if (raw_op.contains("deadline_ms")) {
                const auto& deadline = raw_op.at("deadline_ms");
                if (!deadline.is_number_integer() || deadline.get<std::int64_t>() < 0) {
                    throw SidecarError::make(
                        ErrorKind::Internal,
                        "op \"" + spec.name + "\" has an invalid deadline_ms");
                }
                spec.deadline_ms =
                    static_cast<std::uint64_t>(deadline.get<std::int64_t>());
            }
            descriptor.ops.push_back(std::move(spec));
        }
        return descriptor;
    }

    std::vector<std::string> op_names() const {
        std::vector<std::string> names;
        names.reserve(ops.size());
        for (const auto& op : ops) {
            names.push_back(op.name);
        }
        return names;
    }

    const OpSpec* find_op(const std::string& name) const {
        for (const auto& op : ops) {
            if (op.name == name) {
                return &op;
            }
        }
        return nullptr;
    }

    json bundle() const {
        return json{
            {"protocol", kProtocol},
            {"bundle", kBundle},
            {"toolkit_version", kHostVersion},
            {"binary_version", kHostVersion},
            {"clients", json::array({value})},
        };
    }
};

}  // namespace aio_sidecar
