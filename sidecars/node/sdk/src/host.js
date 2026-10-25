import { encodeFrame, FrameDecoder } from "./frames.js";
import { ErrorKind, WreError } from "./toolkit.js";
import { EngineError } from "./engine.js";
import { schemaHash } from "./hash.js";

const PROTOCOL = 1;
const BUNDLE = "aio";
const HOST_VERSION = "0.1.0";

const BASE_OPS = new Set([
  "hello",
  "describe",
  "targets",
  "metrics",
  "open",
  "close",
  "health",
  "warmup",
  "shutdown",
  "diag",
]);

/**
 * The handle passed to `Engine.call`. Engines use it to observe cancellation,
 * emit events, read the binary frame part and produce a binary result.
 */
export class Call {
  constructor(host, state, input) {
    this._host = host;
    this._state = state;
    this._input = input;
    this._output = Buffer.alloc(0);
  }

  /** Aborts when the consumer cancels or the deadline fires. */
  get signal() {
    return this._state.controller.signal;
  }

  /** Effective deadline in milliseconds, or `undefined` when unbounded. */
  get deadlineMs() {
    return this._state.deadlineMs;
  }

  get cancelled() {
    return this._state.cancelled;
  }

  /** Throws `cancelled` or `timeout`; call this between steps. */
  check() {
    const state = this._state;
    if (state.cancelled) {
      throw new EngineError(ErrorKind.Cancelled, `op "${state.op}" was cancelled`, {
        op: state.op,
        target: state.target,
      });
    }
    if (
      state.timedOut ||
      (state.deadlineAt !== undefined && Date.now() >= state.deadlineAt)
    ) {
      throw new EngineError(
        ErrorKind.Timeout,
        `op "${state.op}" exceeded its deadline of ${state.deadlineMs}ms`,
        { op: state.op, target: state.target },
      );
    }
  }

  emit(name, data) {
    if (typeof name !== "string" || name.length === 0) {
      throw new EngineError(ErrorKind.BadInput, "event name must be a non-empty string", {
        op: this._state.op,
      });
    }
    if (this._state.settled) {
      return;
    }
    this._host._sendEvent(this._state.id, name, data === undefined ? null : data);
  }

  log(level, text) {
    this.emit("log", { level: String(level), text: String(text) });
  }

  /** Raw binary frame part received with the request. */
  input() {
    return this._input;
  }

  /** Sets the binary frame part of the response. */
  setOutput(value) {
    this._output = Buffer.from(value);
  }

  get output() {
    return this._output;
  }
}

/**
 * Protocol v1 host: routes base ops and target ops to one engine instance.
 * Requests are processed serially; `cancel` is handled by the reader as soon
 * as the frame arrives and aborts the in-flight call.
 */
export class Host {
  constructor(engine, options = {}) {
    if (!engine || typeof engine.describe !== "function" || typeof engine.call !== "function") {
      throw new TypeError(
        "engine must implement describe() and call(state, op, params, call)",
      );
    }
    const descriptor = engine.describe();
    validateDescriptor(descriptor);

    this._engine = engine;
    this._descriptor = descriptor;
    this._opNames = new Set(descriptor.ops.map((op) => op.name));
    this._opsByName = new Map(descriptor.ops.map((op) => [op.name, op]));
    this._schemaHash = schemaHash(descriptor);
    this._sessions = new Map();
    this._active = new Map();
    this._nextSession = 1;
    this._queue = Promise.resolve();
    this._metrics = {
      requests: 0,
      calls: 0,
      errors: 0,
      events: 0,
      sessions_opened: 0,
    };
    this._finishing = false;
    this._write =
      options.write ?? ((data, callback) => process.stdout.write(data, callback));
    this._exit = options.exit ?? ((code) => process.exit(code));
    this._pid = options.pid ?? process.pid;
  }

  get descriptor() {
    return this._descriptor;
  }

  get schemaHash() {
    return this._schemaHash;
  }

  get metrics() {
    return { ...this._metrics, sessions_open: this._sessions.size };
  }

  /** Wires stdin/stdout and starts reading frames. */
  run() {
    const decoder = new FrameDecoder();
    process.stdout.on("error", () => this._finish());
    process.stdin.on("data", (chunk) => {
      let frames;
      try {
        frames = decoder.push(chunk);
      } catch (err) {
        this._fatal(err);
        return;
      }
      for (const frame of frames) {
        this.accept(frame.json, frame.bin);
      }
    });
    process.stdin.on("end", () => this._finish());
    process.stdin.resume();
    return this;
  }

  /** Handles one decoded envelope; exposed for embedding and tests. */
  accept(envelope, bin) {
    if (this._finishing) {
      return;
    }
    if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
      this._fatal(new Error("envelope must be a JSON object"));
      return;
    }
    if (envelope.t === "cancel") {
      this._cancel(envelope.id);
      return;
    }
    if (envelope.t !== "req") {
      this._fatal(new Error(`unexpected envelope type "${String(envelope.t)}"`));
      return;
    }

