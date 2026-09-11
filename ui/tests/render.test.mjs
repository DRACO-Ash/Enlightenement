/* What the interface BUILDS, asserted on the nodes rather than on a screenshot.
 *
 * Three of these cover classes of fault that reached a running server in this project: a Python
 * repr on a library card, a plausible-but-wrong value from a misshapen field, and a static label
 * that made a claim the payload could not support. A screenshot found the first two; a test that
 * builds the node finds them before an upload does.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { INDEX_HTML, load } from './harness.mjs';

const SVG_NS = 'http://www.w3.org/2000/svg';

/* The stylesheet with comments stripped. Comments FIRST, and the first version of this did not
 * strip them: the stylesheet's own prose names the classes it discusses, so `.act`, `.sub` and
 * `.stepcard` were read out of comment text as selectors, every clashing class gained a third
 * entry, and the check passed on all three real collisions. A test that proves nothing, which is
 * the fault it exists to prevent, one layer up. */
function stylesheet(markup) {
  return markup
    .slice(markup.indexOf('<style>'), markup.indexOf('</style>'))
    .replace(/\/\*[\s\S]*?\*\//g, ' ');
}

/* Every selector, one per entry, commas split. */
function selectorsIn(sheet) {
  const found = [];
  for (const [, , selector] of sheet.matchAll(/(^|})\s*([^{}@]+)\{/g)) {
    for (const part of selector.split(',')) {
      const trimmed = part.trim();
      if (trimmed && !trimmed.startsWith('@')) found.push(trimmed);
    }
  }
  return found;
}

/* The classes in a selector's LEFTMOST compound - the component the rule belongs to - with
 * pseudo-classes, pseudo-elements and attribute selectors stripped. Stripping matters: without
 * it `.act:hover` reads as a rule about something other than `.act` and every hover state in
 * the stylesheet is flagged. */
function ownerClasses(selector) {
  const leftmost = selector
    .split(/[\s>+~]+/)[0]
    .replace(/::?[\w-]+(\([^)]*\))?/g, '')
    .replace(/\[[^\]]*\]/g, '');
  return [...leftmost.matchAll(/\.([\w-]+)/g)].map(([, name]) => name);
}

/* Classes that carry a bare rule AND are deliberately styled inside another component, each
 * with the reason. A RATCHET, and the point of the whole check: adding an entry is a visible,
 * deliberate act in a diff, where a silent collision is not. Four collisions shipped in one
 * release because nobody could see them; this list is where "yes, that one is on purpose" has
 * to be written down. */
const DELIBERATE_CLASS_REUSE = {
  //: `.scope .tablewrap` squares off a table that sits inside a stimulus panel, which already
  //: has the border and the radius. The same component, adjusted for its context.
  tablewrap: ['.scope .tablewrap'],
  //: `.grid-rows .est .bar` narrows the competency bar inside the estimate grid. Same bar.
  bar: ['.grid-rows .est .bar'],
};

