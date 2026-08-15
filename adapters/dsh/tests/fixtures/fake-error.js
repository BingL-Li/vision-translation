// Fake vision-translation CLI: emits an `error` payload AND exits nonzero,
// exercising B7 (error -> thrown) and B8 (valid JSON driven by status, not exit code).
let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  process.stdout.write(
    JSON.stringify({
      protocol: 1,
      core_version: "0.2.0",
      status: "error",
      error: { code: "image_not_found", message: "image not found: /nope.png" },
    }),
  );
  process.exitCode = 1;
});
