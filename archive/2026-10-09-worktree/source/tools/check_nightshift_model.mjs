#!/usr/bin/env node
// Standalone model contract checks; no browser, network or dependencies.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const root = new URL("../", import.meta.url);
const context = vm.createContext({});
for (const file of ["app/nightshift-model.js", "app/nightshift-content.js"]) {
  vm.runInContext(readFileSync(new URL(file, root), "utf8"), context, { filename: file });
}
const { NightShiftSession, NIGHTSHIFT_CONTENT: content } = context;
const ids = ["s02", "s08", "s10", "s01", "s07", "s11", "s04", "s06", "s03"];
const expected = ["sky", "artifact", "uncertain", "stable", "sky", "sky", "artifact", "sky", "sky"];
const data = { contact: ids.map((id, i) => ({ id, expectedVerdict: expected[i] })) };
const plain = value => JSON.parse(JSON.stringify(value));
const equal = (actual, wanted) => assert.deepEqual(plain(actual), wanted);
const rejects = action => assert.throws(action, { name: "RangeError" });
let passed = 0;
function check(name, action) {
  action();
  passed++;
  console.log(`✓ ${name}`);
}

for (const count of [3, 6, 9]) {
  check(`${count} cases: fixed prefix, focus, budget and clean state`, () => {
    const g = new NightShiftSession(data, count);
    equal(g.cases.map(c => c.id), ids.slice(0, count));
    assert.equal(g.current.id, ids[0]);
    assert.equal(g.state.focus, ids[0]);
    assert.equal(g.budget, count / 3);
    assert.equal(g.remaining, count / 3);
    assert.equal(g.completed, 0);
    equal(g.report(), { answered: 0, total: count, revised: 0, matched: 0, open: 0, unanswered: count });
    equal(g.note(ids[0]), {
      marks: {}, prediction: null, checked: false, decision: null, beforeReveal: null, revealed: false,
    });
    assert.notEqual(g.note(ids[0]).marks, g.note(ids[1]).marks);
  });

  check(`${count} cases: paid frames exhaust budget and retries are free`, () => {
    const g = new NightShiftSession(data, count);
    assert.equal(g.request(ids[0]), false);
    for (const id of ids.slice(0, g.budget)) {
      g.predict(id, "uncertain");
      assert.equal(g.request(id), true);
      assert.equal(g.request(id), true);
      assert.equal(g.note(id).checked, true);
      assert.equal(g.hasThird(id), true);
    }
    const blocked = ids[g.budget];
    g.predict(blocked, "motion");
    assert.equal(g.remaining, 0);
    assert.equal(g.request(blocked), false);
    assert.equal(g.hasThird(blocked), false);
    assert.equal(g.note(blocked).checked, false);
  });

  check(`${count} cases: reverse completion finishes exactly once`, () => {
    const g = new NightShiftSession(data, count);
    for (const id of ids.slice(0, count).reverse()) {
      g.select(id);
      g.predict(id, "uncertain");
      g.decide(id, "uncertain");
      const next = g.nextId();
      assert(next === null || g.note(next).decision === null);
    }
    assert.equal(g.completed, count);
    assert.equal(g.nextId(), null);
    g.decide(ids[0], "sky");
    assert.equal(g.nextId(), null);
    assert.equal(g.completed, count);
  });
}

check("default level and navigation wrap to the last undecided case", () => {
  const g = new NightShiftSession(data);
  assert.equal(g.state.count, 3);
  g.select("s10");
  assert.equal(g.current.id, "s10");
  assert.equal(g.nextId(), "s02");
  for (const id of ["s02", "s08"]) {
    g.predict(id, "stable");
    g.decide(id, "stable");
  }
  assert.equal(g.nextId(), "s10");
  assert.equal(g.state.focus, "s10");
});

