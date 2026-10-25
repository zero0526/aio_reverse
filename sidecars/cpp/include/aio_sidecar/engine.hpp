#pragma once

#include <atomic>
#include <chrono>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <ostream>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "error.hpp"
#include "frame.hpp"

namespace aio_sidecar {

struct SessionCtx {
    std::string session;
    std::string target;
    std::uint32_t pid = 0;
};

inline void to_json(json& out, const SessionCtx& ctx) {
    out = json{{"session", ctx.session}, {"target", ctx.target}, {"pid", ctx.pid}};
}

/// Cancel flag shared with the reader thread. The engine observes it through
/// `Call::check()`; a cancel that arrives before dispatch is replayed by
/// `begin()`.
class CancelState {
public:
    void cancel(std::uint64_t id) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (current_ == id) {
            cancelled_ = true;
        } else {
            cancelled_ids_.insert(id);
        }
    }

    bool begin(std::uint64_t id) {
        std::lock_guard<std::mutex> lock(mutex_);
        current_ = id;
        cancelled_ = cancelled_ids_.erase(id) > 0;
        return cancelled_;
    }

    bool is_cancelled(std::uint64_t id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        return current_ == id && cancelled_;
    }

    void finish(std::uint64_t id) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (current_ == id) {
            current_.reset();
            cancelled_ = false;
        }
    }

private:
    mutable std::mutex mutex_;
    std::optional<std::uint64_t> current_;
    bool cancelled_ = false;
    std::set<std::uint64_t> cancelled_ids_;
};

/// Serializes frames written by the host and by engine events.
class EventSink {
public:
    explicit EventSink(std::ostream& out) : state_(std::make_shared<State>(&out)) {}

    void send(const json& envelope, const std::vector<std::uint8_t>& bin = {}) const {
        std::lock_guard<std::mutex> lock(state_->mutex);
        write_frame(*state_->out, envelope, bin);
    }

    void send_event(
        const json& envelope,
        const std::vector<std::uint8_t>& bin = {}) const {
        state_->events.fetch_add(1, std::memory_order_relaxed);
        send(envelope, bin);
    }

    std::uint64_t event_count() const {
        return state_->events.load(std::memory_order_relaxed);
    }

private:
    struct State {
        explicit State(std::ostream* stream) : out(stream) {}

        std::ostream* out;
        mutable std::mutex mutex;
        std::atomic<std::uint64_t> events{0};
    };

    std::shared_ptr<State> state_;
};

/// Per-call handle passed to `Session::call`.
class Call {
public:
    Call(
        std::uint64_t id,
        std::string op,
        std::string target,
        const std::vector<std::uint8_t>& input,
        std::optional<std::chrono::steady_clock::time_point> deadline,
        std::optional<std::uint64_t> deadline_ms,
        std::shared_ptr<CancelState> cancel,
        EventSink sink)
        : id_(id),
          op_(std::move(op)),
          target_(std::move(target)),
          input_(input),
          deadline_(deadline),
          deadline_ms_(deadline_ms),
          cancel_(std::move(cancel)),
          sink_(std::move(sink)) {}

    /// Throws `cancelled` / `timeout`; call between engine steps.
    void check() const {
        if (cancelled()) {
            throw located(SidecarError::make(
                ErrorKind::Cancelled, "op \"" + op_ + "\" was cancelled"));
        }
        if (timed_out()) {
            throw timeout_error();
        }
    }

    bool cancelled() const { return cancel_->is_cancelled(id_); }

    bool timed_out() const {
        return deadline_.has_value() &&
               std::chrono::steady_clock::now() >= *deadline_;
    }

    std::optional<std::uint64_t> deadline_ms() const { return deadline_ms_; }

    /// Emits one event envelope before the response.
    void emit(const std::string& name, json data = nullptr) {
        if (name.empty()) {
            throw SidecarError::make(
                ErrorKind::Internal, "event name must be a non-empty string");
        }
        json envelope{
            {"t", "evt"},
            {"v", 1},
            {"id", id_},
            {"event", name},
            {"data", std::move(data)},
        };
        sink_.send_event(envelope);
    }

    void log(const std::string& level, const std::string& text) {
        emit("log", json{{"level", level}, {"text", text}});
    }

    /// Raw binary frame part received with the request.
    const std::vector<std::uint8_t>& input() const { return input_; }

    /// Sets the binary frame part of the response.
    void set_output(std::vector<std::uint8_t> bytes) {
        output_ = std::move(bytes);
    }

    std::vector<std::uint8_t> take_output() { return std::move(output_); }

private:
    SidecarError timeout_error() const {
        return located(SidecarError::make(
            ErrorKind::Timeout,
            "op \"" + op_ + "\" exceeded its deadline of " +
                std::to_string(deadline_ms_.value_or(0)) + "ms"));
    }

    SidecarError located(SidecarError error) const {
        error.with_op(op_);
        if (!target_.empty()) {
            error.with_target(target_);
        }
        return error;
    }

    std::uint64_t id_;
    std::string op_;
    std::string target_;
    std::vector<std::uint8_t> input_;
    std::vector<std::uint8_t> output_;
    std::optional<std::chrono::steady_clock::time_point> deadline_;
    std::optional<std::uint64_t> deadline_ms_;
    std::shared_ptr<CancelState> cancel_;
    EventSink sink_;
};

/// Per-session engine state. Only `call` is required.
class Session {
public:
    virtual ~Session() = default;

    virtual json call(const std::string& op, json params, Call& call) = 0;

    virtual json health() { return json{{"ok", true}}; }

    virtual void warmup(Call& /*call*/) {}

    virtual json diagnostics() { return nullptr; }

    virtual void close() {}
};

/// One engine per process. `describe` returns the v1 descriptor subset;
/// `open` builds the per-session state.
class Engine {
public:
    virtual ~Engine() = default;

    virtual json describe() const = 0;

    virtual std::unique_ptr<Session> open(
        const SessionCtx& ctx,
        json config) = 0;
};

}  // namespace aio_sidecar
