/* The interface's decision logic, driven directly.
 *
 * Every case here is a fault this project has actually shipped or nearly shipped, or a control
 * `docs/SECURITY.md` names. The Python suite asserts on the served BYTES - the contrast floor,
 * the absence of invented figures, the verdict-colour reservation - which is the right level for
 * "what reaches the operator" and cannot reach a function's branches. This is the other half.
 */

import assert from 'node:assert/strict';
import test from 'node:test';
import { load, plain } from './harness.mjs';

test('a table cell reads absence, booleans and values as three different things', () => {
  const { app } = load();
  //: A conditional inside a conditional stood here until V0.27.6, and the em dash for absence
  //: is the arm that matters: a blank cell reads as a value the operator failed to notice.
  assert.equal(app.cellText(null), '—');
  assert.equal(app.cellText(undefined), '—');
  assert.equal(app.cellText(true), 'yes');
  assert.equal(app.cellText(false), 'no');
  assert.equal(app.cellText(0), '0', 'a legitimate zero must not read as absence');
  assert.equal(app.cellText(''), '', 'an empty string is a value the author wrote');
  assert.equal(app.cellText(1.5), '1.5');
});

test('an arrow key moves the confidence selection and every other key does not', () => {
  const { app } = load();
  for (const key of ['ArrowRight', 'ArrowDown']) assert.equal(app.arrowStep(key), 1);
  for (const key of ['ArrowLeft', 'ArrowUp']) assert.equal(app.arrowStep(key), -1);
  //: Zero is the caller's "not mine" and it returns without preventing the default, so a Tab or
  //: an Enter must land here. A truthy answer for Tab would trap focus in the radiogroup.
  for (const key of ['Tab', 'Enter', ' ', 'a', 'Escape']) assert.equal(app.arrowStep(key), 0);
});

test('the competency bands cover the whole range and carry a word, not only a colour', () => {
  const { app, value } = load();
  const bands = value('BANDS');
  assert.equal(bands.at(-1).floor, 0, 'the lowest band must catch every remaining estimate');
  //: The flight plan forbids status by colour alone, so every band has a word.
  for (const band of bands) assert.ok(band.word && band.cls, JSON.stringify(band));

  //: Asserted at the BOUNDARIES, because an off-by-one in a `>=` chain is invisible in the middle.
  assert.equal(app.band(0.70).word, 'strong');
  assert.equal(app.band(0.6999).word, 'fair');
  assert.equal(app.band(0.50).word, 'fair');
  assert.equal(app.band(0.4999).word, 'shaky');
  assert.equal(app.band(0.36).word, 'shaky');
  assert.equal(app.band(0.3599).word, 'weak');
  assert.equal(app.band(0).word, 'weak');
});

test('the two band palettes differ at exactly one band, and that is deliberate', () => {
  const { app, value } = load();
  const classes = value('BAND_CLASS_TONE');
  const variables = value('BAND_VARIABLE');
  //: Found by collapsing two four-deep ternary chains in V0.27.6: the CSS class for the middle
  //: band is `shaky` and the CSS custom property is `--warn`. Both are correct against their own
  //: stylesheet, and the difference is exactly one key. Asserted so a future tidy-up that makes
  //: them "consistent" breaks here rather than silently painting an unstyled bar.
  const differing = Object.keys(classes).filter((key) => classes[key] !== variables[key]);
  assert.deepEqual(plain(differing), ['shaky']);
  assert.equal(classes.shaky, 'shaky');
  assert.equal(variables.shaky, 'warn');

  //: Every band a suffix can be must be in both maps, or a bar paints with `|| 'bad'` and reads
  //: as the operator's worst axis when it is their best.
  for (const band of value('BANDS')) {
    const suffix = band.cls.replace('s-', '');
    assert.ok(suffix in classes, `${suffix} missing from BAND_CLASS_TONE`);
    assert.ok(suffix in variables, `${suffix} missing from BAND_VARIABLE`);
  }
  assert.equal(app.bandSuffix(0.9), 'strong');
});

test('the weakest axis is chosen over MEASURED axes only', () => {
  const { app } = load();
  //: A register-row control. An axis with no attempts has no estimate to be worst, and reporting
  //: one as the operator's weakness is a figure the data cannot support - the same class as the
  //: mockup's invented streak. The unmeasured entry here carries the LOWEST number on purpose.
  const chosen = app.weakest([
    { name: 'Never attempted', measured: false, estimate: 0.0 },
    { name: 'Recall', measured: true, estimate: 0.62 },
    { name: 'Calibration', measured: true, estimate: 0.41 },
  ]);
  assert.equal(chosen.name, 'Calibration');

  assert.equal(app.weakest([]), null);
  assert.equal(app.weakest([{ name: 'x', measured: false, estimate: 0.1 }]), null);
  //: `measured` true with a non-numeric estimate is a malformed row, not a weakness.
  assert.equal(app.weakest([{ name: 'x', measured: true, estimate: null }]), null);
});

