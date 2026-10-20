// Reconcile-by-slug over the real ENGINE block (recipe-authoring "The player", design
// decision 11): the ten original cases and the seven gaps A–G, each over a payload the
// script built — the before/after pair from fixtures/local/sample-reconcile-*.md, the
// variant from fixtures/local/sample-variant.md with the export's steak row as its old
// shape — or a declared mutation of the before payload where the pair cannot express it.
// Usage: node reconcile.mjs <player.template.html> <before.json> <after.json> <variant.json> <export.json>
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

const [tplPath, beforePath, afterPath, variantPath, exportPath] = process.argv.slice(2);
const E = loadEngine(tplPath);
const one = p => { const d = JSON.parse(readFileSync(p, "utf8")); if (d.recipes.length !== 1) throw new Error(p + " must hold one recipe"); return d.recipes[0]; };
const BEFORE = one(beforePath), AFTER = one(afterPath), VARIANT = one(variantPath);
const EXPORT = JSON.parse(readFileSync(exportPath, "utf8"));
const STEAK = EXPORT.recipes.find(r => r.id === "rcp-steak-01");
if (!STEAK) throw new Error("the export payload must carry rcp-steak-01");
if (BEFORE.h === AFTER.h) throw new Error("the before/after fixtures must differ in h");
// The pair ships as two basenames so both can sit in fixtures/local/, but it stands for one
// file before and after an edit: a cook's state keys on the file's id, so the before payload
// takes the after's id here (reconcile refuses another recipe's state — case 10 below).
BEFORE.id = AFTER.id;

const MPM = 60000;
const now = Date.UTC(2026, 9, 10, 18, 0);
const min = n => n * MPM;
const clone = o => JSON.parse(JSON.stringify(o));
let fails = 0;
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!cond) fails++; };
const stepOf = (r, id) => E.index(r)[id];
const runOf = (s, id) => { const e = s.run.find(x => x[0] === id); return e ? e[1] : null; };
const doneAt = (s, id) => { const e = s.done.find(x => x[0] === id); return e ? e[1] : null; };
const runEntry = (p, started, started0, n, s) => ({ p, started, started0, n, s });
// An old state at `old`'s version: stamped with its h and its timer/untimed lists.
const stateOn = (old, done, run) => E.stamp(old, { v: 2, rid: old.id, mpm: MPM, startedAt: now - min(30), done, run });
const toTimer = (s, mins) => { s.kind = "timer"; s.phases = mins.map((m, i) => ({ min: m, label: m + " min", iter: 1, iters: 1, seg: i + 1, segs: mins.length })); s.segs = mins.length; s.iters = 1; s.timer_total = mins.reduce((a, b) => a + b, 0); s.scheduled = Math.max(s.scheduled, s.timer_total); s.surplus = 0; };
const toPlain = s => { s.kind = "hands-on"; s.phases = []; s.segs = 0; s.iters = 1; s.timer_total = 0; s.surplus = 0; };
const mutated = (base, h, mutate, aliases) => { const r = clone(base); r.h = h; mutate(r); if (aliases) r.aliases = aliases; return r; };
function recon(name, recipe, state) {
  const res = E.reconcile(recipe, state, now);
  check(name + ": the reconciled state fits the new recipe", res.state && E.fits(recipe, res.state), res.state ? "" : res.toast);
  check(name + ": the reconciled state is stamped with the new h", res.state && res.state.h === recipe.h && res.state.rid === recipe.id);
  return res;
}

// ---- the file pair: before -> after ---------------------------------------------------
// before: rest [5, 10]; toast [2]; boil (plain); sear [2 × 2]; griddle [3] × 3; blanch (plain); plate
// after:  rest [15]; toast; boil ~boil{6%min}; sear split into first/second side [2] each;
//         griddle [3] × 2; blanch retitled without a rename entry; plate
check("before/after: the after payload carries the declared aliases only",
  JSON.stringify(AFTER.aliases) === JSON.stringify({ "sear-the-steak": ["sear-the-first-side", "sear-the-second-side"] }));