check("prediction and decision are revisable without spending or fabricating checks", () => {
  const g = new NightShiftSession(data);
  rejects(() => g.decide("s02", "sky"));
  assert.equal(g.predict("s02", "motion"), true);
  assert.equal(g.predict("s02", "motion"), false);
  assert.equal(g.decide("s02", "sky"), true);
  assert.equal(g.decide("s02", "sky"), false);
  g.predict("s02", "brightness");
  g.decide("s02", "artifact");
  assert.equal(g.note("s02").prediction, "brightness");
  assert.equal(g.note("s02").decision, "artifact");
  assert.equal(g.remaining, 1);
  assert.equal(g.hasThird("s02"), false);
  assert.equal(g.report().revised, 0);
});

check("single reveal requires a decision, grants a free third and preserves the snapshot", () => {
  const g = new NightShiftSession(data);
  assert.equal(g.reveal("s02"), false);
  g.predict("s02", "uncertain");
  assert.equal(g.reveal("s02"), false);
  g.decide("s02", "uncertain");
  assert.equal(g.reveal("s02"), true);
  assert.equal(g.hasThird("s02"), true);
  assert.equal(g.hasThird("s08"), false);
  assert.equal(g.request("s02"), true);
  assert.equal(g.remaining, 1);
  assert.equal(g.note("s02").checked, false);
  g.decide("s02", "sky");
  assert.equal(g.reveal("s02"), true);
  g.revealAll();
  assert.equal(g.note("s02").beforeReveal, "uncertain");
  assert.equal(g.report().revised, 1);
  g.decide("s02", "uncertain");
  assert.equal(g.report().revised, 0);
});

check("general reveal preserves paid checks and records unanswered snapshots as null", () => {
  const g = new NightShiftSession(data);
  g.predict("s02", "motion");
  g.request("s02");
  g.decide("s02", "sky");
  g.revealAll();
  assert.equal(g.note("s02").beforeReveal, "sky");
  assert.equal(g.note("s08").beforeReveal, null);
  assert.equal(g.note("s08").revealed, true);
  assert.equal(g.hasThird("s08"), true);
  assert.equal(g.note("s02").checked, true);
  assert.equal(g.note("s08").checked, false);
  assert.equal(g.remaining, 0);
  assert.equal(g.request("s08"), false); // Prediction remains required.
  g.predict("s08", "artifact");
  assert.equal(g.request("s08"), true);
  g.decide("s08", "artifact");
  g.revealAll();
  assert.equal(g.note("s08").beforeReveal, null);
  assert.equal(g.report().revised, 0);
  assert.equal(g.remaining, 0);
});

check("normalized marks replace only the chosen epoch and gate the hidden third", () => {
  const g = new NightShiftSession(data);
  assert.equal(g.mark("s02", 0, 0, 1), true);
  assert.equal(g.mark("s02", 0, 0, 1), false);
  g.mark("s02", 1, 0.5, 0.6);
  g.mark("s02", 0, 0.2, 0.3);
  rejects(() => g.mark("s02", 2, 0.5, 0.5));
  equal(g.note("s02").marks, { 0: { x: 0.2, y: 0.3 }, 1: { x: 0.5, y: 0.6 } });
  g.predict("s02", "motion");
  g.request("s02");
  g.mark("s02", 2, 0.7, 0.8);
  g.revealAll();
  g.mark("s08", 2, 1, 0);
  equal(g.note("s08").marks, { 2: { x: 1, y: 0 } });
});

check("invalid ids, enums, counts, epochs and coordinates never change state", () => {
  const g = new NightShiftSession(data);
  const before = plain(g.state);
  for (const id of ["missing", "s01", "__proto__", null, 2]) {
    for (const method of ["note", "select", "request", "reveal", "hasThird"]) rejects(() => g[method](id));
    rejects(() => g.predict(id, "motion"));
    rejects(() => g.decide(id, "sky"));
    rejects(() => g.mark(id, 0, 0, 0));
  }
  for (const value of [null, "", "same", "changed", "unsure", 1]) rejects(() => g.predict("s02", value));
  for (const value of [null, "", "motion", "noise", 1]) rejects(() => g.decide("s02", value));
  for (const count of [0, 1, 4, 12, "3", null, NaN]) {
    rejects(() => g.reset(count));
    rejects(() => new NightShiftSession(data, count));
  }
  for (const epoch of [-1, 3, 0.5, "0", null, NaN]) rejects(() => g.mark("s02", epoch, 0, 0));
  for (const value of [-0.1, 1.1, "0.5", null, NaN, Infinity]) {
    rejects(() => g.mark("s02", 0, value, 0));
    rejects(() => g.mark("s02", 0, 0, value));
  }
  equal(g.state, before);
});

