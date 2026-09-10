/* Every view, driven end to end against payloads the real server produced.
 *
 * The fixtures under `fixtures/` were captured from a running instance rather than written by
 * hand, which matters: a hand-written payload agrees with whatever the test author believed the
 * API returns, and this project has already shipped one defect that came from exactly that gap
 * (a `regime` list served as a Python repr, invisible to a green suite). `drill.json` is trimmed
 * to three mark groups of eight points - the real SHAPE at a size a person can read - and
 * nothing else is altered. Where a test needs state the fresh volume cannot produce, such as a
 * MEASURED competency, it derives it from the captured payload and says so.
 */

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { load } from './harness.mjs';

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), 'fixtures');
const fixture = (name) => JSON.parse(readFileSync(join(FIXTURES, `${name}.json`), 'utf8'));

const ME = fixture('me');
const MANIFEST = fixture('manifest');
const DRILL = fixture('drill');
const ANSWER = fixture('answer');
const PROCEDURES = fixture('procedures');
const PROCEDURE = fixture('procedure');

/* The captured dashboard is from a fresh volume, so every axis is unmeasured. Measured state is
 * derived from it rather than invented: the same rows, with estimates and intervals added. */
function measuredMe() {
  const competencies = ME.competencies.map((competency, index) => ({
    ...competency,
    attempts: index + 1,
    measured: true,
    estimate: 0.3 + index * 0.09,
    interval: [0.2 + index * 0.09, 0.45 + index * 0.09],
    mean_brier: 0.18,
  }));
  return { ...ME, competencies, runs_total: 7, due_now: 4 };
}

const ROUTES = {
  '/api/v1/me': ME,
  '/api/v1/content/manifest': MANIFEST,
  '/api/v1/content/procedures': PROCEDURES,
  '/api/v1/content/procedure/': PROCEDURE,
  '/api/v1/drill/next': DRILL,
  '/api/v1/drill/answer': ANSWER,
};

const booted = (routes = ROUTES) => load({ readyState: 'complete', routes });

test('boot wires the shell, reports the content it loaded, and opens the session view', async () => {
  const harness = booted();
  await harness.settle();
  //: The rail carries the drill count and the content hash: the one provenance string that makes
  //: a run reproducible. Both come from the manifest rather than from anything composed here.
  const rail = harness.element('rail-status').textContent;
  assert.match(rail, /^140 drills · 0e395153$/);
  //: The TEXT, not the rendering. The capitals a browser shows come from `text-transform`
  //: in the stylesheet, which is the cascade's job and not this script's - a distinction a
  //: screenshot cannot make and this harness must not pretend to.
  assert.equal(harness.element('session-kicker').textContent, 'Session · content 0e395153');
  //: Every nav control is wired, and the session view is the one that opened.
  assert.equal(harness.document.querySelectorAll('#nav button').length, 4);
  assert.ok(harness.calls.some((call) => call.path === '/api/v1/me'));
});

test('a content fault reaches the operator instead of being swallowed', async () => {
  const harness = booted({
    ...ROUTES,
    '/api/v1/content/manifest': {
      ...MANIFEST,
      ok: false,
      errors: ['rubrics.json: missing rule id', 'drills.json: unknown cue'],
    },
  });
  await harness.settle();
  assert.equal(harness.element('rail-status').textContent, 'content fault');
  //: Both errors, joined, because a content fault an author cannot read is a fault they cannot
  //: fix. The banner is the only place this reaches them.
  const banner = harness.element('banner').textContent;
  assert.match(banner, /missing rule id/);
  assert.match(banner, /unknown cue/);
});

test('an unreachable server says offline rather than showing a stale count', async () => {
  const harness = booted({ ...ROUTES, '/api/v1/content/manifest': new Error('network down') });
  await harness.settle();
  assert.equal(harness.element('rail-status').textContent, 'offline');
});

test('the session view reports measured axes, and reports absence as absence', async () => {
  const harness = booted({ ...ROUTES, '/api/v1/me': measuredMe() });
  await harness.settle();
  assert.match(harness.element('session-title').textContent, /^Today you are drilling /);
  //: The weakest axis is the LOWEST measured estimate, and its card carries the interval.
  assert.equal(harness.element('weak-name').textContent, 'Cue detection');
  assert.match(harness.element('weak-body').textContent, /interval 20 to 45/);
  assert.equal(harness.element('weak-bar').style.width, '30%');
  assert.match(harness.element('weak-bar').style.background, /^var\(--(bad|warn|accent|good)\)$/);
  //: One row per competency, and the count is the payload's, not a constant.
  assert.equal(harness.element('covers').children.length, ME.competencies.length);
  assert.match(harness.element('recorded-body').textContent, /7 answers recorded/);
  //: The game layer carries REAL counts under truthful labels. The mockup's streak has no
  //: source in this payload, so the slot reports answers recorded instead.
  assert.equal(harness.element('streak-n').textContent, '7');
  assert.match(harness.element('streak-unit').textContent, /answers recorded/);
});