check("F: every payload row carries an 8-hex h", [BEFORE, AFTER, VARIANT, ...EXPORT.recipes].every(E.hasStamp));

{ // 1. a sigil gained before start: boil-the-water is a timer now, still available, not running; named in the toast
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(0, now - min(1), now - min(1), 2, 2)]]);
  const { state, toast } = recon("1 sigil gained", AFTER, st);
  const v = E.view(AFTER, state, now);
  check("1 boil-the-water is a timer tile, available, not started", E.isTimer(stepOf(AFTER, "boil-the-water")) && v.available.includes("boil-the-water") && !runOf(state, "boil-the-water"));
  check("1 the toast names it", toast.includes(" Boil the Water is now a timer."), toast);
  check("1 toast-the-spices stays done at its time", doneAt(state, "toast-the-spices") === now - min(5));
}
{ // 4. a done atom gains a sigil → stays done at the same time, and is not called "now a timer"
  const at = now - min(20);
  const st = stateOn(BEFORE, [["boil-the-water", at]], []);
  const { state, toast } = recon("4 done gains sigil", AFTER, st);
  check("4 done stays done with its time", doneAt(state, "boil-the-water") === at && !toast.includes("Boil the Water is now a timer"), toast);
}
{ // B. [5, 10] merged to [15] four minutes into the second phase: 9 elapsed, 6 left
  const st = stateOn(BEFORE, [], [["rest-the-batter", runEntry(1, now - min(4), now - min(9), 2, 2)]]);
  const { state } = recon("B merge", AFTER, st);
  const rs = runOf(state, "rest-the-batter");
  check("B p=0 of 1, started at the iteration's first start", rs && rs.p === 0 && rs.n === 1 && rs.s === 1 && rs.started === now - min(9) && rs.started0 === now - min(9), JSON.stringify(rs));
  check("B minutes left = 6, not 11", rs && E.minutesLeft(stepOf(AFTER, "rest-the-batter"), rs, now, MPM) === 6, rs && String(E.minutesLeft(stepOf(AFTER, "rest-the-batter"), rs, now, MPM)));
}
{ // G. count=3 → count=2 while on the third iteration: shown rung, no minutes left
  const st = stateOn(BEFORE, [["rest-the-batter", now - min(20)]], [["griddle-the-cakes", runEntry(2, now - min(1), now - min(1), 3, 1)]]);
  const { state } = recon("G count change", AFTER, st);
  const rs = runOf(state, "griddle-the-cakes");
  const s = stepOf(AFTER, "griddle-the-cakes");
  check("G payload rebuilt by the script: phases[].iters consistent", s.phases.length === 2 && s.phases.every(p => p.iters === 2) && s.iters === 2);
  check("G clamped to the last phase, shown rung", rs && rs.p === 1 && rs.n === 2 && E.phaseState(s, rs, now, MPM).rung, JSON.stringify(rs));
  check("G minutesLeft = 0", rs && E.minutesLeft(s, rs, now, MPM) === 0, rs && String(E.minutesLeft(s, rs, now, MPM)));
}
{ // A. a two-phase sear split into two atoms while on phase 2: the second child runs with its start kept, the first is done
  const t3 = now - min(1);
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(1, t3, t3 - min(2), 2, 2)]]);
  const { state, toast } = recon("A phase-2 split", AFTER, st);
  const rs = runOf(state, "sear-the-second-side");
  check("A second side runs at p=0 with the phase's start kept", rs && rs.p === 0 && rs.started === t3 && rs.n === 1, JSON.stringify(state.run));
  check("A first side is done at the iteration's first start", doneAt(state, "sear-the-first-side") === t3 - min(2));
  check("A minutes left = 1", rs && E.minutesLeft(stepOf(AFTER, "sear-the-second-side"), rs, now, MPM) === 1);
  check("A the toast counts 1 kept, 1 running", toast.startsWith("Recipe updated. Kept 1 done, 1 running."), toast);
  check("A nothing dropped", !toast.includes("Dropped"), toast);
}
{ // 5a. a split while on phase 1: the first child runs, the second is locked behind it
  const t3 = now - min(1);
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(0, t3, t3, 2, 2)]]);
  const { state } = recon("5a phase-1 split", AFTER, st);
  const rs = runOf(state, "sear-the-first-side");
  const v = E.view(AFTER, state, now);
  check("5a first side runs with its start, second side locked, nothing done by the split", rs && rs.started === t3 && v.locked.includes("sear-the-second-side") && doneAt(state, "sear-the-first-side") === null);
}
{ // 5b. a done split: every child done at the old time
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)], ["sear-the-steak", now - min(1)]], []);
  const { state, toast } = recon("5b done split", AFTER, st);
  check("5b both children done at the old time", ["sear-the-first-side", "sear-the-second-side"].every(id => doneAt(state, id) === now - min(1)));
  check("5b the toast counts the old entries kept", toast.startsWith("Recipe updated. Kept 2 done, 0 running."), toast);
}
{ // 6. a done slug vanished (retitled without a rename entry): dropped and named; the retitled step is simply available
  const st = stateOn(BEFORE, [["boil-the-water", now - min(6)], ["blanch-the-greens", now - min(2)]], []);
  const { state, toast } = recon("6 vanished slug", AFTER, st);
  check("6 dropped and named as no longer in the recipe", !state.done.some(d => d[0] === "blanch-the-greens") && toast.includes(" Dropped: Blanch the greens (no longer in the recipe)."), toast);
  check("6 the retitled step is available", E.view(AFTER, state, now).available.includes("blanch-the-rabe"));
  check("6 the toast counts only what was kept", toast.startsWith("Recipe updated. Kept 1 done, 0 running."), toast);
}
{ // E. a fresh cook and a pasted line both carry the payload's h, so a reopen reconciles nothing
  const fresh = E.freshState(AFTER, now, MPM);
  check("E a fresh state is stamped with h", fresh.h === AFTER.h && fresh.v === 2 && E.fits(AFTER, fresh));
  const clock = ms => new Date(ms).toISOString().slice(11, 16);
  const line = E.stateLine(AFTER, stateOn(AFTER, [["toast-the-spices", now - min(5)]], []), now, clock).line;
  const parsed = E.parseLine(AFTER, line, now, MPM, {});
  check("E a parsed line is stamped with h", !parsed.error && parsed.state.h === AFTER.h && parsed.state.v === 2, parsed.error || "");
  check("E a tap keeps the stamp", E.tap(AFTER, fresh, "toast-the-spices", now).state.h === AFTER.h);
}
{ // F. the line carries h=<8hex>, never undefined, for a nodes row too
  const nodes = EXPORT.recipes.find(r => r.source === "nodes");
  const clock = ms => new Date(ms).toISOString().slice(11, 16);
  const line = E.stateLine(nodes, E.freshState(nodes, now, MPM), now, clock).line;
  check("F a nodes row's line reads h=<8hex>", new RegExp(" h=" + nodes.h + "(?: |$)").test(line) && !line.includes("undefined"), line);
}

