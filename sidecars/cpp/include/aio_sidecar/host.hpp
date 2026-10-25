#pragma once

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <deque>
#include <exception>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#if defined(_WIN32)
#include <process.h>
#else
#include <unistd.h>
#endif

#include "engine.hpp"
#include "error.hpp"
#include "frame.hpp"
#include "spec.hpp"

namespace aio_sidecar {

inline std::uint32_t current_pid() {
#if defined(_WIN32)
    return static_cast<std::uint32_t>(_getpid());
#else
    return static_cast<std::uint32_t>(::getpid());
#endif
}

struct HostOptions {
    std::uint32_t pid = current_pid();
};

namespace detail {

enum class IncomingKind { Frame, Eof, Fatal };

struct Incoming {
    IncomingKind kind = IncomingKind::Eof;
    json value;
    std::vector<std::uint8_t> bin;
    std::string message;
};

/// Bounded hand-off between the stdin reader thread and the serial dispatcher.
struct ReaderQueue {
    void push(Incoming item) {
        {
            std::lock_guard<std::mutex> lock(mutex);
            items.push_back(std::move(item));
        }
        cv.notify_one();
    }

    void close() {
        {
            std::lock_guard<std::mutex> lock(mutex);
            closed = true;
        }
        cv.notify_one();
    }

    bool pop(Incoming& out) {
        std::unique_lock<std::mutex> lock(mutex);
        cv.wait(lock, [this] { return !items.empty() || closed; });
        if (items.empty()) {
            return false;
        }
        out = std::move(items.front());
        items.pop_front();
        return true;
    }

    std::mutex mutex;
    std::condition_variable cv;
    std::deque<Incoming> items;
    bool closed = false;
};

inline void reader_loop(
    const std::shared_ptr<ReaderQueue>& queue,
    const std::shared_ptr<CancelState>& cancel) {
    try {
        for (;;) {
            auto frame = read_frame(std::cin);
            if (!frame.has_value()) {
                queue->push(Incoming{IncomingKind::Eof});
                break;
            }
            if (frame->envelope.is_object() &&
                frame->envelope.value("t", std::string()) == "cancel") {
                if (frame->envelope.contains("id") &&
                    frame->envelope.at("id").is_number_unsigned()) {
                    cancel->cancel(frame->envelope.at("id").get<std::uint64_t>());
                }
                continue;
            }
            Incoming item;
            item.kind = IncomingKind::Frame;
            item.value = std::move(frame->envelope);
            item.bin = std::move(frame->bin);
            queue->push(std::move(item));
        }
    } catch (const std::exception& error) {
        Incoming item;
        item.kind = IncomingKind::Fatal;
        item.message = error.what();
        queue->push(std::move(item));
    } catch (...) {
        Incoming item;
        item.kind = IncomingKind::Fatal;
        item.message = "sidecar reader failed with a non-standard exception";
        queue->push(std::move(item));
    }
    queue->close();
}

inline SidecarError bad_input(const std::string& message, const std::string& op) {
    return SidecarError::make(ErrorKind::BadInput, message).with_op(op);
}

}  // namespace detail

/// Protocol v1 host. Requests are processed serially; the reader thread
/// handles `cancel` frames immediately and queues everything else.
class Host {
public:
    Host(Engine& engine, HostOptions options = {})
        : engine_(engine),
          options_(options),
          descriptor_(Descriptor::parse(engine.describe())),
          schema_hash_(schema_hash(descriptor_.value)),
          sink_(std::cout),
          cancel_(std::make_shared<CancelState>()) {}

    void serve() {
        auto queue = std::make_shared<detail::ReaderQueue>();
        std::thread reader([queue, cancel = cancel_] {
            detail::reader_loop(queue, cancel);
        });
        reader.detach();

        detail::Incoming item;
        while (queue->pop(item)) {
            switch (item.kind) {
                case detail::IncomingKind::Eof:
                    close_all();
                    return;
                case detail::IncomingKind::Fatal:
                    close_all();
                    throw std::runtime_error(
                        "sidecar reader failed: " + item.message);
                case detail::IncomingKind::Frame:
                    if (handle_envelope(item.value, item.bin)) {
                        close_all();
                        return;
                    }
                    break;
            }
        }
        close_all();
    }

private:
    struct Metrics {
        std::uint64_t requests = 0;
        std::uint64_t calls = 0;
        std::uint64_t errors = 0;
        std::uint64_t sessions_opened = 0;
    };

