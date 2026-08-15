/**
 * vision-translation dsh adapter — unit tests (node:test, zero deps, offline).
 *
 * Covers the PROTOCOL v1 boundaries and every edge-condition row of the spec:
 *   B1  attachment ref -> readImage -> b64 envelope
 *   B2  existing path  -> image.path envelope
 *   B3  missing path   -> passed verbatim (CLI classifies)
 *   B4  bad/erroneous attachment ref -> error (throw)
 *   B5  status=ok      -> context text
 *   B6  unavailable    -> normal fail-closed text
 *   B7  status=error   -> thrown
 *   B8  nonzero exit + valid JSON -> status wins
 *   B9  nonzero exit + junk JSON  -> error with stderr tail
 *   B10 timeout -> thrown, child killed
 *   B11 missing python/cli -> descriptive error
 *   B12 max_objects clamped to 1..16
 *   B13 empty model dropped
 *   B14 concurrency-safe returns true
 *
 * The CLI is faked as plain node scripts (`tests/fixtures/*.js`) launched via
 * `process.execPath` (no Python dependency in tests).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  classifyResult,
  resolveCli,
  CliMissingError,
  envelopeFromImage,
  runCli,
  toBase64,
  MEDIA_EXT,
  PACKAGE_ROOT,
} from "../lib/vision.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIX = join(HERE, "fixtures");
const node = process.execPath;

/** A genuine 1x1 transparent PNG, base64 (used for b64-envelope tests). */
const PNG_1x1_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

