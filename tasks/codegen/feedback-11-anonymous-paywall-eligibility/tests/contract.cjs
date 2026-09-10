// Offline authoring checks for the supplied controls. This is not the Harbor
// judge and does not verify native rendering or execute a model submission.
'use strict';
const { getPaywallOffering } = require(require('node:path').resolve(process.argv[2]));
const assert = require('node:assert/strict');
const failures = new Set();
let checks = 0;

function freeze(value) {
  if (value && typeof value === 'object') {
    for (const nested of Object.values(value)) freeze(nested);
    Object.freeze(value);
  }
  return value;
}

function check(group, state, expected) {
  checks++;
  const before = JSON.stringify(state);
  try {
    assert.equal(getPaywallOffering(freeze(state)), expected);
    assert.equal(JSON.stringify(state), before);
  } catch {
    failures.add(group);
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
process.stdout.write(JSON.stringify({ checks, failedGroups: [...failures].sort() }) + '\n');