    struct SessionEntry {
        std::string id;
        std::string target;
        std::unique_ptr<Session> session;
    };

    bool handle_envelope(
        const json& envelope,
        const std::vector<std::uint8_t>& bin) {
        if (!envelope.is_object() ||
            envelope.value("t", std::string()) != "req") {
            throw std::runtime_error(
                "unexpected envelope type " +
                (envelope.is_object() ? envelope.at("t").dump() : std::string("null")));
        }
        if (!envelope.contains("id") ||
            !envelope.at("id").is_number_unsigned()) {
            throw std::runtime_error(
                "request id must be an unsigned integer");
        }
        const auto id = envelope.at("id").get<std::uint64_t>();
        ++metrics_.requests;

        if (!envelope.contains("v") ||
            !envelope.at("v").is_number_unsigned() ||
            envelope.at("v").get<std::uint64_t>() !=
                static_cast<std::uint64_t>(kProtocol)) {
            respond_error(
                id,
                "",
                std::nullopt,
                SidecarError::make(
                    ErrorKind::Protocol,
                    "unsupported protocol version " + envelope.value("v", json()).dump()));
            return false;
        }

        std::string op;
        if (envelope.contains("op") && envelope.at("op").is_string()) {
            op = envelope.at("op").get<std::string>();
        }
        if (op.empty()) {
            respond_error(
                id,
                "",
                std::nullopt,
                SidecarError::make(
                    ErrorKind::BadInput, "op must be a non-empty string"));
            return false;
        }

        json params = json::object();
        if (envelope.contains("params")) {
            const auto& raw = envelope.at("params");
            if (!raw.is_object()) {
                respond_error(
                    id, op, std::nullopt,
                    detail::bad_input("params must be a JSON object", op));
                return false;
            }
            params = raw;
        }

        std::optional<std::string> session_id;
        if (envelope.contains("session")) {
            const auto& raw = envelope.at("session");
            if (!raw.is_string() || raw.get<std::string>().empty()) {
                respond_error(
                    id, op, std::nullopt,
                    detail::bad_input(
                        "session must be a non-empty string", op));
                return false;
            }
            session_id = raw.get<std::string>();
        }

        std::optional<std::uint64_t> requested_deadline;
        if (envelope.contains("deadline_ms")) {
            const auto& raw = envelope.at("deadline_ms");
            if (!raw.is_number_unsigned()) {
                respond_error(
                    id, op, std::nullopt,
                    detail::bad_input(
                        "deadline_ms must be a non-negative integer", op));
                return false;
            }
            requested_deadline = raw.get<std::uint64_t>();
        }

        std::optional<std::string> target_hint;
        if (session_id) {
            const auto found = sessions_.find(*session_id);
            if (found != sessions_.end()) {
                target_hint = found->second->target;
            }
        }

        std::optional<std::uint64_t> deadline_ms = requested_deadline;
        if (!deadline_ms && !is_base_op(op)) {
            const auto* spec = descriptor_.find_op(op);
            if (spec != nullptr && spec->deadline_ms &&
                *spec->deadline_ms > 0) {
                deadline_ms = spec->deadline_ms;
            }
        }

        std::optional<std::chrono::steady_clock::time_point> deadline;
        if (deadline_ms) {
            const auto max_ms = static_cast<std::uint64_t>(
                std::numeric_limits<std::int64_t>::max());
            if (*deadline_ms > max_ms) {
                respond_error(
                    id, op, target_hint,
                    detail::bad_input("deadline_ms is too large", op));
                return false;
            }
            deadline = std::chrono::steady_clock::now() +
                       std::chrono::milliseconds(*deadline_ms);
        }

        if (cancel_->begin(id)) {
            respond_error(
                id, op, target_hint,
                SidecarError::make(
                    ErrorKind::Cancelled,
                    "op \"" + op + "\" was cancelled")
                    .with_op(op));
            cancel_->finish(id);
            return false;
        }

        Call call(
            id,
            op,
            target_hint.value_or(""),
            bin,
            deadline,
            deadline_ms,
            cancel_,
            sink_);

        bool stopping = false;
        try {
            json result = dispatch(op, session_id, std::move(params), call);
            auto output = call.take_output();
            respond_result(id, std::move(result), std::move(output));
            stopping = shutdown_requested_;
        } catch (const SidecarError& error) {
            respond_error(id, op, target_hint, error);
        } catch (const std::exception& error) {
            respond_engine_exception(
                id, op, target_hint, "exception", error.what());
        } catch (...) {
            respond_engine_exception(
                id, op, target_hint, "unknown",
                "engine raised a non-standard exception");
        }
        cancel_->finish(id);
        return stopping;
    }

