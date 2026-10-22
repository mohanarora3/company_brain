// Meterless bridge: serves the Meterless H-MEM and World Model reference engines
// to the Python agents over a small local JSON API.
//
//   node --experimental-transform-types server.ts        (Node 22.7+, no npm install needed)
//
// The engines are the unmodified Apache-2.0 reference implementations from
// github.com/Meterless/Meterless (engines/hmem/reference, engines/world-model/reference),
// vendored into ./vendor by `npm run setup`. Nothing here re-implements them: every
// route below calls a named engine service.
//
// One namespace per company dataset (e.g. "acme-seed-42"). State persists under
// METERLESS_STATE_DIR (default ../.lastday/meterless): H-MEM writes state.json +
// an append-only ledger.jsonl; the World Model writes an event log.

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.METERLESS_BRIDGE_PORT ?? 7077);
const STATE = path.resolve(process.env.METERLESS_STATE_DIR ?? path.join(here, "..", ".lastday", "meterless"));
const ENGINES = process.env.METERLESS_ENGINES_DIR; // optional: a Meterless checkout's engines/ folder

function enginePath(name: "hmem" | "world-model"): { entry: string; label: string } {
  const candidates = [
    ENGINES && { entry: path.join(ENGINES, name, "reference", "src", "index.ts"), label: `METERLESS_ENGINES_DIR/${name}` },
    { entry: path.join(here, "vendor", name, "src", "index.ts"), label: `vendor/${name}` },
  ].filter(Boolean) as { entry: string; label: string }[];
  for (const c of candidates) if (fs.existsSync(c.entry)) return c;
  console.error(`Meterless ${name} engine not found. Run: cd meterless-bridge && npm run setup`);
  process.exit(1);
}

const hmemSrc = enginePath("hmem");
const wmSrc = enginePath("world-model");
const { HMEM } = await import(pathToFileURL(hmemSrc.entry).href);
const { WorldModel } = await import(pathToFileURL(wmSrc.entry).href);
const PIN = (() => {
  try { return fs.readFileSync(path.join(here, "vendor", "PINNED_COMMIT"), "utf-8").trim(); } catch { return "unknown"; }
})();

// Source priority for conflicting facts: what the expert said in an exit interview
// beats a Slack answer, which beats a ticket, which beats a stale wiki page.
const SOURCE_PRIORITY = ["interview", "slack", "jira", "pagerduty", "github", "docs", "agent"];

type NS = { hmem: any; wm: any };
const namespaces = new Map<string, NS>();

function ns(name: string): NS {
  if (!/^[a-z0-9-]{1,64}$/.test(name)) throw new HttpError(400, "bad namespace");
  let n = namespaces.get(name);
  if (!n) {
    const dir = path.join(STATE, name);
    fs.mkdirSync(dir, { recursive: true });
    n = {
      hmem: new HMEM({ persistDir: path.join(dir, "hmem"), actor: "last-day" }),
      wm: new WorldModel({ namespace: name, storage: "local", directory: dir, conflictPolicy: "source-priority",
                           sourcePriority: SOURCE_PRIORITY }),
    };
    namespaces.set(name, n);
  }
  return n;
}

class HttpError extends Error {
  status: number;
  constructor(status: number, msg: string) { super(msg); this.status = status; }
}

function strip(m: any): any {
  if (!m) return m;
  const { embedding, ...rest } = m;
  return rest;
}

async function body(req: http.IncomingMessage): Promise<any> {
  const chunks: Buffer[] = [];
  for await (const c of req) chunks.push(c as Buffer);
  const text = Buffer.concat(chunks).toString("utf-8");
  return text ? JSON.parse(text) : {};
}

// ------------------------------------------------------------------ H-MEM routes
async function hmemRoute(n: NS, rest: string[], q: URLSearchParams, b: any, method: string): Promise<any> {
  const h = n.hmem;
  const [op, arg] = rest;
  if (op === "add" && method === "POST") {
    // MemoryStoreService.add: source is mandatory; enrichment + ledger "create".
    const rec = h.add({ content: b.content, type: b.type ?? "factual", layer: b.layer, tags: b.tags ?? [],
                        confidence: b.confidence, source: b.source,
                        provenance: b.provenance ? { learnedAt: Date.now(), ...b.provenance } : undefined,
                        missionId: b.missionId, derivedFrom: b.derivedFrom });
    return strip(rec);
  }
  if (op === "mine" && method === "POST") {
    // MemoryMiningService.mineInteraction: model-free extraction.
    return (await h.mine(b.event ?? "chat_message", b.text)).map(strip);
  }
  if (op === "query" && method === "POST") {
    // MemoryRetrievalService.query: hybrid ranking, reinjection block and trace.
    const r = h.query(b.query, { topN: b.topN, threshold: b.threshold });
    return { memories: r.memories.map((x: any) => ({ relevance: x.relevance, memory: strip(x.memory) })),
             context: r.context, trace: r.trace };
  }
  if (op === "feedback" && method === "POST") {
    h.feedback(b.id, b.kind);
    return strip(h.store.get(b.id));
  }
  if (op === "audit" && arg) {
    // TrustLedgerService.history: the append-only change record of one memory.
    return { memory: strip(h.store.get(arg)), history: h.ledger.history(arg) };
  }
  if (op === "memories") {
    const tag = q.get("tag");
    const limit = Number(q.get("limit") ?? 500);
    return h.store.all().filter((m: any) => !tag || m.tags.includes(tag)).slice(-limit).map(strip);
  }
  if (op === "conflicts" && method === "POST") {
    // ConflictDetectionService.scan + autoResolve (losers are superseded, never deleted).
    const found = h.conflicts.scan();
    const out = found.map((c: any) => ({ ...c, a: strip(h.store.get(c.memoryA)), b: strip(h.store.get(c.memoryB)) }));
    if (b.autoResolve) for (const c of found) c.outcome = h.conflicts.autoResolve(c);
    return { conflicts: out, queue: h.conflicts.queue() };
  }
  if (op === "sleep" && method === "POST") {
    // SleepCycleService: preview first; execute takes a backup before changing anything.
    const preview = h.sleep.preview();
    if (!b.execute) return { preview };
    return { preview, report: h.sleep.execute(preview) };
  }
  if (op === "stats") {
    const all = h.store.all();
    const layers: Record<string, number> = {};
    for (const m of all) layers[m.layer] = (layers[m.layer] ?? 0) + 1;
    return { memories: all.length, layers, ledger: h.ledger.stats() };
  }
  throw new HttpError(404, `unknown H-MEM route ${op}`);
}

