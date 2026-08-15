// Fake vision-translation CLI that never terminates by itself — exercises the
// runCli kill timer / timeout path (B10). It must be killed externally.
let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  // Intentionally never writes output and never exits.
  setInterval(() => {}, 1_000_000);
});
