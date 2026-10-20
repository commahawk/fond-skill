// The player's ENGINE block against the skill script (recipe-authoring "The player":
// "engine parity with plan"). derive() and simulate() are checked against `plan --json`
// over the random states the Python driver generated; minutesLeft, the tap flows and
// fmtMinutes against hand-worked cases over the fixture rows.
// Usage: node parity.mjs <player.template.html> <payload.json> <cases.json>
import { readFileSync } from "node:fs";
import vm from "node:vm";

function loadEngine(tplPath) {
  const tpl = readFileSync(tplPath, "utf8");
  const start = tpl.indexOf("// ===== ENGINE START"), end = tpl.indexOf("// ===== ENGINE END");
  if (start < 0 || end < 0) throw new Error("ENGINE markers not found in " + tplPath);
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(tpl.slice(start, end) + "\nthis.FondEngine = FondEngine;", ctx);
  return ctx.FondEngine;
}

const [tplPath, dataPath, casesPath] = process.argv.slice(2);
const E = loadEngine(tplPath);
const data = JSON.parse(readFileSync(dataPath, "utf8"));
const byRid = Object.fromEntries(data.recipes.map(r => [r.id, r]));
const cases = JSON.parse(readFileSync(casesPath, "utf8"));
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
let fails = 0;
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!cond) fails++; };

// 1. derive/simulate parity with `plan --json` over every generated state.
let bad = 0;
const shown = [];
for (const c of cases) {
  const r = byRid[c.rid];
  if (!r) { bad++; if (shown.length < 8) shown.push({ rid: c.rid, bad: "recipe missing from the payload" }); continue; }
  const runN = new Map(c.running);
  const done = E.closure(r, c.done, c.running.map(x => x[0]));
  const got = E.derive(r, done, runN);
  const est = E.simulate(r, done, runN);
  const whole = Math.ceil(est - E.EPS);
  const diffs = [];
  if (!eq(got.available, c.expect.available)) diffs.push(["available", got.available, c.expect.available]);
  if (!eq(got.held, c.expect.held)) diffs.push(["held", got.held, c.expect.held]);
  if (!eq([...got.heldBy].sort(), [...c.expect.held_by].sort())) diffs.push(["held_by", got.heldBy, c.expect.held_by]);
  if (!eq(got.locked, c.expect.locked)) diffs.push(["locked", got.locked, c.expect.locked]);
  if (whole !== c.expect.estimate_minutes || Math.abs(est - c.expect.estimate_exact) > 1e-6) diffs.push(["estimate", est, c.expect.estimate_exact]);
  if (diffs.length) { bad++; if (shown.length < 8) shown.push({ rid: c.rid, done: c.done, running: c.running, diffs }); }
}
console.log(`derive/simulate parity: ${cases.length - bad}/${cases.length} cases match plan --json`);
for (const f of shown) console.log(JSON.stringify(f));
if (bad) fails++;
check("at least one case per payload recipe", data.recipes.every(r => cases.some(c => c.rid === r.id)));