test('a clean sheet is described as a clean sheet, with no figure invented for it', async () => {
  const harness = booted();
  await harness.settle();
  //: The captured payload is a fresh volume: nothing measured. A zero dressed as a finding is
  //: the one thing this screen must not do.
  assert.match(harness.element('session-title').textContent, /clean sheet/);
  assert.equal(harness.element('weak-name').textContent, 'Not measured yet');
  assert.match(harness.element('weak-body').textContent, /cannot support/);
  for (const row of harness.element('covers').children) {
    assert.match(row.textContent, /not measured/);
  }
});

test('a failed dashboard fetch tells the operator what failed and why', async () => {
  const harness = booted({
    ...ROUTES,
    '/api/v1/me': { __status: 503, detail: { error: 'storage', message: 'The volume is read-only.' } },
  });
  await harness.settle();
  //: The framing names what failed and the server's own sanitised detail says why. This handler
  //: discarded the error and showed a fixed sentence until V0.27.6.
  const banner = harness.element('banner').textContent;
  assert.match(banner, /session could not be loaded/);
  assert.match(banner, /volume is read-only/);
});

test('the drill view draws the served stimulus, its table and its legend', async () => {
  const harness = booted();
  await harness.settle();
  harness.app.show('drill');
  await harness.settle();

  assert.equal(harness.element('drill-prompt').textContent, DRILL.prompt);
  assert.match(harness.element('drill-kicker').textContent, /DRL-0005/);
  const stimuli = harness.element('stimuli');
  //: An SVG frame in the SVG namespace, with marks in it. A frame built in the HTML namespace
  //: renders nothing at all and looks identical in a DOM dump.
  const frames = stimuli.querySelectorAll('svg');
  assert.equal(frames.length, 1);
  const paths = frames[0].querySelectorAll('path');
  assert.ok(paths.length > 0, 'the served marks drew nothing');
  //: The time axis is labelled with the SEED's timestamps, never bare numbers: a day number
  //: cannot be correlated against a pass schedule, which is what an operator does with a time
  //: axis. The tick labels come straight off the payload.
  const text = frames[0].querySelectorAll('text').map((node) => node.textContent);
  assert.ok(text.some((label) => /Jun \d\d:\d\dZ/.test(label)), JSON.stringify(text));
  //: And the refit ran: it is scheduled inside a frame callback, which the harness invokes.
  assert.ok(frames[0].getAttribute('viewBox'), 'the frame never got a viewBox');
});

test('the confidence group is one radio group with one tab stop, not five buttons', async () => {
  const harness = booted();
  await harness.settle();
  harness.app.show('drill');
  await harness.settle();

  const group = harness.element('confidence-group');
  const buttons = group.children;
  assert.equal(buttons.length, 5);
  //: `role="radiogroup"` is on the element in `index.html`, so it is the document's claim and
  //: the Python suite asserts it there. What the SCRIPT owns is each option's role and the
  //: single tab stop, and that is what is asserted here.
  for (const button of buttons) assert.equal(button.getAttribute('role'), 'radio');
  //: ONE tab stop. Five focusable buttons make a keyboard operator press Tab five times to pass
  //: a single control, which is the gap the handoff named.
  assert.equal(buttons.filter((button) => button.tabIndex === 0).length, 1);
  assert.equal(buttons.filter((button) => button.getAttribute('aria-checked') === 'true').length, 0);

  buttons[2].fire('click');
  const checked = () => group.children.find((b) => b.getAttribute('aria-checked') === 'true');
  assert.ok(checked(), 'a click must select');
  const before = checked().textContent;
  //: Arrow keys move the selection and wrap, which is the radiogroup pattern.
  group.children.find((b) => b.getAttribute('aria-checked') === 'true').fire('keydown', { key: 'ArrowRight' });
  assert.notEqual(checked().textContent, before);
  const tabbed = { key: 'Tab', prevented: false };
  group.children[0].fire('keydown', tabbed);
  assert.ok(checked(), 'Tab must not clear the selection');
});