    const id = envelope.id;
    if (!Number.isInteger(id)) {
      this._fatal(new Error("request id must be an integer"));
      return;
    }

    const state = {
      id,
      op: envelope.op,
      session: envelope.session,
      params: envelope.params === undefined ? {} : envelope.params,
      bin: bin ?? Buffer.alloc(0),
      controller: new AbortController(),
      cancelled: false,
      timedOut: false,
      settled: false,
      deadlineMs: undefined,
      deadlineAt: undefined,
      timer: undefined,
      target: undefined,
    };

    if (this._active.has(id)) {
      this._respondError(
        state,
        new EngineError(ErrorKind.Protocol, `duplicate request id ${id}`, {
          op: typeof envelope.op === "string" ? envelope.op : undefined,
        }),
      );
      return;
    }

    this._metrics.requests += 1;

    if (envelope.v !== PROTOCOL) {
      this._respondError(
        state,
        new EngineError(
          ErrorKind.Protocol,
          `unsupported protocol version ${String(envelope.v)}`,
          { op: typeof envelope.op === "string" ? envelope.op : undefined },
        ),
      );
      return;
    }
    if (typeof envelope.op !== "string" || envelope.op.length === 0) {
      this._respondError(state, new EngineError(ErrorKind.BadInput, "op must be a non-empty string"));
      return;
    }
    if (
      envelope.session !== undefined &&
      (typeof envelope.session !== "string" || envelope.session.length === 0)
    ) {
      this._respondError(
        state,
        new EngineError(ErrorKind.BadInput, "session must be a non-empty string", {
          op: envelope.op,
        }),
      );
      return;
    }
    if (
      envelope.params !== undefined &&
      (envelope.params === null ||
        typeof envelope.params !== "object" ||
        Array.isArray(envelope.params))
    ) {
      this._respondError(
        state,
        new EngineError(ErrorKind.BadInput, "params must be a JSON object", {
          op: envelope.op,
        }),
      );
      return;
    }
    if (
      envelope.deadline_ms !== undefined &&
      (typeof envelope.deadline_ms !== "number" ||
        !Number.isFinite(envelope.deadline_ms) ||
        envelope.deadline_ms < 0)
    ) {
      this._respondError(
        state,
        new EngineError(ErrorKind.BadInput, "deadline_ms must be a non-negative number", {
          op: envelope.op,
        }),
      );
      return;
    }

    if (typeof state.session === "string") {
      const known = this._sessions.get(state.session);
      if (known) {
        state.target = known.target;
      }
    }

