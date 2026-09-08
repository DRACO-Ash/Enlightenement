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
  /* The game layer: streak chip, rank slot, debrief stat cards. ON by the owner's decision of
   * 08 September, as prototyped, and a flag rather than a hardcoded truth so it can be turned
   * off without unpicking three screens. The flight plan's audience section argues the other
   * way - operators "motivated by competence and mission readiness, not by trivia or streaks" -
   * so the flag is where that disagreement lives until one document gives. */
  showGameLayer: true,
  library: { procedures: [], query: '', status: 'all' },
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

/* Every live plot refit, so a redraw can release the ones whose frame it is about to discard.
 * A ResizeObserver is registered on its target's Document, not on the local variable that
 * created it, so "the observer and the frame become unreachable together" does not follow from
 * this code - it depends on whether the engine makes that edge weak, which is an implementation
 * detail rather than a guarantee. A 50-drill session builds 50 observers over detached subtrees
 * on that reading, and disconnecting them is shorter than the argument for not needing to. */
const plotRefits = [];

function releasePlotRefits() {
  while (plotRefits.length) plotRefits.pop().disconnect();
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
  /* And again on resize, because the refit is what makes the no-clipping guarantee true and it
   * ran only at draw time: dragging a window narrower left the stale gutter in place until the
   * next redraw, which is the clipped-label fault returning by another route.
   *
   * The viewBox is RESET to nominal first. Without that the widening ratchets: each resize
   * measures against an already-widened box and grows it again, and the plot shrinks away. */
  if (typeof ResizeObserver === 'function') {
    const refit = new ResizeObserver(() => {
      frame.setAttribute('viewBox', `0 0 ${PLOT_WIDTH} ${PLOT_HEIGHT}`);
      sizePlotText(frame);
    });
    refit.observe(frame);
    plotRefits.push(refit);
  }
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
      /* getBBox is guarded because it is not universally safe on an unrendered subtree: measured
       * in Chromium it returns zeros inside a display:none container, and other engines throw
       * rather than returning. A throw here would escape the requestAnimationFrame callback. The
       * degraded path is the nominal build-time gutter, which is correct at full width. */
      let bounds;
      try {
        bounds = text.getBBox();
      } catch (unmeasurable) {
        return;
      }
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

/* A RADIO GROUP, which the handoff lists as a gap to close. Five buttons carrying `aria-pressed`
 * announce themselves as five independent toggles, and this control is single-select: that is a
 * screen reader being told something untrue about the form. `radio` roles plus one tab stop and
 * arrow-key movement is what the pattern actually is. */
function renderConfidence() {
  const group = document.getElementById('confidence-group');
  clear(group);
  CONFIDENCE.forEach((option, index) => {
    const button = el('button', null, null);
    button.type = 'button';
    button.setAttribute('role', 'radio');
    const chosen = state.confidence === option.step;
    button.setAttribute('aria-checked', String(chosen));
    /* One tab stop for the whole group: the checked option, or the first when none is. */
    button.tabIndex = chosen || (state.confidence === 0 && index === 0) ? 0 : -1;
    button.appendChild(el('span', null, option.label));
    button.appendChild(el('span', null, `${option.probability}`));
    button.addEventListener('click', () => {
      state.confidence = option.step;
      renderConfidence();
      document.querySelector('#confidence-group [aria-checked="true"]').focus();
    });
    button.addEventListener('keydown', (event) => {
      const step = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1
        : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0;
      if (!step) return;
      event.preventDefault();
      const next = (index + step + CONFIDENCE.length) % CONFIDENCE.length;
      state.confidence = CONFIDENCE[next].step;
      renderConfidence();
      document.querySelector('#confidence-group [aria-checked="true"]').focus();
    });
    group.appendChild(button);
  });
}

/* ---------------------------------------------------------------- the countdown */

/* The cue's own target, counted down by the CLIENT for display only. The score's elapsed time is
 * measured server-side from `served_at` and this number never reaches it - the same reason
 * `elapsed_ms` is accepted on the submission and then discarded. So a paused tab, a slow frame or
 * a hostile clock changes what the operator sees and cannot change what they are awarded. */
const countdown = { timer: 0, left: 0, target: 0 };

function stopCountdown() {
  if (countdown.timer) window.clearInterval(countdown.timer);
  countdown.timer = 0;
}

function paintCountdown() {
  const host = document.getElementById('countdown');
  const fill = document.getElementById('countdown-fill');
  const readout = document.getElementById('countdown-n');
  const remaining = Math.max(0, countdown.left);
  fill.style.width = countdown.target > 0
    ? `${Math.max(0, Math.min(100, (remaining / countdown.target) * 100))}%`
    : '0%';
  /* Never colour alone: past the target the WORD changes as well as the hue. */
  readout.textContent = remaining > 0 ? `${remaining}s` : 'over';
  host.classList.toggle('out', remaining === 0);
}

function startCountdown(seconds) {
  stopCountdown();
  countdown.target = Number.isFinite(seconds) && seconds > 0 ? Math.round(seconds) : 0;
  countdown.left = countdown.target;
  paintCountdown();
  if (!countdown.target) return;
  countdown.timer = window.setInterval(() => {
    countdown.left -= 1;
    paintCountdown();
    if (countdown.left <= 0) stopCountdown();
  }, 1000);
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
  /* Outside the try below, deliberately. The array only ever holds ResizeObserver instances
   * created under the `typeof ResizeObserver === 'function'` guard, and `disconnect()` does not
   * throw, so there is nothing here for the handler to catch. If a future entry could throw, this
   * call belongs inside the try: a rejection here would land before `banner(error.message)` exists
   * and the operator would see the loading text and no error. */
  releasePlotRefits();
  clear(document.getElementById('stimuli'));
  try {
    document.getElementById('ops').classList.remove('hidden');
    const drill = await api('/api/v1/drill/next');
    state.drill = drill;
    state.confidence = 0;
    state.servedAt = Date.now();
    /* The id row, built from the served identifiers rather than composed as one string, so the
     * divider is a rule between two facts instead of a punctuation mark inside one. */
    const idrow = document.getElementById('drill-kicker');
    clear(idrow);
    idrow.appendChild(el('b', null, drill.item_id));
    idrow.appendChild(el('span', null, drill.cue_id || 'no cue'));
    idrow.appendChild(el('span', 'div'));
    idrow.appendChild(el('span', null, `rated ${drill.elo}`));
    idrow.appendChild(el('span', null, `target ${drill.time_target_s}s`));
    document.getElementById('drill-prompt').textContent = drill.prompt;
    document.getElementById('drill-meta').textContent =
      `Content ${drill.content_hash.slice(0, 12)}.`;
    startCountdown(drill.time_target_s);
    const host = document.getElementById('stimuli');
    for (const stimulus of drill.stimulus) host.appendChild(drawStimulus(stimulus));
    document.getElementById('response-label').textContent =
      RESPONSE_LABELS[drill.response_format] || 'Your answer';
    document.getElementById('response').value = '';
    renderConfidence();
    document.getElementById('answer-form').classList.remove('hidden');
    document.getElementById('response').focus();
  } catch (error) {
    stopCountdown();
    banner(error.message);
    document.getElementById('drill-prompt').textContent = 'No drill available.';
  }
}

const VERDICT_GLYPH = { accept: '▲', partial: '◆', reject: '▼', none: '○', unscorable: '○' };

const VERDICT_WORD = {
  accept: 'called it',
  partial: 'right, and imprecise',
  reject: 'a named wrong answer',
  none: 'not a recognised answer',
  unscorable: 'could not be scored',
};

const VERDICT_HEADING = {
  accept: 'Right call.',
  partial: 'Right, and imprecise.',
  reject: 'That is a named wrong answer.',
  none: 'Not a recognised answer.',
  unscorable: 'This item could not be scored.',
};

/* One stat card. `delta` is optional and decides the arrow class, so a rating that moved down is
 * not painted as a gain. */
function statCard(key, value, detail, direction) {
  const card = el('div', 's');
  card.appendChild(el('div', 'k', key));
  card.appendChild(el('div', 'v', value));
  if (detail) card.appendChild(el('div', `d${direction ? ` ${direction}` : ''}`, detail));
  return card;
}

/* The debrief. Replaces the drill body once a call is committed.
 *
 * The three stat cards are gated on `showGameLayer` per the handoff, and all three carry REAL
 * fields off the scored payload: the rating and its delta, the calibration verdict with its
 * Brier score, and when the cue comes back. The handoff's third card is a streak, which has no
 * source in this API, so the slot carries the spacing interval instead - a figure an operator
 * can act on rather than one invented to fill a card. */
function renderReveal(result) {
  const host = document.getElementById('reveal');
  clear(host);
  stopCountdown();

  const sheet = el('div', 'debrief');

  const called = el('div', 'called');
  called.appendChild(el('span', `ring ${result.matched}`, VERDICT_GLYPH[result.matched] || '○'));
  called.appendChild(el('span', `what ${result.matched}`,
    `${VERDICT_WORD[result.matched] || 'scored'} · ${result.item_id}`));
  sheet.appendChild(called);

  /* The verdict block keeps its class contract and its glyph: a verdict never rests on colour,
   * and it is never styled through the recency token. */
  const verdict = el('div', `verdict ${result.matched}`);
  const heading = el('h3');
  heading.appendChild(el('span', 'glyph', VERDICT_GLYPH[result.matched] || '○'));
  heading.appendChild(document.createTextNode(VERDICT_HEADING[result.matched] || 'Scored.'));
  verdict.appendChild(heading);
  if (result.why_wrong) verdict.appendChild(el('p', null, result.why_wrong));
  if (result.explain) verdict.appendChild(el('p', null, result.explain));
  sheet.appendChild(verdict);

  if (state.showGameLayer) {
    const stats = el('div', 'stats');
    const delta = result.rating_delta;
    stats.appendChild(statCard(
      'rating',
      result.rating_after === null ? 'unchanged' : String(result.rating_after),
      delta === null || delta === 0 ? 'no change' : `${delta > 0 ? '+' : ''}${delta}`,
      delta === null || delta === 0 ? '' : delta > 0 ? 'up' : 'down',
    ));
    stats.appendChild(statCard(
      'calibration',
      result.brier === null ? 'not scored' : result.brier.toFixed(3),
      result.calibration,
      '',
    ));
    stats.appendChild(statCard(
      'back in',
      result.next_due_in_days === 1 ? '1 day' : `${result.next_due_in_days} days`,
      'spacing interval',
      '',
    ));
    sheet.appendChild(stats);
  }

  /* The operator-habit panel. Its text is the AUTHORED coaching line off the scored payload, not
   * a phrase composed here: a habit this interface made up would be a claim about a person. */
  const habit = result.note;
  if (habit) {
    const panel = el('div', 'habit');
    panel.appendChild(el('div', 'k', 'operator / habit'));
    panel.appendChild(el('div', 't', habit));
    sheet.appendChild(panel);
  }

  sheet.appendChild(el('h2', null, 'Where the score went'));
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
  totalRow.appendChild(el('td', null,
    `Rating ${result.rating_before} to ${result.rating_after}.`));
  body.appendChild(totalRow);
  table.appendChild(body);
  const wrap = el('div', 'tablewrap');
  wrap.appendChild(table);
  sheet.appendChild(wrap);

  if (result.unimplemented_rules && result.unimplemented_rules.length) {
    sheet.appendChild(el('p', 'panel-note',
      `${result.unimplemented_rules.length} rule(s) in this rubric have no predicate yet and were not evaluated: ${result.unimplemented_rules.join(', ')}.`));
  }
  if (result.unimplemented_aggregation && result.unimplemented_aggregation.length) {
    sheet.appendChild(el('p', 'panel-note',
      `Aggregation the rubric asks for and this evaluator does not apply: ${result.unimplemented_aggregation.join(', ')}.`));
  }

  const buttons = el('div', 'buttons');
  const next = el('button', 'act', 'Next cue →');
  next.type = 'button';
  next.addEventListener('click', loadDrill);
  buttons.appendChild(next);
  const read = el('button', 'act2', 'Show the procedure');
  read.type = 'button';
  read.addEventListener('click', () => show('library'));
  buttons.appendChild(read);
  sheet.appendChild(buttons);

  host.appendChild(sheet);
  document.getElementById('ops').classList.add('hidden');
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

/* A banded estimate bar plus its figure, sharing one colour band and always carrying the WORD.
 * The handoff bands by colour alone; the flight plan forbids status by colour alone, so the band
 * name rides along with the number. */
function estimateCell(competency) {
  const cell = el('div', 'est');
  if (!competency.measured) {
    cell.appendChild(el('span', 'fig', 'not measured'));
    return cell;
  }
  const entry = band(competency.estimate);
  const suffix = entry.cls.replace('s-', '');
  const track = el('div', `bar b-${suffix === 'strong' ? 'good' : suffix === 'accent' ? 'accent' : suffix === 'shaky' ? 'shaky' : 'bad'}`);
  const fill = el('i');
  fill.style.width = `${Math.round(competency.estimate * 100)}%`;
  track.appendChild(fill);
  cell.appendChild(track);
  /* The INTERVAL rides with the figure, always. The flight plan calls a bare estimate a claim
   * the data cannot support, and the handoff's own Progress table shows one; this keeps both the
   * handoff's bar and the plan's interval. */
  const low = Math.round(competency.interval[0] * 100);
  const high = Math.round(competency.interval[1] * 100);
  cell.appendChild(el('span',
    `fig f-${suffix === 'strong' ? 'good' : suffix === 'accent' ? 'accent' : suffix === 'shaky' ? 'shaky' : 'bad'}`,
    `${Math.round(competency.estimate * 100)} (${low}\u2013${high})`));
  return cell;
}

async function loadProgress() {
  const cards = document.getElementById('progress-cards');
  const host = document.getElementById('progress-body');
  clear(cards);
  clear(host);
  try {
    const me = await api('/api/v1/me');
    fillGameLayer(me);

    const measured = me.competencies.filter((c) => c.measured);
    const weak = weakest(me.competencies);
    cards.appendChild(statCard('drill rating', String(me.drill_rating),
      `${me.runs_total} ${me.runs_total === 1 ? 'answer' : 'answers'} recorded`, ''));
    cards.appendChild(statCard('measured axes', `${measured.length} of ${me.competencies.length}`,
      measured.length ? 'estimated from your own calls' : 'nothing measured yet', ''));
    cards.appendChild(statCard('weakest',
      weak ? `${Math.round(weak.estimate * 100)}` : 'none yet',
      weak ? weak.name : 'no axis has an attempt', ''));
    cards.appendChild(statCard('due now', String(me.due_now),
      me.due_now === 1 ? 'one cue scheduled' : 'cues scheduled', ''));
    for (const card of cards.children) card.classList.add('s');

    const grid = el('div', 'grid-rows');
    const header = el('div', 'hd');
    header.appendChild(el('span', null, 'Competency'));
    header.appendChild(el('span', null, 'Estimate and interval'));
    header.appendChild(el('span', 'at', 'Calls'));
    header.appendChild(el('span', 'nx', 'Mean brier'));
    grid.appendChild(header);
    for (const competency of me.competencies) {
      const row = el('div', 'rw');
      row.appendChild(el('span', 'nm', competency.name || competency.competency_id));
      row.appendChild(estimateCell(competency));
      row.appendChild(el('span', 'at', String(competency.attempts)));
      row.appendChild(el('span', 'nx',
        competency.mean_brier === null ? '\u2014' : competency.mean_brier.toFixed(3)));
      grid.appendChild(row);
    }
    host.appendChild(grid);
    document.getElementById('progress-identity').textContent = me.identity;
  } catch (error) {
    banner(error.message);
  }
}

/* The status chips. Derived from the statuses the CONTENT actually declares rather than the
 * handoff's `Protect / Defend / Reporting`, which are its own invention: a filter offering a
 * category the library does not contain is a control that can only ever return nothing. */
function renderLibraryChips() {
  const host = document.getElementById('library-chips');
  clear(host);
  const statuses = ['all', ...new Set(
    state.library.procedures.map((p) => p.status).filter(Boolean).sort(),
  )];
  for (const status of statuses) {
    const chip = el('button', null, status);
    chip.type = 'button';
    chip.setAttribute('aria-pressed', String(state.library.status === status));
    chip.addEventListener('click', () => {
      state.library.status = status;
      renderLibraryChips();
      renderLibraryCards();
    });
    host.appendChild(chip);
  }
}

function renderLibraryCards() {
  const grid = document.getElementById('library-grid');
  clear(grid);
  const query = state.library.query.trim().toLowerCase();
  const shown = state.library.procedures.filter((procedure) => {
    if (state.library.status !== 'all' && procedure.status !== state.library.status) return false;
    if (!query) return true;
    return `${procedure.id} ${procedure.name} ${procedure.purpose || ''}`.toLowerCase().includes(query);
  });
  for (const procedure of shown) {
    /* A BUTTON, not a div with a click handler: it is keyboard reachable and announces itself. */
    const card = el('button', 'proc');
    card.type = 'button';
    const top = el('div', 'top');
    top.appendChild(el('span', 'pid', procedure.id));
    top.appendChild(el('span', 'mast', procedure.status || 'status unstated'));
    card.appendChild(top);
    card.appendChild(el('h3', null, procedure.name || procedure.id));
    /* The AUTHORED purpose, which is what the card is for. No mastery percentage: the handoff
     * shows one per card and nothing in this API measures mastery per procedure, so the slot
     * beside the id carries the content's own status instead of an invented figure. */
    card.appendChild(el('p', null, procedure.purpose || 'No purpose recorded for this procedure.'));
    const tags = el('div', 'tags');
    /* One pill per regime, and a non-array is a RENDERING FAULT rather than something to
     * iterate. `for...of` over a string yields characters, so a string-shaped payload split
     * into one pill per letter on the client exactly as it did on the server. The boundary
     * refuses that shape now; this is the second line of defence, and it says so on screen
     * rather than drawing something plausible. */
    if (Array.isArray(procedure.regime)) {
      for (const regime of procedure.regime) tags.appendChild(el('span', null, regime));
    } else if (procedure.regime !== undefined && procedure.regime !== null) {
      tags.appendChild(el('span', null, 'regime unreadable, TBC re-verify'));
    }
    tags.appendChild(el('span', null,
      `${procedure.steps} ${procedure.steps === 1 ? 'step' : 'steps'}`));
    card.appendChild(tags);
    card.addEventListener('click', () => openProcedure(procedure.id));
    grid.appendChild(card);
  }
  if (!shown.length) {
    const empty = el('button', 'proc empty');
    empty.type = 'button';
    empty.disabled = true;
    empty.appendChild(el('span', 'pid', 'nothing matches'));
    empty.appendChild(el('h3', null, query ? `No procedure matches \u201c${state.library.query}\u201d` : 'No procedure in this status'));
    empty.appendChild(el('p', null, 'Clear the search or pick another status.'));
    grid.appendChild(empty);
  }
}

/* One procedure, in full, fetched on demand from the route that serves the document. Rendered
 * as TEXT through `el`, never as markup: every value here is authored content and
 * `test_the_interface_never_writes_an_untrusted_value_as_markup` binds that. */
async function openProcedure(procedureId) {
  const host = document.getElementById('library-body');
  clear(host);
  try {
    const document_ = await api(`/api/v1/content/procedure/${encodeURIComponent(procedureId)}`);
    const procedure = document_.procedure;
    const scope = el('div', 'scope');
    const head = el('div', 'scope-head');
    head.appendChild(el('b', null, procedure.name || procedure.id));
    head.appendChild(el('span', null, procedure.id));
    head.appendChild(el('span', null, procedure.status || 'status unstated'));
    scope.appendChild(head);
    const panels = el('div', 'panels');
    for (const [key, value] of Object.entries(procedure)) {
      if (['id', 'name', 'status'].includes(key)) continue;
      const panel = el('div', null);
      panel.appendChild(el('p', 'panel-title', key.replace(/_/g, ' ')));
      panel.appendChild(el('p', null, typeof value === 'string' ? value : JSON.stringify(value, null, 1)));
      panels.appendChild(panel);
    }
    scope.appendChild(panels);
    host.appendChild(scope);
    host.scrollIntoView({ block: 'nearest' });
  } catch (error) {
    banner(error.message);
  }
}

async function loadLibrary() {
  clear(document.getElementById('library-body'));
  try {
    const index = await api('/api/v1/content/procedures');
    state.library.procedures = index.procedures;
    const search = document.getElementById('library-search');
    if (!search.dataset.wired) {
      search.addEventListener('input', () => {
        state.library.query = search.value;
        renderLibraryCards();
      });
      search.dataset.wired = 'yes';
    }
    renderLibraryChips();
    renderLibraryCards();
  } catch (error) {
    banner(error.message);
  }
}

/* ---------------------------------------------------------------- session and game layer */

/* The competency estimate bands the handoff specifies, top of range first so the first match
 * wins. Colour is never the only carrier: every band also renders its word. */
const BANDS = [
  { floor: 0.70, cls: 's-strong', word: 'strong' },
  { floor: 0.50, cls: 's-accent', word: 'fair' },
  { floor: 0.36, cls: 's-shaky', word: 'shaky' },
  { floor: 0, cls: 's-missed', word: 'weak' },
];

function band(estimate) {
  return BANDS.find((entry) => estimate >= entry.floor) || BANDS[BANDS.length - 1];
}

/* Which competency is weakest, over the MEASURED ones only. An axis with no attempts has no
 * figure at all, so it cannot be the weakest: calling it that would report an absence as a
 * finding, which is the fault `measured` exists to prevent. */
function weakest(competencies) {
  const measured = competencies.filter((c) => c.measured && typeof c.estimate === 'number');
  if (!measured.length) return null;
  return measured.reduce((worst, c) => (c.estimate < worst.estimate ? c : worst), measured[0]);
}

/* The game layer, on by owner decision of 08 September. It renders ONLY what the API supports.
 * Withheld deliberately, because no source exists and the never-invent rule covers a shipped
 * surface: the day-streak count, the rank tier name, the rank target,
 * and the fourteen-day activity bars. The handoff's figures for all four are its own synthetic
 * display data. The chip and rank slots keep the handoff's treatment and carry real numbers
 * under truthful labels instead; the rank TRACK stays hidden until a rank scale exists, because
 * a bar with no defined ceiling is a picture of nothing. */
function fillGameLayer(me) {
  const chip = document.getElementById('game-layer');
  const rank = document.getElementById('rank-block');
  if (!state.showGameLayer) return;
  document.getElementById('streak-n').textContent = String(me.runs_total);
  document.getElementById('streak-unit').textContent = me.runs_total === 1 ? 'answer recorded' : 'answers recorded';
  chip.classList.remove('hidden');
  document.getElementById('rank-name').textContent = 'drill rating';
  document.getElementById('rank-progress').textContent = String(me.drill_rating);
  rank.classList.remove('hidden');
}

async function loadSession() {
  banner('');
  try {
    const me = await api('/api/v1/me');
    fillGameLayer(me);

    /* No session NUMBER exists in the API and the mockup's is synthetic, so the kicker carries
     * the content hash instead: it is the one provenance string that makes a run reproducible,
     * which is what a session id would have been for. */
    document.getElementById('session-kicker').textContent =
      `Session · content ${me.content_hash.slice(0, 8)}`;

    const weak = weakest(me.competencies);
    document.getElementById('session-title').textContent = weak
      ? `Today you are drilling ${weak.name.toLowerCase()}`
      : 'Today you are drilling from a clean sheet';
    document.getElementById('session-sub').textContent = weak
      ? 'The run leads with your weakest measured axis. Cues you have missed come back sooner and harder.'
      : 'Nothing is measured yet, so the first run establishes a baseline rather than correcting one.';

    /* `due_now` is a real count. The mockup's run length in minutes is not derivable from this
     * payload, so it is omitted rather than guessed. */
    document.getElementById('run-count').textContent = String(me.due_now);
    document.getElementById('run-length').textContent =
      me.due_now === 1 ? 'cue due now' : 'cues due now';
    document.getElementById('run-blurb').textContent =
      'Spaced repetition decides the order. An item you got right moves further out; one you'
      + ' missed comes back inside a day.';

    if (weak) {
      document.getElementById('weak-name').textContent = weak.name;
      const low = Math.round(weak.interval[0] * 100);
      const high = Math.round(weak.interval[1] * 100);
      document.getElementById('weak-body').textContent =
        `Estimated ${Math.round(weak.estimate * 100)} out of 100, interval ${low} to ${high},`
        + ` over ${weak.attempts} ${weak.attempts === 1 ? 'call' : 'calls'}.`;
      const bar = document.getElementById('weak-bar');
      bar.style.width = `${Math.round(weak.estimate * 100)}%`;
      bar.style.background = `var(--${band(weak.estimate).cls === 's-strong' ? 'good' : band(weak.estimate).cls === 's-accent' ? 'accent' : band(weak.estimate).cls === 's-shaky' ? 'warn' : 'bad'})`;
    } else {
      document.getElementById('weak-name').textContent = 'Not measured yet';
      document.getElementById('weak-body').textContent =
        'No axis has an attempt against it, so there is no weakest. A figure here before the'
        + ' first call would be a claim the data cannot support.';
    }

    document.getElementById('recorded-n').textContent = String(me.runs_total);
    document.getElementById('recorded-body').textContent =
      `${me.runs_total} ${me.runs_total === 1 ? 'answer' : 'answers'} recorded, drill rating`
      + ` ${me.drill_rating}. The fourteen-day activity strip the mockup shows needs per-day`
      + ' history the dashboard does not expose yet, so it is left out rather than drawn from'
      + ' nothing.';

    const covers = document.getElementById('covers');
    clear(covers);
    me.competencies.forEach((competency, index) => {
      const row = el('div', 'row');
      row.appendChild(el('span', 'idx', String(index + 1).padStart(2, '0')));
      row.appendChild(el('span', 'name', competency.name || competency.competency_id));
      row.appendChild(el('span', 'cues',
        `${competency.attempts} ${competency.attempts === 1 ? 'call' : 'calls'}`));
      if (competency.measured) {
        const entry = band(competency.estimate);
        row.appendChild(el('span', `status ${entry.cls}`,
          `${entry.word} · ${Math.round(competency.estimate * 100)}`));
      } else {
        row.appendChild(el('span', 'status', 'not measured'));
      }
      covers.appendChild(row);
    });

    document.getElementById('session-note').textContent = me.identity;
  } catch (error) {
    banner('The session could not be loaded.');
  }
}

/* ---------------------------------------------------------------- shell */

const VIEWS = { session: loadSession, drill: loadDrill, progress: loadProgress, library: loadLibrary };

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
  /* Any control carrying data-view navigates, so the session hero's secondary button and the
   * nav share one path rather than two that can drift. */
  for (const button of document.querySelectorAll('main [data-view]')) {
    button.addEventListener('click', () => show(button.dataset.view));
  }
  document.getElementById('start-run').addEventListener('click', () => show('drill'));
  api('/api/v1/content/manifest').then((manifest) => {
    document.getElementById('rail-status').textContent =
      manifest.ok ? `${manifest.counts.drills} drills · ${manifest.content_hash.slice(0, 8)}` : 'content fault';
    if (!manifest.ok) banner(manifest.errors.join(' '));
  }).catch(() => {
    document.getElementById('rail-status').textContent = 'offline';
  });
  show('session');
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