// ---- declared mutations of the before payload (what the pair cannot express) ----------
{ // C. split whose first child is not a timer: the run goes to the timer child with its start kept, pat-dry is done, nothing dropped
  const R1 = mutated(BEFORE, "0c0c0c0c", r => {
    const i = r.steps.findIndex(s => s.id === "sear-the-steak");
    const a = { id: "pat-the-steak-dry", ordinal: 0, title: "Pat the Steak Dry", text: "Pat the steak dry.", kind: "instant", occupies: true, scheduled: 0, deps: clone(r.steps[i].deps), rank: r.steps[i].rank, prep: false, needs: [], done_when: null, phases: [], segs: 0, iters: 1, timer_total: 0, surplus: 0, structure: "", timing: "", source: "dsl" };
    const b = clone(r.steps[i]); b.id = "sear-both-sides"; b.title = "Sear Both Sides"; b.deps = ["pat-the-steak-dry"];
    r.steps.splice(i, 1, a, b);
    for (const s of r.steps) s.deps = s.deps.map(d => d === "sear-the-steak" ? "sear-both-sides" : d);
  }, { "sear-the-steak": ["pat-the-steak-dry", "sear-both-sides"] });
  const t1 = now - min(1);
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(0, t1, t1, 2, 2)]]);
  const { state, toast } = recon("C non-timer first child", R1, st);
  const rs = runOf(state, "sear-both-sides");
  check("C the run moved to the timer child with its start kept", rs && rs.p === 0 && rs.started === t1 && rs.n === 2, JSON.stringify(state.run));
  check("C pat-dry is done, nothing dropped", doneAt(state, "pat-the-steak-dry") === t1 && !toast.includes("Dropped") && !toast.includes("no longer a timer"), toast);
}
{ // C'. a split with MORE children than phases (two prep children, then the timer) while on
  // phase 2: R2 hands the run to the first timer child, which keeps the phase index and its start
  const plain = (id, title) => ({ id, ordinal: 0, title, text: "", kind: "instant", occupies: true, scheduled: 0, deps: [], rank: 0, prep: false, needs: [], done_when: null, phases: [], segs: 0, iters: 1, timer_total: 0, surplus: 0, structure: "", timing: "", source: "dsl" });
  const R1 = mutated(BEFORE, "0c0c0c0d", r => {
    const i = r.steps.findIndex(s => s.id === "sear-the-steak");
    const a = plain("pat-the-steak-dry", "Pat the Steak Dry"), b = plain("season-the-steak", "Season the Steak");
    b.deps = ["pat-the-steak-dry"];
    const c = clone(r.steps[i]); c.id = "sear-both-sides"; c.deps = ["season-the-steak"];
    r.steps.splice(i, 1, a, b, c);
    for (const s of r.steps) s.deps = s.deps.map(d => d === "sear-the-steak" ? "sear-both-sides" : d);
  }, { "sear-the-steak": ["pat-the-steak-dry", "season-the-steak", "sear-both-sides"] });
  const t1 = now - min(1);
  const st = stateOn(BEFORE, [], [["sear-the-steak", runEntry(1, t1, t1 - min(2), 2, 2)]]);
  const { state } = recon("C' phase 2 onto a same-shaped timer child", R1, st);
  const rs = runOf(state, "sear-both-sides");
  check("C' phase index and start kept", rs && rs.p === 1 && rs.started === t1 && rs.started0 === t1 - min(2), JSON.stringify(rs));
  check("C' the earlier children are done at the iteration's first start", doneAt(state, "pat-the-steak-dry") === t1 - min(2) && doneAt(state, "season-the-steak") === t1 - min(2));
}
{ // C''. a two-child split on phase 2 whose children match the phase count follows R1 even
  // when the second child is a two-phase timer: it starts that child's first phase at the
  // old phase's start (the spec resolves the split by count, never by inference)
  const R1 = mutated(BEFORE, "0c0c0c0e", r => {
    const i = r.steps.findIndex(s => s.id === "sear-the-steak");
    const a = { id: "pat-the-steak-dry", ordinal: 0, title: "Pat the Steak Dry", text: "", kind: "instant", occupies: true, scheduled: 0, deps: [], rank: 0, prep: false, needs: [], done_when: null, phases: [], segs: 0, iters: 1, timer_total: 0, surplus: 0, structure: "", timing: "", source: "dsl" };
    const b = clone(r.steps[i]); b.id = "sear-both-sides"; b.deps = ["pat-the-steak-dry"];
    r.steps.splice(i, 1, a, b);
    for (const s of r.steps) s.deps = s.deps.map(d => d === "sear-the-steak" ? "sear-both-sides" : d);
  }, { "sear-the-steak": ["pat-the-steak-dry", "sear-both-sides"] });
  const t1 = now - min(1);
  const st = stateOn(BEFORE, [], [["sear-the-steak", runEntry(1, t1, t1 - min(2), 2, 2)]]);
  const { state } = recon("C'' two children, two phases", R1, st);
  const rs = runOf(state, "sear-both-sides");
  check("C'' child[1] runs from the phase's start; child[0] is done", rs && rs.p === 0 && rs.started === t1 && doneAt(state, "pat-the-steak-dry") === t1 - min(2), JSON.stringify(rs));
}
{ // D. rename onto an id that is already done: one entry, the earlier time, the cook not cleared
  const R1 = mutated(BEFORE, "0d0d0d0d", r => {
    r.steps = r.steps.filter(s => s.id !== "toast-the-spices");
    for (const s of r.steps) s.deps = s.deps.map(d => d === "toast-the-spices" ? "boil-the-water" : d);
  }, { "toast-the-spices": ["boil-the-water"] });
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)], ["boil-the-water", now - min(4)]], []);
  const { state, toast } = recon("D rename onto a done id", R1, st);
  check("D one done entry at the earlier time", state.done.filter(d => d[0] === "boil-the-water").length === 1 && doneAt(state, "boil-the-water") === now - min(5), JSON.stringify(state.done));
  check("D both old entries count as kept", toast.startsWith("Recipe updated. Kept 2 done, 0 running."), toast);
}
{ // 7. a running timer loses its sigil: it leaves running, is available (its deps are done), and the toast says to tap it
  const R1 = mutated(BEFORE, "07070707", r => toPlain(stepOf(r, "sear-the-steak")));
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(0, now - min(1), now - min(1), 2, 2)]]);
  const { state, toast } = recon("7 sigil lost while running", R1, st);
  check("7 run dropped, step available", !state.run.length && E.view(R1, state, now).available.includes("sear-the-steak"));
  check("7 the toast says to tap it when it is done", toast.includes(" Sear the Steak is no longer a timer — tap it when it's done."), toast);
}
{ // 8. an inserted prerequisite of a running step is implied done; the run survives
  const R1 = mutated(BEFORE, "08080808", r => {
    const i = r.steps.findIndex(s => s.id === "sear-the-steak");
    r.steps.splice(i, 0, { id: "pat-the-steak-dry", ordinal: 0, title: "Pat the Steak Dry", text: "", kind: "instant", occupies: true, scheduled: 0, deps: [], rank: -1, prep: false, needs: [], done_when: null, phases: [], segs: 0, iters: 1, timer_total: 0, surplus: 0, structure: "", timing: "", source: "dsl" });
    stepOf(r, "sear-the-steak").deps.push("pat-the-steak-dry");
  });
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(0, now - min(1), now - min(1), 2, 2)]]);
  const { state } = recon("8 inserted prerequisite", R1, st);
  check("8 the new prerequisite is implied done now; the run survives", doneAt(state, "pat-the-steak-dry") === now && !!runOf(state, "sear-the-steak"));
}
{ // 2. 1 → 2 phases while running: the phase restarts from the iteration's first start, elapsed time kept
  const R1 = mutated(BEFORE, "02020202", r => toTimer(stepOf(r, "toast-the-spices"), [1, 1]));
  const st = stateOn(BEFORE, [], [["toast-the-spices", runEntry(0, now - 90000, now - 90000, 1, 1)]]);
  const { state } = recon("2 one phase becomes two", R1, st);
  const rs = runOf(state, "toast-the-spices");
  const ps = rs && E.phaseState(stepOf(R1, "toast-the-spices"), rs, now, MPM);
  check("2 p=0 of 2 from the iteration's first start; the first 1-min phase has rung", rs && rs.p === 0 && rs.n === 2 && rs.started === now - 90000 && ps.rung && ps.next.min === 1, JSON.stringify(rs));
  check("2 minutes left = 0 + the unstarted 1-min phase = 1", rs && E.minutesLeft(stepOf(R1, "toast-the-spices"), rs, now, MPM) === 1);
}
{ // 3. 2 → 1 phases while on phase 2 (merge within the iteration): elapsed time kept
  const R1 = mutated(BEFORE, "03030303", r => toTimer(stepOf(r, "sear-the-steak"), [4]));
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(1, now - min(1), now - min(3), 2, 2)]]);
  const { state } = recon("3 two phases become one", R1, st);
  const rs = runOf(state, "sear-the-steak");
  check("3 p clamped to the single phase, started at the iteration's first start", rs && rs.p === 0 && rs.n === 1 && rs.started === now - min(3));
  check("3 ends one minute from now", rs && E.phaseState(stepOf(R1, "sear-the-steak"), rs, now, MPM).end === now + min(1));
}
{ // 9. a retired version-1 state (the prototype's optional-timer era) is cleared with one notice
  const st = { v: 1, rid: BEFORE.id, mpm: MPM, done: [], run: [["boil-the-water", { p: 0, started: now - min(6), opt: true }]] };
  const res = E.reconcile(AFTER, st, now);
  check("9 a v1 state is cleared, never mapped", res.state === null && /earlier version/.test(res.toast), res.toast);
}
{ // 10. a state for another recipe is never adopted
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], []);
  st.rid = "local:someone-else";
  check("10 another recipe's state is cleared", E.reconcile(AFTER, st, now).state === null);
}
{ // 11. a closed run: a running step that a done step depends on becomes done, not running
  const st = stateOn(BEFORE, [["sear-the-steak", now - min(1)]], [["toast-the-spices", runEntry(0, now - min(3), now - min(3), 1, 1)]]);
  const { state } = recon("11 closed run", AFTER, st);
  check("11 the prerequisite of a done step is done, not running", !runOf(state, "toast-the-spices") && doneAt(state, "toast-the-spices") !== null);
}
{ // 12. a split with no timer child: the run is dropped, every child named as no longer a timer, the children open
  const R1 = mutated(BEFORE, "12121212", r => {
    const i = r.steps.findIndex(s => s.id === "sear-the-steak");
    const a = clone(r.steps[i]); a.id = "pat-the-steak-dry"; a.title = "Pat the Steak Dry"; toPlain(a); a.scheduled = 1;
    const b = clone(r.steps[i]); b.id = "sear-by-feel"; b.title = "Sear by Feel"; toPlain(b); b.scheduled = 4; b.deps = ["pat-the-steak-dry"];
    r.steps.splice(i, 1, a, b);
    for (const s of r.steps) s.deps = s.deps.map(d => d === "sear-the-steak" ? "sear-by-feel" : d);
  }, { "sear-the-steak": ["pat-the-steak-dry", "sear-by-feel"] });
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(0, now - min(1), now - min(1), 2, 2)]]);
  const { state, toast } = recon("12 no timer child", R1, st);
  check("12 nothing runs; pat-dry is available", !state.run.length && E.view(R1, state, now).available.includes("pat-the-steak-dry"));
  check("12 the children are named as no longer timers", toast.includes("Pat the Steak Dry is no longer a timer") && toast.includes("Sear by Feel is no longer a timer"), toast);
}
{ // 13. a run whose old state carries no s (an earlier page): the current phases per iteration stand in
  const st = stateOn(BEFORE, [], [["rest-the-batter", { p: 1, started: now - min(4), started0: now - min(9), n: 2 }]]);
  const { state } = recon("13 old entry without s", BEFORE, Object.assign(st, { h: "13131313" }));
  const rs = runOf(state, "rest-the-batter");
  check("13 the run is kept with p clamped and its start", rs && rs.p === 1 && rs.started === now - min(4) && rs.s === 2);
}

