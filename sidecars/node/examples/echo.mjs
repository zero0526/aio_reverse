import { readFileSync } from "node:fs";

import { runStdio } from "../sdk/src/index.js";
import { EngineError } from "../sdk/src/engine.js";
import { ErrorKind } from "../sdk/src/toolkit.js";

const descriptor = JSON.parse(
  readFileSync(
    new URL("../../conformance/fixtures/echo.descriptor.json", import.meta.url),
    "utf8",
  ),
);

function badInput(message, op) {
  return new EngineError(ErrorKind.BadInput, message, { op });
}

const engine = {
  describe() {
    return descriptor;
  },

  open(config, ctx) {
    return { config, ctx, calls: 0, events: 0 };
  },

  async call(state, op, params, call) {
    state.calls += 1;

    switch (op) {
      case "echo":
        return {
          value: params.value === undefined ? null : params.value,
          config: state.config,
        };

      case "execute": {
        const entrypoint = params.entrypoint;
        if (typeof entrypoint !== "string" || entrypoint.length === 0) {
          throw badInput("execute requires a non-empty entrypoint", op);
        }
        const sourceKind = params.source_kind;
        if (sourceKind !== "text" && sourceKind !== "binary") {
          throw badInput('source_kind must be "text" or "binary"', op);
        }
        const source = params.source === undefined ? null : params.source;
        if (sourceKind === "text" && typeof source !== "string") {
          throw badInput("source must be a string for text sources", op);
        }
        if (sourceKind === "binary" && source !== null) {
          throw badInput("source must be null for binary sources", op);
        }
        const args = params.arguments === undefined ? [] : params.arguments;
        if (!Array.isArray(args)) {
          throw badInput("arguments must be an array", op);
        }
        const environment =
          params.environment === undefined ? null : params.environment;
        const memoryLimit =
          params.memory_limit_mb === undefined ? 64 : params.memory_limit_mb;
        if (
          typeof memoryLimit !== "number" ||
          !Number.isFinite(memoryLimit) ||
          memoryLimit <= 0
        ) {
          throw badInput("memory_limit_mb must be a positive number", op);
        }
        const input = call.input();
        return {
          result: {
            entrypoint,
            arguments: args,
            environment,
            source_kind: sourceKind,
            source,
            memory_limit_mb: memoryLimit,
          },
          source_bytes:
            sourceKind === "binary" ? input.length : Buffer.byteLength(source, "utf8"),
        };
      }

      case "emit": {
        const name = params.event === undefined ? "progress" : params.event;
        if (name !== "progress" && name !== "log") {
          throw badInput("event must be progress or log", op);
        }
        const data = params.data === undefined ? { note: "emitted" } : params.data;
        call.emit(name, data);
        state.events += 1;
        return { emitted: name, data };
      }

      case "bytes": {
        const input = call.input();
        call.setOutput(input);
        return { size: input.length, hex: input.toString("hex") };
      }

      case "fail": {
        const kind = params.kind;
        if (!Object.values(ErrorKind).includes(kind)) {
          throw badInput(`unknown error kind "${String(kind)}"`, op);
        }
        throw new EngineError(
          kind,
          typeof params.message === "string" ? params.message : `echo ${kind}`,
          {
            op,
            detail: params.detail,
            retryable:
              typeof params.retryable === "boolean" ? params.retryable : undefined,
          },
        );
      }

      case "throw": {
        const error = new Error(
          typeof params.message === "string"
            ? params.message
            : "echo engine exploded",
        );
        error.name = "EchoEngineError";
        throw error;
      }

      case "sleep": {
        const ms = params.ms === undefined ? 1000 : params.ms;
        if (typeof ms !== "number" || !Number.isFinite(ms) || ms < 0) {
          throw badInput("ms must be a non-negative number", op);
        }
        const started = Date.now();
        for (;;) {
          call.check();
          const remaining = ms - (Date.now() - started);
          if (remaining <= 0) {
            break;
          }
          await new Promise((resolve) =>
            setTimeout(resolve, Math.min(10, remaining)),
          );
        }
        call.check();
        return { slept_ms: Date.now() - started };
      }

      case "stats":
        return { calls: state.calls, events: state.events, config: state.config };

      default:
        throw new EngineError(ErrorKind.Unsupported, `op "${op}" is not implemented`, {
          op,
        });
    }
  },

  health(state) {
    return {
      ok: true,
      target: descriptor.id,
      detail: { calls: state.calls, events: state.events },
    };
  },

  warmup(_state, call) {
    call.log("info", "echo engine warmed up");
    return { warm: true };
  },

  diagnostics(state) {
    return {
      calls: state.calls,
      events: state.events,
      config: state.config,
      context: state.ctx,
    };
  },

  close() {},
};

runStdio(engine);