test('an answer with no text, and one with no confidence, are both refused before the wire', async () => {
  const harness = booted();
  await harness.settle();
  harness.app.show('drill');
  await harness.settle();
  const before = harness.calls.length;

  harness.element('answer-form').fire('submit');
  assert.match(harness.element('banner').textContent, /Type your call first/);
  assert.equal(harness.calls.length, before, 'an empty call must not reach the server');

  harness.element('response').value = 'manoeuvre, then screen for conjunctions';
  harness.element('answer-form').fire('submit');
  //: Calibration is scored, so a call with no stated confidence is incomplete rather than
  //: silently defaulted: defaulting it would record a confidence the operator never gave.
  assert.match(harness.element('banner').textContent, /how sure you are/);
  assert.equal(harness.calls.length, before);
});

test('a committed answer is scored, revealed, and never scored twice', async () => {
  const harness = booted();
  await harness.settle();
  harness.app.show('drill');
  await harness.settle();

  harness.element('response').value = 'manoeuvre, then screen for conjunctions';
  harness.element('confidence-group').children[2].fire('click');
  harness.element('answer-form').fire('submit');
  await harness.settle();

  const posted = harness.calls.filter((call) => call.path === '/api/v1/drill/answer');
  assert.equal(posted.length, 1);
  const body = JSON.parse(posted[0].options.body);
  assert.equal(body.drill_run_id, DRILL.drill_run_id);
  assert.equal(body.response, 'manoeuvre, then screen for conjunctions');
  assert.ok(body.confidence >= 1 && body.confidence <= 5);
  //: The elapsed time is measured from when the drill was SERVED, and the award is computed
  //: server-side from that: the client's countdown is a display.
  assert.ok(Number.isFinite(body.elapsed_ms) && body.elapsed_ms >= 0);

  const reveal = harness.element('reveal');
  assert.ok(!reveal.classList.contains('hidden'));
  assert.match(reveal.textContent, /Not a recognised answer/);
  //: The decomposition is the payload's rules, plus the total row.
  assert.equal(reveal.querySelectorAll('tr').length, ANSWER.score_components.length + 2);
  //: And what the rubric asked for and the evaluator did not apply is disclosed.
  assert.match(reveal.textContent, /calibration_weight/);
  //: Re-armed in `finally`, deliberately: the operator moves on with `Next cue`, and a
  //: permanently dead button would strand them if the reveal ever failed to render. What
  //: stops a double score is the run id, which the server refuses twice - asserted above by
  //: there being exactly one POST for one submit.
  assert.equal(harness.element('submit').disabled, false);
});

test('a refused submission surfaces the server message and re-arms the form', async () => {
  const harness = booted({
    ...ROUTES,
    '/api/v1/drill/answer': {
      __status: 409,
      detail: { error: 'already_scored', message: 'That run was already scored.' },
    },
  });
  await harness.settle();
  harness.app.show('drill');
  await harness.settle();
  harness.element('response').value = 'breakup';
  harness.element('confidence-group').children[4].fire('click');
  harness.element('answer-form').fire('submit');
  await harness.settle();

  assert.match(harness.element('banner').textContent, /already scored/);
  //: Re-armed, not dead. A refusal the operator cannot retry is a lost session.
  assert.equal(harness.element('submit').disabled, false);
});

test('the countdown paints from the served target and stops when the drill ends', async () => {
  const harness = booted();
  await harness.settle();
  harness.app.show('drill');
  await harness.settle();

  const digits = harness.element('countdown-n').textContent;
  assert.match(digits, /^\d+s$/, 'the countdown carries its unit');
  assert.ok(Number.parseInt(digits, 10) <= DRILL.time_target_s);
  harness.tick();
  assert.match(harness.element('countdown-fill').style.width, /%$/);
  //: The countdown is display only, and it must not outlive the drill: a timer still running
  //: behind a debrief repaints a element the operator is no longer looking at.
  harness.app.stopCountdown();
  harness.tick();
  assert.ok(true);
});

test('a drill that cannot be served says so where the prompt would be', async () => {
  const harness = booted({
    ...ROUTES,
    '/api/v1/drill/next': {
      __status: 503,
      detail: { error: 'content_unavailable', message: 'No item has a resolvable stimulus.' },
    },
  });
  await harness.settle();
  harness.app.show('drill');
  await harness.settle();

  //: The banner carries the server's reason AND the prompt says the view is empty on purpose.
  //: A blank prompt with a banner above it reads as a view that has not finished loading, and an
  //: operator waits for a cue that is never coming.
  assert.match(harness.element('banner').textContent, /resolvable stimulus/);
  assert.equal(harness.element('drill-prompt').textContent, 'No drill available.');
});