check("malformed archives are rejected before a session starts", () => {
  for (const invalid of [null, {}, { contact: [] }, { contact: data.contact.slice(1) },
    { contact: [...data.contact, data.contact[0]] },
    { contact: data.contact.map(c => ({ ...c, expectedVerdict: "candidate" })) }]) {
    assert.throws(() => new NightShiftSession(invalid), { name: "TypeError" });
  }
});

check("reset clears all notes and snapshots, changes level, and keeps level when omitted", () => {
  const g = new NightShiftSession(data, 9);
  g.select("s03");
  g.mark("s03", 0, 0.4, 0.4);
  g.predict("s03", "brightness");
  g.request("s03");
  g.decide("s03", "sky");
  g.revealAll();
  const oldNote = g.note("s03");
  g.reset(6);
  assert.equal(g.state.count, 6);
  assert.equal(g.state.focus, "s02");
  assert.equal(g.remaining, 2);
  assert.equal(g.completed, 0);
  rejects(() => g.note("s03"));
  for (const c of g.cases) {
    assert.equal(g.hasThird(c.id), false);
    equal(g.note(c.id).marks, {});
    assert.equal(g.note(c.id).beforeReveal, null);
  }
  g.reset();
  assert.equal(g.state.count, 6);
  g.reset(9);
  assert.notEqual(g.note("s03"), oldNote);
});

check("report uses current versions; open, matches, revisions and unanswered overlap as documented", () => {
  const g = new NightShiftSession(data, 6);
  const decide = (id, verdict) => { g.predict(id, "uncertain"); g.decide(id, verdict); };
  decide("s02", "uncertain");
  g.reveal("s02");
  g.decide("s02", "sky");
  decide("s08", "sky");
  decide("s10", "uncertain"); // An uncertain archival verdict can match and remain open.
  decide("s01", "stable");
  g.revealAll();
  decide("s07", "uncertain"); // First answer after review is not a revised answer.
  equal(g.report(), { answered: 5, total: 6, revised: 1, matched: 3, open: 2, unanswered: 1 });
  assert.equal(g.note("s07").beforeReveal, null);
  g.decide("s08", "artifact");
  equal(g.report(), { answered: 5, total: 6, revised: 2, matched: 4, open: 2, unanswered: 1 });
});

check("real data and Russian content cover every level and selected archival case", () => {
  const actual = vm.createContext({ window: {} });
  vm.runInContext(readFileSync(new URL("app/data.js", root), "utf8"), actual, { filename: "app/data.js" });
  for (const count of [3, 6, 9]) {
    const g = new NightShiftSession(actual.window.GAME_DATA, count);
    assert(content.levels[count].label && content.levels[count].description);
    for (const c of g.cases) {
      assert(c.frames.length === 3 && c.explanation.length > 10);
      assert(content.cases[c.id].prompt.length > 20 && content.cases[c.id].mentor.length > 20);
      g.predict(c.id, "uncertain");
      g.decide(c.id, c.expectedVerdict);
    }
    assert.equal(g.report().matched, count);
    assert.equal(g.nextId(), null);
  }
  equal(Object.keys(content.predictions), ["motion", "brightness", "artifact", "stable", "uncertain"]);
  equal(Object.keys(content.verdicts), ["sky", "artifact", "stable", "uncertain"]);
  equal([3, 6, 9].map(count => content.levels[count].label), ["Первая смена", "Исследователь", "Астроном"]);
  assert.equal(content.character, "Ника, дежурный астроном");
});

console.log(`NightShiftSession OK: ${passed} checks`);
