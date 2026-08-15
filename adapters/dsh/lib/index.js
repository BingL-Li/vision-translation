/**
 * vision-translation — native dsh (Cordis) plugin.
 *
 * Registers one dsh tool, `vision_translate`, that grounds an image into a
 * structured <vision-context> block. It never re-implements core logic: it
 * spawns the Python CLI (`cli.py`, PROTOCOL v1) and speaks JSON — the same
 * cross-language contract every other adapter uses (see PROTOCOL.md).
 *
 * Host integration unique to the native path: dsh Web-UI image uploads are
 * `ImageBlock` attachments referenced by an opaque `sha256:<hex>` string (an
 * ImageAttachmentRef), which a stdio MCP tool can never receive. This plugin
 * resolves those refs via `ctx.attachments.readImage` and ships the bytes to
 * the CLI over a stdin b64 envelope — no shared filesystem needed. This is the
 * native-plugin trigger the ADAPTERS.md registry marked as the official path.
 *
 * Tool contract (see PROTOCOL.md / ADAPTERS.md):
 *   - ok          -> normal value with <vision-context> text (render)
 *   - unavailable -> NORMAL value with an explicit "do not guess" message
 *                    (fail-closed is a legal result — never a thrown error)
 *   - error       -> thrown error (isError) — a broken call worth surfacing
 */
import z from "@deepseek-ai/schemastery";
import { defineTool } from "@deepseek-ai/dsh-tools";
import { AttachmentId } from "@deepseek-ai/dsh-attachment";
import {
  classifyResult,
  resolveCli,
  envelopeFromImage,
  CliMissingError,
  runCli,
} from "./vision.js";

export const name = "vision-translate";
export const inject = ["tools", "attachments"];

/** Schemastery configuration for the vision-translate tool. */
export const Config = z.object({
  /** Absolute path to cli.py; "" (default) = auto-detect. */
  cliPath: z.string().default(""),
  /** Python binary name/path used to run cli.py. */
  pythonBin: z.string().default("python3"),
  /** Cooperative tool-call timeout in ms (also the CLI kill timer). */
  toolCallTimeoutMs: z.number().min(1).default(120000),
});

const DESCRIPTION =
  "Translation with Visual Primitives: translate an image into a structured " +
  "visual-primitives context (object bbox coordinates / spatial relations / " +
  "OCR / scene summary) and return <vision-context> text. Use this tool when " +
  "you need coordinates, positions, counting, layout, or structured entities " +
  "from an image. Pass `image` as a local file path or a dsh attachment " +
  "reference (sha256:<hex>). The image is sent to an OpenRouter auxiliary " +
  "vision model. If the result says vision is unavailable, do NOT guess or " +
  "fabricate the image content — tell the user you cannot see the image.";

export function apply(ctx, config = {}) {
  const cliPath = config.cliPath ?? "";
  const pythonBin = config.pythonBin || "python3";
  const toolCallTimeoutMs =
    typeof config.toolCallTimeoutMs === "number" && config.toolCallTimeoutMs > 0
      ? config.toolCallTimeoutMs
      : 120000;

  ctx.tools.register(
    defineTool({
      name: "vision_translate",
      description: DESCRIPTION,
      parameters: {
        image: {
          type: "string",
          required: true,
          description:
            "Local absolute/relative file path, OR a dsh image attachment " +
            "reference (sha256:<hex> or attachment:sha256:<hex>).",
        },
        question: {
          type: "string",
          description: "Optional question guiding the parse focus.",
        },
        model: {
          type: "string",
          description: "Optional auxiliary VLM model override (default = CLI chain).",
        },
        max_objects: {
          type: "integer",
          description: "Optional max primitives to keep (1..16, default 16).",
        },
      },
      output: {
        schema: {
          type: "object",
          additionalProperties: false,
          properties: {
            text: { type: "string", required: true },
          },
        },
        render: (_args, value) => [{ type: "text", text: value.text }],
      },
      // Cooperative timeout: the dsh timeout policy wraps exec.signal, which we
      // forward into runCli; toolCallTimeoutMs also drives the kill timer.
      timeoutMs: toolCallTimeoutMs,
      // B14: read-only spawn, no shared mutable state — safe to run parallel.
      isConcurrencySafe: () => true,
      presentCall: (args) => ({
        card: "generic",
        title: "Analyze image (vision-translate)",
        kind: "other",
        rawInput: args && args.image,
      }),
      async execute(args, exec) {
        // B11 discovery: config cliPath -> env VISION_TRANSLATION_CLI ->
        // package-relative ../../cli.py. Throws a descriptive CliMissingError.
        let resolved;
        try {
          resolved = resolveCli({ cliPath, pythonBin });
        } catch (err) {
          throw err instanceof CliMissingError
            ? err
            : new Error(`vision-translate: ${err.message}`);
        }

        // attachmentReader resolves a dsh attachment ref->bytes (and media type)
        // via ctx.attachments.readImage, honouring exec.signal cancellation.
        const attachmentReader = async (ref) => {
          const stored = await ctx.attachments.readImage(
            { attachmentId: AttachmentId(ref), mediaType: undefined },
            exec.signal,
          );
          return {
            data: stored.data,
            mediaType: stored.ref?.mediaType,
            ref: stored.ref,
          };
        };

        const envelope = await envelopeFromImage(
          args.image,
          attachmentReader,
          {
            question: args.question,
            model: args.model,
            max_objects: args.max_objects,
          },
        );

        const payload = await runCli(resolved.pythonBin, resolved.cliPath, envelope, {
          timeoutMs: toolCallTimeoutMs,
          signal: exec.signal,
        });

        const result = classifyResult(payload);
        if (result.kind === "error") {
          // B7: error state -> thrown (isError); mirror the MCP message shape.
          throw new Error(`${result.code}: ${result.message}`);
        }
        // B5 (ok) and B6 (unavailable) are both NORMAL successful values.
        return { text: result.text };
      },
    }),
  );
}