// ------------------------------------------------------------ World Model routes
async function wmRoute(n: NS, rest: string[], q: URLSearchParams, b: any, method: string): Promise<any> {
  const wm = n.wm;
  const [op, arg] = rest;
  if (op === "batch" && method === "POST") {
    // Every write goes through the engine's single-writer queue and needs provenance.
    const results: any[] = [];
    for (const o of b.ops ?? []) {
      try {
        if (o.op === "entity") results.push((await wm.upsertEntity(o)).id);
        else if (o.op === "context") results.push((await wm.upsertContext(o)).id);
        else if (o.op === "relate") results.push((await wm.relate(o)).id);
        else if (o.op === "fact") {
          const f = await wm.assertFact(o);
          const live = wm.view("facts").about(f.about).filter((x: any) => x.predicate === o.predicate);
          results.push({ id: f.id, supersededBy: wm.view("facts").about(f.about).find((x: any) => x.id === f.id)?.supersededBy,
                         rivals: live.map((x: any) => ({ id: x.id, value: x.value, source: x.source, supersededBy: x.supersededBy })) });
        } else results.push({ error: `unknown op ${o.op}` });
      } catch (e: any) {
        results.push({ error: String(e?.message ?? e) });
      }
    }
    return { results };
  }
  const graph = wm.view("graph");
  if (op === "entity" && arg) return { entity: graph.entity(decodeURIComponent(arg)) ?? null };
  if (op === "neighbors") return graph.neighborsOf(q.get("id"), { via: q.get("via") ?? undefined, at: q.get("at") ?? undefined });
  if (op === "incoming") return graph.incoming(q.get("id"), { via: q.get("via") ?? undefined });
  if (op === "facts" && arg) return wm.view("facts").about(decodeURIComponent(arg));
  if (op === "entity-at") return { entity: wm.view("snapshot").entityAt(q.get("id"), q.get("at")) ?? null };
  if (op === "query") return graph.query({ type: q.get("type") ?? undefined });
  if (op === "audit") {
    const limit = Number(q.get("limit") ?? 100);
    return wm.audit().slice(-limit);
  }
  if (op === "relationships") {
    const type = q.get("type");
    const id = q.get("id");
    const all = wm.events().filter((e: any) => e.kind === "relate").map((e: any) => e.payload);
    const state = new Map<string, any>();
    for (const r of all) state.set(r.id, r);
    // Report closed edges too, so the UI can show ownership history (bitemporal validFrom/validTo).
    const live = [...state.keys()].map((rid) => wm["store"].state.relationships.get(rid) ?? state.get(rid));
    return live.filter((r: any) => (!type || r.type === type) && (!id || r.from === id || r.to === id));
  }
  if (op === "merge-queue") return wm.mergeQueue();
  if (op === "stats") {
    const ents = graph.query({});
    const byType: Record<string, number> = {};
    for (const e of ents) byType[e.type] = (byType[e.type] ?? 0) + 1;
    return { entities: ents.length, byType, events: wm.events().length, audit: wm.audit().length };
  }
  throw new HttpError(404, `unknown World Model route ${op}`);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const parts = url.pathname.split("/").filter(Boolean);
  res.setHeader("Content-Type", "application/json");
  try {
    let out: any;
    if (parts[0] === "health") {
      out = { ok: true, engines: { hmem: hmemSrc.label, worldModel: wmSrc.label }, pinnedCommit: PIN,
              node: process.version, namespaces: [...namespaces.keys()], stateDir: STATE };
    } else if (parts[0] === "hmem" && parts[1]) {
      out = await hmemRoute(ns(parts[1]), parts.slice(2), url.searchParams, req.method === "POST" ? await body(req) : {}, req.method ?? "GET");
    } else if (parts[0] === "wm" && parts[1]) {
      out = await wmRoute(ns(parts[1]), parts.slice(2), url.searchParams, req.method === "POST" ? await body(req) : {}, req.method ?? "GET");
    } else if (parts[0] === "reset" && parts[1] && req.method === "POST") {
      namespaces.delete(parts[1]);
      fs.rmSync(path.join(STATE, parts[1]), { recursive: true, force: true });
      out = { reset: parts[1] };
    } else {
      throw new HttpError(404, "not found");
    }
    res.end(JSON.stringify(out ?? null));
  } catch (e: any) {
    res.statusCode = e instanceof HttpError ? e.status : 500;
    res.end(JSON.stringify({ error: String(e?.message ?? e) }));
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`meterless-bridge on http://127.0.0.1:${PORT} | H-MEM: ${hmemSrc.label} | World Model: ${wmSrc.label} | pin ${PIN}`);
});
