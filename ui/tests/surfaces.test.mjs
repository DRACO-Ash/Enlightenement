/* The plot and table surfaces, over stimuli the real generators produced.
 *
 * `fixtures/surfaces.json` holds one client-form stimulus per surface this file exercises, taken
 * from `compose(build_registry(), ...)` at a fixed seed - the same call the drill route makes -
 * and trimmed to two mark groups of six points. Not hand-written, for the reason the view tests
 * give: a payload invented by the test author agrees with the author's belief about the API
 * rather than with the API.
 *
 * PRD-COCO carries a table, PRD-EPHEMERIS an axis with no authored ticks, PRD-PHOTOMETRY a
 * recency ramp, PRD-TRIC a step series. Four products, four rendering paths that the waterfall
 * in the drill fixture does not reach.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { load } from './harness.mjs';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), 'fixtures');
const SURFACES = JSON.parse(readFileSync(join(FIXTURES, 'surfaces.json'), 'utf8'));

/* Draw one stimulus into a detached scope, the way `loadDrill` does. */
function draw(harness, stimulus) {
  const scope = harness.app.drawStimulus(stimulus);
  return scope;
}

test('a tabular product renders its columns, its alignment and its emphasis', () => {
  const harness = load();
  const stimulus = SURFACES.table;
  const scope = draw(harness, stimulus);

  const headers = scope.querySelectorAll('th').map((cell) => cell.textContent);
  assert.deepEqual([...headers], stimulus.columns.map((column) => column.label));
  //: A right-aligned column is right-aligned in the HEAD as well as the body. Numbers that line
  //: up under a left-aligned header are harder to compare, which is the whole point of a table.
  for (const [index, column] of stimulus.columns.entries()) {
    const cell = scope.querySelectorAll('th')[index];
    assert.equal(cell.className, column.align === 'right' ? 'r' : '', column.label);
  }
  const rows = scope.querySelectorAll('tr');
  assert.equal(rows.length, stimulus.rows.length + 1, 'one head row plus one row per record');
  //: Every cell carries text: an empty cell reads as a value the operator failed to notice, and
  //: `cellText` exists to make absence explicit instead.
  for (const cell of scope.querySelectorAll('td')) {
    assert.ok(cell.textContent.length > 0, 'a blank cell is indistinguishable from a missed one');
  }
  //: The table scrolls inside its own container rather than widening the page.
  assert.ok(scope.find('tablewrap').length > 0);
});

test('an axis with no authored ticks generates its own, and honours inversion', () => {
  const harness = load();
  const stimulus = SURFACES.noticks;
  const scope = draw(harness, stimulus);
  const frame = scope.querySelectorAll('svg')[0];
  const labels = frame.querySelectorAll('text').map((node) => node.textContent);
  //: Five generated ticks, so an axis the content did not label is still readable. An unlabelled
  //: axis is a picture rather than a measurement.
  assert.ok(labels.length >= 5, `only ${labels.length} labels on an unticked axis`);
  for (const label of labels) assert.notEqual(label.trim(), '');
  assert.ok(frame.getAttribute('viewBox'), 'the frame never got a viewBox');
});

test('a ramped product legends the recency scale and drops the role swatches', () => {
  const harness = load();
  const stimulus = SURFACES.ramp;
  assert.ok(harness.app.ramped(stimulus), 'the fixture must actually carry a ramp');
  const scope = draw(harness, stimulus);
  const legend = scope.find('legend')[0];
  const text = legend.textContent;
  //: When the points are drawn in the RAMP, a role swatch beside the label is a lie: the swatch
  //: would show a colour the panel does not use for that series.
  assert.match(text, /most recent/);
  assert.match(text, /oldest/);
  const swatches = legend.querySelectorAll('i');
  assert.equal(swatches.length, 3, 'exactly the three ramp stops carry a swatch');
  for (const label of stimulus.legend.map((pair) => pair[0])) {
    assert.ok(text.includes(label), `${label} missing from the legend`);
  }
});

test('an unramped product legends its roles with a swatch each', () => {
  const harness = load();
  //: PRD-EPHEMERIS, which encodes no recency. PRD-TRIC was the first choice here and it DOES
  //: ramp four of its seven groups, which the assertion caught - a reminder that "which products
  //: use the ramp" is a fact about the generators and not something to assume from a name.
  const stimulus = SURFACES.noticks;
  assert.equal(harness.app.ramped(stimulus), false);
  const scope = draw(harness, stimulus);
  const legend = scope.find('legend')[0];
  assert.equal(legend.querySelectorAll('i').length, stimulus.legend.length);
});

test('a step series is drawn as a staircase, never as a curve through the changes', () => {
  const harness = load();
  const scope = draw(harness, SURFACES.step);
  const paths = scope
    .querySelectorAll('path')
    .map((node) => node.getAttribute('d'))
    .filter(Boolean);
  //: `H` then `V` is the staircase. A discrete state change drawn as a slope asserts a
  //: transition that did not happen, on a product whose whole subject is when state changed.
  assert.ok(
    paths.some((d) => /H[\d.]+V[\d.]+/.test(d)),
    `no staircase segment in ${JSON.stringify(paths.slice(0, 2))}`,
  );
});

