'use strict';
/*
 * The operator interface.
 *
 * Two rules this file holds, and both are checked by tests rather than trusted:
 *
 * 1. NOTHING is ever assigned as markup. Every value from the server reaches the document
 *    through textContent or through a namespaced SVG element created by name. The content is
 *    authored and the server is ours, but "the data is trusted" is how every one of these bugs
 *    starts, and the cost of the discipline is nil.
 * 2. Plots are drawn from the panel description the server sends, honouring its axes. An
 *    inverted axis is inverted because a magnitude axis runs brighter upward; a renderer that
 *    ignored the flag would teach the opposite of the signature.
 *
 * Colour: the recency ramp is the ONLY place red appears. A verdict never uses it. In the real
 * toolset red means "most recent data", and a red verdict here would teach an operator to read
 * one colour two unrelated ways.
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

/* Confidence steps and the probability each asserts. A proper scoring rule needs a number, and
 * these are the five the training layer scores against. */
const CONFIDENCE = [
  { step: 1, label: 'Guess', probability: 15 },
  { step: 2, label: 'Lean', probability: 35 },
  { step: 3, label: 'Fair', probability: 55 },
  { step: 4, label: 'Sure', probability: 75 },
  { step: 5, label: 'Certain', probability: 93 },
];

/* Role to CSS custom property. Roles come from the generator, never colours, so the palette
 * lives in one place and a renderer cannot pick a hex value. */
const ROLE_COLOURS = {
  'series-a': 'var(--sig)',
  'series-b': 'var(--you)',
  'track': 'var(--sig)',
  'state-change': 'var(--cue)',
  'minimum': 'var(--recent)',
  'reference': 'var(--ink4)',
  'object-held': 'var(--sig)',
  'object-drift': 'var(--you)',
};

const state = {
  drill: null,
  confidence: 0,
  servedAt: 0,
  busy: false,
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function svg(tag, attributes) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes || {})) {
    node.setAttribute(key, String(value));
  }
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

async function api(path, options) {
  const response = await fetch(path, Object.assign({ headers: { 'accept': 'application/json' } }, options));
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body && body.detail;
    const message = (detail && (detail.message || detail.error)) || 'The request failed.';
    throw new Error(message);
  }
  return body;
}

function banner(message) {
  const node = document.getElementById('banner');
  if (!message) { node.classList.add('hidden'); clear(node); return; }
  clear(node);
  node.appendChild(el('span', null, message));
  node.classList.remove('hidden');
}

/* ---------------------------------------------------------------- plot drawing */

const PLOT_WIDTH = 620;
const PLOT_HEIGHT = 260;
const PAD = { left: 58, right: 16, top: 14, bottom: 40 };
/* A timestamp needs more gutter than a number: 58px fits "0.003" and clipped "23 Jan 09:00Z" to
 * "Jan 09:00Z", the day sheared off the viewBox, which is worse than a bare number because it
 * looks like a complete label. This reserve is a FIRST GUESS only - it is computed at build time
 * from the nominal font size, and `sizePlotText` then resets that size after layout, so the
 * guarantee comes from the measured refit there rather than from this arithmetic.
 *
 * Derived from the font size rather than eyeballed: 0.62 em is the advance of every monospace
 * face in the stack (SF Mono, Menlo, Cascadia Mono, DejaVu Sans Mono are all 0.600 to 0.603, and
 * the margin covers the fallback). */
const TICK_ADVANCE_EM = 0.62;
const TICK_GUTTER = 14;
/* Refit passes for the measured gutter. Widening the viewBox changes the scale, which changes the
 * font size, which changes the width: three passes converge on every width measured. */
const TEXT_FIT_PASSES = 3;
const TEXT_FIT_TOLERANCE = 0.5;
const TEXT_FIT_PAD = 4;
/* Where the horizontal tick labels and the axis caption sit below the axis, in multiples of the
 * applied font size. At the nominal 13 units these land on 240 and 256, the original positions. */
const X_TICK_OFFSET_EM = 1.55;
const X_CAPTION_OFFSET_EM = 2.75;

/* Text inside a plot must not scale with the plot, and this is measured rather than assumed.
 * A plot in a wide column renders LARGER than its own coordinate system and one in a narrow
 * column renders smaller: the artboards had the second case and the true floor was 7.3 px, and
 * the first pass at this file had the first case and axis captions rendered at 23 px. So the
 * font size is set after layout from the actual ratio, floored so nothing carrying meaning
 * lands under this. */
