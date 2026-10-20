// The paste sheet's reader (recipe-authoring "The FOND1 line carries h= and a stale line
// is refused"): a matching h, a stale h, an absent h (an earlier line), the retired :o@
// form, the mode letters, n/s/started0 on every run entry, an 18-hour timer, the DST
// hour, the day offset (a 36-hour phase, a countdown past midnight), garbage and duplicates,
// a malformed stamp (refused, naming it), a head that does not match as a whole, and the
// wrapper punctuation a paste may carry around the line (read through; a bad stamp inside
// it still refused by name).
// Usage: node parse_line.mjs <player.template.html> <export.json> <variant.json>
process.env.TZ = "America/New_York";   // the DST case below needs a zone with a fall-back hour
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

const [tplPath, exportPath, variantPath] = process.argv.slice(2);
const E = loadEngine(tplPath);
const EXPORT = JSON.parse(readFileSync(exportPath, "utf8"));
const VARIANT = JSON.parse(readFileSync(variantPath, "utf8")).recipes[0];
const steak = EXPORT.recipes.find(r => r.id === "rcp-steak-01");
const pasta = EXPORT.recipes.find(r => r.id === "rcp-pasta-02");
if (!steak || !pasta) throw new Error("the export payload must carry rcp-steak-01 and rcp-pasta-02");

const M = 60000;
const clock = ms => { const d = new Date(ms); return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0"); };
let fails = 0;
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!cond) fails++; };
const at = (y, mo, d, h, mi) => new Date(y, mo, d, h, mi, 0, 0).getTime();
const now = at(2026, 9, 10, 18, 0);