    json dispatch(
        const std::string& op,
        const std::optional<std::string>& session_id,
        json params,
        Call& call) {
        if (op == "hello") {
            return hello();
        }
        if (op == "describe") {
            return descriptor_.bundle();
        }
        if (op == "targets") {
            return json::array({descriptor_.id});
        }
        if (op == "metrics") {
            return metrics_value();
        }
        if (op == "open") {
            return open(std::move(params));
        }
        if (op == "close") {
            return close_session(session_id, op);
        }
        if (op == "health") {
            return require_session(session_id, op).session->health();
        }
        if (op == "warmup") {
            auto& entry = require_session(session_id, op);
            entry.session->warmup(call);
            return json{{"warm", true}};
        }
        if (op == "diag") {
            return diag(session_id, op);
        }
        if (op == "shutdown") {
            close_all();
            shutdown_requested_ = true;
            return json{{"stopping", true}};
        }
        return target_op(op, session_id, std::move(params), call);
    }

    json hello() const {
        return json{
            {"protocol", kProtocol},
            {"bundle", kBundle},
            {"binary_version", kHostVersion},
            {"toolkit_version", kHostVersion},
            {"schema_hash", schema_hash_},
            {"targets", json::array({descriptor_.id})},
            {"workers", 1},
            {"pid", options_.pid},
        };
    }

    json metrics_value() const {
        return json{
            {"requests", metrics_.requests},
            {"calls", metrics_.calls},
            {"errors", metrics_.errors},
            {"events", sink_.event_count()},
            {"sessions_opened", metrics_.sessions_opened},
            {"sessions_open", sessions_.size()},
        };
    }

    json open(json params) {
        const auto target = params.value("target", std::string());
        if (target.empty()) {
            throw detail::bad_input("open requires a target string", "open");
        }
        if (target != descriptor_.id) {
            throw SidecarError::make(
                ErrorKind::Unsupported, "unknown target \"" + target + "\"")
                .with_op("open")
                .with_target(target);
        }

        const json config =
            params.contains("config") ? params.at("config") : json::object();
        const std::string session = "s" + std::to_string(next_session_++);
        const SessionCtx ctx{session, target, options_.pid};

        auto engine_session = engine_.open(ctx, config);
        if (!engine_session) {
            throw SidecarError::make(
                ErrorKind::Internal, "engine.open() returned no session")
                .with_op("open");
        }
        ++metrics_.sessions_opened;

        auto entry = std::make_unique<SessionEntry>();
        entry->id = session;
        entry->target = target;
        entry->session = std::move(engine_session);
        sessions_.emplace(session, std::move(entry));

        json ops = json::array();
        for (const auto& name : descriptor_.op_names()) {
            ops.push_back(name);
        }
        return json{
            {"session", session},
            {"target", target},
            {"worker", 0},
            {"ops", ops},
        };
    }

    json close_session(
        const std::optional<std::string>& session_id,
        const std::string& op) {
        if (!session_id) {
            throw detail::bad_input(
                "op \"" + op + "\" requires a session", op);
        }
        const auto found = sessions_.find(*session_id);
        if (found == sessions_.end()) {
            throw SidecarError::make(
                ErrorKind::BadInput,
                "unknown session \"" + *session_id + "\"")
                .with_op(op);
        }
        auto entry = std::move(found->second);
        sessions_.erase(found);
        entry->session->close();
        return json{{"closed", true}};
    }