// ---- the variant: the export's steak row is its old shape -----------------------------
{ // the fixture variant: blanch-the-greens renamed, sear-the-steak split, preheat gains a sigil
  const t3 = now - min(1);
  const st = stateOn(STEAK, [["boil-the-water", now - min(8)], ["toast-the-spices", now - min(5)], ["blanch-the-greens", now - min(2)]],
                     [["sear-the-steak", runEntry(1, t3, t3 - min(2), 2, 2)]]);
  st.rid = VARIANT.id;   // the same recipe, kept as a variant file: its page's state keys on the local id
  const { state, toast } = recon("V the fixture variant", VARIANT, st);
  check("V the renamed done step is done under its new slug at its time", doneAt(state, "blanch-the-rabe") === now - min(2) && doneAt(state, "blanch-the-greens") === null);
  const rs = runOf(state, "sear-the-second-side");
  check("V the phase-2 sear runs on the second side, the first side done", rs && rs.started === t3 && doneAt(state, "sear-the-first-side") === t3 - min(2));
  check("V the toast: kept 3 done, 1 running, preheat is now a timer", toast === "Recipe updated. Kept 3 done, 1 running. Preheat the Oven is now a timer.", toast);
  check("V preheat is available as a timer, not started", E.view(VARIANT, state, now).available.includes("preheat-the-oven") && E.isTimer(stepOf(VARIANT, "preheat-the-oven")) && !runOf(state, "preheat-the-oven"));
}