const AXIS_FONT_PX = 13;

function extent(values) {
  let low = Infinity, high = -Infinity;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    if (value < low) low = value;
    if (value > high) high = value;
  }
  if (low === Infinity) return [0, 1];
  if (low === high) return [low - 1, high + 1];
  return [low, high];
}

function axisRange(axis, values) {
  const [low, high] = extent(values);
  const min = axis && axis.minimum !== null && axis.minimum !== undefined ? axis.minimum : low;
  const max = axis && axis.maximum !== null && axis.maximum !== undefined ? axis.maximum : high;
  return min === max ? [min - 1, max + 1] : [min, max];
}

function ramp(fraction) {
  /* Recency: most recent at one end, oldest at the other, and this is the one place red is used.
   * Three stops rather than a gradient function so the two halves are separately legible. */
  if (fraction <= 0.5) return 'var(--recent)';
  if (fraction <= 0.85) return 'var(--older)';
  return 'var(--oldest)';
}

function drawPanel(panel) {
  const wrap = el('div');
  if (panel.title) wrap.appendChild(el('p', 'panel-title', panel.title));

  const groups = (panel.marks || []).concat(panel.steps || []);
  const xs = [], ys = [];
  for (const group of groups) { xs.push(...group.x); ys.push(...group.y); }
  const [x0, x1] = axisRange(panel.x, xs);
  const [y0, y1] = axisRange(panel.y, ys);

  const frame = svg('svg', {
    viewBox: `0 0 ${PLOT_WIDTH} ${PLOT_HEIGHT}`,
    width: '100%',
    role: 'img',
    'aria-label': panel.title || 'plot',
    style: 'display:block',
  });

  const supplied = (panel.y && panel.y.ticks) || [];
  const widest = supplied.reduce((most, [, text]) => Math.max(most, String(text).length), 0);
  const padLeft = Math.max(PAD.left, widest * AXIS_FONT_PX * TICK_ADVANCE_EM + TICK_GUTTER);
  const plotW = PLOT_WIDTH - padLeft - PAD.right;
  const plotH = PLOT_HEIGHT - PAD.top - PAD.bottom;
  const sx = (value) => padLeft + ((value - x0) / (x1 - x0)) * plotW;
  /* The inverted flag, honoured. Not a preference: a magnitude axis runs brighter upward. */
  const sy = (value) => {
    const t = (value - y0) / (y1 - y0);
    return panel.y && panel.y.inverted
      ? PAD.top + t * plotH
      : PAD.top + plotH - t * plotH;
  };

  /* An axis may supply its own ticks, and a TIMELINE must: on a waterfall the vertical axis is
   * time, and "0.003" to "4.99" are the internals of the plot rather than anything an operator
   * can correlate against a pass schedule or a provider post. Where ticks are supplied they are
   * positioned by VALUE through sy(), so they land correctly whichever way the axis runs. */
  const suppliedTicks = supplied;
  const yTicks = suppliedTicks.length
    ? suppliedTicks.map(([value, text]) => ({ y: sy(value), text }))
    : Array.from({ length: 5 }, (unused, i) => {
        const y = PAD.top + (i / 4) * plotH;
        const value = panel.y && panel.y.inverted
          ? y0 + (i / 4) * (y1 - y0)
          : y1 - (i / 4) * (y1 - y0);
        return { y, text: formatTick(value) };
      });
  for (const tick of yTicks) {
    frame.appendChild(svg('line', { x1: padLeft, y1: tick.y, x2: PLOT_WIDTH - PAD.right, y2: tick.y, stroke: 'var(--grid)', 'stroke-width': 1 }));
    const label = svg('text', {
      x: padLeft - 8, y: tick.y + 4, fill: 'var(--ink3)',
      'font-size': AXIS_FONT_PX, 'text-anchor': 'end', 'font-family': 'var(--data)',
    });
    label.textContent = tick.text;
    frame.appendChild(label);
  }
  for (let i = 0; i <= 4; i += 1) {
    const x = padLeft + (i / 4) * plotW;
    const label = svg('text', {
      x, y: PLOT_HEIGHT - PAD.bottom + 20, 'data-role': 'x-tick', fill: 'var(--ink3)',
      'font-size': AXIS_FONT_PX, 'text-anchor': 'middle', 'font-family': 'var(--data)',
    });
    label.textContent = formatTick(x0 + (i / 4) * (x1 - x0));
    frame.appendChild(label);
  }

  for (const group of groups) {
    drawGroup(frame, group, sx, sy);
  }

  const axisLabel = svg('text', {
    x: PLOT_WIDTH / 2, y: PLOT_HEIGHT - 4, 'data-role': 'x-caption', fill: 'var(--ink4)',
    'font-size': AXIS_FONT_PX, 'text-anchor': 'middle', 'font-family': 'var(--data)',
  });
  axisLabel.textContent = axisCaption(panel.x);
  frame.appendChild(axisLabel);

  wrap.appendChild(frame);
  /* Deferred to the next frame, when the SVG has a box to measure. */
  requestAnimationFrame(() => sizePlotText(frame));
  /* The axis says WHY it is inverted. This read "inverted, brighter upward" for every inverted
   * axis, which is true of a magnitude axis and nonsense on a timeline - and it was rendered on
   * every waterfall the product has ever drawn. */
  const inversionNote = panel.y && panel.y.inverted
    ? ` · inverted: ${(panel.y.inversion_note || 'see the panel note')}`
    : '';
  const yCaption = el('p', 'panel-note', `Vertical: ${axisCaption(panel.y)}${inversionNote}`);
  wrap.appendChild(yCaption);
  for (const note of panel.notes || []) wrap.appendChild(el('p', 'panel-note', note));
  return wrap;
}

