/* What the interface BUILDS, asserted on the nodes rather than on a screenshot.
 *
 * Three of these cover classes of fault that reached a running server in this project: a Python
 * repr on a library card, a plausible-but-wrong value from a misshapen field, and a static label
 * that made a claim the payload could not support. A screenshot found the first two; a test that
 * builds the node finds them before an upload does.
 */

import assert from 'node:assert/strict';
import test from 'node:test';
import { load } from './harness.mjs';

const SVG_NS = 'http://www.w3.org/2000/svg';

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

  const cards = grid.children;
  assert.equal(cards.length, 4);
  const tags = cards.map((card) => card.find('tags')[0]);

  //: One pill per regime for the array, and the ids are not repr-shaped.
  const good = tags[0].children.map((pill) => pill.textContent);
  assert.deepEqual([...good.slice(0, 2)], ['LEO', 'GEO']);
  assert.ok(!good.join('').includes('['), 'a list rendered as its own repr reached an operator once');

  for (const index of [1, 2]) {
    const pills = tags[index].children.map((pill) => pill.textContent);
    assert.ok(
      pills.some((text) => text.includes('regime unreadable')),
      `a non-array regime must be reported, not iterated: ${JSON.stringify(pills)}`,
    );
    //: And it must NOT have been split into one pill per character.
    assert.ok(pills.length <= 2, `a string regime was iterated into ${pills.length} pills`);
  }

  //: An ABSENT regime is not a fault. It draws no pill and says nothing, because there is
  //: nothing to report - the unknown marker is for a value of the wrong shape.
  const absent = tags[3].children.map((pill) => pill.textContent);
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
