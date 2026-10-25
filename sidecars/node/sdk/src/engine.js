import { ErrorKind, WreError } from "./toolkit.js";

/**
 * Engine contract implemented by each sidecar client.
 *
 * @typedef {Object} EngineContext
 * @property {string} session  Host-assigned session id.
 * @property {string} target   Target id from the descriptor.
 * @property {number} pid      Host process id.
 *
 * @typedef {Object} Engine
 * @property {() => Object} describe  Returns the descriptor (v1 subset).
 * @property {(config: any, ctx: EngineContext) => any} [open]
 *   Builds per-session state. May be async.
 * @property {(state: any, op: string, params: Object, call: Object) => any} call
 *   Handles a target op. May be async. `call` is a {@link import("./host.js").Call}.
 * @property {(state: any) => any} [health]
 * @property {(state: any, call: Object) => any} [warmup]
 * @property {(state: any) => any} [diagnostics]
 * @property {(state: any) => void} [close]
 */

const KNOWN_KINDS = new Set(Object.values(ErrorKind));

export const RETRYABLE_KINDS = new Set([
  ErrorKind.Blocked,
  ErrorKind.Timeout,
  ErrorKind.Resource,
]);

/**
 * The error type engines should throw for expected failures. It is a
 * `WreError`, so the host serializes `kind`, `retryable`, `detail`, `target`
 * and `op` onto the wire; Python then raises the matching typed exception and
 * fires an alert before doing so.
 */
export class EngineError extends WreError {
  constructor(kind, message, extra = {}) {
    if (!KNOWN_KINDS.has(kind)) {
      throw new TypeError(`unknown sidecar error kind: ${String(kind)}`);
    }
    const retryable = extra.retryable === undefined ? RETRYABLE_KINDS.has(kind) : extra.retryable;
    super(kind, message, { ...extra, retryable });
    this.name = "EngineError";
  }
}