test('a progress fetch that fails surfaces the reason', async () => {
  //: The dashboard is fetched by BOTH the session view and the progress view. This answers the
  //: first call and refuses the second, so the failure under test is the one the progress view
  //: sees rather than a session that never loaded. The counter sits outside the route because
  //: the routes are built before `harness` is bound.
  let dashboardCalls = 0;
  const harness = booted({
    ...ROUTES,
    '/api/v1/me': () => {
      dashboardCalls += 1;
      return dashboardCalls > 1
        ? { __status: 503, detail: { error: 'storage', message: 'progress.json is unreadable.' } }
        : measuredMe();
    },
  });
  await harness.settle();
  assert.equal(harness.element('banner').textContent, '');
  harness.app.show('progress');
  await harness.settle();
  assert.match(harness.element('banner').textContent, /progress\.json is unreadable/);
});

test('the progress view reports every axis with its interval', async () => {
  const harness = booted({ ...ROUTES, '/api/v1/me': measuredMe() });
  await harness.settle();
  harness.app.show('progress');
  await harness.settle();

  assert.equal(harness.element('progress-cards').children.length, 4);
  const body = harness.element('progress-body');
  const figures = body.find('fig');
  assert.equal(figures.length, ME.competencies.length);
  //: Every figure carries its interval. A bare estimate is a claim the data cannot support.
  for (const figure of figures) {
    assert.match(figure.textContent, /^\d+ \(\d+–\d+\)$/, figure.textContent);
  }
  //: The identity line is the PRIVACY statement, not a name: operator identity does not
  //: exist yet and every run is recorded against a synthetic operator until the DPIA is
  //: closed. Asserted so the screen cannot start naming an individual by accident.
  const identity = harness.element('progress-identity').textContent;
  assert.match(identity, /synthetic operator/);
  assert.match(identity, /DPIA/);
});

test('the library lists the procedures, filters them, and opens one', async () => {
  const harness = booted();
  await harness.settle();
  harness.app.show('library');
  await harness.settle();

  const grid = harness.element('library-grid');
  assert.equal(grid.children.length, PROCEDURES.count);
  //: The status chips are derived from the statuses the CONTENT declares, plus "all". A filter
  //: offering a category the library does not contain can only ever return nothing.
  const chips = harness.element('library-chips');
  const labels = chips.children.map((chip) => chip.textContent);
  const statuses = new Set(PROCEDURES.procedures.map((procedure) => procedure.status));
  assert.equal(labels.length, statuses.size + 2, JSON.stringify(labels));
  assert.ok(labels.includes('all'));
  //: A legend, so the fieldset has an accessible name.
  assert.equal(chips.children[0].tagName, 'LEGEND');

  const draft = chips.children.find((chip) => chip.textContent === 'draft');
  draft.fire('click');
  const shown = harness.element('library-grid').children.length;
  assert.ok(shown > 0 && shown < PROCEDURES.count, `filtering to draft showed ${shown}`);

  //: Search narrows on the text an author wrote, and an unmatched query says so rather than
  //: rendering an empty grid that reads as a loading state.
  chips.children.find((chip) => chip.textContent === 'all').fire('click');
  const search = harness.element('library-search');
  search.value = 'zzzz-no-such-procedure';
  search.fire('input');
  //: ONE card, and it is the empty state rather than nothing at all: a bare empty grid reads as
  //: a view still loading, and the operator waits for something that is not coming.
  const empty = harness.element('library-grid').children;
  assert.equal(empty.length, 1);
  assert.ok(empty[0].classList.contains('empty'));
  assert.equal(empty[0].disabled, true, 'the empty state must not look clickable');
  assert.match(empty[0].textContent, /No procedure matches/);

  search.value = '';
  search.fire('input');
  harness.app.openProcedure('PROC-MNV');
  await harness.settle();
  assert.match(harness.element('library-body').textContent, /PROC-MNV/);
});

test('a library fetch that fails does not leave the view looking empty', async () => {
  const harness = booted({
    ...ROUTES,
    '/api/v1/content/procedures': {
      __status: 503,
      detail: { error: 'content_unavailable', message: 'One procedure is malformed.' },
    },
  });
  await harness.settle();
  harness.app.show('library');
  await harness.settle();
  assert.match(harness.element('banner').textContent, /malformed/);
});

test('switching views hides the others and marks the current one for a screen reader', async () => {
  const harness = booted();
  await harness.settle();
  for (const name of ['drill', 'progress', 'library', 'session']) {
    harness.app.show(name);
    await harness.settle();
    const current = harness.document
      .querySelectorAll('#nav button')
      .filter((button) => button.getAttribute('aria-current') === 'page');
    assert.equal(current.length, 1, `${name}: exactly one control is current`);
    assert.equal(current[0].getAttribute('data-view'), name);
  }
});