// --------------------------------------------------------------------------- //
// classifyResult — three-state mapping (B5/B6/B7) + malformed payloads
// --------------------------------------------------------------------------- //
test("classifyResult: ok -> context text", () => {
  const r = classifyResult({
    protocol: 1,
    status: "ok",
    context: "<vision-context>x</vision-context>",
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.text, "<vision-context>x</vision-context>");
});

test("classifyResult: unavailable -> fail-closed text with do-not-guess", () => {
  const r = classifyResult({
    protocol: 1,
    status: "unavailable",
    unavailable: { reason: "no_api_key", message: "no key" },
  });
  assert.equal(r.kind, "unavailable");
  assert.equal(r.reason, "no_api_key");
  assert.match(r.text, /^vision unavailable \(reason: no_api_key\): no key\nDo not guess or fabricate the image content\.$/);
});

test("classifyResult: error -> { kind:'error', code, message }", () => {
  const r = classifyResult({
    protocol: 1,
    status: "error",
    error: { code: "internal", message: "boom" },
  });
  assert.equal(r.kind, "error");
  assert.equal(r.code, "internal");
  assert.equal(r.message, "boom");
});

test("classifyResult: unknown status throws", () => {
  assert.throws(() => classifyResult({ status: "wat" }), /unknown status/);
});

test("classifyResult: non-object/non-json throws", () => {
  assert.throws(() => classifyResult(null), /non-object/);
  assert.throws(() => classifyResult("nope"), /non-object/);
});

// --------------------------------------------------------------------------- //
// resolveCli — discovery order (B11)
// --------------------------------------------------------------------------- //
test("resolveCli: config.cliPath wins over env & fallback", () => {
  const r = resolveCli(
    { cliPath: "/cfg/cli.py", pythonBin: "python3" },
    { VISION_TRANSLATION_CLI: "/env/cli.py" },
  );
  assert.equal(r.cliPath, "/cfg/cli.py");
  assert.equal(r.source, "config.cliPath");
});

test("resolveCli: env VISION_TRANSLATION_CLI when config cliPath empty", () => {
  const r = resolveCli(
    { cliPath: "", pythonBin: "python3" },
    { VISION_TRANSLATION_CLI: "/env/cli.py" },
  );
  assert.equal(r.cliPath, "/env/cli.py");
  assert.equal(r.source, "env.VISION_TRANSLATION_CLI");
});

test("resolveCli: package-relative fallback when neither set", () => {
  const r = resolveCli({ cliPath: "", pythonBin: "python3" }, {});
  assert.equal(r.source, "package-relative ../../cli.py");
  // PACKAGE_ROOT = …/adapters/dsh -> + ../../cli.py → repo root cli.py
  const p = accessPath(r.cliPath);
  assert.ok(p.endsWith(join("vision-translation", "cli.py")), p);
  assert.equal(pathParts(p).includes("adapters"), false);
});

test("resolveCli: empty pythonBin defaults to python3", () => {
  const r = resolveCli({ cliPath: "", pythonBin: "" }, {});
  assert.equal(r.pythonBin, "python3");
});

test("resolveCli: standalone install without repo fallback -> CliMissingError (B11)", () => {
  // Simulate an npm install outside the repo: no ../../cli.py exists.
  assert.throws(
    () => resolveCli({ cliPath: "", pythonBin: "python3" }, {}, "/nonexistent/pkg-root"),
    (err) => err instanceof CliMissingError && /could not locate the Python CLI/.test(err.message),
  );
});

// --------------------------------------------------------------------------- //
// envelopeFromImage — B1/B2/B3/B4/B12/B13
// --------------------------------------------------------------------------- //
test("envelopeFromImage: attachment ref -> b64 envelope (B1)", async () => {
  const imgBase64 = PNG_1x1_B64;
  const data = Buffer.from(imgBase64, "base64");
  const reader = async (ref) => ({ data, mediaType: "image/png" });
  const env = await envelopeFromImage(
    "sha256:" + "a".repeat(64),
    reader,
    { question: "q", model: "m", max_objects: 8 },
  );
  assert.equal(env.protocol, 1);
  assert.equal(env.image.ext, ".png");
  const bytes = Buffer.from(env.image.b64, "base64");
  assert.equal(bytes.toString("base64"), imgBase64);
  assert.equal(env.question, "q");
  assert.equal(env.options.model, "m");
  assert.equal(env.options.max_objects, 8);
});

test("envelopeFromImage: attachment:sha256: prefix normalized before reader (B1)", async () => {
  let seen;
  const reader = async (ref) => {
    seen = ref;
    return { data: Buffer.from(PNG_1x1_B64, "base64"), mediaType: "image/jpeg" };
  };
  const env = await envelopeFromImage("attachment:sha256:" + "b".repeat(64), reader);
  // dsh's store ID_PATTERN only accepts `sha256:<hex>`, so the prefix must be
  // stripped before the reader is called (see vision.js envelopeFromImage).
  assert.equal(seen, "sha256:" + "b".repeat(64));
  assert.equal(env.image.ext, ".jpg");
});

test("envelopeFromImage: path (existing or not) -> image.path (B2/B3)", async () => {
  const env = await envelopeFromImage("./some/existing.png".replace("existing", "missing"), async () => {
    throw new Error("should not be called");
  });
  assert.equal(env.image.path, "./some/missing.png");
  assert.equal(env.protocol, 1);
  // No b64 at all, and no reader invocation for a plain path.
  assert.equal("b64" in env.image, false);
});

test("envelopeFromImage: bad ref / reader throws -> throws (B4)", async () => {
  const reader = async () => {
    throw new Error("storage down");
  };
  await assert.rejects(
    () => envelopeFromImage("sha256:" + "c".repeat(64), reader),
    /could not resolve image attachment/,
  );
});

test("envelopeFromImage: empty resolved bytes -> throws (B4)", async () => {
  const reader = async () => ({ data: new Uint8Array(0), mediaType: "image/png" });
  await assert.rejects(
    () => envelopeFromImage("sha256:" + "d".repeat(64), reader),
    /attachment is empty/,
  );
});

test("envelopeFromImage: unsupported media type -> throws (extends B4)", async () => {
  const reader = async () => ({ data: new Uint8Array(2), mediaType: "image/bmp" });
  await assert.rejects(
    () => envelopeFromImage("sha256:" + "e".repeat(64), reader),
    /unsupported image media type/,
  );
});

test("envelopeFromImage: empty image arg -> throws", async () => {
  await assert.rejects(() => envelopeFromImage("", async () => ({})), /empty `image`/);
});

test("envelopeFromImage: max_objects clamped to 1..16 (B12)", async () => {
  const env = await envelopeFromImage("/img.png", async () => {
    throw new Error("never");
  }, { max_objects: 99 });
  assert.equal(env.options.max_objects, 16);
  const env2 = await envelopeFromImage("/img.png", async () => {
    throw new Error("never");
  }, { max_objects: 0 });
  assert.equal(env2.options.max_objects, 1);
});

test("envelopeFromImage: empty model dropped so CLI uses default chain (B13)", async () => {
  const env = await envelopeFromImage("/img.png", async () => {
    throw new Error("never");
  }, { model: "" });
  assert.equal("model" in env.options, false);
});

// --------------------------------------------------------------------------- //
// runCli — spawn + parse + status-branch + timeout (B5/B6/B7/B8/B9/B10)
// --------------------------------------------------------------------------- //
const OK_ENVELOPE = { protocol: 1, image: { path: "/x.png" } };

test("runCli: ok payload -> resolves parseable payload (B5)", async () => {
  const p = await runCli(node, join(FIX, "fake-ok.js"), OK_ENVELOPE);
  assert.equal(p.status, "ok");
  assert.match(p.context, /<vision-context>/);
});

test("runCli: unavailable payload -> resolves (exit 0) (B6)", async () => {
  const p = await runCli(node, join(FIX, "fake-unavailable.js"), OK_ENVELOPE);
  assert.equal(p.status, "unavailable");
  assert.equal(p.unavailable.reason, "no_api_key");
});

test("runCli: error payload + nonzero exit -> payload still resolves (B8)", async () => {
  const p = await runCli(node, join(FIX, "fake-error.js"), OK_ENVELOPE);
  assert.equal(p.status, "error");
  assert.equal(p.error.code, "image_not_found");
});

test("runCli: nonzero exit + junk stdout -> CliOutputError with stderr tail (B9)", async () => {
  await assert.rejects(
    () => runCli(node, join(FIX, "fake-nonjson.js"), OK_ENVELOPE),
    (err) =>
      err.name === "CliOutputError" &&
      /exited with code 1/.test(err.message) &&
      /internal boom/.test(err.message),
  );
});

test("runCli: timeout kills child and rejects (B10)", async () => {
  const t0 = Date.now();
  await assert.rejects(
    () => runCli(node, join(FIX, "fake-hang.js"), OK_ENVELOPE, { timeoutMs: 200 }),
    (err) => err.name === "CliAbortedError",
  );
  assert.ok(Date.now() - t0 < 5000, "timeout should reject promptly");
});

test("runCli: abort signal rejection kills child (signal path)", async () => {
  const ac = new AbortController();
  const promise = runCli(node, join(FIX, "fake-hang.js"), OK_ENVELOPE, { signal: ac.signal });
  // Abort after a tick so the child is running.
  setTimeout(() => ac.abort(), 50);
  await assert.rejects(() => promise, (err) => err.name === "CliAbortedError");
});

test("runCli: missing python binary -> spawn error (B11)", async () => {
  await assert.rejects(
    () => runCli("/nonexistent/python-that-does-not-exist", join(FIX, "fake-ok.js"), OK_ENVELOPE),
    (err) => err.code === "ENOENT",
  );
});

// --------------------------------------------------------------------------- //
// B14 + helpers
// --------------------------------------------------------------------------- //
test("defineTool is declared concurrency-safe (B14)", async () => {
  // The tool definition lives in lib/index.js (imports dsh peer packages we do
  // not install in tests). Guard the contract via a source assertion: the
  // defineTool options must declare isConcurrencySafe returning true — a
  // read-only spawn with no shared mutable state.
  const src = await readFile(join(HERE, "..", "lib", "index.js"), "utf8");
  assert.match(src, /isConcurrencySafe:\s*\(\)\s*=>\s*true/);
});

test("toBase64: Uint8Array encoding round-trips", () => {
  const bytes = new Uint8Array([1, 2, 3, 200, 201]);
  assert.equal(toBase64(bytes), Buffer.from(bytes).toString("base64"));
});

test("MEDIA_EXT maps all dsh supported image types", () => {
  assert.equal(MEDIA_EXT["image/png"], ".png");
  assert.equal(MEDIA_EXT["image/jpeg"], ".jpg");
  assert.equal(MEDIA_EXT["image/webp"], ".webp");
  assert.equal(MEDIA_EXT["image/gif"], ".gif");
});

// --------------------------------------------------------------------------- //
// tiny path helpers (kept local to avoid extra dependencies)
// --------------------------------------------------------------------------- //
function accessPath(p) {
  return resolve(p);
}
function pathParts(p) {
  return p.split(/[\\/]/);
}