test('an axis honours an authored zero and widens a flat range', () => {
  const { app } = load();
  //: `??` replaced a three-part null-and-undefined test in V0.27.6, and the case the long form
  //: existed to protect is a legitimate 0: `axis.minimum = 0` must pin the axis at zero rather
  //: than falling through to the data's own low.
  assert.deepEqual(plain(app.axisRange({ minimum: 0, maximum: 10 }, [4, 6])), [0, 10]);
  assert.deepEqual(plain(app.axisRange({ minimum: null, maximum: null }, [4, 6])), [4, 6]);
  assert.deepEqual(plain(app.axisRange(undefined, [4, 6])), [4, 6]);
  //: A flat series would divide by zero in the scale, so it is widened rather than drawn.
  assert.deepEqual(plain(app.axisRange(undefined, [5, 5])), [4, 6]);
  assert.deepEqual(plain(app.axisRange({ minimum: 3, maximum: 3 }, [1, 9])), [2, 4]);
  //: A non-finite sample is dropped, not propagated into the range.
  assert.deepEqual(plain(app.axisRange(undefined, [1, NaN, 9, Infinity])), [1, 9]);
  assert.deepEqual(plain(app.axisRange(undefined, [])), [0, 1]);
});

test('the recency ramp puts the newest observation at the red end', () => {
  const { app } = load();
  //: This was BACKWARDS once, on a product where red-for-recency is the first thing an analyst
  //: reads: the window start - the oldest point on the panel - was drawn in the newest colour.
  assert.equal(app.ramp(0), 'var(--recent)');
  assert.equal(app.ramp(0.5), 'var(--recent)');
  assert.equal(app.ramp(0.6), 'var(--older)');
  assert.equal(app.ramp(0.85), 'var(--older)');
  assert.equal(app.ramp(1), 'var(--oldest)');
});

test('the plot text refit reports "cannot measure" rather than guessing a size', () => {
  const { app } = load();
  const frame = { getBoundingClientRect: () => ({ width: 0 }) };
  //: Zero means unmeasurable and the caller returns. A real size can never be zero, because the
  //: floor is a third of the nominal, so one return value carries both answers unambiguously.
  assert.equal(app.fittedTextSize(frame, { width: 620 }), 0, 'an unlaid-out frame has no size');
  assert.equal(app.fittedTextSize({ getBoundingClientRect: () => ({ width: 620 }) }, null), 0);

  const measurable = { getBoundingClientRect: () => ({ width: 310 }) };
  const size = app.fittedTextSize(measurable, { width: 620 });
  //: Half the CSS width means twice the viewBox size, which is the whole point of sizing in
  //: viewBox units: the label renders at a constant CSS size as the plot narrows.
  assert.ok(size > 0, 'a measurable frame must yield a size');
  assert.equal(size, app.fittedTextSize({ getBoundingClientRect: () => ({ width: 310 }) }, { width: 620 }));
  //: And the floor holds when the scale collapses, rather than the size going to zero.
  const tiny = app.fittedTextSize({ getBoundingClientRect: () => ({ width: 1e9 }) }, { width: 620 });
  assert.ok(tiny > 0, 'the size floor must keep the label visible at any scale');
});

test('overflow is detected on each side of the box independently', () => {
  const { app, value } = load();
  const tolerance = value('TEXT_FIT_TOLERANCE');
  const box = { x: 0, y: 0, width: 100, height: 50 };
  const inside = { minX: 0, minY: 0, maxX: 100, maxY: 50 };
  assert.equal(app.overflows(box, inside), false);

  //: Every side, separately. Only the LEFT one had been found when this was written inline, and
  //: a label sheared off the right edge reads as a complete label rather than a clipped one.
  const push = tolerance + 1;
  assert.equal(app.overflows(box, { ...inside, minX: -push }), true, 'left');
  assert.equal(app.overflows(box, { ...inside, minY: -push }), true, 'top');
  assert.equal(app.overflows(box, { ...inside, maxX: 100 + push }), true, 'right');
  assert.equal(app.overflows(box, { ...inside, maxY: 50 + push }), true, 'bottom');

  //: Inside the tolerance is not an overflow, or the refit loop never settles.
  const nudge = tolerance / 2;
  assert.equal(app.overflows(box, { ...inside, minX: -nudge, maxY: 50 + nudge }), false);
});
