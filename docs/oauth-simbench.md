# OAuth sign-in tier (GoldenGate)

Customers reported that agents driving the simulator fail on **OAuth sign-in
flows**. This tier turns that signal into device-use evals. It adds one golden
app, `GoldenGate`, and three tasks — one per sign-in surface an Expo app
actually ships — verified from app state, the UI-event journal and the identity
provider's own records, with no LLM judge.

## Why OAuth is a distinct capability

The existing simbench probes stay inside one app's own view tree. A sign-in flow
leaves it: it crosses into a system consent alert, an out-of-process web sheet,
or a different app entirely, and only returns through a custom-scheme callback.
Those transitions are exactly where driver stacks lose the thread, so the tier
measures a capability the note/scroll/form probes never touch.

## The golden app

`GoldenGate` embeds its own identity provider, **HarborID**, as a loopback HTTP
server inside the process (`NWListener` on `127.0.0.1`). The flow therefore
needs no network and no external service, yet every driver-facing surface is the
real one:

- **Authorization Code + PKCE.** The app opens `/authorize` with an `S256`
  `code_challenge` and a random `state`; HarborID serves its own login and
  consent pages, redirects to `goldengate://callback?code=...&state=...`, and
  the app exchanges the code at `/token` (verifying the PKCE verifier) then
  reads `/userinfo`. A callback that did not come out of the provider's login
  and consent pages cannot mint a session.
- **Four fixed accounts.** Username plus an "access code" (a plain text field,
  not a password field, so Safari's password manager does not interpose a
  "Save Password?" sheet on the OAuth surface itself). Each task fixes which
  account to use so the verifier checks an exact identity.
- **Journal.** The app and the provider append every step to `events.json`
  (`sign-in-started-ui`, `provider-authorize`, `provider-login-accepted`,
  `provider-consent-granted`/`-denied`, `callback-received`,
  `provider-token-issued`, `signed-in`, ...). Writing `session.json` directly
  cannot reproduce the provider's PKCE-bound record, so injected state scores
  zero.

## The three surfaces

| Task | Surface | Expo analogue | Difficulty |
|---|---|---|---|
| `simbench-ios-08-goldengate-embedded-web-login` | In-app `WKWebView` sheet | An in-app browser/web login | medium |
| `simbench-ios-09-goldengate-system-auth-session` | `ASWebAuthenticationSession` | `expo-web-browser` `openAuthSessionAsync` / `expo-auth-session` | hard |
| `simbench-ios-10-goldengate-browser-handoff` | Hand-off to Safari, `goldengate://` callback | A full external-browser OAuth round-trip | hard |

## What the driver tools can do here (measured 2026-09-16)

These findings are the reason the tier exists, and they set what is shippable:

- **Embedded (`WKWebView`).** agent-device reads the in-app web form as a
  semantic tree and drives it with `role`+`label` selectors. Fully drivable;
  the scripted oracle signs in deterministically.
- **System (`ASWebAuthenticationSession`).** agent-device reads the app screen
  and the iOS "Wants to Use ... to Sign In" alert (native), but the web sheet
  itself is **out of process and returns a sparse, unreadable tree**. argent's
  accessibility service does read that sheet as normalized-coordinate elements.
  The oracle is a hybrid: agent-device for the native surfaces, argent for the
  web form. Drivable, but only if the stack can read the out-of-process sheet.
- **Browser hand-off (Safari).** With the pinned agent-device version, tapping
  Safari's web input returns `TEXT_INPUT_NOT_FOCUSED` and typing fails, so
  agent-device cannot complete a Safari login today. argent reads Safari's web
  content, but foregrounding the hand-off and typing remain flaky. This task is
  **authored and locked but held out of the model job cohorts** until a driver
  can reliably drive Safari web input — the same "authored, outside cohorts"
  posture the paywall codegen task uses.

## Verification

`tests/verify.py` (per task) credits a sign-in only when all three agree:

1. **App session** — `session.json` records the fixed username, the expected
   `mode` (`embedded`/`system`/`browser`), a non-empty access token and a
   pairing code.
2. **Ordered journal** — sign-in start, authorization, login, consent, callback,
   token issuance, user-info retrieval and sign-in appear in order. All provider
   events must identify the same request as the current session.
3. **Provider record** — that request has `consent = allow`, an authorization
   code and a stored PKCE `code_challenge`; its issued access token and pairing
   code exactly match the session.

Reward is `1.0` only if every named check passes. The shared
`simbench_evidence.py` collector snapshots the container after quiescing the app
and validates a per-trial manifest, exactly like the other simbench tasks.

## Calibration status

Run real Harbor brackets before trusting any model number:

```sh
uv run expo-simbench-calibrate --task simbench-ios-08-goldengate-embedded-web-login --attempts 2
uv run expo-simbench-calibrate --task simbench-ios-09-goldengate-system-auth-session --attempts 2
```

Both tasks ship a scripted-oracle ceiling (`allow` → `1.0`), a no-op floor
(`0`) and a **consent-denied** negative control: the oracle completes the
HarborID login but refuses access, which must leave no session and score `0`,
proving the verifier grades consent rather than mere login. Task 08's oracle
uses agent-device; task 09's uses the agent-device + argent hybrid, so its
calibration additionally needs `argent` installed (as the vision-grid task
already does). Task 10 has an oracle and verifier but is not part of any job or
calibration cohort pending Safari web-input support.

During authoring (2026-09-16, iOS 26.5 simulator), the oracles were validated
end to end for tasks 08 and 09: `allow` reached `signed-in` and scored `1.0`,
`deny` and a fresh unopened app both scored `0`. A multi-attempt
`expo-simbench-calibrate` run on the target runtime is still the gate before
publishing model comparisons.

The pre-merge review strengthened these checks: mismatched tokens, pairing
codes, request IDs or missing token events now fail. Denial calibration also
requires `sim_oauth_consent_denied=1`, proving the expected user's login and
denial occurred with no session; an unopened app's zero is insufficient.
Offline evidence tests cover all three surfaces, and the shared Swift app
typechecks against the simulator SDK. The strengthened verifier still needs
the live calibration commands above before publishing model comparisons.