function sizePlotText(frame) {
  /* Two jobs, and the second exists because the first defeated the axis gutter.
   *
   * Text is sized in viewBox units so it RENDERS at a constant CSS size whatever the plot's
   * width: as the plot narrows the scale falls and the size in viewBox units grows. The left
   * gutter was reserved once at build time in viewBox units and did not grow with it, so below
   * roughly 680 CSS px the timestamp labels sheared off the left edge of the viewBox - measured
   * in a browser at 620, 480 and 390 px viewports, leftmost label x of -14, -55 and -100. That
   * is the owner-reported clipping fault reproduced by the fix for the owner-reported clipping
   * fault, and the comment beside the gutter constant claimed a label of any length would fit.
   *
   * So after sizing, the actual overflow is MEASURED with getBBox and the viewBox is widened to
   * the left to contain it. Geometry is untouched: the canvas simply starts further left.
   * Widening changes the scale, which changes the size, so it iterates - bounded, because a
   * bounded loop that gives up slightly small beats an unbounded one that hangs the frame. */
  for (let pass = 0; pass < TEXT_FIT_PASSES; pass += 1) {
    const box = frame.getBoundingClientRect();
    const viewBox = frame.viewBox && frame.viewBox.baseVal;
    if (!box.width || !viewBox || !viewBox.width) return;
    const scale = box.width / viewBox.width;
    if (!Number.isFinite(scale) || scale <= 0) return;
    const size = Math.max(AXIS_FONT_PX / scale, AXIS_FONT_PX / 3);
    for (const text of frame.querySelectorAll('text')) {
      text.setAttribute('font-size', size.toFixed(2));
    }

    /* The horizontal labels sit BELOW the axis at offsets that must scale with the text, or they
     * collide with the caption: at a 31-unit font the fixed 20 and 36 unit offsets overlap, which
     * a screenshot at 430px showed plainly while every number was inside the box. Positioned from
     * the size actually applied, and chosen to land on the original 240 and 256 at 13 units so the
     * nominal design is unchanged. */
    const axisY = PLOT_HEIGHT - PAD.bottom;
    for (const tick of frame.querySelectorAll('[data-role="x-tick"]')) {
      tick.setAttribute('y', (axisY + size * X_TICK_OFFSET_EM).toFixed(1));
    }
    for (const caption of frame.querySelectorAll('[data-role="x-caption"]')) {
      caption.setAttribute('y', (axisY + size * X_CAPTION_OFFSET_EM).toFixed(1));
    }

    /* Expand on every side the text actually needs, not just the left: the same fixed-gutter
     * fault applies to each edge, and only the left one had been found. */
    let minX = viewBox.x;
    let minY = viewBox.y;
    let maxX = viewBox.x + viewBox.width;
    let maxY = viewBox.y + viewBox.height;
    for (const text of frame.querySelectorAll('text')) {
      const bounds = text.getBBox();
      if (!bounds.width && !bounds.height) continue;
      minX = Math.min(minX, bounds.x);
      minY = Math.min(minY, bounds.y);
      maxX = Math.max(maxX, bounds.x + bounds.width);
      maxY = Math.max(maxY, bounds.y + bounds.height);
    }
    const grew = minX < viewBox.x - TEXT_FIT_TOLERANCE
      || minY < viewBox.y - TEXT_FIT_TOLERANCE
      || maxX > viewBox.x + viewBox.width + TEXT_FIT_TOLERANCE
      || maxY > viewBox.y + viewBox.height + TEXT_FIT_TOLERANCE;
    if (!grew) return;
    const x0 = Math.min(minX, viewBox.x) - TEXT_FIT_PAD;
    const y0 = Math.min(minY, viewBox.y) - TEXT_FIT_PAD;
    const x1 = Math.max(maxX, viewBox.x + viewBox.width) + TEXT_FIT_PAD;
    const y1 = Math.max(maxY, viewBox.y + viewBox.height) + TEXT_FIT_PAD;
    frame.setAttribute(
      'viewBox',
      `${x0.toFixed(1)} ${y0.toFixed(1)} ${(x1 - x0).toFixed(1)} ${(y1 - y0).toFixed(1)}`,
    );
  }
}

