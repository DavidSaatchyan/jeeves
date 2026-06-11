import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const crypto = require("crypto");

const KEYS_DIR = join(__dirname, "..", "..", ".openflo-data", "federation", "keys");

if (!existsSync(KEYS_DIR)) mkdirSync(KEYS_DIR, { recursive: true });

export function generateIdentity(name = "default") {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519", {
    publicKeyEncoding: { type: "spki", format: "pem" },
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
  });

  writeFileSync(join(KEYS_DIR, `${name}.pub`), publicKey);
  writeFileSync(join(KEYS_DIR, `${name}.key`), privateKey, { mode: 0o600 });

  const peerId = getPeerId(publicKey);
  return { peerId, publicKey, privateKey };
}

export function loadIdentity(name = "default") {
  const pubPath = join(KEYS_DIR, `${name}.pub`);
  const keyPath = join(KEYS_DIR, `${name}.key`);

  if (!existsSync(pubPath) || !existsSync(keyPath)) {
    return generateIdentity(name);
  }

  return {
    peerId: getPeerId(readFileSync(pubPath, "utf-8")),
    publicKey: readFileSync(pubPath, "utf-8"),
    privateKey: readFileSync(keyPath, "utf-8"),
  };
}

export function getPeerId(publicKeyPem) {
  const der = crypto.createPublicKey(publicKeyPem).export({ type: "spki", format: "der" });
  return crypto.createHash("sha256").update(der).digest("hex").slice(0, 16);
}

export function signMessage(privateKeyPem, payload) {
  const sign = crypto.createSign("sha256");
  sign.update(JSON.stringify(payload));
  sign.end();
  return sign.sign(privateKeyPem, "base64");
}

export function verifySignature(publicKeyPem, payload, signature) {
  const verify = crypto.createVerify("sha256");
  verify.update(JSON.stringify(payload));
  verify.end();
  try {
    return verify.verify(publicKeyPem, signature, "base64");
  } catch {
    return false;
  }
}

export function storePeer(peerId, publicKeyPem, metadata = {}) {
  const peersPath = join(KEYS_DIR, "..", "peers.json");
  let peers = {};
  try { peers = JSON.parse(readFileSync(peersPath, "utf-8")); } catch {}

  peers[peerId] = {
    peerId,
    publicKey: publicKeyPem,
    firstSeen: peers[peerId]?.firstSeen || new Date().toISOString(),
    lastSeen: new Date().toISOString(),
    successCount: peers[peerId]?.successCount || 0,
    failCount: peers[peerId]?.failCount || 0,
    ...metadata,
  };

  writeFileSync(peersPath, JSON.stringify(peers, null, 2));
  return peers[peerId];
}

export function getPeers() {
  const peersPath = join(KEYS_DIR, "..", "peers.json");
  try { return JSON.parse(readFileSync(peersPath, "utf-8")); } catch { return {}; }
}
