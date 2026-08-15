// Fake vision-translation CLI for tests: reads a PROTOCOL v1 stdin envelope
// and emits a `ok` payload (B5). Invoked as `node fake-ok.js`.
let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  process.stdout.write(
    JSON.stringify({
      protocol: 1,
      core_version: "0.2.0",
      status: "ok",
      context: "<vision-context>\n[bbox] etc.</vision-context>",
      model: "xiaomi/mimo-v2.5",
    }),
  );
});
