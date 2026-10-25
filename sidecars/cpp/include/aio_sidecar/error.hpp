#pragma once

#include <optional>
#include <stdexcept>
#include <string>
#include <utility>

#include "frame.hpp"

namespace aio_sidecar {

enum class ErrorKind {
    BadInput,
    Unsupported,
    TargetDrift,
    Blocked,
    Timeout,
    Cancelled,
    Resource,
    Protocol,
    Internal,
};

inline const char* error_kind_name(ErrorKind kind) {
    switch (kind) {
        case ErrorKind::BadInput: return "bad_input";
        case ErrorKind::Unsupported: return "unsupported";
        case ErrorKind::TargetDrift: return "target_drift";
        case ErrorKind::Blocked: return "blocked";
        case ErrorKind::Timeout: return "timeout";
        case ErrorKind::Cancelled: return "cancelled";
        case ErrorKind::Resource: return "resource";
        case ErrorKind::Protocol: return "protocol";
        case ErrorKind::Internal: return "internal";
    }
    return "internal";
}

inline bool error_kind_retryable(ErrorKind kind) {
    return kind == ErrorKind::Blocked || kind == ErrorKind::Timeout ||
           kind == ErrorKind::Resource;
}

inline std::optional<ErrorKind> parse_error_kind(const std::string& value) {
    for (auto kind : {ErrorKind::BadInput, ErrorKind::Unsupported, ErrorKind::TargetDrift,
                      ErrorKind::Blocked, ErrorKind::Timeout, ErrorKind::Cancelled,
                      ErrorKind::Resource, ErrorKind::Protocol, ErrorKind::Internal}) {
        if (value == error_kind_name(kind)) {
            return kind;
        }
    }
    return std::nullopt;
}

/// Typed failure understood by every binding. `retryable` defaults from the
/// kind and may be overridden by the engine.
class SidecarError : public std::runtime_error {
public:
    SidecarError(
        ErrorKind kind,
        const std::string& message,
        bool retryable,
        std::string target = {},
        std::string op = {},
        json detail = nullptr)
        : std::runtime_error(message),
          kind_(kind),
          retryable_(retryable),
          target_(std::move(target)),
          op_(std::move(op)),
          detail_(std::move(detail)) {}

    static SidecarError make(ErrorKind kind, const std::string& message) {
        return SidecarError(kind, message, error_kind_retryable(kind));
    }

    ErrorKind kind() const { return kind_; }
    bool retryable() const { return retryable_; }
    const std::string& target() const { return target_; }
    const std::string& op() const { return op_; }
    const json& detail() const { return detail_; }

    SidecarError& with_target(std::string target) {
        target_ = std::move(target);
        return *this;
    }

    SidecarError& with_op(std::string op) {
        op_ = std::move(op);
        return *this;
    }

    SidecarError& with_detail(json detail) {
        detail_ = std::move(detail);
        return *this;
    }

    SidecarError& with_retryable(bool retryable) {
        retryable_ = retryable;
        return *this;
    }

    json to_wire(
        const std::optional<std::string>& fallback_target,
        const std::optional<std::string>& fallback_op) const {
        json wire = json::object();
        wire["kind"] = error_kind_name(kind_);
        wire["message"] = what();
        wire["retryable"] = retryable_;
        if (!target_.empty()) {
            wire["target"] = target_;
        } else if (fallback_target) {
            wire["target"] = *fallback_target;
        }
        if (!op_.empty()) {
            wire["op"] = op_;
        } else if (fallback_op) {
            wire["op"] = *fallback_op;
        }
        if (!detail_.is_null()) {
            wire["detail"] = detail_;
        }
        return wire;
    }

private:
    ErrorKind kind_;
    bool retryable_;
    std::string target_;
    std::string op_;
    json detail_;
};

}  // namespace aio_sidecar