function axisCaption(axis) {
  if (!axis) return '';
  return axis.unit ? `${axis.label} (${axis.unit})` : axis.label;
}

function formatTick(value) {
  const magnitude = Math.abs(value);
  if (magnitude >= 10000) return `${(value / 1000).toFixed(1)}k`;
  if (magnitude >= 100) return value.toFixed(0);
  if (magnitude >= 1) return value.toFixed(2);
  return value.toFixed(3);
}

function drawGroup(frame, group, sx, sy) {
  const colour = ROLE_COLOURS[group.role] || 'var(--sig)';
  if (group.glyph === 'line' || group.glyph === 'step') {
    drawPath(frame, group, sx, sy, colour);
    return;
  }
  /* A plus-cross scatter, not a polyline. A connecting line asserts continuity between
   * observations that are not continuous, and it hides the pass structure. */
  const size = group.glyph === 'dot' ? 3 : 2.6;
  for (let i = 0; i < group.x.length; i += 1) {
    const x = sx(group.x[i]);
    const y = sy(group.y[i]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const stroke = group.ramp && group.ramp.length === group.x.length ? ramp(group.ramp[i]) : colour;
    if (group.glyph === 'dot' || group.glyph === 'square') {
      frame.appendChild(svg(group.glyph === 'dot' ? 'circle' : 'rect',
        group.glyph === 'dot'
          ? { cx: x, cy: y, r: size, fill: stroke }
          : { x: x - size, y: y - size, width: size * 2, height: size * 2, fill: 'none', stroke, 'stroke-width': 1.3 }));
      continue;
    }
    if (group.glyph === 'bar') {
      frame.appendChild(svg('rect', { x, y: y - 4, width: 3, height: 8, fill: stroke }));
      continue;
    }
    frame.appendChild(svg('path', {
      d: `M${x - size} ${y}H${x + size}M${x} ${y - size}V${y + size}`,
      stroke, 'stroke-width': 1.1, 'stroke-linecap': 'round',
    }));
  }
}

function drawPath(frame, group, sx, sy, colour) {
  const parts = [];
  for (let i = 0; i < group.x.length; i += 1) {
    const x = sx(group.x[i]);
    const y = sy(group.y[i]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    if (parts.length === 0) { parts.push(`M${x.toFixed(2)} ${y.toFixed(2)}`); continue; }
    /* A staircase for a step series. Discrete state changes are steps in the real products, and
     * a curve through them asserts a transition that did not happen. */
    parts.push(group.glyph === 'step' ? `H${x.toFixed(2)}V${y.toFixed(2)}` : `L${x.toFixed(2)} ${y.toFixed(2)}`);
  }
  if (!parts.length) return;
  frame.appendChild(svg('path', {
    d: parts.join(''), fill: 'none', stroke: colour, 'stroke-width': 1.6, 'stroke-linejoin': 'round',
  }));
}

function drawTable(stimulus) {
  const wrap = el('div', 'tablewrap');
  const table = el('table');
  const head = el('thead');
  const headRow = el('tr');
  for (const column of stimulus.columns) {
    const th = el('th', column.align === 'right' ? 'r' : null, column.label);
    headRow.appendChild(th);
  }
  head.appendChild(headRow);
  table.appendChild(head);
  const body = el('tbody');
  for (const row of stimulus.rows) {
    const tr = el('tr');
    for (const column of stimulus.columns) {
      const raw = row[column.key];
      const value = raw === null || raw === undefined ? '—'
        : (typeof raw === 'boolean' ? (raw ? 'yes' : 'no') : String(raw));
      const classes = [column.align === 'right' ? 'r' : '', column.emphasis ? 'em' : ''].filter(Boolean).join(' ');
      tr.appendChild(el('td', classes || null, value));
    }
    body.appendChild(tr);
  }
  table.appendChild(body);
  wrap.appendChild(table);
  return wrap;
}

function ramped(stimulus) {
  /* Whether any group on this surface encodes recency in colour. If one does, a role swatch
   * beside it is a lie: the points are drawn in the ramp, not in the role colour. */
  for (const panel of stimulus.panels || []) {
    for (const group of (panel.marks || []).concat(panel.steps || [])) {
      if (group.ramp && group.ramp.length === group.x.length && group.x.length) return true;
    }
  }
  return false;
}

function buildLegend(stimulus) {
  const legend = el('div', 'legend');
  const usesRamp = ramped(stimulus);
  if (usesRamp) {
    for (const [label, colour] of [['most recent', 'var(--recent)'], ['older', 'var(--older)'], ['oldest', 'var(--oldest)']]) {
      const item = el('span');
      const swatch = el('i');
      swatch.style.background = colour;
      item.appendChild(swatch);
      item.appendChild(el('span', null, label));
      legend.appendChild(item);
    }
  }
  for (const [label, role] of stimulus.legend) {
    const item = el('span');
    if (!usesRamp) {
      const swatch = el('i');
      swatch.style.background = ROLE_COLOURS[role] || 'var(--sig)';
      item.appendChild(swatch);
    }
    item.appendChild(el('span', null, usesRamp ? `· ${label}` : label));
    legend.appendChild(item);
  }
  return legend;
}

function drawStimulus(stimulus) {
  const scope = el('div', 'scope');
  const head = el('div', 'scope-head');
  const title = el('span');
  title.appendChild(el('b', null, stimulus.title));
  head.appendChild(title);
  for (const [key, value] of stimulus.header || []) {
    head.appendChild(el('span', null, `${key}: ${value}`));
  }
  head.appendChild(el('span', null, stimulus.product_id));
  scope.appendChild(head);

  if (stimulus.panels && stimulus.panels.length) {
    const panels = el('div', stimulus.panels.length > 1 ? 'panels multi' : 'panels');
    for (const panel of stimulus.panels) panels.appendChild(drawPanel(panel));
    scope.appendChild(panels);
  }
  if (stimulus.columns && stimulus.columns.length) {
    scope.appendChild(drawTable(stimulus));
  }
  if (stimulus.legend && stimulus.legend.length) {
    scope.appendChild(buildLegend(stimulus));
  }
  if (stimulus.reads_as) {
    scope.appendChild(el('p', 'foot', stimulus.reads_as));
  }
  if (stimulus.footer) scope.appendChild(el('div', 'foot', stimulus.footer));
  return scope;
}

/* ---------------------------------------------------------------- the drill loop */

function renderConfidence() {
  const group = document.getElementById('confidence-group');
  clear(group);
  for (const option of CONFIDENCE) {
    const button = el('button', null, null);
    button.type = 'button';
    button.setAttribute('aria-pressed', String(state.confidence === option.step));
    button.appendChild(el('span', null, option.label));
    button.appendChild(document.createTextNode(' '));
    button.appendChild(el('span', null, `${option.probability}`));
    button.addEventListener('click', () => {
      state.confidence = option.step;
      renderConfidence();
    });
    group.appendChild(button);
  }
}

const RESPONSE_LABELS = {
  free_classification: 'Name the event',
  ordered_actions: 'The actions, in order',
  yes_no_with_reason: 'Yes or no, and why',
  numeric_estimate: 'Your number',
  threshold_call: 'Your call against the threshold',
  product_request: 'Which product do you ask for',
  anatomy_question: 'Your answer',
  no_action_correct: 'What do you do',
  cross_product_reconciliation: 'Reconcile the products',
  reasoned_argument: 'Your argument',
};

async function loadDrill() {
  banner('');
  document.getElementById('reveal').classList.add('hidden');
  document.getElementById('answer-form').classList.add('hidden');
  document.getElementById('drill-prompt').textContent = 'Loading a drill…';
  clear(document.getElementById('stimuli'));
  try {
    const drill = await api('/api/v1/drill/next');
    state.drill = drill;
    state.confidence = 0;
    state.servedAt = Date.now();
    document.getElementById('drill-kicker').textContent = `${drill.item_id} · ${drill.cue_id || 'no cue'}`;
    document.getElementById('drill-prompt').textContent = drill.prompt;
    document.getElementById('drill-meta').textContent =
      `Rated ${drill.elo}. Target ${drill.time_target_s} seconds. Content ${drill.content_hash.slice(0, 12)}.`;
    const host = document.getElementById('stimuli');
    for (const stimulus of drill.stimulus) host.appendChild(drawStimulus(stimulus));
    document.getElementById('response-label').textContent =
      RESPONSE_LABELS[drill.response_format] || 'Your answer';
    document.getElementById('response').value = '';
    renderConfidence();
    document.getElementById('answer-form').classList.remove('hidden');
    document.getElementById('response').focus();
  } catch (error) {
    banner(error.message);
    document.getElementById('drill-prompt').textContent = 'No drill available.';
  }
}

const VERDICT_GLYPH = { accept: '▲', partial: '◆', reject: '▼', none: '○', unscorable: '○' };

function renderReveal(result) {
  const host = document.getElementById('reveal');
  clear(host);

  const verdict = el('div', `verdict ${result.matched}`);
  const heading = el('h3');
  heading.appendChild(el('span', 'glyph', VERDICT_GLYPH[result.matched] || '○'));
  heading.appendChild(document.createTextNode(
    result.matched === 'accept' ? 'Correct.'
      : result.matched === 'partial' ? 'Right, and imprecise.'
      : result.matched === 'reject' ? 'That is a named wrong answer.'
      : result.matched === 'unscorable' ? 'This item could not be scored.'
      : 'Not a recognised answer.'));
  verdict.appendChild(heading);
  if (result.why_wrong) verdict.appendChild(el('p', null, result.why_wrong));
  if (result.note) verdict.appendChild(el('p', null, result.note));
  if (result.explain) verdict.appendChild(el('p', null, result.explain));
  host.appendChild(verdict);

  host.appendChild(el('h2', null, 'Where the score went'));
  const table = el('table');
  const head = el('thead');
  const headRow = el('tr');
  for (const label of ['Rule', 'Award', 'Why']) {
    headRow.appendChild(el('th', label === 'Award' ? 'r' : null, label));
  }
  head.appendChild(headRow);
  table.appendChild(head);
  const body = el('tbody');
  for (const component of result.score_components) {
    const tr = el('tr');
    tr.appendChild(el('td', null, component.rule_id));
    tr.appendChild(el('td', 'r em', component.award.toFixed(2)));
    tr.appendChild(el('td', null, component.explain));
    body.appendChild(tr);
  }
  const totalRow = el('tr');
  totalRow.appendChild(el('td', null, 'Total'));
  totalRow.appendChild(el('td', 'r em', result.total.toFixed(2)));
  totalRow.appendChild(el('td', null, `Rating ${result.rating_before} to ${result.rating_after}. Due again in ${result.next_due_in_days} day${result.next_due_in_days === 1 ? '' : 's'}.`));
  body.appendChild(totalRow);
  table.appendChild(body);
  const wrap = el('div', 'tablewrap');
  wrap.appendChild(table);
  host.appendChild(wrap);

  host.appendChild(el('p', 'note', `Calibration: ${result.calibration}. Brier ${result.brier.toFixed(3)}.`));
  if (result.unimplemented_rules && result.unimplemented_rules.length) {
    host.appendChild(el('p', 'panel-note',
      `${result.unimplemented_rules.length} rule(s) in this rubric have no predicate yet and were not evaluated: ${result.unimplemented_rules.join(', ')}.`));
  }

  const next = el('button', 'act', 'Next drill');
  next.type = 'button';
  next.addEventListener('click', loadDrill);
  host.appendChild(next);
  host.classList.remove('hidden');
  next.focus();
}

async function submitAnswer(event) {
  event.preventDefault();
  if (state.busy || !state.drill) return;
  const response = document.getElementById('response').value.trim();
  if (!response) { banner('Type your call first.'); return; }
  if (state.drill.confidence_required && !state.confidence) {
    banner('Say how sure you are. Calibration is scored.');
    return;
  }
  state.busy = true;
  document.getElementById('submit').disabled = true;
  try {
    const result = await api('/api/v1/drill/answer', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'accept': 'application/json' },
      body: JSON.stringify({
        drill_run_id: state.drill.drill_run_id,
        response,
        confidence: state.confidence || 3,
        elapsed_ms: Math.max(0, Date.now() - state.servedAt),
      }),
    });
    document.getElementById('answer-form').classList.add('hidden');
    renderReveal(result);
    banner('');
  } catch (error) {
    banner(error.message);
  } finally {
    state.busy = false;
    document.getElementById('submit').disabled = false;
  }
}

