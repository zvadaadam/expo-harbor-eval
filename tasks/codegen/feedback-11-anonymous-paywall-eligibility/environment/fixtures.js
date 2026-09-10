const ready = {
  session: { status: 'ready', userId: null },
  customer: { status: 'ready', appUserId: '$RCAnonymousID:fresh', activeEntitlements: [] },
  offerings: {
    status: 'ready',
    byPlacement: { onboarding: { identifier: 'welcome' }, settings: { identifier: 'annual' } },
    current: { identifier: 'unrelated-default' },
  },
  placement: 'onboarding',
};

const fixtures = [
  { label: 'Fresh install', state: ready },
  { label: 'Signed in', state: { ...ready, session: { status: 'ready', userId: 'account-a' },
    customer: { ...ready.customer, appUserId: 'account-a' } } },
  { label: 'Logged out', state: { ...ready, customer: { ...ready.customer, appUserId: '$RCAnonymousID:after-logout' } } },
  { label: 'Premium', state: { ...ready, customer: { ...ready.customer, activeEntitlements: ['premium'] } } },
  { label: 'Switching accounts', state: { ...ready, session: { status: 'ready', userId: 'account-b' },
    customer: { ...ready.customer, appUserId: 'account-a' } } },
  { label: 'Loading customer', state: { ...ready, customer: { ...ready.customer, status: 'loading' } } },
  { label: 'Customer error', state: { ...ready, customer: { ...ready.customer, status: 'error' } } },
  { label: 'Settings placement', state: { ...ready, placement: 'settings' } },
  { label: 'Unassigned placement', state: { ...ready, placement: 'campaign' } },
];

module.exports = { fixtures };