    this._active.set(id, state);
    this._armDeadline(state, envelope.deadline_ms);
    this._queue = this._queue
      .then(() => this._dispatch(state))
      .catch((err) => this._respondError(state, err));
  }

  _armDeadline(state, requested) {
    let ms = requested;
    if (ms === undefined && !BASE_OPS.has(state.op)) {
      const declared = this._opsByName.get(state.op);
      if (declared && typeof declared.deadline_ms === "number" && declared.deadline_ms > 0) {
        ms = declared.deadline_ms;
      }
    }
    if (ms === undefined || ms <= 0) {
      return;
    }
    state.deadlineMs = ms;
    state.deadlineAt = Date.now() + ms;
    state.timer = setTimeout(() => {
      state.timedOut = true;
      state.controller.abort();
      this._respondError(
        state,
        new EngineError(
          ErrorKind.Timeout,
          `op "${state.op}" exceeded its deadline of ${ms}ms`,
          { op: state.op, target: state.target },
        ),
      );
    }, ms);
    if (typeof state.timer.unref === "function") {
      state.timer.unref();
    }
  }

  _cancel(id) {
    const state = this._active.get(id);
    if (!state || state.settled) {
      return;
    }
    state.cancelled = true;
    state.controller.abort();
    this._respondError(
      state,
      new EngineError(ErrorKind.Cancelled, `op "${state.op}" was cancelled`, {
        op: state.op,
        target: state.target,
      }),
    );
  }

  async _dispatch(state) {
    if (state.settled) {
      return;
    }
    try {
      if (BASE_OPS.has(state.op)) {
        await this._handleBase(state);
        return;
      }
      await this._handleTargetOp(state);
    } catch (err) {
      this._respondError(state, err);
    } finally {
      if (state.timer) {
        clearTimeout(state.timer);
        state.timer = undefined;
      }
      this._active.delete(state.id);
    }
  }

  async _handleBase(state) {
    switch (state.op) {
      case "hello":
        return this._respondResult(state, this._hello());
      case "describe":
        return this._respondResult(state, this._describe());
      case "targets":
        return this._respondResult(state, [this._descriptor.id]);
      case "metrics":
        return this._respondResult(state, this.metrics);
      case "open":
        return this._open(state);
      case "close":
        return this._closeSession(state);
      case "health":
        return this._sessionOp(state, "health");
      case "warmup":
        return this._sessionOp(state, "warmup");
      case "diag":
        return this._diag(state);
      case "shutdown":
        return this._shutdown(state);
      default:
        throw new EngineError(ErrorKind.Unsupported, `unknown base op "${state.op}"`, {
          op: state.op,
        });
    }
  }

  _hello() {
    return {
      protocol: PROTOCOL,
      bundle: BUNDLE,
      binary_version: HOST_VERSION,
      toolkit_version: HOST_VERSION,
      schema_hash: this._schemaHash,
      targets: [this._descriptor.id],
      workers: 1,
      pid: this._pid,
    };
  }

  _describe() {
    return {
      protocol: PROTOCOL,
      bundle: BUNDLE,
      toolkit_version: HOST_VERSION,
      binary_version: HOST_VERSION,
      clients: [this._descriptor],
    };
  }

  async _open(state) {
    const requested = state.params.target;
    if (typeof requested !== "string" || requested.length === 0) {
      throw new EngineError(ErrorKind.BadInput, "open requires a target string", {
        op: "open",
      });
    }
    if (requested !== this._descriptor.id) {
      throw new EngineError(ErrorKind.Unsupported, `unknown target "${requested}"`, {
        op: "open",
        target: requested,
      });
    }

    const config = state.params.config === undefined ? {} : state.params.config;
    const sid = `s${this._nextSession++}`;
    state.target = requested;

    let sessionState;
    if (typeof this._engine.open === "function") {
      sessionState = await this._engine.open(config, {
        session: sid,
        target: requested,
        pid: this._pid,
      });
    }
    this._sessions.set(sid, { id: sid, target: requested, config, state: sessionState });
    this._metrics.sessions_opened += 1;
    this._respondResult(state, {
      session: sid,
      target: requested,
      worker: 0,
      ops: this._descriptor.ops.map((op) => op.name),
    });
  }

  async _handleTargetOp(state) {
    const session = this._requireSession(state);
    if (!this._opNames.has(state.op)) {
      throw new EngineError(
        ErrorKind.Unsupported,
        `op "${state.op}" is not declared by target "${session.target}"`,
        { op: state.op, target: session.target },
      );
    }
    if (state.settled) {
      return;
    }
    this._metrics.calls += 1;
    const call = new Call(this, state, state.bin);
    const result = await this._engine.call(session.state, state.op, state.params, call);

    if (state.cancelled) {
      throw new EngineError(ErrorKind.Cancelled, `op "${state.op}" was cancelled`, {
        op: state.op,
        target: session.target,
      });
    }
    if (
      state.timedOut ||
      (state.deadlineAt !== undefined && Date.now() >= state.deadlineAt)
    ) {
      throw new EngineError(
        ErrorKind.Timeout,
        `op "${state.op}" exceeded its deadline of ${state.deadlineMs}ms`,
        { op: state.op, target: session.target },
      );
    }
    this._respondResult(state, result, call.output);
  }

  async _closeSession(state) {
    const session = this._requireSession(state);
    if (typeof this._engine.close === "function") {
      await this._engine.close(session.state);
    }
    this._sessions.delete(session.id);
    this._respondResult(state, { closed: true });
  }

  async _sessionOp(state, op) {
    const session = this._requireSession(state);
    let result;
    if (op === "health") {
      result =
        typeof this._engine.health === "function"
          ? await this._engine.health(session.state)
          : undefined;
      if (result === undefined) {
        result = { ok: true, target: session.target };
      }
    } else {
      const call = new Call(this, state, state.bin);
      result =
        typeof this._engine.warmup === "function"
          ? await this._engine.warmup(session.state, call)
          : undefined;
      if (result === undefined) {
        result = { warm: true };
      }
      this._respondResult(state, result, call.output);
      return;
    }
    this._respondResult(state, result);
  }

  _diag(state) {
    const session = this._requireSession(state);
    const report =
      typeof this._engine.diagnostics === "function"
        ? this._engine.diagnostics(session.state)
        : null;
    this._respondResult(state, {
      target: session.target,
      session: session.id,
      mode: "off",
      path: null,
      report: report === undefined ? null : report,
    });
  }

  async _shutdown(state) {
    const sessions = Array.from(this._sessions.values());
    this._sessions.clear();
    for (const session of sessions) {
      if (typeof this._engine.close === "function") {
        try {
          await this._engine.close(session.state);
        } catch {
          // Shutdown is best effort; the response is already committed below.
        }
      }
    }
    this._respondResult(state, { stopping: true }, Buffer.alloc(0), () =>
      this._finish(),
    );
  }

  _requireSession(state) {
    if (typeof state.session !== "string" || state.session.length === 0) {
      throw new EngineError(ErrorKind.BadInput, `op "${state.op}" requires a session`, {
        op: state.op,
      });
    }
    const session = this._sessions.get(state.session);
    if (!session) {
      throw new EngineError(ErrorKind.BadInput, `unknown session "${state.session}"`, {
        op: state.op,
      });
    }
    state.target = session.target;
    return session;
  }

  _sendEvent(id, event, data) {
    this._metrics.events += 1;
    this._send({ t: "evt", v: PROTOCOL, id, event, data });
  }

  _respondResult(state, result, bin = Buffer.alloc(0), after) {
    if (state.settled) {
      return;
    }
    state.settled = true;
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = undefined;
    }
    this._send(
      {
        t: "res",
        v: PROTOCOL,
        id: state.id,
        ok: true,
        result: result === undefined ? null : result,
      },
      bin,
      after,
    );
  }

  _respondError(state, err) {
    if (!state || state.settled) {
      return;
    }
    state.settled = true;
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = undefined;
    }
    this._metrics.errors += 1;
    const target = err instanceof WreError ? err.target ?? state.target : state.target;
    const op = err instanceof WreError ? err.op ?? state.op : state.op;
    this._send({
      t: "res",
      v: PROTOCOL,
      id: state.id,
      ok: false,
      error: wireError(err, target, op),
    });
  }

  _send(envelope, bin, after) {
    let data;
    try {
      data = encodeFrame(envelope, bin ?? Buffer.alloc(0));
    } catch (err) {
      this._fatal(err);
      return;
    }
    try {
      this._write(data, after);
    } catch (err) {
      this._fatal(err);
    }
  }

  _finish() {
    if (this._finishing) {
      return;
    }
    this._finishing = true;
    const sessions = Array.from(this._sessions.values());
    this._sessions.clear();
    for (const session of sessions) {
      if (typeof this._engine.close === "function") {
        try {
          const pending = this._engine.close(session.state);
          if (pending && typeof pending.then === "function") {
            pending.catch(() => {});
          }
        } catch {
          // Best effort on disconnect.
        }
      }
    }
    this._exit(0);
  }

  _fatal(err) {
    if (this._finishing) {
      return;
    }
    this._finishing = true;
    try {
      const detail = err && err.stack ? err.stack : String(err);
      process.stderr.write(`aio-sidecar-host fatal: ${detail}\n`);
    } catch {
      // stderr is advisory.
    }
    this._exit(1);
  }
}

