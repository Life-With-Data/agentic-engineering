# Security and Hardening

Build-time security practice: treat every external input as hostile, every
secret as sacred, and every authorization check as mandatory. This is the
build-time counterpart to the audit-time
[`security-sentinel`](../../../agents/review/security-sentinel.md) agent —
harden during implementation, then audit before deployment.

Use when building anything that accepts user input, implements auth, stores
or transmits sensitive data, integrates external services, handles uploads /
webhooks / payments / PII, or calls an LLM.

## Process: threat model first

Controls without a threat model are guesses. Five minutes before hardening:

1. **Map the trust boundaries** — where untrusted data enters: HTTP requests,
   uploads, webhooks, third-party APIs, queues, and **LLM output**.
2. **Name the assets** — credentials, PII, payment data, admin actions, money.
3. **Run STRIDE over each boundary**: Spoofing → authentication/signatures;
   Tampering → integrity checks, parameterized queries, HTTPS; Repudiation →
   audit logging; Information disclosure → encryption, field allowlists,
   generic errors; Denial of service → rate limits, size caps, timeouts;
   Elevation of privilege → authorization checks, least privilege.
4. **Write abuse cases next to use cases** — "how would I misuse this?" is the
   first test.

If a feature's trust boundaries cannot be named, it is not ready to secure
(OWASP A04: Insecure Design).

## The three-tier boundary system

**Always (no exceptions):** validate all external input at the system
boundary; parameterize every query; encode output (keep framework
auto-escaping on); HTTPS everywhere; hash passwords with
bcrypt/scrypt/argon2; set security headers (CSP, HSTS, X-Frame-Options,
X-Content-Type-Options); httpOnly + secure + sameSite session cookies; run
the dependency audit before every release.

**Ask first (human approval):** new or changed auth flows; storing new
categories of sensitive data; new external integrations; CORS changes; file
upload handlers; rate-limit changes; granting elevated roles.

**Never:** commit secrets; log sensitive data; trust client-side validation
as a boundary; disable security headers for convenience; `eval()`/`innerHTML`
with user data; auth tokens in client-accessible storage; expose stack traces
to users.

Framework-specific mechanics (which middleware, which validation library)
come from the repository's mapped assets, not this reference.

## High-signal specifics

- **SSRF**: any server-side fetch of a user-influenced URL (webhooks, "import
  from URL", link previews) can target internal services — allowlist scheme
  and host, resolve ALL DNS records and reject non-unicast ranges (loopback,
  link-local `169.254.169.254` cloud metadata, private, unique-local), and
  forbid redirects. Even then a short-TTL rebind can race the check (TOCTOU);
  for high-risk surfaces connect to the pinned IP or use a filtering agent.
- **Committed secret**: rotate it. Deleting the line or rewriting history is
  not enough — assume compromise the moment it reaches a remote; revoke and
  reissue first, then purge.
- **Uploads**: allowlist MIME types and cap size; never trust the extension —
  check magic bytes when it matters.
- **Audit triage**: critical/high + reachable in production → fix now;
  fix unavailable → workaround, replacement, or allowlisted with a review
  date; moderate → next release cycle; low → routine updates. Record reason
  and review date for anything deferred.
- **Supply chain**: the audit catches CVEs, not malice — commit the lockfile
  and install with `npm ci` (or equivalent) in CI, review new dependencies
  (maintenance, downloads, `postinstall` scripts), watch for typosquats.

## Securing AI / LLM features

Map LLM-calling features to the
[OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/):

- **Treat all model output as untrusted input** (LLM05) — never into `eval`,
  SQL, a shell, `innerHTML`, or a file path without the same validation and
  encoding as raw user input.
- **Assume prompts can be hijacked** (LLM01) — untrusted text in the context
  window carries instructions; the system prompt is not a security boundary.
  Enforce permissions in code.
- **Keep secrets and other users' data out of prompts** (LLM02/LLM07) —
  anything in context can be echoed back.
- **Constrain tool and agent permissions** (LLM06) — minimum scope,
  confirmation for destructive actions, validate every tool argument.
- **Bound consumption** (LLM10) — cap tokens, rate, and loop depth.
- **Isolate retrieval data** (LLM08) — partition embeddings per tenant;
  validate documents before indexing.

## Red flags

User input reaching queries/shell/HTML directly; secrets in source or
history; endpoints without authz checks; wildcard CORS; no rate limit on
auth; stack traces to users; critical-vulnerable dependencies; un-allowlisted
server-side URL fetches; LLM output in a query/DOM/shell; secrets or PII in
an LLM context window. And the rationalizations that produce them: "internal
tool", "add security later", "no one would exploit this", "the framework
handles it", "just a prototype", "it's only text from the model" — all false.

## Checklist

The itemized review and pre-commit verification checklist lives in
[security-checklist](security-and-hardening-checklist.md) — run it for every
security-relevant change.