/* ---------------------------------------------------------------- other surfaces */

async function loadProgress() {
  const host = document.getElementById('progress-body');
  clear(host);
  try {
    const me = await api('/api/v1/me');
    document.getElementById('progress-identity').textContent = me.identity;
    const table = el('table');
    const head = el('thead');
    const headRow = el('tr');
    for (const label of ['Competency', 'Attempts', 'Estimate', 'Interval']) {
      headRow.appendChild(el('th', label === 'Competency' ? null : 'r', label));
    }
    head.appendChild(headRow);
    table.appendChild(head);
    const body = el('tbody');
    for (const competency of me.competencies) {
      const tr = el('tr');
      tr.appendChild(el('td', null, competency.name || competency.competency_id));
      tr.appendChild(el('td', 'r', String(competency.attempts)));
      /* "Not measured" and "measured at zero" are different statements and are rendered
       * differently. A bare estimate never appears: the interval is part of the value. */
      tr.appendChild(el('td', 'r', competency.measured ? `${Math.round(competency.estimate * 100)}%` : 'not measured'));
      tr.appendChild(el('td', 'r', competency.interval
        ? `${Math.round(competency.interval[0] * 100)} to ${Math.round(competency.interval[1] * 100)}`
        : '—'));
      body.appendChild(tr);
    }
    table.appendChild(body);
    const wrap = el('div', 'tablewrap');
    wrap.appendChild(table);
    host.appendChild(wrap);
    host.appendChild(el('p', 'note',
      `Drill rating ${me.drill_rating}. ${me.runs_total} answers recorded. ${me.due_now} items due now.`));
  } catch (error) {
    banner(error.message);
  }
}

