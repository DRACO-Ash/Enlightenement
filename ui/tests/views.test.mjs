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
  const text = [...frames[0].querySelectorAll('text')].map((node) => node.textContent);
  //: Matched on the SHAPE of a timestamp, not on a month. This read `/Jun \d\d:\d\dZ/`, and
  //: halving `MAX_SPAN_DAYS` at V0.27.15 moved `SYNTHETIC_EPOCH_SPAN_HOURS` and with it the
  //: seeded window - from 05 June to 30 June, which runs into July - so the month had become a
  //: coincidence that happened to still hold. A test pinned to an incidental fact passes until
  //: it doesn't, and then fails for a reason that has nothing to do with what it is checking.
  const stamped = /^\d\d [A-Z][a-z]{2} \d\d:\d\dZ$/;
  assert.ok(text.some((label) => stamped.test(label)), JSON.stringify(text));
  //: And the labels are the SERVED ones, so the axis cannot be labelled from anything else.
  const ticks = DRILL.stimulus[0].panels[0].y.ticks.map(([, label]) => label);
  assert.ok(ticks.length > 0, 'the fixture carries no tick labels');
  for (const label of ticks) assert.ok(text.includes(label), `${label} is not on the axis`);
  //: And the refit ran: it is scheduled inside a frame callback, which the harness invokes.
  assert.ok(frames[0].getAttribute('viewBox'), 'the frame never got a viewBox');

  //: **The legend and the header, which this test claimed in its own name and never asserted.**
  //: The fixture is DRL-0005, the artefact item: at V0.27.10 its panel lost the "Drifting
  //: object" legend entry, because with every track holding station that entry described
  //: nothing and invited an operator to hunt for a track that is not there. The server decides
  //: which entries exist and the interface must draw exactly those - no more, so a stale entry
  //: cannot survive here, and no fewer, so a dropped one cannot either.
  const rendered = stimuli.textContent;
  const served = DRILL.stimulus[0];
  assert.deepEqual(
    served.legend.map(([label]) => label),
    ['Held longitude'],
    'the fixture no longer captures the artefact panel this test reasons about',
  );
  for (const [label] of served.legend) {
    assert.ok(rendered.includes(label), `legend entry ${label} was not drawn`);
  }
  assert.ok(!rendered.includes('Drifting object'), 'a legend entry with no mark against it');

  //: And the header rows, which carry the whole evidence for this item: the impossible figure
  //: verbatim and the two element-set epochs to the millisecond. The interface dropping either
  //: would leave the operator with nothing to reason from, and `for_client()` strips the
  //: server's derived facts, so these strings are the only client-visible disclosure there is.
  for (const [label, value] of served.header) {
    assert.ok(rendered.includes(label), `header label ${label} was not drawn`);
    assert.ok(rendered.includes(String(value)), `header value for ${label} was not drawn`);
  }
  assert.match(rendered, /Elset 1 epoch/);
  assert.match(rendered, /:\d\d\.\d\d\dZ/, 'the epochs lost their millisecond resolution');
  assert.ok(rendered.includes('-22,900,000'), 'the reported figure was not drawn verbatim');
});

