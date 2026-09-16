// Execute the submitted pure policy helper. Rendering remains a separate check.
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext(Object.create(null), {
  codeGeneration: { strings: false, wasm: false },
});
let loadError = null;
try {
  const source = fs.readFileSync(process.argv[2], 'utf8');
  vm.runInContext(`const module = { exports: {} }; const exports = module.exports;\n(function(module, exports) {\n${source}\n})(module, exports);`, context, { timeout: 1000 });
  if (vm.runInContext('typeof module.exports.getPaywallOffering', context, { timeout: 1000 }) !== 'function') {
    throw new Error('Missing getPaywallOffering export');
  }
} catch {
  loadError = 'Candidate module failed to load or export getPaywallOffering';
}
const failures = new Set();
let checks = 0;
let executedChecks = 0;
let failedChecks = 0;
const counterexamples = {};

function freeze(value) {
  if (value && typeof value === 'object') {
    for (const nested of Object.values(value)) freeze(nested);
    Object.freeze(value);
  }
  return value;
}

function check(group, state, expected) {
  checks++;
  let actual;
  try {
    if (loadError) throw new Error('Candidate unavailable');
    // No host objects or callbacks enter the candidate's context. Each call
    // has a deadline; a nonterminating helper is a candidate failure.
    executedChecks++;
    actual = vm.runInContext(`module.exports.getPaywallOffering((${freeze.toString()})(${JSON.stringify(state)}))`, context, { timeout: 50 });
  } catch {
    // Do not inspect candidate-owned exceptions or objects on the host.
    loadError ??= 'Candidate helper threw or timed out';
  }
  if (loadError || actual !== expected) {
    failures.add(group);
    failedChecks++;
    counterexamples[group] ??= { state, expected,
      actual: actual === null || typeof actual === 'string' || typeof actual === 'boolean'
        ? actual : `<${typeof actual}>`, error: loadError };
  }
}

const identities = [
  { user: null, customer: '$RCAnonymousID:fresh', allowed: true },
  { user: 'account-a', customer: 'account-a', allowed: true },
  { user: null, customer: '$RCAnonymousID:after-logout', allowed: true },
  { user: 'account-b', customer: 'account-a', allowed: false },
  { user: null, customer: 'account-a', allowed: false },
  { user: null, customer: null, allowed: false },
  { user: null, customer: '', allowed: false },
  { user: null, customer: '$RCAnonymousID:', allowed: false },
  { user: '', customer: '', allowed: false },
];
const statuses = ['ready', 'loading', 'error'];
const placements = { onboarding: 'welcome', settings: 'annual', campaign: null, empty: null, unset: null };
for (const identity of identities) {
  for (const entitlements of [[], ['premium'], ['other-product'], ['other-product', 'premium']]) {
    for (const [placement, offering] of Object.entries(placements)) {
      for (const auth of statuses) for (const customer of statuses) for (const offerings of statuses) {
        const state = {
          session: { status: auth, userId: identity.user },
          customer: { status: customer, appUserId: identity.customer, activeEntitlements: entitlements },
          offerings: { status: offerings, byPlacement: {
            onboarding: { identifier: 'welcome' }, settings: { identifier: 'annual' },
            empty: { identifier: '' }, unset: null,
          }, current: { identifier: 'unrelated-default' } },
          placement,
        };
        const ready = auth === 'ready' && customer === 'ready' && offerings === 'ready';
        const entitled = entitlements.includes('premium');
        const expected = ready && !entitled && identity.allowed ? offering : null;
        const group = !ready || entitled ? 'resource-and-entitlement-gates'
          : !identity.allowed || expected ? 'anonymous-and-identified-eligibility' : 'placement-specific-offering';
        check(group, state, expected);
      }
    }
  }
}
process.stdout.write(JSON.stringify({ checks, executedChecks, failedChecks,
  failedGroups: [...failures].sort(), counterexamples, loadError }) + '\n');