async function loadLibrary() {
  const host = document.getElementById('library-body');
  clear(host);
  try {
    const manifest = await api('/api/v1/content/manifest');
    const scope = el('div', 'scope');
    const head = el('div', 'scope-head');
    head.appendChild(el('span', null, 'Loaded content'));
    head.appendChild(el('span', null, `hash ${manifest.content_hash.slice(0, 16)}`));
    scope.appendChild(head);
    const list = el('div', 'legend');
    for (const [kind, count] of Object.entries(manifest.counts)) {
      list.appendChild(el('span', null, `${kind}: ${count}`));
    }
    scope.appendChild(list);
    scope.appendChild(el('div', 'foot', `Thresholds from ${manifest.thresholds_source}.`));
    host.appendChild(scope);
    if (!manifest.scored_scenarios_ready) {
      host.appendChild(el('p', 'banner', manifest.why_not_ready));
    }
  } catch (error) {
    banner(error.message);
  }
}

/* ---------------------------------------------------------------- shell */

const VIEWS = { drill: loadDrill, progress: loadProgress, library: loadLibrary };

function show(name) {
  for (const view of Object.keys(VIEWS)) {
    document.getElementById(`view-${view}`).classList.toggle('hidden', view !== name);
  }
  for (const button of document.querySelectorAll('#nav button')) {
    if (button.dataset.view === name) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  }
  const loader = VIEWS[name];
  if (loader) loader();
}

function boot() {
  document.getElementById('answer-form').addEventListener('submit', submitAnswer);
  for (const button of document.querySelectorAll('#nav button')) {
    button.addEventListener('click', () => show(button.dataset.view));
  }
  api('/api/v1/content/manifest').then((manifest) => {
    document.getElementById('rail-status').textContent =
      manifest.ok ? `${manifest.counts.drills} drills · ${manifest.content_hash.slice(0, 8)}` : 'content fault';
    if (!manifest.ok) banner(manifest.errors.join(' '));
  }).catch(() => {
    document.getElementById('rail-status').textContent = 'offline';
  });
  show('drill');
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
