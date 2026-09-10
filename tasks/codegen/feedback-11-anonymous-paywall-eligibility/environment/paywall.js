function getPaywallOffering({ session, customer, offerings, placement }) {
  if (session.status !== 'ready' || customer.status !== 'ready' || offerings.status !== 'ready') return null;
  // Only identified customers can proceed to the placement paywall.
  if (!session.userId || customer.appUserId !== session.userId) return null;
  if (customer.activeEntitlements.includes('premium')) return null;
  return offerings.byPlacement[placement]?.identifier || null;
}

module.exports = { getPaywallOffering };