test('the harness dispatches events the way the DOM does, because four gaps say it must', () => {
  /* **The harness is an instrument, and an instrument that flatters the code is worse than
   * none.** Four fidelity gaps so far: `requestAnimationFrame` not calling back hid 68 lines, a
   * missing `viewBox.baseVal` hid 38, a missing `childElementCount` hid a whole section, and
   * `querySelectorAll` returning an array let a crash ship that took the library screen down.
   * The fifth was `fire()` dispatching to the target only: a button inside a clickable table
   * row called `openProcedure`, the event bubbled to the row's handler and called it again, and
   * no test could see one click become two fetches.
   *
   * Three of those five surface as coverage or as a failing assertion. Two - the array and the
   * missing bubble - surface as NOTHING, which is the direction worth a test of its own. This
   * one holds the dispatch contract, so a future simplification of `fire()` fails here rather
   * than quietly blinding every test that depends on it.
   */
  const { app, document } = load();
  const outer = document.createElement('div');
  const inner = document.createElement('button');
  outer.appendChild(inner);

  const seen = [];
  outer.addEventListener('click', () => seen.push('outer'));
  inner.addEventListener('click', () => seen.push('inner'));
  inner.fire('click');
  //: Target first, then up the chain - which is what made the double-fire possible.
  assert.deepEqual(seen, ['inner', 'outer'], 'the harness does not bubble');

  //: `stopPropagation` is honoured, which is the fix the double-fire needed.
  const stopped = [];
  const held = document.createElement('div');
  const control = document.createElement('button');
  held.appendChild(control);
  held.addEventListener('click', () => stopped.push('outer'));
  control.addEventListener('click', (event) => {
    event.stopPropagation();
    stopped.push('inner');
  });
  control.fire('click');
  assert.deepEqual(stopped, ['inner'], 'stopPropagation is ignored');

  //: And the event carries the target and the node currently handling it, as the DOM does.
  let targets = null;
  const parent = document.createElement('div');
  const child = document.createElement('span');
  parent.appendChild(child);
  parent.addEventListener('click', (event) => {
    targets = { target: event.target === child, current: event.currentTarget === parent };
  });
  child.fire('click');
  assert.deepEqual(targets, { target: true, current: true });
  assert.ok(app, 'the app context loaded');
});

test('no component reuses a class name the stylesheet already styles bare', () => {
  /* **Four name collisions shipped in one release and nobody could see any of them.** `.act` is
   * the primary button, so naming the step card `.act` restyled every button in the
   * application. `.rail` is the STICKY TOP NAVIGATION BAR - position sticky, z-index 20, a
   * backdrop blur - so the flow's step-number column inherited all of it on every procedure
   * screen. `.sub` is a page-subtitle paragraph, so a header band took its `max-width: 620px`
   * and 26px margin inside a 1124px card. `.ask` gave the decision header a subtitle's
   * letter-spacing.
   *
   * Every one is invisible to a browser sweep that checks overflow, console errors and page
   * exceptions, because the symptom is under-fill, wrong spacing or unwanted position rather
   * than a break. So: a class with a BARE rule may not also be styled where it is not the
   * component the rule belongs to. A bare rule applies everywhere the name appears, and nobody
   * adding the name later goes looking for it.
   *
   * **This check has now been too narrow twice.** It first read class names out of comments and
   * only inspected the leftmost compound, and passed on all four collisions. Then it was
   * delimited `.prochead` to `.scope {` - and the V0.29.0 table region landed BEFORE `.prochead`,
   * so `.libtable` and eight cell classes fell outside the window entirely. Widening it to
   * "everything below the card grid" was wrong too: the stylesheet is not ordered that way, and
   * `.covers` and `.tablewrap` are progress and stimulus components that happen to sit there.
   * There is no region boundary that means what I wanted it to mean, so there is none: the whole
   * stylesheet is scanned and the deliberate reuses are declared above by name.
   */
  const sheet = stylesheet(readFileSync(INDEX_HTML, 'utf8'));
  const selectors = selectorsIn(sheet);
  assert.ok(selectors.length > 200, `only ${selectors.length} selectors parsed`);

  const bare = new Set(
    selectors.filter((selector) => /^\.[\w-]+$/.test(selector)).map((selector) => selector.slice(1)),
  );
  assert.ok(bare.size > 20, `only ${bare.size} bare rules found`);

  /* **The SECOND collision shape, and checking only the first is why `.act` slipped through.**
   * A class is reused two ways: styled inside somebody else's component (`.leg > .rail`), or
   * given a second BARE rule of its own by a new component - which is exactly what naming the
   * step card `.act` did, and what naming the table `.covers` would do. The owner check below
   * cannot see the second shape, because the new rule owns the name too.
   *
   * So the bare-rule COUNT per class is ratcheted. Two classes legitimately have two today,
   * from `.act, .act2 { shared } .act { specific }`, which is ordinary CSS; a third would mean
   * a new component has claimed the name. Mechanical, and its diff is readable.
   */
  const doubled = [...bare]
    .map((name) => [name, selectors.filter((selector) => selector === `.${name}`).length])
    .filter(([, count]) => count > 1)
    .sort();
  assert.deepEqual(
    doubled,
    [
      ['act', 2],
      ['act2', 2],
    ],
    `a class gained or lost a bare rule: ${JSON.stringify(doubled)}. Two bare rules for one name`
      + ' means either the shared-plus-specific pair the buttons use, or a new component that has'
      + ' claimed a name the stylesheet already styles.',
  );

  const undeclared = [];
  for (const name of [...bare].sort()) {
    const reused = selectors.filter(
      (selector) => selector.includes(`.${name}`) && !ownerClasses(selector).includes(name),
    );
    const allowed = DELIBERATE_CLASS_REUSE[name] || [];
    for (const selector of reused) {
      /* `.${name}` as a substring would match `.barchart` for `bar`, so the owner check above
       * is confirmed against the selector's own class list rather than its text. */
      if (!selectorsMention(selector, name)) continue;
      if (!allowed.includes(selector)) undeclared.push(`.${name} is reused by ${selector}`);
    }
  }
  assert.deepEqual(undeclared, [], undeclared.join('\n'));
});

