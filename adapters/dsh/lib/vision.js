/**
 * vision.js — pure, testable logic for the vision-translation dsh node adapter.
 *
 * This module never re-implements core logic (prompts, JSON parsing, bbox
 * math, VLM calls) — see CONTRIBUTING.md and PROTOCOL.md. It is thin glue
 * between a dsh tool call and the Python CLI (`cli.py`, the spawn boundary).
 *
 * Responsibilities (all unit-tested in tests/vision.test.js):
 *   - runCli():             spawn the CLI with a stdin b64/path envelope, parse
 *                           its stdout JSON, branch on `status` not exit code.
 *   - classifyResult():     the PROTOCOL v1 three-state mapping.
 *   - envelopeFromImage():  turn a dsh string arg (attachment ref or local
 *                           path) into a PROTOCOL v1 stdin envelope.
 *   - resolveCli():         the documented discovery order for cli.py.
 *
 * PROTOCOL v1 normative spec: ../../PROTOCOL.md
 *   status: ok | unavailable (fail-closed, exit 0) | error (exit 1/2)
 *   stdout = exactly one JSON object, nothing else (logs -> stderr)
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/** MediaType -> file extension used by the CLI b64 envelope (`ext`). */
export const MEDIA_EXT = {
  "image/png": ".png",
  "image/jpeg": ".jpg",
  "image/webp": ".webp",
  "image/gif": ".gif",
};

/** Match a dsh attachment ref: `sha256:<hex>` or `attachment:sha256:<hex>`. */
export const ATTACHMENT_REF = /^(?:attachment:)?sha256:[0-9a-f]{64}$/i;

/** stderr tail cap for error messages (B9). */
const STDERR_CAP = 500;

/** The CLI/core's own internal HTTP timeout, kept as a sanity reference. */
export const CLI_INTERNAL_TIMEOUT_MS = 60_000;

/** Absolute path of this source file's own directory (ESM). */
const LIB_DIR = dirname(fileURLToPath(import.meta.url));
/** Package root (…/adapters/dsh) — one level above lib/. */
export const PACKAGE_ROOT = resolve(LIB_DIR, "..");

/**
 * Classify a parsed CLI response payload into one of the three PROTOCOL v1
 * states (B5/B6/B7/B8). Never throws on a well-formed payload — it maps every
 * `status` the CLI can emit.
 *
 * @param payload parsed `JSON.parse(stdout)` result from the CLI.
 * @returns one of:
 *   { kind: 'ok',          text }                  (B5  — <vision-context>)
 *   { kind: 'unavailable', text, reason, message } (B6  — fail-closed)
 *   { kind: 'error',       code, message }         (B7  — caller surfaces as throw)
 * @throws on a structurally invalid payload (no JSON object / no `status`).
 */
export function classifyResult(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("vision CLI returned a non-object payload");
  }
  const status = payload.status;
  if (status === "ok") {
    if (typeof payload.context !== "string") {
      throw new Error("vision CLI: ok response missing string `context`");
    }
    return { kind: "ok", text: payload.context };
  }
  if (status === "unavailable") {
    const reason = payload.unavailable?.reason ?? "unknown";
    const message =
      typeof payload.unavailable?.message === "string"
        ? payload.unavailable.message
        : "vision is not available.";
    // B6 wording mirrors the MCP server (`vision unavailable (reason: …)`).
    return {
      kind: "unavailable",
      reason,
      message,
      text: `vision unavailable (reason: ${reason}): ${message}\nDo not guess or fabricate the image content.`,
    };
  }
  if (status === "error") {
    const code = payload.error?.code ?? "internal";
    const message =
      typeof payload.error?.message === "string"
        ? payload.error.message
        : "vision CLI reported an error.";
    return { kind: "error", code, message };
  }
  throw new Error(`vision CLI returned unknown status: ${JSON.stringify(status)}`);
}

/** A concise, user-actionable error for CLI discovery failures (B11). */
export class CliMissingError extends Error {
  constructor(bundledCliPath) {
    super(
      [
        "vision-translation: could not locate the Python CLI (cli.py).",
        "The npm package should bundle it at:",
        `  ${bundledCliPath}`,
        "If that file is missing, reinstall `vision-translation-dsh` (or provide the CLI explicitly):",
        "  - plugin config  `cliPath` (absolute path to cli.py)",
        "  - env            `VISION_TRANSLATION_CLI` (absolute path to cli.py)",
        "and ensure `pythonBin` (default \"python3\") can run it.",
      ].join("\n"),
    );
    this.name = "CliMissingError";
  }
}

/** Wraps an aborted (tool-timeout / cancellation) CLI run. */
export class CliAbortedError extends Error {
  constructor() {
    super("vision-translation: CLI call aborted (timeout or cancellation).");
    this.name = "CliAbortedError";
  }
}

/** Wraps a CLI that exited without a single-valid-JSON stdout payload (B9). */
export class CliOutputError extends Error {
  constructor(detail) {
    super(detail);
    this.name = "CliOutputError";
  }
}

