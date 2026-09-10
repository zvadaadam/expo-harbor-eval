function getPaywallOffering({ session, customer, offerings, placement }) {
  if ([session, customer, offerings].some((resource) => resource.status !== 'ready')) return null;
  const id = customer.appUserId;
  const identityReady = session.userId === null
    ? typeof id === 'string' && id.startsWith('$RCAnonymousID:') && id.length > '$RCAnonymousID:'.length
    : typeof session.userId === 'string' && session.userId.length > 0 && id === session.userId;
  if (!identityReady || customer.activeEntitlements.includes('premium')) return null;
  const offering = Object.hasOwn(offerings.byPlacement, placement) ? offerings.byPlacement[placement] : null;
  return typeof offering?.identifier === 'string' && offering.identifier.length > 0 ? offering.identifier : null;
}

module.exports = { getPaywallOffering };