/* Whether a selector really mentions this class, rather than a longer name starting with it. */
function selectorsMention(selector, name) {
  return [...selector.matchAll(/\.([\w-]+)/g)].some(([, found]) => found === name);
}

test('a scatter mark is the right element for its glyph, with the right geometry', () => {
  const { app } = load();
  const dot = app.scatterMark('dot', 10, 20, 3, 'var(--sig)');
  assert.equal(dot.tagName, 'CIRCLE');
  assert.equal(dot.namespaceURI, SVG_NS, 'an SVG mark in the HTML namespace does not render');
  assert.equal(dot.getAttribute('r'), '3');
  assert.equal(dot.getAttribute('fill'), 'var(--sig)');

  const square = app.scatterMark('square', 10, 20, 2.6, 'var(--you)');
  assert.equal(square.tagName, 'RECT');
  //: Centred on the point, not hung off it: a square drawn from the point would sit down and to
  //: the right of the observation it represents.
  assert.equal(square.getAttribute('x'), '7.4');
  assert.equal(square.getAttribute('y'), '17.4');
  assert.equal(square.getAttribute('width'), '5.2');
  assert.equal(square.getAttribute('fill'), 'none', 'a filled square hides the marks beneath it');

  const bar = app.scatterMark('bar', 10, 20, 2.6, 'var(--cue)');
  assert.equal(bar.tagName, 'RECT');
  assert.equal(bar.getAttribute('fill'), 'var(--cue)');

  //: The default is a plus-cross, and the point is that it is NOT a polyline: a connecting line
  //: asserts continuity between observations that are not continuous.
  const cross = app.scatterMark('cross', 10, 20, 2.6, 'var(--sig)');
  assert.equal(cross.tagName, 'PATH');
  assert.match(cross.getAttribute('d'), /^M7\.4 20H12\.6M10 17\.4V22\.6$/);
  const unknown = app.scatterMark('not-a-glyph', 10, 20, 2.6, 'var(--sig)');
  assert.equal(unknown.tagName, 'PATH', 'an unrecognised glyph must still draw something');
});