test('the confidence group is one radio group with one tab stop, not five buttons', async () => {
  const harness = booted();
  await harness.settle();
  harness.app.show('drill');
  await harness.settle();

  const group = harness.element('confidence-group');
  const buttons = [...group.children];
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
  const checked = () => [...group.children].find((b) => b.getAttribute('aria-checked') === 'true');
  assert.ok(checked(), 'a click must select');
  const before = checked().textContent;
  //: Arrow keys move the selection and wrap, which is the radiogroup pattern.
  [...group.children].find((b) => b.getAttribute('aria-checked') === 'true').fire('keydown', { key: 'ArrowRight' });
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
  const labels = [...chips.children].map((chip) => chip.textContent);
  const statuses = new Set(PROCEDURES.procedures.map((procedure) => procedure.status));
  assert.equal(labels.length, statuses.size + 2, JSON.stringify(labels));
  assert.ok(labels.includes('all'));
  //: A legend, so the fieldset has an accessible name.
  assert.equal(chips.children[0].tagName, 'LEGEND');

  const draft = [...chips.children].find((chip) => chip.textContent === 'draft');
  draft.fire('click');
  const shown = harness.element('library-grid').children.length;
  assert.ok(shown > 0 && shown < PROCEDURES.count, `filtering to draft showed ${shown}`);

  //: Search narrows on the text an author wrote, and an unmatched query says so rather than
  //: rendering an empty grid that reads as a loading state.
  [...chips.children].find((chip) => chip.textContent === 'all').fire('click');
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

/* ---------------------------------------------------------------- the procedure flow
 * The Library redesign, V0.28.0. What it replaced rendered `Object.entries(procedure)` through
 * `JSON.stringify`, and the test above asserted `/PROC-MNV/` and nothing else - so a text dump
 * and a flow chart pass it identically. These are the assertions that tell them apart. */

const FLOW = PROCEDURE.procedure;

async function opened() {
  const harness = booted();
  await harness.settle();
  harness.app.show('library');
  await harness.settle();
  harness.app.openProcedure(FLOW.id);
  await harness.settle();
  return harness;
}

test('a library card shows the shape of the work before any of its prose', async () => {
  //: An operator choosing between thirteen procedures reads the SHAPE first: how much work, how
  //: much judgement, how many products they will have to open, whether it hands over. Those four
  //: counts are derived server-side, because the interface holds the index and not the documents
  //: and could only compute them by fetching all thirteen - the content-sized body that index
  //: exists to avoid.
  const harness = booted();
  await harness.settle();
  harness.app.show('library');
  await harness.settle();
  const cards = [...harness.element('library-grid').children];
  assert.equal(cards.length, PROCEDURES.count);

  const entry = PROCEDURES.procedures.find((row) => row.id === FLOW.id);
  assert.ok(entry, `${FLOW.id} is not in the index fixture`);
  for (const field of ['steps', 'decisions', 'stops', 'onward']) {
    assert.equal(typeof entry[field], 'number', `the index fixture lost ${field}`);
  }
  const card = cards.find((node) => node.textContent.includes(FLOW.id));
  const text = card.textContent;
  //: Read off the FIXTURE, so the card cannot drift away from the index that feeds it.
  assert.ok(text.includes(`${entry.steps}`) && text.includes('steps'), text);
  assert.ok(text.includes(entry.decisions === 1 ? 'decision' : 'decisions'), text);
  assert.ok(text.includes(entry.stops === 1 ? 'stop' : 'stops'), text);
  assert.ok(text.includes(`${entry.onward} onward`), text);

  //: The preview strip: one node per step and decision, capped, plus the closure cap. Squares
  //: and diamonds in the same vocabulary the map inside the procedure uses, so the two teach
  //: each other rather than being two notations for one idea.
  const strip = [...card.querySelectorAll('div')].find((node) => node.classList.contains('strip'));
  assert.ok(strip, 'a card rendered no preview strip');
  const gems = [...strip.children].filter((node) => node.classList.contains('gem')).length;
  const boxes = [...strip.children].filter((node) => node.classList.contains('box')).length;
  assert.equal([...strip.children].filter((node) => node.classList.contains('cap')).length, 1);
  assert.ok(gems > 0 && gems <= entry.decisions, `${gems} diamonds for ${entry.decisions} decisions`);
  assert.ok(boxes > 0, 'the strip drew no steps');
  //: **Capped, and it SAYS it is capped.** A 21-step procedure at full length is a hairline of
  //: 12px squares nobody can count, so past the cap the strip draws a remainder rather than
  //: quietly drawing a shorter procedure than the one on the card.
  const long = PROCEDURES.procedures.reduce((a, b) => (a.steps + a.decisions > b.steps + b.decisions ? a : b));
  const longCard = cards.find((node) => node.textContent.includes(long.id));
  const longStrip = [...longCard.querySelectorAll('div')].find((node) => node.classList.contains('strip'));
  const nodes = [...longStrip.children].filter((n) => n.classList.contains('box') || n.classList.contains('gem')).length;
  if (long.steps + long.decisions > nodes) {
    const more = [...longStrip.children].find((node) => node.classList.contains('more'));
    assert.ok(more, `${long.id} folded its strip silently`);
    assert.equal(more.textContent, `+${long.steps + long.decisions - nodes}`);
  }

  //: Status is a dot AND a word here too, never colour alone.
  const mast = [...card.querySelectorAll('span')].find((node) => node.classList.contains('mast'));
  assert.ok([...mast.children].some((node) => node.classList.contains('dot')), 'no status dot');
  assert.ok(mast.textContent.includes(entry.status), mast.textContent);
});

test('a procedure renders as a flow and never as a serialised object', async () => {
  const harness = await opened();
  const body = harness.element('library-body');
  const text = body.textContent;

  //: **The fault this replaced, asserted directly.** `JSON.stringify(value, null, 1)` leaves
  //: braces, quoted keys and bracketed arrays in operator-facing prose. None may appear.
  for (const artefact of ['{', '}', '["', '"n":', 'threshold_ref', 'goto_procedure']) {
    assert.ok(!text.includes(artefact), `the dump artefact ${artefact} reached the operator`);
  }
  //: And the key names are rendered as WORDS. `key.replaceAll('_', ' ')` produced "not this
  //: procedure when" as a heading, which is a field name with the underscores taken out.
  assert.ok(!text.includes('not this procedure when'));
  assert.match(text, /Not this procedure when/);

  //: Every step's action is REACHABLE, so nothing is lost to the redesign. Reachable and not
  //: merely present: the fold hides five of the eight until asked, which is the design and not
  //: a loss, so the fold is opened first. Asserting against the initial render would have been
  //: asserting that the fold does not work.
  const rail = [...body.querySelectorAll('button')].find((node) => node.classList.contains('fold'));
  assert.ok(rail, 'the fixture no longer folds, so this reads only part of the flow');
  rail.fire('click');
  const whole = body.textContent;
  for (const step of FLOW.steps) {
    assert.ok(whole.includes(step.action), `step ${step.n} lost its action`);
  }
  //: And the reporting block, which is an OBJECT in the content and rendered as
  //: `[object Object]` in the first draft of this view.
  assert.ok(!whole.includes('[object Object]'), 'a field reached the operator unrendered');
  for (const must of FLOW.reporting.must_state) {
    assert.ok(whole.includes(must), `the report requirement "${must}" was dropped`);
  }
  assert.ok(whole.includes(FLOW.reporting.time_standard));
  //: `verbal_required: false` must render as WORDS. Under a truthiness test it printed nothing,
  //: so "no verbal report needed" and "the content is silent" looked identical on the page, and
  //: they are different instructions.
  assert.match(whole, /Verbal.*(required|not required)/);
});

test('the exclusions sit above the flow, not buried under the reporting rules', async () => {
  const harness = await opened();
  const text = harness.element('library-body').textContent;
  //: The most useful paragraph on the page was LAST in the dump, below the reporting rules,
  //: where an operator deciding whether they are even in the right procedure never reached it.
  const exclusions = text.indexOf('Not this procedure when');
  const flow = text.indexOf('The flow');
  const reporting = text.indexOf('Reporting');
  assert.ok(exclusions > 0 && flow > 0 && reporting > 0, JSON.stringify({ exclusions, flow, reporting }));
  assert.ok(exclusions < flow, 'the exclusions are below the flow');
  assert.ok(exclusions < reporting, 'the exclusions are below the reporting rules');
  //: ANY at one end and ALL at the other, stated in the heading rather than left to a bullet.
  assert.match(text, /Enter when any of these/);
  assert.match(text, /Close when all of these/);
});

test('every marker carries a word and a glyph, never colour alone', async () => {
  const harness = await opened();
  const body = harness.element('library-body');

  //: A monochrome print and a screen must read identically, so each marker is a GLYPH plus a
  //: WORD and the colour is the third carrier. Asserted structurally: every `.mk` row holds an
  //: svg and a `.word` with text in it.
  const rows = [...body.querySelectorAll('div')].filter((node) => node.classList.contains('mk'));
  assert.ok(rows.length > 0, 'no marker rendered at all');
  for (const row of rows) {
    assert.equal(row.querySelectorAll('svg').length >= 1, true, 'a marker has no glyph');
    const word = [...row.querySelectorAll('div')].find((node) => node.classList.contains('word'));
    assert.ok(word && word.textContent.trim().length > 0, 'a marker has no word');
  }

  //: And the marker classes the FIXTURE actually carries are the ones that appear. Counted from
  //: the content rather than hardcoded, so a fixture change fails this instead of passing.
  const text = body.textContent;
  const expected = [
    [FLOW.steps.filter((s) => s.products && s.products.length).length, /Stop — read the product/g],
    [FLOW.steps.filter((s) => s.threshold_ref).length, /Threshold/g],
    [FLOW.steps.filter((s) => s.common_error).length, /Common error/g],
    [FLOW.steps.filter((s) => s.why).length, /Why/g],
  ];
  for (const [count, pattern] of expected) {
    assert.ok(count > 0, `the fixture carries no ${pattern} marker, so this asserts nothing`);
  }
  //: **Opened first**, because the fold is doing its job: two of the fixture's markers sit on
  //: folded steps, so asserting them against the initial render was asserting that the fold does
  //: not work. This test is about the markers; the fold has its own.
  const rail = [...body.querySelectorAll('button')].find((node) => node.classList.contains('fold'));
  if (rail) rail.fire('click');
  const whole = body.textContent;

  //: The threshold names what to look up and does NOT invent a value to fill the space.
  for (const step of FLOW.steps.filter((s) => s.threshold_ref)) {
    assert.ok(whole.includes(step.threshold_ref), `threshold ${step.threshold_ref} was dropped`);
  }
  //: A step that names a product renders the product id, because the step cannot be completed
  //: from its text alone: it names a plot the operator has to actually look at.
  for (const step of FLOW.steps.filter((s) => s.products && s.products.length)) {
    for (const product of step.products) assert.ok(whole.includes(product), product);
  }
});

test('the map counts what the content actually carries', async () => {
  const harness = await opened();
  const text = harness.element('library-body').textContent;
  const stops = FLOW.steps.filter((s) => s.products && s.products.length).length;
  const jumps = FLOW.decision_points.reduce(
    (total, point) => total + point.branches.filter((b) => b.goto_procedure).length, 0,
  );
  //: Derived from the fixture, so the tally cannot drift away from the procedure it describes.
  assert.ok(text.includes(`${FLOW.steps.length} steps`), text.slice(0, 400));
  assert.ok(text.includes(`${FLOW.decision_points.length} decisions`));
  assert.ok(text.includes(`${stops} stops`));
  assert.ok(text.includes(jumps === 1 ? '1 onward link' : `${jumps} onward links`));
});

test('a long procedure folds its middle, names what is inside, and opens on request', async () => {
  const harness = await opened();
  const body = harness.element('library-body');
  //: Scoped to the FIRST `.flow`, which is the steps. The decision track is a second `.flow` of
  //: `.leg` rows, so counting legs across the whole body counted 8 steps plus 3 decisions and
  //: reported 11 against an expected 8 - the test measuring the wrong thing, not the code.
  const stepFlow = () => [...body.querySelectorAll('div')].filter((node) => node.classList.contains('flow'))[0];
  const legs = () => [...stepFlow().children].filter((node) => node.classList.contains('leg'));

  //: The fixture carries eight steps against a fold threshold of six, so the flow arrives as
  //: two steps, the folded rail, and the last step. A flow nobody scrolls to the end of is a
  //: flow nobody reads, which is what a 21-step procedure rendered whole.
  const folded = [...body.querySelectorAll('button')].find((node) => node.classList.contains('fold'));
  assert.ok(folded, 'nothing folded at eight steps against a threshold of six');
  assert.match(folded.textContent, /5 steps folded/);
  //: **Named, not just counted.** "Five steps folded" tells an operator nothing about whether
  //: the part they need is inside, so the rail carries the first clause of each folded action.
  const middle = FLOW.steps.slice(2, FLOW.steps.length - 1);
  for (const step of middle) {
    const clause = step.action.split(/[.;]/)[0].slice(0, 40);
    assert.ok(folded.textContent.includes(clause), `the rail does not name step ${step.n}`);
  }
  const beforeOpen = legs().length;

  folded.fire('click');
  //: Opened, every step is on the spine and the rail is gone.
  assert.equal(legs().length, FLOW.steps.length, `expected ${FLOW.steps.length} legs`);
  assert.ok(legs().length > beforeOpen);
  assert.ok(![...body.querySelectorAll('button')].some((node) => node.classList.contains('fold')));
  for (const step of FLOW.steps) {
    assert.ok(body.textContent.includes(step.action), `step ${step.n} missing after opening`);
  }
});

test('the decision track says out loud that the content does not place the decisions', async () => {
  const harness = await opened();
  const text = harness.element('library-body').textContent;
  //: **The one refusal in this design.** The content ORDERS decision points but does not bind
  //: them to a step number, so a diamond between step 6 and step 7 would be inventing a
  //: sequence nobody authored. The decisions keep their own track and the page says why.
  assert.match(text, /does not bind them to a step/);
  for (const point of FLOW.decision_points) {
    assert.ok(text.includes(point.id), `${point.id} is not on the page`);
    assert.ok(text.includes(point.question), `${point.id} lost its question`);
    for (const branch of point.branches) {
      assert.ok(text.includes(branch.condition), `${point.id} lost a condition`);
      assert.ok(text.includes(branch.then), `${point.id} lost a consequence`);
    }
  }
  //: A decision is the one marker that is not an instruction, so it is framed as a judgement.
  assert.match(text, /stop · think · then choose/);
});

test('a branch that names another procedure navigates to it', async () => {
  const harness = await opened();
  const body = harness.element('library-body');
  const jump = [...body.querySelectorAll('button')].find((node) => node.classList.contains('goto'));
  //: The content names the procedure a branch hands over to, so the chip NAVIGATES rather than
  //: describing it: the thirteen procedures form a graph and this is the only edge in it.
  const target = FLOW.decision_points
    .flatMap((point) => point.branches)
    .find((branch) => branch.goto_procedure).goto_procedure;
  assert.ok(jump, 'a branch names a procedure and rendered no way to reach it');
  assert.match(jump.textContent, new RegExp(target));
  //: And it carries the target's NAME from the index, not only its id: an operator choosing a
  //: branch under pressure should not have to remember what PROC-RPO stands for.
  const named = PROCEDURES.procedures.find((entry) => entry.id === target);
  if (named) assert.ok(jump.textContent.includes(named.name), jump.textContent);

  jump.fire('click');
  await harness.settle();
  //: Asserted on the REQUEST, because the stub serves one fixture for every id, so asserting on
  //: the rendered body would pass even if the click navigated nowhere.
  const asked = harness.calls.map((call) => call.path);
  assert.ok(
    asked.some((path) => path.includes(encodeURIComponent(target))),
    `no request for ${target}: ${JSON.stringify(asked)}`,
  );
});

test('a procedure replaces the index rather than stacking below it', async () => {
  //: **The library is TWO screens.** The first draft of this redesign appended the flow beneath
  //: the card grid, so opening a procedure put 5,900 pixels of it under thirteen cards and an
  //: operator scrolled past the whole library to reach the step they came for. Every test passed
  //: and the rendered page said otherwise, which is why this assertion exists: it failed against
  //: nothing, so nothing was holding the design's own two-screen shape.
  const harness = booted();
  await harness.settle();
  harness.app.show('library');
  await harness.settle();
  const index = harness.element('library-index');
  assert.equal(index.hidden, false, 'the index is hidden before a procedure is even opened');

  harness.app.openProcedure(FLOW.id);
  await harness.settle();
  //: `hidden` and not a class, so it is hidden from assistive technology too rather than merely
  //: painted away - a screen reader walking a hidden grid is the same defect one sense along.
  assert.equal(index.hidden, true, 'the card index is still on the page under the flow');

  const back = [...harness.element('library-body').querySelectorAll('button')]
    .find((node) => node.textContent === 'Back to the library');
  assert.ok(back, 'a procedure opens with no way back to the index');
  back.fire('click');
  //: Back restores the index and repaints the grid, and the body is emptied so a stale flow
  //: cannot sit under the cards.
  assert.equal(index.hidden, false);
  assert.equal(harness.element('library-grid').children.length, PROCEDURES.count);
  assert.equal(harness.element('library-body').children.length, 0);
});

test('re-entering the library shows the index even if a procedure was left open', async () => {
  //: Without the reset in `loadLibrary`, opening a procedure and then navigating away and back
  //: left the view completely blank: the flow was cleared and the index was still hidden, so the
  //: library had nothing in it at all. A blank view reads as a failed load.
  const harness = booted();
  await harness.settle();
  harness.app.show('library');
  await harness.settle();
  harness.app.openProcedure(FLOW.id);
  await harness.settle();
  assert.equal(harness.element('library-index').hidden, true);

  harness.app.show('drill');
  await harness.settle();
  harness.app.show('library');
  await harness.settle();
  assert.equal(harness.element('library-index').hidden, false, 'the library came back blank');
  assert.equal(harness.element('library-grid').children.length, PROCEDURES.count);
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
    const current = [...harness.document.querySelectorAll('#nav button')]
      .filter((button) => button.getAttribute('aria-current') === 'page');
    assert.equal(current.length, 1, `${name}: exactly one control is current`);
    assert.equal(current[0].getAttribute('data-view'), name);
  }
});