test('every surface states what it reads as, and where its numbers came from', () => {
  const harness = load();
  for (const [name, stimulus] of Object.entries(SURFACES)) {
    const scope = draw(harness, stimulus);
    const text = scope.textContent;
    //: The footer carries the seed and the provenance markers. A synthetic surface that does not
    //: say so is the fabrication rule broken on the one screen an operator trusts most.
    assert.ok(text.includes(stimulus.footer), `${name}: the footer is not rendered`);
    assert.match(stimulus.footer, /seed 0x/, `${name}: the footer states no seed`);
    if (stimulus.reads_as) {
      assert.ok(text.includes(stimulus.reads_as), `${name}: reads_as is not rendered`);
    }
    for (const [label, value] of stimulus.header) {
      assert.ok(text.includes(label), `${name}: header label ${label} missing`);
      assert.ok(text.includes(String(value)), `${name}: header value for ${label} missing`);
    }
  }
});

test('the refit widens the box when a label overflows it, and settles', () => {
  const harness = load();
  const stimulus = SURFACES.noticks;
  const scope = draw(harness, stimulus);
  const frame = scope.querySelectorAll('svg')[0];
  const nominal = frame.getAttribute('viewBox');

  //: A label measured well outside the box on the LEFT, which is the fault this path exists for:
  //: below about 680 CSS px the timestamp labels sheared off the left edge of the viewBox.
  for (const text of frame.querySelectorAll('text')) {
    text.box = { x: -80, y: -10, width: 40, height: 12 };
  }
  harness.app.sizePlotText(frame);
  const widened = frame.getAttribute('viewBox');
  assert.notEqual(widened, nominal, 'an overflowing label did not widen the box');
  assert.ok(Number(widened.split(' ')[0]) < 0, `the box did not grow leftwards: ${widened}`);

  //: And it SETTLES. The widening changes the scale, which changes the size, so the loop is
  //: bounded; a second call with the labels now inside must not keep growing it.
  for (const text of frame.querySelectorAll('text')) {
    text.box = { x: 10, y: 10, width: 20, height: 10 };
  }
  harness.app.sizePlotText(frame);
  const settled = frame.getAttribute('viewBox');
  harness.app.sizePlotText(frame);
  assert.equal(frame.getAttribute('viewBox'), settled, 'the refit never settled');
});

test('a label that cannot be measured degrades to the nominal box rather than throwing', () => {
  const harness = load();
  const scope = draw(harness, SURFACES.noticks);
  const frame = scope.querySelectorAll('svg')[0];
  //: `getBBox` is not universally safe on an unrendered subtree: Chromium returns zeros inside a
  //: `display:none` container and other engines throw. A throw here would escape the frame
  //: callback, so the guard degrades to the build-time gutter instead.
  for (const text of frame.querySelectorAll('text')) text.box = null;
  const before = frame.getAttribute('viewBox');
  harness.app.sizePlotText(frame);
  assert.equal(frame.getAttribute('viewBox'), before);
});

test('a resize re-runs the refit from the nominal box rather than ratcheting', () => {
  const harness = load();
  const scope = draw(harness, SURFACES.noticks);
  const frame = scope.querySelectorAll('svg')[0];
  //: One observer per FRAME, and this product draws two panels, so the observer for the frame
  //: under test is found by its target rather than by being the most recent.
  const observer = harness.observers.find((candidate) => candidate.target === frame);
  assert.ok(observer, 'the plot registered no resize observer for this frame');
  assert.equal(
    harness.observers.length,
    scope.querySelectorAll('svg').length,
    'one refit observer per frame, or a resize leaves a panel stale',
  );

  for (const text of frame.querySelectorAll('text')) {
    text.box = { x: -60, y: 0, width: 30, height: 12 };
  }
  observer.callback();
  const first = frame.getAttribute('viewBox');
  //: Run again with the same overflow. The box is reset to nominal before each refit, so the
  //: answer is identical - without the reset each resize measured an already-widened box and
  //: grew it again, and the plot shrank away.
  observer.callback();
  assert.equal(frame.getAttribute('viewBox'), first, 'the viewBox ratcheted across resizes');
});

test('a redraw releases the observers it is about to orphan', () => {
  const harness = load();
  draw(harness, SURFACES.noticks);
  draw(harness, SURFACES.step);
  const live = harness.observers.length;
  assert.ok(live >= 2);
  //: A 50-drill session would otherwise build 50 observers over detached subtrees, on the
  //: reading that the engine does not make that edge weak.
  harness.app.releasePlotRefits();
  assert.ok(harness.observers.every((observer) => observer.disconnected));
});

test('a non-finite sample is dropped rather than drawn at a nonsense coordinate', () => {
  const harness = load();
  const stimulus = structuredClone(SURFACES.step);
  const panel = stimulus.panels[0];
  const group = (panel.marks[0] ?? panel.steps[0]);
  group.x = [...group.x, Number.NaN, 1];
  group.y = [...group.y, 5, Number.POSITIVE_INFINITY];
  const scope = draw(harness, stimulus);
  //: It must render, and it must not carry NaN into an attribute: `d="MNaN 12"` is a path the
  //: browser drops silently, so the whole series disappears rather than one point.
  const drawn = scope.querySelectorAll('path').map((node) => node.getAttribute('d')).join(' ');
  assert.ok(!drawn.includes('NaN'), drawn.slice(0, 120));
  assert.ok(!drawn.includes('Infinity'), drawn.slice(0, 120));
});