// The line the engine writes, read back: matching h accepted.
{
  const st = E.tap(steak, E.tap(steak, E.freshState(steak, now - 5 * M, M), "toast-the-spices", now - 5 * M).state, "rest-the-dough", now - 3 * M).state;
  const line = E.stateLine(steak, st, now, clock);
  check("the line carries the mode letter j and h= after t=", new RegExp("^FOND1 rcp-steak-01 j d=\\S* r=\\S* t=\\d{2}:\\d{2} h=" + steak.h + "( \\||$)").test(line.line), line.line);
  check("the words name the recipe by its id without 'Fond id'", line.words.startsWith("Cooking Skillet Steak Supper (rcp-steak-01), ") && !line.words.includes("Fond id"), line.words);
  const back = E.parseLine(steak, line.line, now, M, {});
  check("a matching h is accepted", !back.error, back.error || "");
  const rs = back.state && back.state.run.find(x => x[0] === "rest-the-dough")[1];
  check("the run entry carries p, started, started0, n and s", rs && rs.p === 0 && rs.n === 2 && rs.s === 2 && Number.isFinite(rs.started0), JSON.stringify(rs));
  check("the parsed state is stamped v2 with h, t and u", back.state && back.state.v === 2 && back.state.h === steak.h && Array.isArray(back.state.t) && Array.isArray(back.state.u));
  // stale h
  const stale = line.line.replace(" h=" + steak.h, " h=00000000");
  const r2 = E.parseLine(steak, stale, now, M, {});
  check("a stale h is refused with the exact message", r2.error === "That line is from an earlier version of this recipe. Ask Claude for a line from the current one.", r2.error);
  // absent h (an earlier line)
  const old = line.line.replace(" h=" + steak.h, "");
  const r3 = E.parseLine(steak, old, now, M, {});
  check("a line without h is accepted and replays the same cook", !r3.error && JSON.stringify(E.view(steak, r3.state, now).available) === JSON.stringify(E.view(steak, back.state, now).available), r3.error || "");
  check("the state from an old line is stamped with the current h", r3.state && r3.state.h === steak.h);
}
// The variant: mode letter l; a line with the j letter for the same id still parses (the letter names the source, not the recipe).
{
  const st = E.tap(VARIANT, E.freshState(VARIANT, now - M, M), "preheat-the-oven", now - M).state;
  const line = E.stateLine(VARIANT, st, now, clock).line;
  check("a local file's line carries the letter l", line.startsWith("FOND1 local:sample-variant l "), line);
  check("the letters j, m and l are all read", ["j", "m", "l"].every(l => !E.parseLine(VARIANT, line.replace(" l ", " " + l + " "), now, M, {}).error));
  check("another letter is not a FOND1 line", /Paste the whole line/.test(E.parseLine(VARIANT, line.replace(" l ", " x "), now, M, {}).error));
}
// The retired optional-timer form is refused naming the step.
{
  const r = E.parseLine(steak, "FOND1 rcp-steak-01 j d= r=preheat-the-oven:o@18:30 t=18:00 h=" + steak.h, now, M, {});
  check("a :o@ run is refused naming the step", /^Step preheat-the-oven is written in the retired :o@ form/.test(r.error), r.error);
}
// started0 is reconstructed from the earlier segments of the iteration (assumed back to back).
{
  const r = E.parseLine(steak, "FOND1 rcp-steak-01 j d= r=rest-the-dough:2/2@18:09 t=18:00 h=" + steak.h, now, M, {});
  const rs = r.state && r.state.run[0][1];
  check("phase 2 of [5, 10] ending at 18:09: started 17:59, started0 17:54", rs && rs.p === 1 && rs.started === at(2026, 9, 10, 17, 59) && rs.started0 === at(2026, 9, 10, 17, 54), JSON.stringify(rs));
}
// A pasted line with the replay tail is read the same (the tail is informational here).
{
  const r = E.parseLine(steak, "FOND1 rcp-steak-01 j d=toast-the-spices r=rest-the-dough:1/2@18:04 t=18:00 h=" + steak.h + " | --done toast-the-spices --running rest-the-dough=14", now, M, {});
  check("a line with its replay tail parses", !r.error && r.state.done.some(d => d[0] === "toast-the-spices") && r.state.run.length === 1, r.error || "");
}
// An 18-hour timer: the end time is after t= even when the clock reads earlier.
{
  const long = JSON.parse(JSON.stringify(steak));
  long.id = "rcp-long"; long.h = "1a1a1a1a";
  const s = long.steps.find(x => x.id === "rest-the-dough");   // the index shares the step objects
  s.phases = [{ min: 1080, label: "18 hr", iter: 1, iters: 1, seg: 1, segs: 1 }]; s.segs = 1; s.iters = 1; s.timer_total = 1080; s.scheduled = 1080; s.surplus = 0;
  const late = at(2026, 9, 10, 20, 0);   // the line was made at 18:00; the 18-hour rest ends at 12:00 tomorrow
  const r = E.parseLine(long, "FOND1 rcp-long j d= r=rest-the-dough:1/1@12:00 t=18:00 h=1a1a1a1a", late, M, {});
  const rs = r.state && r.state.run[0][1];
  check("an 18-hour countdown ends tomorrow at 12:00, started today at 18:00", rs && rs.started === at(2026, 9, 10, 18, 0) && rs.started + 1080 * M === at(2026, 9, 11, 12, 0), r.error || JSON.stringify(rs));
  check("the countdown reads 16 hours left", rs && E.minutesLeft(E.index(long)["rest-the-dough"], rs, late, M) === 960);
}
// The DST hour (America/New_York falls back on 2026-11-01 at 02:00): a line made in the
// repeated hour still parses, with the end after t= and within the phase's length.
{
  const dstNow = new Date(2026, 10, 1, 1, 50, 0, 0).getTime();
  const r = E.parseLine(steak, "FOND1 rcp-steak-01 j d= r=rest-the-dough:1/2@01:55 t=01:50 h=" + steak.h, dstNow, M, {});
  const rs = r.state && r.state.run[0][1];
  const end = rs && rs.started + 5 * M;
  check("a line in the DST hour parses with its end after t=", !r.error && end > dstNow - 60e3 && end <= dstNow + 70 * M, r.error || String((end - dstNow) / M));
}
// A phase of a day or more (`+<days>d`, calendar days after t='s day): a 36-hour rest one
// hour in writes its end with the day offset and reads back to 2,100 minutes left with its
// start kept — not 660 with the start moved back a day.
{
  const long = JSON.parse(JSON.stringify(steak));
  long.id = "rcp-long-36"; long.h = "2b2b2b2b";
  const s = long.steps.find(x => x.id === "rest-the-dough");
  s.phases = [{ min: 2160, label: "36 hr", iter: 1, iters: 1, seg: 1, segs: 1 }]; s.segs = 1; s.iters = 1; s.timer_total = 2160; s.scheduled = 2160; s.surplus = 0;
  const started = at(2026, 9, 10, 17, 0);   // tapped at 17:00; the rest ends at 05:00 two days on
  const st = E.tap(long, E.freshState(long, started, M), "rest-the-dough", started).state;
  const line = E.stateLine(long, st, now, clock);
  check("the end carries +2d; t= carries no day", / r=rest-the-dough:1\/1@05:00\+2d t=18:00 h=2b2b2b2b/.test(line.line), line.line);
  check("the words say the day", line.words.includes("ends 05:00 in 2 days."), line.words);
  check("the replay tail says 2100", line.replay === "--running rest-the-dough=2100", line.replay);
  const back = E.parseLine(long, line.line, now, M, {});
  const rs = back.state && back.state.run[0][1];
  check("2,100 minutes left, the start kept", rs && rs.started === started && E.minutesLeft(E.index(long)["rest-the-dough"], rs, now, M) === 2100, back.error || JSON.stringify(rs));
  // the same rest tapped yesterday evening ends tomorrow morning: +1d, 840 minutes left
  const eve = at(2026, 9, 9, 20, 0);
  const l1 = E.stateLine(long, E.tap(long, E.freshState(long, eve, M), "rest-the-dough", eve).state, now, clock).line;
  check("an end tomorrow carries +1d", / r=rest-the-dough:1\/1@08:00\+1d /.test(l1), l1);
  const b1 = E.parseLine(long, l1, now, M, {});
  check("… and reads back to 840 minutes left from the same start", !b1.error && b1.state.run[0][1].started === eve && E.minutesLeft(E.index(long)["rest-the-dough"], b1.state.run[0][1], now, M) === 840, b1.error || "");
}
// A countdown that crosses midnight carries +1d; the bare form of the same line (one from
// before the offset) reads the same.
{
  const late = at(2026, 9, 10, 23, 50), later = at(2026, 9, 10, 23, 55), now2 = at(2026, 9, 10, 23, 56);
  let st = E.tap(steak, E.freshState(steak, late, M), "rest-the-dough", late).state;
  st = E.tap(steak, st, "rest-the-dough", later).state;   // phase 2 of [5, 10] runs 23:55 → 00:05
  const line = E.stateLine(steak, st, now2, clock).line;
  check("an end past midnight carries +1d", / r=rest-the-dough:2\/2@00:05\+1d t=23:56 /.test(line), line);
  const a = E.parseLine(steak, line, now2, M, {}), b = E.parseLine(steak, line.replace("+1d", ""), now2, M, {});
  const ra = a.state && a.state.run[0][1], rb = b.state && b.state.run[0][1];
  check("it reads back to started 23:55, started0 23:50, 9 minutes left", ra && ra.started === later && ra.started0 === late && E.minutesLeft(E.index(steak)["rest-the-dough"], ra, now2, M) === 9, a.error || JSON.stringify(ra));
  check("the bare form reads the same", rb && rb.started === ra.started && rb.started0 === ra.started0, b.error || JSON.stringify(rb));
}
// A day on t= counts from today; +0d is the bare time; a malformed offset is refused.
{
  const plain = E.parseLine(steak, "FOND1 rcp-steak-01 j d= r=rest-the-dough:1/2@18:04 t=18:00 h=" + steak.h, now, M, {});
  const zero = E.parseLine(steak, "FOND1 rcp-steak-01 j d= r=rest-the-dough:1/2@18:04+0d t=18:00+0d h=" + steak.h, now, M, {});
  check("+0d on t= and on an end reads as the bare line", !plain.error && !zero.error && zero.state.run[0][1].started === plain.state.run[0][1].started, zero.error || plain.error || "");
  const bad = E.parseLine(steak, "FOND1 rcp-steak-01 j d= r=rest-the-dough:1/2@18:04+xd t=18:00 h=" + steak.h, now, M, {});
  check("a malformed day offset is refused naming the step", /Could not read the running step 'rest-the-dough:1\/2@18:04\+xd'/.test(bad.error), bad.error || "accepted");
}
// Garbage and duplicates.
{
  const bad = [
    ["", /Paste the whole line/],
    ["FOND1", /Paste the whole line/],
    ["hello there", /Paste the whole line/],
    ["FOND1 rcp-pasta-02 j d= r= t=18:00 h=" + steak.h, /That line is for rcp-pasta-02, not rcp-steak-01/],
    ["FOND1 rcp-steak-01 j d=no-such-step r= t=18:00", /Unknown step id 'no-such-step'/],
    ["FOND1 rcp-steak-01 j d=toast-the-spices,toast-the-spices r= t=18:00", /listed twice in d=/],
    ["FOND1 rcp-steak-01 j d=toast-the-spices r=toast-the-spices:1/1@18:02 t=18:00", /both done and running/],
    ["FOND1 rcp-steak-01 j d= r=rest-the-dough:1/2@18:05,rest-the-dough:2/2@18:15 t=18:00", /listed twice/],
    ["FOND1 rcp-steak-01 j d= r=rest-the-dough:3/2@18:05 t=18:00", /has no countdown 3\/2/],
    ["FOND1 rcp-steak-01 j d= r=preheat-the-oven:1/1@18:05 t=18:00", /has no countdown 1\/1/],
    ["FOND1 rcp-steak-01 j d= r=rest-the-dough:1/2@25:05 t=18:00", /impossible time/],
    ["FOND1 rcp-steak-01 j d= r= t=24:00", /not a clock time/],
    ["FOND1 rcp-steak-01 j d= r=garbage t=18:00", /Could not read the running step 'garbage'/],
    ["FOND1 rcp-steak-01 j d=simmer-the-sauce r=sear-the-steak:1/2@18:02 t=18:00", /can't be running/],
  ];
  for (const [line, re] of bad) {
    const r = E.parseLine(steak, line, now, M, {});
    check("refused: " + JSON.stringify(line).slice(0, 70), !!r.error && re.test(r.error), r.error || "accepted");
  }
}
// A malformed stamp refuses the whole line, naming it — never skipped over and read as an
// earlier, unstamped line (which would bypass the stale-recipe guard). The head is read as a
// whole: FOND1 at a word start, through t= and an optional h=, then the replay tail, a
// closing backtick and prose, or closing punctuation and the end of the line.
{
  const head = "FOND1 rcp-steak-01 j d=toast-the-spices r=rest-the-dough:1/2@18:04 t=18:00";
  const stamps = [
    ["h=garbage", "garbage"],
    ["seven hex digits", steak.h.slice(0, 7)],
    ["nine hex digits", steak.h + "0"],
    ["upper case", "D0ED784F"],
    ["an empty h=", ""],
  ];
  if (/[a-f]/.test(steak.h)) stamps.push(["this recipe's own stamp in upper case", steak.h.toUpperCase()]);
  for (const [name, h] of stamps) {
    for (const tail of ["", " | --done toast-the-spices --running rest-the-dough=4"]) {
      const r = E.parseLine(steak, head + " h=" + h + tail, now, M, {});
      check("refused, naming the stamp: " + name + (tail ? " (with the replay tail)" : ""),
        !r.state && r.error === "That line's stamp h=" + h + " is not eight hex digits (0-9, a-f), so nothing was applied. Paste the whole line again, or ask Claude for a new one.",
        r.error || "accepted");
    }
  }
  const valid = E.parseLine(steak, head + " h=" + steak.h, now, M, {});
  check("a valid stamp is accepted", !valid.error && valid.state.run.length === 1, valid.error || "");
  const none = E.parseLine(steak, head, now, M, {});
  check("no stamp at all is accepted as an earlier line", !none.error && none.state.h === steak.h, none.error || "");
  const piped = E.parseLine(steak, head + " h=" + steak.h + "|--done toast-the-spices", now, M, {});
  check("a pipe right after the stamp ends it", !piped.error, piped.error || "");
  const wrapped = E.parseLine(steak, "`" + head + " h=" + steak.h + "`", now, M, {});
  check("a line in inline-code backticks is read", !wrapped.error, wrapped.error || "");
  const pasted = E.parseLine(steak, "Cooking Skillet Steak Supper (rcp-steak-01), 18:00 on my clock.\n" + head + " h=" + steak.h + " \n", now, M, {});
  check("a line on its own line under the words is read", !pasted.error, pasted.error || "");
  for (const line of [head + " h=" + steak.h + " and more", head + " x=1", head + " H=" + steak.h, "x" + head + " h=" + steak.h]) {
    const r = E.parseLine(steak, line, now, M, {});
    check("a head that does not match as a whole is refused: " + JSON.stringify(line.slice(-24)), !r.state && /Paste the whole line/.test(r.error || ""), r.error || "accepted");
  }
  const stale = E.parseLine(steak, head + " h=00000000", now, M, {});
  check("a well-formed other stamp is still the stale refusal", /earlier version of this recipe/.test(stale.error || ""), stale.error || "accepted");

  // Wrapper punctuation around a pasted line is not part of it: a quote, bold, a bracket, a
  // blockquote `>`, `line:`, a full stop after it, inline code inside a sentence — each read
  // with and without the replay tail, and a malformed stamp inside each still refused by name.
  const replay = " | --done toast-the-spices --running rest-the-dough=4";
  const named = h => "That line's stamp h=" + h + " is not eight hex digits (0-9, a-f), so nothing was applied. Paste the whole line again, or ask Claude for a new one.";
  const wraps = [
    ["double quotes", l => '"' + l + '"'],
    ["curly quotes", l => "\u201c" + l + "\u201d"],
    ["single quotes", l => "'" + l + "'"],
    ["bold", l => "**" + l + "**"],
    ["parentheses", l => "(" + l + ")"],
    ["square brackets", l => "[" + l + "]"],
    ["a blockquote >", l => "> " + l],
    ["a > with no space", l => ">" + l],
    ["line: with no space", l => "line:" + l],
    ["a full stop after it", l => l + "."],
    ["quotes and a full stop", l => '"' + l + '".'],
    ["inline code and a full stop", l => "`" + l + "`."],
    ["inline code inside a sentence", l => "Paste `" + l + "` into the box."],
  ];
  for (const [name, wrap] of wraps) {
    for (const tail of ["", replay]) {
      const ok = E.parseLine(steak, wrap(head + " h=" + steak.h + tail), now, M, {});
      check("read through " + name + (tail ? " (with the replay tail)" : ""), !ok.error && ok.state.h === steak.h && ok.state.run.length === 1, ok.error || "");
      const bad = E.parseLine(steak, wrap(head + " h=garbage" + tail), now, M, {});
      check("h=garbage through " + name + (tail ? " (with the replay tail)" : "") + " is refused by name", !bad.state && bad.error === named("garbage"), bad.error || "accepted");
    }
    const bare = E.parseLine(steak, wrap(head), now, M, {});
    check("an unstamped line through " + name + " is read as an earlier line", !bare.error && bare.state.h === steak.h, bare.error || "");
  }
  for (const h of [steak.h.slice(0, 7), steak.h + "0", "D0ED784F", ""]) {
    const r = E.parseLine(steak, head + " h=" + h + ".", now, M, {});
    check("a full stop after a malformed stamp h=" + h + " leaves it refused by name", !r.state && r.error === named(h), r.error || "accepted");
  }
  // An h= after a closing backtick, or after closing punctuation, is not skipped as prose.
  for (const line of [head + "` h=garbage", head + "`h=garbage", head + ". h=garbage", head + '" h=garbage', head + "` h=" + steak.h + " and more"]) {
    const r = E.parseLine(steak, line, now, M, {});
    check("an h= after the line's end is not skipped: " + JSON.stringify(line.slice(-22)), !r.state && /Paste the whole line/.test(r.error || ""), r.error || "accepted");
  }
  // FOND1 inside a word is still not a line (`_` counts as a word character).
  const inword = E.parseLine(steak, "_" + head + " h=" + steak.h, now, M, {});
  check("FOND1 after _ is not at a word start", !inword.state && /Paste the whole line/.test(inword.error || ""), inword.error || "accepted");
}
// The closure: a done step implies its prerequisites done.
{
  const r = E.parseLine(steak, "FOND1 rcp-steak-01 j d=simmer-the-sauce r= t=18:00", now, M, {});
  check("a done step implies its chain done", !r.error && ["sear-the-steak", "toast-the-spices"].every(id => r.state.done.some(d => d[0] === id)), r.error || "");
}

console.log(fails ? `\n${fails} FAILED` : "\nall parse_line cases pass");
process.exit(fails ? 1 : 0);
