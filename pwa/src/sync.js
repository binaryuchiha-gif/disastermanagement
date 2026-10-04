// Offline sync queue for SOS + hazard reports. Idempotent uploads with
// client-generated UUIDs; last-writer-wins conflict policy by timestamp.
// Uses IndexedDB in the browser; falls back to an in-memory map under node so
// the queue logic is unit-testable without a browser.

const DB_NAME = "resqflow-x";
const STORE = "outbox";

let memStore = null; // node fallback

async function getStore(mode = "readonly") {
  if (typeof indexedDB === "undefined") {
    if (!memStore) memStore = new Map();
    return { mem: memStore, mode };
  }
  const db = await new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return { db, tx: db.transaction(STORE, mode).objectStore(STORE), mode };
}

export async function queueItem(kind, payload) {
  const item = { ...payload, kind, _queuedAt: Date.now(), _sent: false };
  const s = await getStore("readwrite");
  if (s.mem) { s.mem.set(item.id, item); return item; }
  return new Promise((resolve, reject) => {
    const req = s.tx.put(item);
    req.onsuccess = () => resolve(item);
    req.onerror = () => reject(req.error);
  });
}

export const queueSOS = (p) => queueItem("sos", p);
export const queueReport = (p) => queueItem("report", p);

export async function pending() {
  const s = await getStore();
  if (s.mem) return [...s.mem.values()].filter((i) => !i._sent);
  return new Promise((resolve) => {
    const out = [];
    s.tx.openCursor().onsuccess = (e) => {
      const cur = e.target.result;
      if (cur) { if (!cur.value._sent) out.push(cur.value); cur.continue(); }
      else resolve(out);
    };
  });
}

// Idempotent flush: POST each pending item with its UUID; server dedupes by id.
export async function flush(postFn) {
  const items = await pending();
  const results = [];
  for (const item of items) {
    try {
      const ok = await postFn(item); // server returns true on accept/dedupe
      if (ok) { item._sent = true; await markSent(item); results.push({ id: item.id, ok: true }); }
      else results.push({ id: item.id, ok: false });
    } catch {
      results.push({ id: item.id, ok: false, retry: true });
    }
  }
  return results;
}

async function markSent(item) {
  const s = await getStore("readwrite");
  if (s.mem) { s.mem.set(item.id, item); return; }
  s.tx.put(item);
}

// Conflict resolution: last-writer-wins by timestamp for report-status updates.
export function resolveConflict(local, remote) {
  if (!remote) return local;
  if (!local) return remote;
  return (local.ts || 0) >= (remote.ts || 0) ? local : remote;
}

// test helper
export function _resetMem() { memStore = new Map(); }
