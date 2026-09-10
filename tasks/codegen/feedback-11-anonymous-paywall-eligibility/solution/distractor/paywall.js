function getPaywallOffering({ offerings, placement }) {
  // Let anonymous customers through by removing the restrictive early returns.
  return offerings.byPlacement[placement]?.identifier || offerings.current?.identifier || null;
}

module.exports = { getPaywallOffering };
