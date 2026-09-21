# Event model-health collector (local component)

The event reservation gate reads a short-lived, server-owned JSON snapshot.
This collector is an **opt-in producer** for that file. It has not been deployed,
has not been run against Oberon, Arena, Brutus, or Flightpath, and does not
constitute live model certification. Current labs are unchanged.

The trusted operator supplies a private JSON configuration with schema
`1.0` and a nonempty `targets` array. Each target names an exact `cluster_id`
and `model_id`, and three HTTPS endpoints:

- `readiness_url`: trusted serving adapter returning HTTP 200 and exact
  `cluster_id`, `model_id`, and integer `ready_replicas` fields; this must
  reflect the target cluster's actual
  serving replicas, not a hand-authored status page;
- `route_url`: caller-reachable route health endpoint returning HTTP 200;
- `inference_url`: OpenAI-compatible chat-completions endpoint returning HTTP
  200 with nonempty `choices[0].message.content` for `inference_body`. Its
  response `model` must equal the configured `model_id`, or the explicitly
  configured `response_model_id` when the serving backend uses a known alias.
  A 200 response from another model is negative evidence.

Optional `readiness_token_env`, `route_token_env`, and `inference_token_env`
name environment variables containing credentials. Do not put tokens or
passwords in the JSON file. Endpoint URLs require HTTPS, and the client verifies
TLS and does not follow redirects. Configure allowlisted, operator-controlled
targets only; never accept target URLs or bodies from requesters. A deployment
must additionally restrict egress to approved endpoints and protect both the
configuration and output file from untrusted writes.

The CLI is `scripts/collect_event_model_health.py`. It requires
`EVENT_MODEL_HEALTH_PROBE_CONFIG_FILE` and
`EVENT_MODEL_HEALTH_SNAPSHOT_FILE`; it performs no work unless explicitly
invoked. The snapshot is validated, written to a mode-0600 temporary file,
flushed, and atomically renamed into place. Its timestamp is probe *start*,
not the end, so long runs cannot rejuvenate old evidence. Runs lasting over
120 seconds fail without replacing prior evidence. Missing credential
references fail the run. Network, HTTP, or malformed-response failures become
negative evidence (`0`, `false`, or `false`) and are never logged with response
bodies or authorization headers. The admission reader independently rejects
stale snapshots, so a failed run cannot keep allowing new model-dependent
reservations indefinitely.

Before deploying a scheduled producer, certify the readiness adapter's
cluster/model mapping, route vantage point, least-privilege credentials,
egress allowlist, clock synchronization, TLS roots, probe cost, schedule, and
restart behavior. Add deployed contract and failure-injection evidence. This
collector proves responsiveness only; it does not prove 25/30-seat throughput.