test('a misshapen regime says so on screen rather than drawing something plausible', () => {
  const { app, element, value } = load();
  //: The SECOND line of defence, and it is load-bearing. `for...of` over a STRING yields
  //: characters, so a string-shaped payload rendered one pill per letter - on the server first,
  //: as a Python repr, and then on the client. The boundary refuses that shape now; this asserts
  //: the client refuses it too, because "the server validates it" is a claim about the server.
  const grid = element('library-grid');
  value('state').library.procedures = [
    { id: 'PROC-A', name: 'Good', status: 'active', purpose: 'p', regime: ['LEO', 'GEO'], steps: 3 },
    { id: 'PROC-B', name: 'String', status: 'active', purpose: 'p', regime: 'LEOMEO', steps: 3 },
    { id: 'PROC-C', name: 'Mapping', status: 'active', purpose: 'p', regime: { a: 1 }, steps: 3 },
    { id: 'PROC-D', name: 'Absent', status: 'active', purpose: 'p', steps: 3 },
  ];
  app.renderLibraryCards();

  const cards = [...grid.children];
  assert.equal(cards.length, 4);
  const tags = cards.map((card) => card.find('tags')[0]);

  //: One pill per regime for the array, and the ids are not repr-shaped.
  const good = [...tags[0].children].map((pill) => pill.textContent);
  assert.deepEqual([...good.slice(0, 2)], ['LEO', 'GEO']);
  assert.ok(!good.join('').includes('['), 'a list rendered as its own repr reached an operator once');

  for (const index of [1, 2]) {
    const pills = [...tags[index].children].map((pill) => pill.textContent);
    assert.ok(
      pills.some((text) => text.includes('regime unreadable')),
      `a non-array regime must be reported, not iterated: ${JSON.stringify(pills)}`,
    );
    //: And it must NOT have been split into one pill per character.
    assert.ok(pills.length <= 2, `a string regime was iterated into ${pills.length} pills`);
  }

  //: An ABSENT regime is not a fault. It draws no pill and says nothing, because there is
  //: nothing to report - the unknown marker is for a value of the wrong shape.
  const absent = [...tags[3].children].map((pill) => pill.textContent);
  assert.ok(!absent.some((text) => text.includes('unreadable')), JSON.stringify(absent));
});

test('the debrief reports a rating that moved, and one that did not, differently', () => {
  const { app, element } = load();
  const host = element('reveal');
  const result = {
    matched: 'accept',
    item_id: 'DRL-0001',
    rating_before: 1200,
    rating_after: 1213,
    rating_delta: 13,
    brier: 0.0625,
    calibration: 'confident and right',
    next_due_in_days: 3,
    note: '',
    total: 100,
    score_components: [{ rule_id: 'D-NAMED', award: 45, explain: 'named it' }],
    unimplemented_rules: [],
    unimplemented_aggregation: [],
  };
  app.renderReveal(result);
  const up = host.find('d')[0];
  assert.equal(up.textContent, '+13');
  assert.ok(up.classList.contains('up'), 'a gain must not be painted as a loss');

  //: A drop carries the sign the payload gave it and the down class. A `+` on a negative number
  //: is the kind of detail a nested ternary gets wrong.
  app.renderReveal({ ...result, rating_after: 1187, rating_delta: -13 });
  const down = host.find('d')[0];
  assert.equal(down.textContent, '-13');
  assert.ok(down.classList.contains('down'));

  //: No movement is stated as no movement, with NO direction class: an arrow either way would
  //: be a claim about a change that did not happen.
  app.renderReveal({ ...result, rating_delta: 0 });
  const flat = host.find('d')[0];
  assert.equal(flat.textContent, 'no change');
  assert.ok(!flat.classList.contains('up') && !flat.classList.contains('down'));

  //: And an unscored rating says so rather than printing a number it does not have.
  app.renderReveal({ ...result, rating_after: null, rating_delta: null });
  assert.equal(host.find('v')[0].textContent, 'unchanged');
});

test('the debrief withholds the habit panel when the payload carries no coaching line', () => {
  const { app } = load();
  //: The panel's text is the AUTHORED line off the scored payload. A habit this interface made
  //: up would be a claim about a person, so an absent note renders nothing at all.
  assert.equal(app.habitPanel({ note: '' }), null);
  assert.equal(app.habitPanel({ note: undefined }), null);
  const panel = app.habitPanel({ note: 'You commit before reading the second panel.' });
  assert.ok(panel.textContent.includes('second panel'));
  assert.ok(panel.classList.contains('habit'));
});