// 2. minutesLeft: the SKILL.md rule, by hand over the fixture's steak and pasta rows
// (present in both export fixtures; a payload without them skips this block).
const M = 60000, t0 = 1_000_000_000_000;
const steak = byRid["rcp-steak-01"], pasta = byRid["rcp-pasta-02"];
if (steak && pasta) {
  const S = id => { const s = E.index(steak)[id]; if (!s) throw new Error("steak step missing: " + id); return s; };
  const P = id => { const s = E.index(pasta)[id]; if (!s) throw new Error("pasta step missing: " + id); return s; };
  const rs = (p, started) => ({ p, started, started0: started, n: 0, s: 1 });
  const hand = [
    // flatbreads: count=2, ~cook{3%min}, duration=4 (surplus 1). One minute into the first
    // countdown: 2 + 1 + (3 + 1) = 7 (SKILL.md "How long to go?").
    ["flatbreads 1 min in", E.minutesLeft(S("cook-the-flatbreads"), rs(0, t0), t0 + 1 * M, M), 7],
    ["flatbreads rang #1", E.minutesLeft(S("cook-the-flatbreads"), rs(0, t0), t0 + 3 * M, M), 5],
    ["flatbreads rang #1 + surplus out", E.minutesLeft(S("cook-the-flatbreads"), rs(0, t0), t0 + 4 * M + 1, M), 4],
    ["flatbreads #2 30 s in", E.minutesLeft(S("cook-the-flatbreads"), rs(1, t0), t0 + 0.5 * M, M), 4],
    ["flatbreads #2 all out", E.minutesLeft(S("cook-the-flatbreads"), rs(1, t0), t0 + 5 * M, M), 0],
    // segments 5 then 10: 2 min into the 5: 3 + 10 = 13; rang on the 5, waiting: 0 + 10
    ["rest-the-dough 2 min in", E.minutesLeft(S("rest-the-dough"), rs(0, t0), t0 + 2 * M, M), 13],
    ["rest-the-dough rang part 1", E.minutesLeft(S("rest-the-dough"), rs(0, t0), t0 + 6 * M, M), 10],
    // simmer: ~simmer{20%min} with duration 22 (surplus 2): 19 min in -> 1 + 2 = 3; rang 1 min ago -> 1
    ["simmer 19 min in", E.minutesLeft(S("simmer-the-sauce"), rs(0, t0), t0 + 19 * M, M), 3],
    ["simmer rang 1 min ago", E.minutesLeft(S("simmer-the-sauce"), rs(0, t0), t0 + 21 * M, M), 1],
    ["simmer all out", E.minutesLeft(S("simmer-the-sauce"), rs(0, t0), t0 + 22 * M + 1, M), 0],
    // 30-second legacy timer: 1 until it rings, then 0
    ["30 s timer, 10 s in", E.minutesLeft(P("4"), rs(0, t0), t0 + 10000, M), 1],
    ["30 s timer rang", E.minutesLeft(P("4"), rs(0, t0), t0 + 31000, M), 0],
    // legacy repeat x2 of 1 min: first, 20 s in -> 1 + 1 = 2; waiting after first ring -> 1
    ["puff #1 20 s in", E.minutesLeft(P("3"), rs(0, t0), t0 + 20000, M), 2],
    ["puff rang #1", E.minutesLeft(P("3"), rs(0, t0), t0 + 61000, M), 1],
  ];
  for (const [name, got, want] of hand) check("minutesLeft " + name + " = " + got, got === want, got === want ? "" : "(want " + want + ")");

  // 3. Tap flows: a timer step takes one tap per countdown plus one to resolve; a ring
  // never resolves; a held step does nothing; a locked step does nothing; every run entry
  // carries started0, n and s.
  function flow(r, ids) {
    let st = E.freshState(r, t0, M);
    const events = [];
    let now = t0;
    for (const id of ids) { now += 1000; const res = E.tap(r, st, id, now); events.push(res.event); st = res.state; }
    return { events, st };
  }
  const f1 = flow(pasta, ["3", "3", "3"]);
  check("tap flow puff x2: start > advance > resolve", eq(f1.events, ["start", "advance", "resolve"]) && f1.st.done.length === 1, f1.events.join(" > "));
  const f1b = flow(pasta, ["3"]);
  const entry = f1b.st.run[0][1];
  check("a started run carries p, started, started0, n and s", entry.p === 0 && entry.started === entry.started0 && entry.n === 2 && entry.s === 1, JSON.stringify(entry));
  const f1c = flow(pasta, ["3", "3"]);
  const adv = f1c.st.run[0][1];
  check("advancing into the next iteration moves started0", adv.p === 1 && adv.started0 === adv.started && adv.started > entry.started, JSON.stringify(adv));
  const f2 = flow(steak, ["toast-the-spices", "griddle-the-corn-cakes"]);
  check("an occupying timer holds hands-on work", eq(f2.events, ["start", "held"]), f2.events.join(" > "));
  const f3 = flow(pasta, ["8"]);
  check("a tap on a locked step does nothing", eq(f3.events, ["locked"]), f3.events.join(" > "));
  const f4 = flow(pasta, ["5", "9", "9"]);
  check("a cue step resolves on tap; a timer resolves on the second tap", eq(f4.events, ["resolve", "start", "resolve"]), f4.events.join(" > "));
  const f5 = flow(steak, ["rest-the-dough", "rest-the-dough"]);
  const rest = f5.st.run[0][1];
  check("advancing within an iteration keeps started0", rest.p === 1 && rest.started0 < rest.started && rest.s === 2, JSON.stringify(rest));
  check("a fresh state is stamped with h, t and u", f1.st.h === pasta.h && Array.isArray(f1.st.t) && Array.isArray(f1.st.u) && f1.st.v === 2);
} else {
  console.log("hand-worked minutesLeft and tap cases skipped: the steak and pasta rows are not in this payload");
}

// 4. fmtMinutes vs the script's fmt_minutes
const fm = [[0.5, "30 seconds"], [12, "12 min"], [1.5, "1.5 min"], [90, "1 hr 30 min"], [1080, "18 hr"], [0, "0 min"]];
for (const [m, want] of fm) { const got = E.fmtMinutes(m); check(`fmtMinutes(${m}) = ${got}`, got === want, got === want ? "" : "(want " + want + ")"); }

console.log(fails ? `\n${fails} FAILED` : "\nall parity checks pass");
process.exit(fails ? 1 : 0);