/**
 * Resolve the python binary + cli.py path using the documented discovery order
 * (config `cliPath`/`pythonBin` → env `VISION_TRANSLATION_CLI` →
 * bundled `python/cli.py` inside the installed npm package →
 * package-relative `../../cli.py` for in-repo development + `python3`).
 * Throws CliMissingError (B11) when nothing resolves.
 *
 * @param config  plugin config ({ cliPath, pythonBin }).
 * @param envOverride optional injected env (default process.env; test seam).
 * @param rootOverride optional package-root override (default PACKAGE_ROOT;
 *        test seam) used to compute the bundled and package-relative fallbacks.
 * @returns {{ pythonBin: string, cliPath: string, source: string }}
 * @throws {CliMissingError} when neither the bundled CLI nor the package-relative
 *         fallback exists on disk (B11).
 */
export function resolveCli(config, envOverride = process.env, rootOverride = PACKAGE_ROOT) {
  const cfgCli = config?.cliPath;
  const cfgPython = config?.pythonBin;
  const envCli = envOverride.VISION_TRANSLATION_CLI;
  const pythonBin = cfgPython || "python3";

  if (typeof cfgCli === "string" && cfgCli.trim() !== "") {
    return { pythonBin, cliPath: cfgCli, source: "config.cliPath" };
  }
  if (typeof envCli === "string" && envCli.trim() !== "") {
    return { pythonBin, cliPath: envCli, source: "env.VISION_TRANSLATION_CLI" };
  }

  // 3. Bundled CLI: in the npm install layout this is
  //    `node_modules/vision-translation-dsh/python/cli.py` (spec D1). It is
  //    build output created by `prepack` and shipped via the `files` whitelist.
  const bundledCli = resolve(rootOverride, "python", "cli.py");
  if (existsSync(bundledCli)) {
    return { pythonBin, cliPath: bundledCli, source: "package python/cli.py" };
  }

  // 4. In-repo development fallback: from the package root
  //    (`adapters/dsh`), `../../cli.py` reaches the repository-root cli.py.
  //    When the package is installed standalone (no repo around it), this
  //    path won't exist — fail with the actionable CliMissingError instead of
  //    letting the spawn produce a cryptic "can't open file" (B11).
  const fallback = resolve(rootOverride, "../../", "cli.py");
  if (existsSync(fallback)) {
    return { pythonBin, cliPath: fallback, source: "package-relative ../../cli.py" };
  }
  throw new CliMissingError(bundledCli);
}

/**
 * Turn a dsh string `image` argument (attachment ref or local path) into a
 * PROTOCOL v1 stdin envelope. This is where dsh host integration happens:
 * Web-UI uploads are `sha256:<hex>` attachment refs, not filesystem paths, so
 * they are resolved through `attachmentReader` back to bytes and shipped to
 * the CLI as a b64 envelope — no shared filesystem required.
 *
 * @param imageArg the model-supplied `image` string.
 * @param attachmentReader async `(ref) => Promise<{ data: Uint8Array; mediaType?: string }>`
 *        that resolves a dsh attachment reference to bytes (and optionally its
 *        media type). Injected by the plugin from `ctx.attachments.readImage`.
 * @param options { question?, model?, max_objects? } forwarded to the envelope.
 * @returns the PROTOCOL v1 envelope object.
 * @throws {Error} when the attachment ref cannot be resolved (B4) or is
 *         invalid/bad media type (matches CLI-b64 pattern).
 */
export async function envelopeFromImage(
  imageArg,
  attachmentReader,
  { question = "", model = "", max_objects } = {},
) {
  const raw = String(imageArg ?? "").trim();
  if (!raw) {
    throw new Error("vision-translate: empty `image` argument.");
  }

  const envelope = {
    protocol: 1,
    image: null,
    question,
    options: {},
  };

  // B13: empty model => let the CLI use its default chain; never forward "".
  if (model) envelope.options.model = model;
  // B12: clamp max_objects to 1..16 (matches CLI/MCP).
  if (max_objects !== undefined && max_objects !== null) {
    envelope.options.max_objects = Math.max(1, Math.min(16, Number(max_objects)));
  }

  if (ATTACHMENT_REF.test(raw)) {
    // B1: attachment ref -> readImage -> b64 envelope. Normalize the ref
    // first: dsh's store ID_PATTERN only accepts `sha256:<hex>` (see
    // dsh-attachment-local), so the optional `attachment:` prefix must be
    // stripped before AttachmentId() branding / readImage lookup.
    const normalized = raw.replace(/^attachment:/i, "");
    let stored;
    try {
      stored = await attachmentReader(normalized);
    } catch (err) {
      // B4: invalid ref / readImage failure -> error state (propagate to caller).
      const detail = err instanceof Error ? err.message : String(err);
      throw new Error(`vision-translate: could not resolve image attachment (${detail})`);
    }
    const data = stored?.data;
    if (!data || typeof data.byteLength !== "number" || data.byteLength === 0) {
      throw new Error("vision-translate: resolved image attachment is empty.");
    }
    const mediaType = stored?.mediaType || guessMediaType(stored?.ref);
    const ext = MEDIA_EXT[mediaType];
    if (!ext || !mediaType) {
      throw new Error(`vision-translate: unsupported image media type: ${mediaType ?? "unknown"}`);
    }
    envelope.image = { b64: toBase64(data), ext };
    return envelope;
  }

  // B2/B3: ordinary path (existing or not) is handed to the CLI verbatim —
  // the CLI classifies `image_not_found` -> error state (B3), so we never
  // pre-judge existence here.
  envelope.image = { path: raw };
  return envelope;
}

