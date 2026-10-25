#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "aio_sidecar/engine.hpp"
#include "aio_sidecar/host.hpp"
#include "echo_descriptor.hpp"

namespace {

using aio_sidecar::Call;
using aio_sidecar::ErrorKind;
using aio_sidecar::SidecarError;
using aio_sidecar::json;

SidecarError bad_input(const std::string& message, const std::string& op) {
    return SidecarError::make(ErrorKind::BadInput, message).with_op(op);
}

std::string hex_encode(const std::vector<std::uint8_t>& bytes) {
    static constexpr char kHex[] = "0123456789abcdef";
    std::string out;
    out.reserve(bytes.size() * 2);
    for (const auto byte : bytes) {
        out.push_back(kHex[(byte >> 4) & 0x0f]);
        out.push_back(kHex[byte & 0x0f]);
    }
    return out;
}

json execute_request(const json& params, const Call& call, const std::string& op) {
    if (!params.contains("entrypoint") || !params.at("entrypoint").is_string() ||
        params.at("entrypoint").get<std::string>().empty()) {
        throw bad_input("execute requires a non-empty entrypoint", op);
    }
    const auto entrypoint = params.at("entrypoint").get<std::string>();

    if (!params.contains("source_kind") || !params.at("source_kind").is_string()) {
        throw bad_input("source_kind must be \"text\" or \"binary\"", op);
    }
    const auto source_kind = params.at("source_kind").get<std::string>();
    if (source_kind != "text" && source_kind != "binary") {
        throw bad_input("source_kind must be \"text\" or \"binary\"", op);
    }

    const json source =
        params.contains("source") ? params.at("source") : json(nullptr);
    if (source_kind == "text" && !source.is_string()) {
        throw bad_input("source must be a string for text sources", op);
    }
    if (source_kind == "binary" && !source.is_null()) {
        throw bad_input("source must be null for binary sources", op);
    }

    const json arguments =
        params.contains("arguments") ? params.at("arguments") : json::array();
    if (!arguments.is_array()) {
        throw bad_input("arguments must be an array", op);
    }
    const json environment =
        params.contains("environment") ? params.at("environment") : json(nullptr);

    std::uint64_t memory_limit = 64;
    if (params.contains("memory_limit_mb")) {
        const auto& raw = params.at("memory_limit_mb");
        if (!raw.is_number_unsigned() || raw.get<std::uint64_t>() == 0) {
            throw bad_input("memory_limit_mb must be a positive integer", op);
        }
        memory_limit = raw.get<std::uint64_t>();
    }

    const std::size_t source_bytes = source_kind == "binary"
                                         ? call.input().size()
                                         : source.get<std::string>().size();

    return json{
        {"result",
         json{
             {"entrypoint", entrypoint},
             {"arguments", arguments},
             {"environment", environment},
             {"source_kind", source_kind},
             {"source", source},
             {"memory_limit_mb", memory_limit},
         }},
        {"source_bytes", source_bytes},
    };
}

class EchoSession final : public aio_sidecar::Session {
public:
    EchoSession(aio_sidecar::SessionCtx ctx, json config)
        : ctx_(std::move(ctx)), config_(std::move(config)) {}

