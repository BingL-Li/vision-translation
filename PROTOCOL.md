# PROTOCOL v1 — normative specification

> This is the **single source of truth** for the vision-translation CLI
> protocol. `cli.py` implements it; `ADAPTERS.md` and the template reference
> it. If any other file disagrees with this one, this file wins.

## 1. Output contract

`stdout` carries **exactly one JSON object**, nothing else. All
human-readable logs go to `stderr`. An adapter can always do
`JSON.parse(stdout)` — if that ever fails, it is a bug in the CLI, not in
the adapter.

Every response carries `protocol` and `core_version`:

```json
{"protocol": 1, "core_version": "0.2.0", ...}
```

## 2. Status: three states

### `ok` — vision context produced

```json
{"protocol": 1, "core_version": "0.2.0",
 "status": "ok",
 "context": "<vision-context>…</vision-context>",
 "model": "xiaomi/mimo-v2.5"}
```

### `unavailable` — fail-closed, protocol alive (legal result, exit 0)

The vision parse could not be produced (no key, VLM down, invalid VLM
output…). **This is not a crash.** Adapters should treat it as a
retry/fallback trigger.

```json
{"protocol": 1, "core_version": "0.2.0",
 "status": "unavailable",
 "unavailable": {"reason": "<reason>", "message": "detail"}}
```

`reason` ∈ `{no_api_key, auth, rate_limited, upstream, vlm_invalid_output, invalid_image}`:

| reason             | meaning                                                      |
|--------------------|--------------------------------------------------------------|
| `no_api_key`       | no OpenRouter key found (env, `~/.hermes/.env`, or `~/.env`) |
| `auth`             | HTTP 401/403 — key present but rejected                      |
| `rate_limited`     | HTTP 429                                                    |
| `upstream`         | other HTTP / network errors from the VLM endpoint            |
| `vlm_invalid_output` | VLM returned unusable JSON 3× (fail-closed)                |
| `invalid_image`    | image file unreadable / empty / bad base64                   |

### `error` — malformed request or internal bug (nonzero exit)

The call itself was wrong — the adapter did something wrong, or the CLI has
a bug. Adapters should surface this, not retry blindly.

```json
{"protocol": 1, "core_version": "0.2.0",
 "status": "error",
 "error": {"code": "usage" | "image_not_found" | "internal",
           "message": "human-readable detail"}}
```

- `usage` — bad argv or bad stdin envelope (exit 2)
- `image_not_found` — the path does not exist (exit 1). Note: a file that
  exists but is unreadable/empty is `unavailable` / `invalid_image`, not
  `image_not_found`.
- `internal` — anything else (exit 1)

## 3. Exit codes

| exit | status            |
|------|-------------------|
| 0    | `ok` or `unavailable` (both are legal results) |
| 1    | `error` (`image_not_found` / `internal`) |
| 2    | `error` with code `usage` |

Adapters should **branch on `status`, not on the exit code**; the exit code
exists for shell users.

## 4. Input

### Positional argv

```bash
python cli.py <image_path> ["question"]
```

### Stdin envelope (preferred for cross-filesystem / agent use)

The image travels with the request, so a remote adapter does not need
shared storage:

```json
{"protocol": 1,
 "image": {"path": "/abs/or/rel/path"}            // xor
        | {"b64": "<base64>", "ext": ".png"},     // xor
 "question": "optional guiding question",
 "options": {"model": "…", "max_objects": 16}}
```

- `argv` wins over stdin when both are present.
- **Forward compatibility**: unknown fields are ignored; missing optional
  fields get defaults. An adapter written for a newer protocol must not
  break old servers, and vice versa.

## 5. Read-only commands (no tokens, no network — safe for CI handshakes)

```bash
python cli.py --self-check
```

```json
{"protocol": 1, "core_version": "0.2.0",
 "status": "ok" | "unavailable",
 "checks": {"openrouter_key": true|false,
            "key_source": "env" | "<absolute path of the .env file>" | null,
            "core_import": "ok"}}
```

Exit 0 in both cases. Without a key, `status` is `unavailable` with
`reason: no_api_key` — this is the documented no-key behaviour, not a
failure.

```bash
python cli.py --protocol-version
```

```json
{"protocol": 1, "core_version": "0.2.0", "status": "ok", "cli": "0.2.0"}
```

Exit 0.

## 6. Versioning

- `protocol` — the envelope/response shape. `1` is current. A **breaking**
  change to the shape bumps the protocol number (and the repo major
  version). Adapters declare which protocol they speak.
- `core_version` — core behaviour changes that keep the shape only bump
  `core_version`. It is kept in sync with `version:` in `plugin.yaml`;
  CI asserts the match.

## 7. Compatibility rules (adapter-facing)

1. Never assume the response has more fields than documented here.
2. Unknown fields in the response are safe to ignore.
3. `unavailable` may carry a `message`; use `reason` for logic.
4. A missing optional field means "use the default" — never guess.
