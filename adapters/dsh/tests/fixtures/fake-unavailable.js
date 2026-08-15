// Fake vision-translation CLI: emits an `unavailable` payload, exit 0 (B6).
let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  process.stdout.write(
    JSON.stringify({
      protocol: 1,
      core_version: "0.2.0",
      status: "unavailable",
      unavailable: { reason: "no_api_key", message: "no OpenRouter key found" },
    }),
  );
});
