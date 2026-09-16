The onboarding paywall is missing on fresh installs and after logout, although
the customer and placement offering have loaded. Changing the OTA channel did
not help. Repair the eligibility logic used by `App.tsx`.

This app deliberately supports purchases without an account. The local fixtures
stand in for auth, RevenueCat customer info and placement offerings; no account,
SDK key, backend, purchase or deployment is needed. Keep the screen wired to
`getPaywallOffering` in `paywall.js`, with the same inputs and return value.
Keep this helper a standalone CommonJS module with no imports, I/O or timers;
its exported function is executed against snapshots in an isolated JavaScript context.

The product contract is:

- All three resources (`session`, `customer`, `offerings`) must be `ready`.
  Loading and errors must hide the paywall.
- A logged-out session has `userId: null`. Its customer is ready for purchases
  when `appUserId` is a nonempty RevenueCat anonymous ID (`$RCAnonymousID:` plus
  a suffix). Login is optional. A signed-in session requires an exact match
  between its nonempty user ID and the customer ID; hide during account changes.
- Anyone with the `premium` entitlement must not see this upsell. Other
  entitlements do not grant premium.
- Return the offering identifier assigned to the requested `placement` in
  `offerings.byPlacement`. Missing/empty assignments hide the paywall; the
  unrelated `current` offering is never a placement fallback.
- Evaluate the current snapshot on every render without mutating it. Fresh
  install, login, logout and switching placements must all keep working.

Keep every fixture and its selection control. Do not replace the state-driven
screen with a hard-coded paywall, remove its guards, or change the product
contract. Repair the app code; explanatory text alone is not a fix.