/** Map an ImageAttachmentRef's mediaType, when one is available. */
function guessMediaType(ref) {
  return ref && typeof ref.mediaType === "string" ? ref.mediaType : null;
}

/** Uint8Array/ArrayBuffer/string -> base64 string (Node-safe). */
export function toBase64(data) {
  if (typeof Buffer !== "undefined") return Buffer.from(data).toString("base64");
  let bin = "";
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

/**
 * Spawn the CLI on stdin with the PROTOCOL v1 envelope and resolve to its
 * parsed stdout payload. Branching on `status` (not the exit code) happens in
 * the caller via {@link classifyResult} — but this function already honours
 * B8 (a nonzero exit with valid JSON is still a parseable payload) and B9 (no
 * valid JSON with nonzero exit -> a descriptive error with stderr tail).
 *
 * @param pythonBin binary name/path used to run cli.py.
 * @param cliPath absolute path to cli.py.
 * @param envelope PROTOCOL v1 stdin envelope object.
 * @param options { timeoutMs?, signal? } — timeoutMs is a hard kill timer
 *        (default 120s); signal (typically exec.signal) aborts the child on
 *        tool cancellation/timeout.
 * @returns Promise<object> the parsed stdout JSON payload.
 * @throws CliAbortedError on signal abort / timeout (B10).
 * @throws CliOutputError when the CLI exits nonzero without usable JSON (B9),
 *         or exits zero without JSON (still an output error).
 * @throws the spawn error (e.g. ENOENT for a missing binary) as-is.
 */
export function runCli(pythonBin, cliPath, envelope, { timeoutMs = 120_000, signal } = {}) {
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(pythonBin, [cliPath], { stdio: ["pipe", "pipe", "pipe"] });
    } catch (err) {
      reject(err);
      return;
    }

    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = timeoutMs > 0 ? setTimeout(onTimeout, timeoutMs) : null;

    function finish(fn, value) {
      if (settled) return;
      settled = true;
      // Always release the kill timer first so a signal-abort settle does not
      // leave a 120s timer keeping the host event loop alive (B10).
      if (timer) clearTimeout(timer);
      if (signal?.aborted) {
        // Cancellation wins over whatever settled first.
        reject(new CliAbortedError());
        return;
      }
      fn(value);
    }

    function onTimeout() {
      if (signal?.aborted) return; // already handled by signal path
      killChild();
      finish(reject, new CliAbortedError());
    }

    function killChild() {
      try {
        child?.kill("SIGKILL");
      } catch {
        /* already gone */
      }
      // Release the stdio handles so the parent's event loop doesn't linger on
      // the child's pipes even if the child was mid-write when killed (B10).
      try {
        child?.stdin?.destroy();
        child?.stdout?.destroy();
        child?.stderr?.destroy();
      } catch {
        /* already closed */
      }
    }

    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      // Cap retained stderr to avoid unbounded memory; message truncates later.
      stderr += chunk;
      if (stderr.length > STDERR_CAP * 2) stderr = stderr.slice(-STDERR_CAP);
    });
    child.on("error", (err) => {
      if (signal?.aborted) {
        finish(reject, new CliAbortedError());
      } else {
        finish(reject, err);
      }
    });
    child.on("close", (code) => {
      let payload = null;
      try {
        payload = JSON.parse(stdout);
      } catch {
        payload = null;
      }
      if (payload && typeof payload === "object" && payload.status) {
        // B8/B5-B7: a valid JSON payload wins regardless of the exit code.
        finish(resolve, payload);
        return;
      }
      if (code !== 0) {
        // B9: nonzero exit without usable JSON -> error with stderr tail.
        const tail = stderr.trim().slice(-STDERR_CAP);
        const msg = tail
          ? `vision CLI exited with code ${code}: ${tail}`
          : `vision CLI exited with code ${code} and no usable JSON on stdout.`;
        finish(reject, new CliOutputError(msg));
        return;
      }
      // Exit 0 but stdout held no usable JSON object — still an output bug.
      finish(reject, new CliOutputError("vision CLI exited 0 without a JSON payload on stdout."));
    });

    // Signal abort (tool cancellation / policy timeout): kill and settle.
    if (signal) {
      if (signal.aborted) {
        killChild();
        finish(reject, new CliAbortedError());
      } else {
        signal.addEventListener(
          "abort",
          () => {
            killChild();
            finish(reject, new CliAbortedError());
          },
          { once: true },
        );
      }
    }

    try {
      child.stdin.write(JSON.stringify(envelope));
      child.stdin.end();
    } catch (err) {
      finish(reject, err);
    }
  });
}