    json diag(
        const std::optional<std::string>& session_id,
        const std::string& op) {
        auto& entry = require_session(session_id, op);
        return json{
            {"target", entry.target},
            {"session", entry.id},
            {"mode", "off"},
            {"path", nullptr},
            {"report", entry.session->diagnostics()},
        };
    }

    json target_op(
        const std::string& op,
        const std::optional<std::string>& session_id,
        json params,
        Call& call) {
        auto& entry = require_session(session_id, op);
        if (descriptor_.find_op(op) == nullptr) {
            throw SidecarError::make(
                ErrorKind::Unsupported,
                "op \"" + op + "\" is not declared by target \"" +
                    entry.target + "\"")
                .with_op(op)
                .with_target(entry.target);
        }

        ++metrics_.calls;
        json result = entry.session->call(op, std::move(params), call);

        if (call.cancelled()) {
            throw SidecarError::make(
                ErrorKind::Cancelled,
                "op \"" + op + "\" was cancelled")
                .with_op(op)
                .with_target(entry.target);
        }
        if (call.timed_out()) {
            throw SidecarError::make(
                ErrorKind::Timeout,
                "op \"" + op + "\" exceeded its deadline of " +
                    std::to_string(call.deadline_ms().value_or(0)) + "ms")
                .with_op(op)
                .with_target(entry.target);
        }
        return result;
    }

    SessionEntry& require_session(
        const std::optional<std::string>& session_id,
        const std::string& op) {
        if (!session_id) {
            throw detail::bad_input(
                "op \"" + op + "\" requires a session", op);
        }
        const auto found = sessions_.find(*session_id);
        if (found == sessions_.end()) {
            throw SidecarError::make(
                ErrorKind::BadInput,
                "unknown session \"" + *session_id + "\"")
                .with_op(op);
        }
        return *found->second;
    }

    void respond_result(
        std::uint64_t id,
        json result,
        std::vector<std::uint8_t> bin) {
        sink_.send(
            json{
                {"t", "res"},
                {"v", kProtocol},
                {"id", id},
                {"ok", true},
                {"result", std::move(result)},
            },
            bin);
    }

    void respond_error(
        std::uint64_t id,
        const std::string& op,
        const std::optional<std::string>& target,
        const SidecarError& error) {
        ++metrics_.errors;
        const std::optional<std::string> fallback_op =
            op.empty() ? std::nullopt : std::optional<std::string>(op);
        sink_.send(json{
            {"t", "res"},
            {"v", kProtocol},
            {"id", id},
            {"ok", false},
            {"error", error.to_wire(target, fallback_op)},
        });
    }

    void respond_engine_exception(
        std::uint64_t id,
        const std::string& op,
        const std::optional<std::string>& target,
        const char* type,
        const std::string& message) {
        SidecarError error = SidecarError::make(ErrorKind::Internal, message);
        error.with_op(op);
        if (target) {
            error.with_target(*target);
        }
        error.with_detail(json{
            {"engine_exception",
             json{{"type", type}, {"message", message}}},
        });
        respond_error(id, op, target, error);
    }

    void close_all() {
        std::vector<std::unique_ptr<SessionEntry>> entries;
        entries.reserve(sessions_.size());
        for (auto& item : sessions_) {
            entries.push_back(std::move(item.second));
        }
        sessions_.clear();
        for (auto& entry : entries) {
            try {
                entry->session->close();
            } catch (...) {
            }
        }
    }

    Engine& engine_;
    HostOptions options_;
    Descriptor descriptor_;
    std::string schema_hash_;
    EventSink sink_;
    std::shared_ptr<CancelState> cancel_;
    std::map<std::string, std::unique_ptr<SessionEntry>> sessions_;
    std::uint64_t next_session_ = 1;
    Metrics metrics_;
    bool shutdown_requested_ = false;
};

/// Serves protocol v1 over stdin/stdout until `shutdown` or EOF.
inline void run_stdio(Engine& engine, HostOptions options = {}) {
    Host host(engine, options);
    host.serve();
}

}  // namespace aio_sidecar