test('a rubric this evaluator did not fully apply is disclosed, not omitted', () => {
  const { app } = load();
  //: A score that silently skipped a rule reads exactly like a complete score, and those are
  //: opposite facts. Both disclosures are separate because a rubric can trip either.
  assert.equal(app.disclosureNotes({}).length, 0);
  const rules = app.disclosureNotes({ unimplemented_rules: ['D-A', 'D-B'] });
  assert.equal(rules.length, 1);
  assert.ok(rules[0].textContent.includes('D-A, D-B'));
  assert.ok(rules[0].textContent.includes('2 rule(s)'));

  const both = app.disclosureNotes({
    unimplemented_rules: ['D-A'],
    unimplemented_aggregation: ['speed_factor'],
  });
  assert.equal(both.length, 2);
  assert.ok(both[1].textContent.includes('speed_factor'));
});

test('a verdict carries a glyph and a heading, so it never rests on colour', () => {
  const { app, value } = load();
  const glyphs = value('VERDICT_GLYPH');
  for (const matched of Object.keys(glyphs)) {
    const block = app.verdictBlock({ matched });
    assert.ok(block.classList.contains('verdict'));
    assert.ok(block.classList.contains(matched), `the verdict class must name ${matched}`);
    const heading = block.children[0];
    assert.equal(heading.tagName, 'H3');
    //: The glyph is a separate span so the heading reads as glyph-then-words to a screen reader
    //: and so the meaning survives a monochrome print.
    assert.ok(heading.children[0].classList.contains('glyph'));
    assert.ok(heading.textContent.length > heading.children[0].textContent.length);
  }
  //: An unrecognised verdict still renders a glyph and a sentence rather than an empty block.
  const unknown = app.verdictBlock({ matched: 'something-new' });
  assert.ok(unknown.textContent.trim().length > 0);
});

test('a competency row states "not measured" rather than dressing a zero as a finding', () => {
  const { app } = load();
  //: The one place a zero could be read as a result. An axis with no attempts has no estimate,
  //: and a `0` beside a band word would report a weakness the data cannot support.
  const unmeasured = app.competencyRow({ name: 'Recall', attempts: 0, measured: false }, 0);
  assert.equal(unmeasured.find('idx')[0].textContent, '01', 'the index is padded for alignment');
  assert.ok(unmeasured.textContent.includes('0 calls'));
  assert.ok(unmeasured.textContent.includes('not measured'));
  const status = unmeasured.find('status')[0];
  assert.equal(status.className, 'status', 'an unmeasured row must carry no band class');

  const measured = app.competencyRow({ name: 'Recall', attempts: 1, measured: true, estimate: 0.62 }, 9);
  assert.equal(measured.find('idx')[0].textContent, '10');
  assert.ok(measured.textContent.includes('1 call'), 'one attempt is a call, not calls');
  assert.ok(measured.textContent.includes('fair'), 'the band WORD rides with the figure');
  assert.ok(measured.textContent.includes('62'));
});

test('an estimate always carries its interval, never a bare number', () => {
  const { app } = load();
  //: The flight plan calls a bare estimate a claim the data cannot support. The handoff's own
  //: Progress table shows one; this keeps the handoff's bar and the plan's interval.
  const cell = app.estimateCell({
    measured: true,
    estimate: 0.62,
    interval: [0.48, 0.74],
  });
  const figure = cell.find('fig')[0];
  assert.equal(figure.textContent, '62 (48–74)');
  assert.ok(figure.classList.contains('f-accent'), 'the tone must match the band');
  const track = cell.children[0];
  assert.equal(track.children[0].style.width, '62%');

  const absent = app.estimateCell({ measured: false });
  assert.equal(absent.find('fig')[0].textContent, 'not measured');
  assert.equal(absent.children.length, 1, 'an unmeasured axis draws no bar');
});
