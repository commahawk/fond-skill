// Random tap-driven cooks through the player's engine (recipe-authoring "The player": the
// FOND1 line "parses back to the same cook"). For each snapshot: the FOND1 line carries
// ` h=<8hex>` after `t=`, parses back to the same cook, and its replay tail goes to the
// output file so the Python driver can run the real `plan … --h` on it.
// Usage: node roundtrip.mjs <player.template.html> <payload.json> <out.json> [runs-per-recipe]
import { readFileSync, writeFileSync } from "node:fs";
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

const [tplPath, dataPath, outPath, runsArg] = process.argv.slice(2);
const E = loadEngine(tplPath);
const data = JSON.parse(readFileSync(dataPath, "utf8"));
const runsPer = +(runsArg || 150);

// The FOND1 grammar (recipe-authoring "The FOND1 line carries h="): the same expression
// the Python no-leak check keeps as FOND1_RE.
const FOND1_RE = /^FOND1 (\S+) ([jml]) d=((?:[^\s,]+)(?:,[^\s,]+)*)? r=((?:[^\s,@]+:\d+\/\d+@\d{2}:\d{2}(?:\+\d+d)?!?)(?:,[^\s,@]+:\d+\/\d+@\d{2}:\d{2}(?:\+\d+d)?!?)*)? t=\d{2}:\d{2}(?:\+\d+d)? h=[0-9a-f]{8}(?: \| (?:--done [^\s]+)?(?: ?--running [^\s]+)?)?$/;

let seed = 99;
const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const pick = a => a[Math.floor(rnd() * a.length)];
const clock = ms => { const d = new Date(ms); return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); };
const M = 60000;
const out = [];
let total = 0, parseFail = 0, grammarFail = 0, dayOffsets = 0;
const fails = [];
for (const r of data.recipes) {
  for (let run = 0; run < runsPer; run++) {
    // Cooks start between 17:30 and 23:30, so some countdowns end past midnight and their
    // ends carry `+1d` — the day offset is exercised by the round trip, not only by hand.
    let now = new Date(2026, 9, 9, 17, 30, 0).getTime() + Math.floor(rnd() * 6 * 3600) * 1000;
    let st = E.freshState(r, now, M);
    const moves = Math.floor(rnd() * r.steps.length * 3);
    for (let i = 0; i < moves; i++) {
      now += Math.floor(rnd() * 6 * M);
      const v = E.view(r, st, now);
      const tappable = [...v.available, ...st.run.map(x => x[0])];
      if (!tappable.length) break;
      st = E.tap(r, st, pick(tappable), now).state;
      if (rnd() < 0.35) {
        total++;
        const line = E.stateLine(r, st, now, clock);
        if (/@\d{2}:\d{2}\+\d+d/.test(line.line)) dayOffsets++;
        if (!FOND1_RE.test(line.line) || !line.line.includes(" h=" + r.h + " ") && !line.line.endsWith(" h=" + r.h)) {
          grammarFail++;
          if (fails.length < 6) fails.push({ line: line.line, error: "does not match the FOND1 grammar or lacks h=" });
        }
        const back = E.parseLine(r, line.line, now, M, {});
        if (back.error) { parseFail++; if (fails.length < 6) fails.push({ line: line.line, error: back.error }); continue; }
        if (back.state.h !== r.h || back.state.v !== 2) { parseFail++; if (fails.length < 6) fails.push({ line: line.line, error: "parsed state not stamped with h / v2" }); continue; }
        const a = E.view(r, st, now), b = E.view(r, back.state, now);
        const same = JSON.stringify([a.available, a.held, a.locked, [...a.done].sort()]) === JSON.stringify([b.available, b.held, b.locked, [...b.done].sort()]);
        const nOk = [...a.runN].every(([id, n]) => Math.abs((b.runN.get(id) ?? -99) - n) <= 1);
        const entriesOk = back.state.run.every(([id, rs]) => Number.isFinite(rs.started0) && rs.n === E.index(r)[id].phases.length && rs.s === E.segsOf(E.index(r)[id]));
        if (!same || !nOk || !entriesOk) { parseFail++; if (fails.length < 6) fails.push({ line: line.line, a: [a.available, a.held, [...a.runN]], b: [b.available, b.held, [...b.runN]], entriesOk }); }
        out.push({ rid: r.id, h: r.h, line: line.line, replay: line.replay, expect: { available: a.available, held: a.held, locked: a.locked, estimate_minutes: a.whole } });
      }
    }
  }
}
writeFileSync(outPath, JSON.stringify(out));
console.log(`FOND1 round trip: ${total - parseFail}/${total} snapshots parse back to the same cook; ${total - grammarFail}/${total} match the grammar with h=; ${dayOffsets} carry a day offset`);
for (const f of fails.slice(0, 6)) console.log(JSON.stringify(f));
process.exit(parseFail || grammarFail || !total ? 1 : 0);