// ---- alias chains: the append-only envelope names an id a later entry moved on --------
{ // H. rename a -> b, then rename b -> c: a done a is done as c at its time, a running one keeps its run, nothing is dropped
  const R1 = mutated(BEFORE, "0a0a0a01", r => {
    const t = r.steps.find(s => s.id === "toast-the-spices"); t.id = "bloom-the-spices"; t.title = "Bloom the Spices";
    const b = r.steps.find(s => s.id === "rest-the-batter"); b.id = "rest-the-batter-overnight"; b.title = "Rest the Batter Overnight";
    for (const s of r.steps) s.deps = s.deps.map(d => d === "toast-the-spices" ? "bloom-the-spices" : d === "rest-the-batter" ? "rest-the-batter-overnight" : d);
  }, { "toast-the-spices": ["toast-the-cumin"], "toast-the-cumin": ["bloom-the-spices"],
       "rest-the-batter": ["rest-the-mix"], "rest-the-mix": ["rest-the-batter-overnight"] });
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["rest-the-batter", runEntry(1, now - min(4), now - min(9), 2, 2)]]);
  const { state, toast } = recon("H chain of two renames", R1, st);
  check("H the done id is done under the chain's end, at its time", doneAt(state, "bloom-the-spices") === now - min(5) && doneAt(state, "toast-the-spices") === null, JSON.stringify(state.done));
  const rs = runOf(state, "rest-the-batter-overnight");
  check("H the running id keeps its run under the chain's end", rs && rs.p === 1 && rs.started === now - min(4) && rs.started0 === now - min(9), JSON.stringify(state.run));
  check("H minutes left = 6, as before the edit", rs && E.minutesLeft(stepOf(R1, "rest-the-batter-overnight"), rs, now, MPM) === 6);
  check("H the toast counts both kept and drops nothing", toast === "Recipe updated. Kept 1 done, 1 running.", toast);
  // a sigil gained at the chain's end is named through the chain (boil-the-water is plain before)
  const R2 = mutated(BEFORE, "0a0a0a02", r => {
    const b = r.steps.find(s => s.id === "boil-the-water"); b.id = "bring-the-water-to-a-boil"; b.title = "Bring the Water to a Boil"; toTimer(b, [6]);
    for (const s of r.steps) s.deps = s.deps.map(d => d === "boil-the-water" ? "bring-the-water-to-a-boil" : d);
  }, { "boil-the-water": ["boil-the-kettle"], "boil-the-kettle": ["bring-the-water-to-a-boil"] });
  const t2 = recon("H' a sigil gained at the chain's end", R2, stateOn(BEFORE, [], [])).toast;
  check("H' the toast names the chain's end as now a timer", t2 === "Recipe updated. Kept 0 done, 0 running. Bring the Water to a Boil is now a timer.", t2);
}
{ // I. rename sear-the-steak -> sear-the-meat, then split sear-the-meat -> first, second: the after shape, reached through the chain
  const R1 = mutated(AFTER, "0a0a0a03", () => {}, { "sear-the-steak": ["sear-the-meat"], "sear-the-meat": ["sear-the-first-side", "sear-the-second-side"] });
  const t3 = now - min(1);
  const st = stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["sear-the-steak", runEntry(1, t3, t3 - min(2), 2, 2)]]);
  const { state, toast } = recon("I rename then split", R1, st);
  const rs = runOf(state, "sear-the-second-side");
  check("I phase 2 runs on the second child with its start; the first child is done at the iteration's first start", rs && rs.p === 0 && rs.started === t3 && doneAt(state, "sear-the-first-side") === t3 - min(2), JSON.stringify(state.run));
  check("I 1 kept, 1 running, nothing dropped", toast.startsWith("Recipe updated. Kept 1 done, 1 running.") && !toast.includes("Dropped"), toast);
  const d = recon("I' a done id through rename then split", R1, stateOn(BEFORE, [["toast-the-spices", now - min(5)], ["sear-the-steak", now - min(1)]], []));
  check("I' both children done at the old time", ["sear-the-first-side", "sear-the-second-side"].every(id => doneAt(d.state, id) === now - min(1)) && d.toast.startsWith("Recipe updated. Kept 2 done, 0 running."), d.toast);
}
{ // J. rename a -> b, then rename b -> c, and c is not in the recipe: dropped and named once, nothing invented
  const R1 = mutated(BEFORE, "0a0a0a04", r => {
    r.steps = r.steps.filter(s => s.id !== "toast-the-spices");
    for (const s of r.steps) s.deps = s.deps.filter(d => d !== "toast-the-spices");
  }, { "toast-the-spices": ["toast-the-cumin"], "toast-the-cumin": ["bloom-the-spices"] });
  const { state, toast } = recon("J a chain that ends in a vanished slug", R1, stateOn(BEFORE, [["toast-the-spices", now - min(5)]], []));
  check("J no done entry survives", state.done.length === 0, JSON.stringify(state.done));
  check("J named once, as no longer in the recipe", toast === "Recipe updated. Kept 0 done, 0 running. Dropped: Toast the spices (no longer in the recipe).", toast);
  const R2 = mutated(R1, "0a0a0a05", r => {
    r.steps = r.steps.filter(s => s.id !== "rest-the-batter");
    for (const s of r.steps) s.deps = s.deps.filter(d => d !== "rest-the-batter");
  }, { "toast-the-spices": ["toast-the-cumin"], "toast-the-cumin": ["bloom-the-spices"], "rest-the-batter": ["rest-the-mix"], "rest-the-mix": ["rest-overnight"] });
  const r2 = recon("J' a running chain that ends in a vanished slug", R2,
    stateOn(BEFORE, [["toast-the-spices", now - min(5)]], [["rest-the-batter", runEntry(0, now - min(1), now - min(1), 2, 2)]]));
  check("J' each named once", r2.toast === "Recipe updated. Kept 0 done, 0 running. Dropped: Toast the spices, Rest the batter (no longer in the recipe).", r2.toast);
}

console.log(fails ? `\n${fails} FAILED` : "\nall reconcile cases pass");
process.exit(fails ? 1 : 0);
