export function calculateTrust(peer, globalStats = {}) {
  const successRate = peer.successCount + peer.failCount > 0
    ? peer.successCount / (peer.successCount + peer.failCount)
    : 0.5;

  const firstSeen = new Date(peer.firstSeen || Date.now()).getTime();
  const ageDays = (Date.now() - firstSeen) / (1000 * 60 * 60 * 24);
  const age = Math.min(ageDays / 30, 1);

  const uptime = peer.uptime || 0.95;
  const threatRatio = peer.threatCount
    ? Math.max(0, 1 - (peer.threatCount / Math.max(peer.successCount + peer.failCount, 1)))
    : 1;

  const score = (
    0.4 * successRate +
    0.2 * uptime +
    0.2 * threatRatio +
    0.2 * age
  );

  return {
    score: Math.round(score * 1000) / 1000,
    factors: { successRate, uptime, threatRatio, age },
    threshold: 0.3,
    trusted: score >= 0.3,
  };
}

export function updatePeerOutcome(peersData, peerId, success) {
  const peer = peersData[peerId];
  if (!peer) return null;

  if (success) {
    peer.successCount = (peer.successCount || 0) + 1;
  } else {
    peer.failCount = (peer.failCount || 0) + 1;
  }
  peer.lastSeen = new Date().toISOString();

  return calculateTrust(peer);
}
