// The paste sheet's confirmation over the real ENGINE block (recipe-authoring "The player":
// a paste sheet "that warns before a pasted line would undo or stop progress"). The warning
// names what the line takes back, the NEXT Apply applies it — no wait between the two
// presses — editing the line re-arms the warning, and a line that keeps or adds progress
// applies at once. The sheet keeps one flag, `armed`, and passes it back in: this file
// drives pasteDecision the way the sheet's Apply handler does.
// Usage: node paste_confirm.mjs <player.template.html> <export.json>
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

const [tplPath, exportPath] = process.argv.slice(2);
const E = loadEngine(tplPath);
const EXPORT = JSON.parse(readFileSync(exportPath, "utf8"));
const steak = EXPORT.recipes.find(r => r.id === "rcp-steak-01");
if (!steak) throw new Error("the export payload must carry rcp-steak-01");

const M = 60000;
const clock = ms => { const d = new Date(ms); return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); };
const now = new Date(2026, 9, 10, 18, 0, 0, 0).getTime();
let fails = 0;
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!cond) fails++; };
const title = id => E.index(steak)[id].title;
const lineOf = st => E.stateLine(steak, st, now, clock).line;
const parsed = text => { const r = E.parseLine(steak, text, now, M, { startedAt: now - 10 * M }); if (r.error) throw new Error(r.error); return r.state; };
const tail = " t=" + clock(now) + " h=" + steak.h;
const AGAIN = ". Tap Apply again to use it anyway.";

// The cook on the page: Boil the Water done (an untimed tap resolves), Rest the Dough running.
const current = E.tap(steak, E.tap(steak, E.freshState(steak, now - 10 * M, M), "boil-the-water", now - 5 * M).state, "rest-the-dough", now - 3 * M).state;
check("the fixture cook has one done and one running step",
      current.done.length === 1 && current.done[0][0] === "boil-the-water" && current.run.length === 1 && current.run[0][0] === "rest-the-dough");

// 1. The page's own line parses back to the same cook: no warning, applied at once.
{
  const d = E.pasteDecision(steak, current, parsed(lineOf(current)), false);
  check("the cook's own line applies at once", d.apply && !d.armed && d.warning === "", JSON.stringify(d));
}
// 2. A line that adds progress applies at once.
{
  const more = E.tap(steak, current, "preheat-the-oven", now).state;
  const d = E.pasteDecision(steak, current, parsed(lineOf(more)), false);
  check("a line that adds a done step applies at once", d.apply && !d.armed && d.warning === "", JSON.stringify(d));
}
// 3–5. The fresh line (nothing done, nothing running) would undo and stop: warned once, then the
//      NEXT Apply applies it — the review's case: no wait between the two presses.
{
  const fresh = parsed(lineOf(E.freshState(steak, now - 10 * M, M)));
  const expect = "This line would undo " + title("boil-the-water") + " and stop " + title("rest-the-dough") + AGAIN;
  const first = E.pasteDecision(steak, current, fresh, false);
  check("the first Apply warns, names the undone and the stopped step, applies nothing",
        !first.apply && first.armed && first.warning === expect, first.warning);
  const second = E.pasteDecision(steak, current, fresh, first.armed);
  check("the next Apply applies the warned line, however soon", second.apply && !second.armed && second.warning === "", JSON.stringify(second));
  const third = E.pasteDecision(steak, current, fresh, false);
  check("after an edit (the sheet disarms) the warning returns once more", !third.apply && third.armed && third.warning === expect, third.warning);
  const same = E.pasteDecision(steak, current, fresh, true);
  check("an armed sheet never warns twice for the same text", same.apply && same.warning === "", JSON.stringify(same));
}
// 6. Stop only: the line keeps the done step and drops the running one.
{
  const d = E.pasteDecision(steak, current, parsed("FOND1 rcp-steak-01 j d=boil-the-water r=" + tail), false);
  check("a line that stops the running step warns about the stop only", !d.apply && d.warning === "This line would stop " + title("rest-the-dough") + AGAIN, d.warning);
}
// 7. Undo only: the line keeps the countdown and drops the done step.
{
  const running = lineOf(current).split(" r=")[1].split(" t=")[0];
  const d = E.pasteDecision(steak, current, parsed("FOND1 rcp-steak-01 j d= r=" + running + tail), false);
  check("a line that un-resolves the done step warns about the undo only", !d.apply && d.warning === "This line would undo " + title("boil-the-water") + AGAIN, d.warning);
}
// 8. A running step the line marks done is progress, not a stop.
{
  const d = E.pasteDecision(steak, current, parsed("FOND1 rcp-steak-01 j d=boil-the-water,rest-the-dough r=" + tail), false);
  check("a running step the line marks done is not a stop", d.apply && d.warning === "", d.warning);
}
// 9. A done id the recipe no longer carries is named by its slug, never a crash.
{
  const ghost = E.clone(current);
  ghost.done.push(["ghost-step", now - M]);
  const d = E.pasteDecision(steak, ghost, parsed(lineOf(E.freshState(steak, now - 10 * M, M))), false);
  check("an unknown done id is named by its slug", !d.apply && d.warning.includes("undo " + title("boil-the-water") + ", " + E.humanize("ghost-step")), d.warning);
}
// 10. pasteWarning alone: "" for a no-op, the text otherwise.
{
  check("pasteWarning is empty for the cook's own line", E.pasteWarning(steak, current, parsed(lineOf(current))) === "");
  check("pasteWarning carries the text for a stop", E.pasteWarning(steak, current, parsed("FOND1 rcp-steak-01 j d=boil-the-water r=" + tail)).endsWith(AGAIN));
}

console.log(fails ? `\n${fails} FAILED` : "\nall paste_confirm cases pass");
process.exit(fails ? 1 : 0);
