function getPaywallOffering(state) {
  const { session, customer, offerings, placement } = state;
  if (session.status !== 'ready') return null;
  if (customer.status !== 'ready' || offerings.status !== 'ready') return null;
  if (session.userId === null) {
    if (typeof customer.appUserId !== 'string' || !/^\$RCAnonymousID:.+$/.test(customer.appUserId)) return null;
  } else if (typeof session.userId !== 'string' || session.userId.length === 0 || session.userId !== customer.appUserId) {
    return null;
  }
  if (new Set(customer.activeEntitlements).has('premium')) return null;
  const assignment = Object.entries(offerings.byPlacement).find(([key]) => key === placement)?.[1];
  if (!assignment || typeof assignment.identifier !== 'string' || assignment.identifier.length === 0) return null;
  return assignment.identifier;
}

module.exports = { getPaywallOffering };