    json call(const std::string& op, json params, Call& call) override {
        ++calls_;

        if (op == "echo") {
            const json value =
                params.contains("value") ? params.at("value") : json(nullptr);
            return json{{"value", value}, {"config", config_}};
        }
        if (op == "execute") {
            return execute_request(params, call, op);
        }
        if (op == "emit") {
            const std::string name =
                params.contains("event") && params.at("event").is_string()
                    ? params.at("event").get<std::string>()
                    : "progress";
            if (name != "progress" && name != "log") {
                throw bad_input("event must be progress or log", op);
            }
            const json data = params.contains("data")
                                  ? params.at("data")
                                  : json{{"note", "emitted"}};
            call.emit(name, data);
            ++events_;
            return json{{"emitted", name}, {"data", data}};
        }
        if (op == "bytes") {
            std::vector<std::uint8_t> input = call.input();
            const auto size = input.size();
            const auto hex = hex_encode(input);
            call.set_output(std::move(input));
            return json{{"size", size}, {"hex", hex}};
        }
        if (op == "fail") {
            if (!params.contains("kind") || !params.at("kind").is_string()) {
                throw bad_input("fail requires an error kind", op);
            }
            const auto raw_kind = params.at("kind").get<std::string>();
            const auto kind = aio_sidecar::parse_error_kind(raw_kind);
            if (!kind) {
                throw bad_input("unknown error kind \"" + raw_kind + "\"", op);
            }
            const std::string message =
                params.contains("message") && params.at("message").is_string()
                    ? params.at("message").get<std::string>()
                    : "echo " + std::string(aio_sidecar::error_kind_name(*kind));
            SidecarError error(
                *kind, message, aio_sidecar::error_kind_retryable(*kind));
            error.with_op(op);
            if (params.contains("detail")) {
                error.with_detail(params.at("detail"));
            }
            if (params.contains("retryable") &&
                params.at("retryable").is_boolean()) {
                error.with_retryable(params.at("retryable").get<bool>());
            }
            throw error;
        }
        if (op == "throw") {
            const std::string message =
                params.contains("message") && params.at("message").is_string()
                    ? params.at("message").get<std::string>()
                    : "echo engine exploded";
            throw std::runtime_error(message);
        }
        if (op == "sleep") {
            std::uint64_t ms = 1000;
            if (params.contains("ms")) {
                const auto& raw = params.at("ms");
                if (!raw.is_number_unsigned()) {
                    throw bad_input("ms must be a non-negative integer", op);
                }
                ms = raw.get<std::uint64_t>();
            }
            const auto started = std::chrono::steady_clock::now();
            for (;;) {
                call.check();
                const auto elapsed =
                    std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::steady_clock::now() - started)
                        .count();
                if (static_cast<std::uint64_t>(elapsed) >= ms) {
                    break;
                }
                const auto remaining = ms - static_cast<std::uint64_t>(elapsed);
                std::this_thread::sleep_for(
                    std::chrono::milliseconds(std::min<std::uint64_t>(remaining, 10)));
            }
            call.check();
            const auto slept =
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - started)
                    .count();
            return json{{"slept_ms", slept}};
        }
        if (op == "stats") {
            return json{
                {"calls", calls_}, {"events", events_}, {"config", config_}};
        }

        throw SidecarError::make(
            ErrorKind::Unsupported, "op \"" + op + "\" is not implemented")
            .with_op(op);
    }

    json health() override {
        return json{
            {"ok", true},
            {"target", ctx_.target},
            {"detail", json{{"calls", calls_}, {"events", events_}}},
        };
    }

    void warmup(Call& call) override {
        call.log("info", "echo engine warmed up");
    }

    json diagnostics() override {
        json context;
        aio_sidecar::to_json(context, ctx_);
        return json{
            {"calls", calls_},
            {"events", events_},
            {"config", config_},
            {"context", context},
        };
    }

    void close() override {}

private:
    aio_sidecar::SessionCtx ctx_;
    json config_;
    std::uint64_t calls_ = 0;
    std::uint64_t events_ = 0;
};

class EchoEngine final : public aio_sidecar::Engine {
public:
    explicit EchoEngine(json descriptor) : descriptor_(std::move(descriptor)) {}

    json describe() const override { return descriptor_; }

    std::unique_ptr<aio_sidecar::Session> open(
        const aio_sidecar::SessionCtx& ctx,
        json config) override {
        return std::make_unique<EchoSession>(ctx, std::move(config));
    }

private:
    json descriptor_;
};

}  // namespace

int main() {
    try {
        json descriptor = json::parse(echo_fixture::kDescriptorJson);
        EchoEngine engine(std::move(descriptor));
        aio_sidecar::run_stdio(engine);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "echo sidecar failed: " << error.what() << "\n";
        return 1;
    }
}