function validateDescriptor(descriptor) {
  if (!descriptor || typeof descriptor !== "object" || Array.isArray(descriptor)) {
    throw new TypeError("engine.describe() must return a descriptor object");
  }
  if (typeof descriptor.id !== "string" || descriptor.id.length === 0) {
    throw new TypeError("engine descriptor requires a non-empty string id");
  }
  if (!Array.isArray(descriptor.ops)) {
    throw new TypeError(`engine "${descriptor.id}" descriptor requires an ops array`);
  }
  const seen = new Set();
  for (const op of descriptor.ops) {
    if (!op || typeof op.name !== "string" || op.name.length === 0) {
      throw new TypeError(`engine "${descriptor.id}" has an op without a name`);
    }
    if (seen.has(op.name)) {
      throw new TypeError(`engine "${descriptor.id}" declares op "${op.name}" twice`);
    }
    seen.add(op.name);
  }
}

function wireError(err, target, op) {
  if (err instanceof WreError) {
    const payload = {
      kind: err.kind,
      message: err.message,
      retryable: err.retryable,
    };
    const effectiveTarget = err.target ?? target;
    if (effectiveTarget !== undefined) {
      payload.target = effectiveTarget;
    }
    const effectiveOp = err.op ?? op;
    if (effectiveOp !== undefined) {
      payload.op = effectiveOp;
    }
    if (err.detail !== undefined) {
      payload.detail = err.detail;
    }
    return payload;
  }

  const type = err && typeof err.name === "string" ? err.name : typeof err;
  const message = err && typeof err.message === "string" ? err.message : String(err);
  const engineException = { type, message };
  if (err && typeof err.stack === "string") {
    engineException.stack = err.stack;
  }
  const payload = {
    kind: ErrorKind.Internal,
    message,
    retryable: false,
    detail: { engine_exception: engineException },
  };
  if (target !== undefined) {
    payload.target = target;
  }
  if (op !== undefined) {
    payload.op = op;
  }
  return payload;
}

export function createHost(engine, options = {}) {
  return new Host(engine, options);
}

export function runStdio(engine, options = {}) {
  return createHost(engine, options).run();
}
