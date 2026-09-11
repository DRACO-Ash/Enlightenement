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
  /* `layout` is the index's second view and `sort` is the column it is ordered by. Both live in
   * state rather than in the DOM so switching views and filtering do not fight each other: the
   * table and the cards read the same filtered list. */
  library: { procedures: [], query: '', status: 'all', layout: 'cards', sort: 'id', ascending: true },
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
  while (node.firstChild) node.firstChild.remove();
}

async function api(path, options) {
  const response = await fetch(path, { headers: { 'accept': 'application/json' }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
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
  /* `??` is the whole of the old three-part test: it falls through for null AND undefined and
   * keeps a legitimate 0, which is the case the long form existed to protect. */
  const min = axis?.minimum ?? low;
  const max = axis?.maximum ?? high;
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

  const supplied = panel.y?.ticks || [];
  const widest = supplied.reduce((most, [, text]) => Math.max(most, String(text).length), 0);
  const padLeft = Math.max(PAD.left, widest * AXIS_FONT_PX * TICK_ADVANCE_EM + TICK_GUTTER);
  const plotW = PLOT_WIDTH - padLeft - PAD.right;
  const plotH = PLOT_HEIGHT - PAD.top - PAD.bottom;
  const sx = (value) => padLeft + ((value - x0) / (x1 - x0)) * plotW;
  /* The inverted flag, honoured. Not a preference: a magnitude axis runs brighter upward. */
  const sy = (value) => {
    const t = (value - y0) / (y1 - y0);
    return panel.y?.inverted
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
        const value = panel.y?.inverted
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
  const inversionNote = panel.y?.inverted
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
    const viewBox = frame.viewBox?.baseVal;
    const size = fittedTextSize(frame, viewBox);
    if (!size) return;
    applyTextSize(frame, size);
    const extent = measuredTextExtent(frame, viewBox);
    if (!extent) return;
    if (!overflows(viewBox, extent)) return;
    widenViewBox(frame, viewBox, extent);
  }
}

/* The font size this scale needs, in viewBox units, or 0 when the frame cannot be measured yet.
 * Zero is never a legitimate size - the floor is a third of the nominal - so one return value
 * carries both answers without ambiguity. */
function fittedTextSize(frame, viewBox) {
  const box = frame.getBoundingClientRect();
  if (!box.width || !viewBox?.width) return 0;
  const scale = box.width / viewBox.width;
  if (!Number.isFinite(scale) || scale <= 0) return 0;
  return Math.max(AXIS_FONT_PX / scale, AXIS_FONT_PX / 3);
}

/* Apply the size, and move the labels whose offsets have to scale with it.
 *
 * The horizontal labels sit BELOW the axis at offsets that must scale with the text, or they
 * collide with the caption: at a 31-unit font the fixed 20 and 36 unit offsets overlap, which
 * a screenshot at 430px showed plainly while every number was inside the box. Positioned from
 * the size actually applied, and chosen to land on the original 240 and 256 at 13 units so the
 * nominal design is unchanged. */
function applyTextSize(frame, size) {
  for (const text of frame.querySelectorAll('text')) {
    text.setAttribute('font-size', size.toFixed(2));
  }
  const axisY = PLOT_HEIGHT - PAD.bottom;
  for (const tick of frame.querySelectorAll('[data-role="x-tick"]')) {
    tick.setAttribute('y', (axisY + size * X_TICK_OFFSET_EM).toFixed(1));
  }
  for (const caption of frame.querySelectorAll('[data-role="x-caption"]')) {
    caption.setAttribute('y', (axisY + size * X_CAPTION_OFFSET_EM).toFixed(1));
  }
}

/* The union of every label's box with the viewBox, or null when a box cannot be measured.
 *
 * Expanded on every side the text actually needs, not just the left: the same fixed-gutter
 * fault applies to each edge, and only the left one had been found. */
function measuredTextExtent(frame, viewBox) {
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
    } catch {
      /* No binding: nothing here reads the error, and an unread name is a reader wondering what
       * was meant to happen to it. The reason for swallowing it is the comment above. */
      return null;
    }
    if (!bounds.width && !bounds.height) continue;
    minX = Math.min(minX, bounds.x);
    minY = Math.min(minY, bounds.y);
    maxX = Math.max(maxX, bounds.x + bounds.width);
    maxY = Math.max(maxY, bounds.y + bounds.height);
  }
  return { minX, minY, maxX, maxY };
}

/* Whether the measured text has left the box by more than the tolerance, on any side. */
function overflows(viewBox, extent) {
  return extent.minX < viewBox.x - TEXT_FIT_TOLERANCE
    || extent.minY < viewBox.y - TEXT_FIT_TOLERANCE
    || extent.maxX > viewBox.x + viewBox.width + TEXT_FIT_TOLERANCE
    || extent.maxY > viewBox.y + viewBox.height + TEXT_FIT_TOLERANCE;
}

/* Widen the canvas to contain the text. Geometry is untouched: it simply starts further out. */
function widenViewBox(frame, viewBox, extent) {
  const x0 = Math.min(extent.minX, viewBox.x) - TEXT_FIT_PAD;
  const y0 = Math.min(extent.minY, viewBox.y) - TEXT_FIT_PAD;
  const x1 = Math.max(extent.maxX, viewBox.x + viewBox.width) + TEXT_FIT_PAD;
  const y1 = Math.max(extent.maxY, viewBox.y + viewBox.height) + TEXT_FIT_PAD;
  frame.setAttribute(
    'viewBox',
    `${x0.toFixed(1)} ${y0.toFixed(1)} ${(x1 - x0).toFixed(1)} ${(y1 - y0).toFixed(1)}`,
  );
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
  const size = group.glyph === 'dot' ? 3 : 2.6;
  /* Decided once. The same comparison sat inside the loop and was re-answered for every
   * observation, which on a waterfall is several hundred times per group. */
  const usesRamp = group.ramp?.length === group.x.length;
  for (let i = 0; i < group.x.length; i += 1) {
    const x = sx(group.x[i]);
    const y = sy(group.y[i]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    frame.appendChild(scatterMark(group.glyph, x, y, size, usesRamp ? ramp(group.ramp[i]) : colour));
  }
}

/* One scatter mark, by glyph. A chain of `continue`s with a node type and its attributes each
 * chosen by their own nested ternary stood in the loop above; each glyph now builds its own node
 * and the loop only places it. */
function scatterMark(glyph, x, y, size, stroke) {
  if (glyph === 'dot') return svg('circle', { cx: x, cy: y, r: size, fill: stroke });
  if (glyph === 'square') {
    return svg('rect', {
      x: x - size, y: y - size, width: size * 2, height: size * 2,
      fill: 'none', stroke, 'stroke-width': 1.3,
    });
  }
  if (glyph === 'bar') return svg('rect', { x, y: y - 4, width: 3, height: 8, fill: stroke });
  /* The default is a plus-cross scatter, not a polyline. A connecting line asserts continuity
   * between observations that are not continuous, and it hides the pass structure. */
  return svg('path', {
    d: `M${x - size} ${y}H${x + size}M${x} ${y - size}V${y + size}`,
    stroke, 'stroke-width': 1.1, 'stroke-linecap': 'round',
  });
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

/* A cell's display text. Absence is an em dash, a boolean reads as a word, everything else is
 * its own string. Lifted out of a ternary nested inside a ternary: three outcomes read down the
 * page beat three outcomes read inside out. */
function cellText(raw) {
  if (raw === null || raw === undefined) return '—';
  if (typeof raw === 'boolean') return raw ? 'yes' : 'no';
  return String(raw);
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
  for (const row of stimulus.rows) body.appendChild(tableRow(stimulus.columns, row));
  table.appendChild(body);
  wrap.appendChild(table);
  return wrap;
}

/* One data row. Lifted out so the table builder is two flat loops rather than a loop inside a
 * loop with the cell's own decisions inlined at the bottom of it. */
function tableRow(columns, row) {
  const tr = el('tr');
  for (const column of columns) {
    const classes = [column.align === 'right' ? 'r' : '', column.emphasis ? 'em' : '']
      .filter(Boolean).join(' ');
    tr.appendChild(el('td', classes || null, cellText(row[column.key])));
  }
  return tr;
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

  if (stimulus.panels?.length) {
    const panels = el('div', stimulus.panels.length > 1 ? 'panels multi' : 'panels');
    for (const panel of stimulus.panels) panels.appendChild(drawPanel(panel));
    scope.appendChild(panels);
  }
  if (stimulus.columns?.length) {
    scope.appendChild(drawTable(stimulus));
  }
  if (stimulus.legend?.length) {
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
/* Which way an arrow key moves the confidence selection: forward, back, or not an arrow at all.
 * The caller treats 0 as "not mine" and returns, so a named function keeps the three answers
 * apart. Both axes are accepted because the group reads as a row and is laid out as one. */
const NEXT_KEYS = new Set(['ArrowRight', 'ArrowDown']);
const PREVIOUS_KEYS = new Set(['ArrowLeft', 'ArrowUp']);

function arrowStep(key) {
  if (NEXT_KEYS.has(key)) return 1;
  if (PREVIOUS_KEYS.has(key)) return -1;
  return 0;
}

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
      const step = arrowStep(event.key);
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
  /* **"Name the event" contradicted half the items using this format.** DRL-0005 asks "The
   * tooling reports this drift rate. What do you do?" and its accepted answers are actions -
   * "reject the value, check epoch separation" - so an operator was asked for an action and
   * told to name an event. The owner's words on the served screen: "I also don't understand the
   * question here." `free_classification` covers both "classify this" and "what do you do", so
   * the label has to be one that neither prompt contradicts. The PROMPT above it is the
   * question; this names the box. */
  free_classification: 'Your call',
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
    /* **The line under the prompt is for the OPERATOR, and it held a bare content hash.**
     * "Content 0e395153ae12." is the most prominent line after the question, in the position
     * where a reader looks for context about what they are being asked, and it says nothing
     * anyone can act on. It is build provenance, it is already in the session strip
     * ("Session · content 0e395153") and the seed is already in the stimulus footer, so it was
     * duplicated into the one place it is least useful. The slot now carries the confidence
     * instruction, which is the thing an operator actually needs before answering. */
    document.getElementById('drill-meta').textContent = drill.confidence_required
      ? 'Say how sure you are as well as what you think. Both are scored.'
      : '';
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
  if (detail) {
    /* Built as a statement rather than a template inside a template: the class is `d` with an
     * optional direction, and the nested form made a two-word string look like arithmetic. */
    const detailClass = direction ? `d ${direction}` : 'd';
    card.appendChild(el('div', detailClass, detail));
  }
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
  sheet.appendChild(calledRing(result));
  sheet.appendChild(verdictBlock(result));
  if (state.showGameLayer) sheet.appendChild(statsRow(result));
  const habit = habitPanel(result);
  if (habit) sheet.appendChild(habit);
  sheet.appendChild(el('h2', null, 'Where the score went'));
  sheet.appendChild(scoreTable(result));
  for (const note of disclosureNotes(result)) sheet.appendChild(note);
  const buttons = revealButtons();
  sheet.appendChild(buttons.node);

  host.appendChild(sheet);
  document.getElementById('ops').classList.add('hidden');
  host.classList.remove('hidden');
  buttons.focusTarget.focus();
}

/* What the operator called, and what it was. */
function calledRing(result) {
  const called = el('div', 'called');
  called.appendChild(el('span', `ring ${result.matched}`, VERDICT_GLYPH[result.matched] || '○'));
  called.appendChild(el('span', `what ${result.matched}`,
    `${VERDICT_WORD[result.matched] || 'scored'} · ${result.item_id}`));
  return called;
}

/* The verdict block keeps its class contract and its glyph: a verdict never rests on colour,
 * and it is never styled through the recency token. */
function verdictBlock(result) {
  const verdict = el('div', `verdict ${result.matched}`);
  const heading = el('h3');
  heading.appendChild(el('span', 'glyph', VERDICT_GLYPH[result.matched] || '○'));
  heading.appendChild(document.createTextNode(VERDICT_HEADING[result.matched] || 'Scored.'));
  verdict.appendChild(heading);
  if (result.why_wrong) verdict.appendChild(el('p', null, result.why_wrong));
  if (result.explain) verdict.appendChild(el('p', null, result.explain));
  return verdict;
}

/* The three game-layer cards, all carrying REAL fields off the scored payload. */
function statsRow(result) {
  const stats = el('div', 'stats');
  const delta = result.rating_delta;
  /* One decision, made once, read twice. The rating moved or it did not; a nested ternary in
   * each argument asked the same question twice and answered it in two different shapes. */
  const moved = delta !== null && delta !== 0;
  let direction = '';
  if (moved) direction = delta > 0 ? 'up' : 'down';
  const sign = moved && delta > 0 ? '+' : '';
  stats.appendChild(statCard(
    'rating',
    result.rating_after === null ? 'unchanged' : String(result.rating_after),
    moved ? `${sign}${delta}` : 'no change',
    direction,
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
  return stats;
}

/* The operator-habit panel, or null when the payload carries no coaching line. Its text is the
 * AUTHORED line off the scored payload, not a phrase composed here: a habit this interface made
 * up would be a claim about a person. */
function habitPanel(result) {
  if (!result.note) return null;
  const panel = el('div', 'habit');
  panel.appendChild(el('div', 'k', 'operator / habit'));
  panel.appendChild(el('div', 't', result.note));
  return panel;
}

/* Rule by rule, with the total and the rating move on the last row. */
function scoreTable(result) {
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
  return wrap;
}

/* What the rubric asked for and this evaluator did not do. Disclosed rather than omitted: a
 * score that silently skipped a rule reads as a complete score. */
function disclosureNotes(result) {
  const notes = [];
  if (result.unimplemented_rules?.length) {
    notes.push(el('p', 'panel-note',
      `${result.unimplemented_rules.length} rule(s) in this rubric have no predicate yet and were not evaluated: ${result.unimplemented_rules.join(', ')}.`));
  }
  if (result.unimplemented_aggregation?.length) {
    notes.push(el('p', 'panel-note',
      `Aggregation the rubric asks for and this evaluator does not apply: ${result.unimplemented_aggregation.join(', ')}.`));
  }
  return notes;
}

/* The two ways out of the debrief. The node and the button that takes focus are returned
 * together, because the caller focuses after the sheet is in the document. */
function revealButtons() {
  const buttons = el('div', 'buttons');
  const next = el('button', 'act', 'Next cue →');
  next.type = 'button';
  next.addEventListener('click', loadDrill);
  buttons.appendChild(next);
  const read = el('button', 'act2', 'Show the procedure');
  read.type = 'button';
  read.addEventListener('click', () => show('library'));
  buttons.appendChild(read);
  return { node: buttons, focusTarget: next };
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
  const tone = BAND_CLASS_TONE[bandSuffix(competency.estimate)] || 'bad';
  const track = el('div', `bar b-${tone}`);
  const fill = el('i');
  fill.style.width = `${Math.round(competency.estimate * 100)}%`;
  track.appendChild(fill);
  cell.appendChild(track);
  /* The INTERVAL rides with the figure, always. The flight plan calls a bare estimate a claim
   * the data cannot support, and the handoff's own Progress table shows one; this keeps both the
   * handoff's bar and the plan's interval. */
  const low = Math.round(competency.interval[0] * 100);
  const high = Math.round(competency.interval[1] * 100);
  cell.appendChild(el('span', `fig f-${tone}`,
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
  /* The group's name, rebuilt with the chips because they are rebuilt from the content's own
   * statuses on every filter change. A fieldset takes its accessible name from its legend. */
  host.appendChild(el('legend', 'offscreen', 'Filter by status'));
  const statuses = ['all', ...new Set(
    state.library.procedures.map((p) => p.status).filter(Boolean).sort((a, b) => a.localeCompare(b)),
  )];
  for (const status of statuses) {
    const chip = el('button', null, status);
    chip.type = 'button';
    chip.setAttribute('aria-pressed', String(state.library.status === status));
    chip.addEventListener('click', () => {
      state.library.status = status;
      renderLibraryChips();
      renderLibraryIndex();
    });
    host.appendChild(chip);
  }
}

/* The most nodes a card's preview strip will draw. A 21-step procedure at full length turns the
 * strip into a hairline of 12px squares nobody can count, so past this it draws the first
 * `PREVIEW_NODES` and says how many are behind them. The stats footer carries the real totals,
 * so nothing is lost and nothing is implied. */
const PREVIEW_NODES = 11;

/* The shape of a procedure, at a glance, before any of its prose. Squares are steps, diamonds
 * are decisions, and the filled cap is closure - the same vocabulary as the flow's own map, so
 * the strip on the card and the map inside the procedure teach each other.
 *
 * The counts come from the INDEX route, which derives them server-side: the interface holds the
 * index and not the documents, so it could only compute these by fetching all thirteen, which is
 * the content-sized body that index exists to avoid. */
function previewStrip(procedure) {
  const strip = el('div', 'strip');
  const steps = Number(procedure.steps) || 0;
  const decisions = Number(procedure.decisions) || 0;
  const total = steps + decisions;
  if (!total) return strip;
  const drawn = Math.min(total, PREVIEW_NODES);
  /* Decisions are spread through the strip rather than bunched at the end, because the strip is
   * about SHAPE - roughly where in the run of work the judgement falls - and the content does
   * not bind a decision to a step, which is the same refusal the flow itself makes. It is a
   * silhouette and not a claim about order, which is why the flow says so in words. */
  const every = decisions ? Math.max(2, Math.round(drawn / (decisions + 1))) : 0;
  /* Counted in a local, and that is not a style preference. The first version asked the strip
   * itself - `strip.querySelectorAll('span').filter(...)` - which works in the test harness and
   * THROWS in a browser: `querySelectorAll` returns a NodeList, which has no `.filter`. The
   * whole library screen rendered as one error banner and all 56 interface tests passed. The
   * harness has been corrected to return a NodeList-like so this class cannot pass again. */
  let gems = 0;
  for (let index = 0; index < drawn; index += 1) {
    if (index) strip.appendChild(el('i', 'link'));
    const isDecision = every > 0 && index > 0 && index % every === 0 && gems < decisions;
    if (isDecision) gems += 1;
    strip.appendChild(el('span', isDecision ? 'gem' : 'box'));
  }
  strip.appendChild(el('i', 'link end'));
  strip.appendChild(el('span', 'cap'));
  if (total > drawn) strip.appendChild(el('span', 'more', `+${total - drawn}`));
  return strip;
}

/* The stats footer: how much work, how much judgement, how many products to open, and whether
 * the procedure hands over. Four figures an operator reads before any prose when choosing
 * between thirteen. Every one is a count the server derived from a list the author wrote. */
function shapeStats(procedure) {
  const row = el('div', 'shape');
  const stat = (value, label, tone) => {
    const cell = el('span', `stat${tone ? ` ${tone}` : ''}`);
    cell.appendChild(el('b', null, String(value)));
    cell.appendChild(el('span', null, label));
    row.appendChild(cell);
  };
  const steps = Number(procedure.steps) || 0;
  stat(steps, steps === 1 ? 'step' : 'steps');
  /* Rendered only where the index actually carries the figure. An older index served `steps`
   * alone, so a zero here would be indistinguishable from a field that is not there, and
   * "0 decisions" is a claim about the procedure rather than about the payload. */
  if (procedure.decisions !== undefined) {
    stat(procedure.decisions, procedure.decisions === 1 ? 'decision' : 'decisions', 'judge');
  }
  if (procedure.stops !== undefined) {
    stat(procedure.stops, procedure.stops === 1 ? 'stop' : 'stops', 'halt');
  }
  if (procedure.onward) {
    const cell = el('span', 'stat onward');
    cell.appendChild(glyph('onward', 13));
    cell.appendChild(el('span', null, `${procedure.onward} onward`));
    row.appendChild(cell);
  }
  return row;
}

/* The index's TABLE columns. Cards answer "what is this procedure"; a table answers "which of
 * the thirteen should I be in", which is a comparison across rows - so every numeric column is
 * sortable and every one is a figure the server derived from the content the author wrote. No
 * column here is decoration, and none is invented: `key` names a field the index route serves.
 *
 * `numeric` drives both the right alignment and the sort comparator, because a right-aligned
 * column that sorts as text is the specific way a table lies about its own numbers: "10" would
 * come before "9". */
const LIBRARY_COLUMNS = [
  { key: 'id', label: 'Procedure', cell: 'pid' },
  { key: 'name', label: 'Name', cell: 'nm' },
  { key: 'status', label: 'Status', cell: 'st' },
  { key: 'regime', label: 'Regime', cell: 'rg' },
  { key: 'steps', label: 'Steps', numeric: true },
  { key: 'decisions', label: 'Decisions', numeric: true, cell: 'judge' },
  { key: 'stops', label: 'Stops', numeric: true, cell: 'halt' },
  { key: 'onward', label: 'Onward', numeric: true },
];

/* What each of the two shaped cells DISPLAYS, in one place, so the cell and the sort cannot
 * disagree. They did, for malformed content: `status` displayed "status unstated" while the
 * comparator saw `''`, and `regime` displayed "regime unreadable, TBC re-verify" while the
 * comparator saw the raw value. Unreachable for shipped data - the index route guarantees a list
 * regime and a non-empty status - so this closes the class rather than an instance. A table that
 * sorts on something other than what it shows is unfalsifiable from the screen. */
function statusText(procedure) {
  return procedure.status || 'status unstated';
}

function statusSettled(procedure) {
  return String(procedure.status || '').toLowerCase() === 'active';
}

function regimeText(procedure) {
  /* A non-array is a RENDERING FAULT rather than something to join, and it says so on screen
   * rather than drawing something plausible - the same refusal the cards make. */
  return Array.isArray(procedure.regime)
    ? procedure.regime.join(' ')
    : 'regime unreadable, TBC re-verify';
}

/* The text a column sorts on, which is the text the cell shows. */
const COLUMN_TEXT = { status: statusText, regime: regimeText };

/* One comparison, so the table cannot sort one way and display another. A numeric column
 * compares as a NUMBER, because a right-aligned column that sorts as text is the specific way a
 * table lies about its own figures: "10" would come before "9". */
function compareProcedures(left, right, column) {
  if (column.numeric) return (Number(left[column.key]) || 0) - (Number(right[column.key]) || 0);
  const shown = COLUMN_TEXT[column.key] || ((row) => String(row[column.key] ?? ''));
  return shown(left).localeCompare(shown(right));
}

/* The procedures the index is currently showing, filtered by status and query. Shared by both
 * views deliberately: the cards and the table showed different sets while this was inline in
 * `renderLibraryCards`, so switching layout silently changed what was on screen. */
function shownProcedures() {
  const query = state.library.query.trim().toLowerCase();
  return state.library.procedures.filter((procedure) => {
    if (state.library.status !== 'all' && procedure.status !== state.library.status) return false;
    if (!query) return true;
    return `${procedure.id} ${procedure.name} ${procedure.purpose || ''}`.toLowerCase().includes(query);
  });
}

function renderLibraryLayoutChips() {
  const host = document.getElementById('library-layouts');
  clear(host);
  const legend = el('legend', 'offscreen', 'Layout');
  host.appendChild(legend);
  for (const layout of ['cards', 'table']) {
    const chip = el('button', null, layout);
    chip.type = 'button';
    /* `aria-pressed`, matching the status chips: a toggle that only changes colour is invisible
     * to a screen reader, and this pair is the one control that changes the whole view. */
    chip.setAttribute('aria-pressed', String(state.library.layout === layout));
    chip.addEventListener('click', () => {
      state.library.layout = layout;
      renderLibraryIndex();
    });
    host.appendChild(chip);
  }
}

function renderLibraryTable() {
  const host = document.getElementById('library-table');
  clear(host);
  const shown = shownProcedures();
  if (!shown.length) {
    /* The same refusal the card grid makes: an empty container reads as a view still loading,
     * and the operator waits for something that is not coming. `role="status"` so it is
     * ANNOUNCED - the card grid's plain paragraph tells a sighted reader and nobody else, which
     * is the one place this view improves on the pattern it copied. */
    const empty = el('p', 'note');
    empty.setAttribute('role', 'status');
    empty.textContent = state.library.query
      ? `No procedure matches \u201c${state.library.query}\u201d.`
      : 'No procedure in this status.';
    host.appendChild(empty);
    return;
  }
  const column = LIBRARY_COLUMNS.find((entry) => entry.key === state.library.sort) || LIBRARY_COLUMNS[0];
  const ordered = [...shown].sort((left, right) => {
    const order = compareProcedures(left, right, column);
    return state.library.ascending ? order : -order;
  });

  const wrap = el('div', 'libtable');
  const table = el('table');
  const head = el('thead');
  const headRow = el('tr');
  for (const entry of LIBRARY_COLUMNS) {
    const th = el('th', entry.numeric ? 'r' : null);
    th.setAttribute('scope', 'col');
    const active = entry.key === state.library.sort;
    /* `aria-sort` only on the sorted column, which is what the attribute means: setting it to
     * "none" on the rest announces eight sortable columns as eight sort states. */
    if (active) th.setAttribute('aria-sort', state.library.ascending ? 'ascending' : 'descending');
    const button = el('button');
    button.type = 'button';
    button.appendChild(el('span', null, entry.label));
    /* A GLYPH for the direction, not colour alone, and only on the column that is sorted. */
    if (active) button.appendChild(el('span', 'caret', state.library.ascending ? '\u25B2' : '\u25BC'));
    /* Lifted out of the attribute call, because a conditional inside a conditional is the
     * readability pattern just swept out of `src/` - and `sonar.sources=src`, so no gate sees
     * `ui/`. The rule is worth holding in both runtimes or in neither. */
    const direction = state.library.ascending ? 'ascending' : 'descending';
    let label = `Sort by ${entry.label}`;
    if (active) label = `${entry.label}, sorted ${direction}. Reverse the order.`;
    button.setAttribute('aria-label', label);
    button.addEventListener('click', () => {
      /* Clicking the sorted column reverses it; clicking another sorts by it. Numeric columns
       * open DESCENDING, because "which has the most steps" is the question a reader clicking
       * a count column is asking, and ascending would answer the opposite one first. */
      if (active) state.library.ascending = !state.library.ascending;
      else {
        state.library.sort = entry.key;
        state.library.ascending = !entry.numeric;
      }
      renderLibraryTable();
    });
    th.appendChild(button);
    headRow.appendChild(th);
  }
  head.appendChild(headRow);
  table.appendChild(head);

  const body = el('tbody');
  for (const procedure of ordered) {
    /* **A row stays a ROW.** It carried `role="button"`, `tabindex="0"` and an `aria-label`,
     * and every part of that was wrong in a way no test here could see. `tr` permits only
     * `role=row` in ARIA in HTML; a `tbody` with a non-row child leaves the eight `td` cells
     * without the ancestor their `cell` role requires, so table navigation stops reaching
     * them; and a button's accessible name comes from `aria-label`, which REPLACES its
     * contents - so the row announced as "Open Manoeuvre, button" and the steps, decisions,
     * stops and onward figures were not exposed at all. This view exists for cross-row
     * comparison of exactly those numbers, so for a screen-reader user it carried none of the
     * thing it is for.
     *
     * The control is a real `button` in the Procedure cell, which is what the card grid
     * already does. The row keeps a click handler as a mouse convenience and nothing else: no
     * role, no tabindex, no label. A focusable element with no role is its own small lie, and
     * the button is the keyboard and assistive-technology path. */
    const row = el('tr');
    const open = () => openProcedure(procedure.id);
    for (const entry of LIBRARY_COLUMNS) {
      const classes = [entry.numeric ? 'r' : '', entry.cell || ''].filter(Boolean).join(' ');
      const cell = el('td', classes || null);
      if (entry.key === 'id') {
        const control = el('button', 'open');
        control.type = 'button';
        control.textContent = cellText(procedure.id);
        /* **The accessible name must CONTAIN the visible text** - WCAG 2.5.3 Label in Name,
         * Level A - and this read `Open ${procedure.name}` alone, so the visible "PROC-MNV" was
         * nowhere in "Open Manoeuvre detection and characterisation" for any of the thirteen
         * rows. `aria-label` wins the name computation, so a speech-input user reading the
         * screen and saying "click PROC-MNV" did not reach the control.
         *
         * The comment that stood here claimed the opposite, and the test asserted the id as the
         * visible text and the NAME in the label - locking the violation in as correct. The
         * header buttons ten lines up had it right all along: "Sort by Steps" contains "Steps". */
        const naming = procedure.name ? `, ${procedure.name}` : '';
        control.setAttribute('aria-label', `Open ${cellText(procedure.id)}${naming}`);
        /* **Stopped here, or one click opens the procedure twice.** The row below carries its
         * own click handler so the whole row is clickable, and without this the event bubbles
         * into it: two fetches, two rendered documents, and two rate-limit tokens for one
         * activation. The row handler is kept because a clickable row is worth having in a
         * table; what it cannot do is run in addition to the control inside it. */
        control.addEventListener('click', (event) => {
          if (event.stopPropagation) event.stopPropagation();
          open();
        });
        cell.appendChild(control);
      } else if (entry.key === 'status') {
        /* Status is a dot AND a word here too, never colour alone. */
        cell.appendChild(el('i', statusSettled(procedure) ? 'dot on' : 'dot off'));
        cell.appendChild(el('span', null, statusText(procedure)));
      } else if (entry.key === 'regime') {
        cell.textContent = regimeText(procedure);
      } else {
        cell.textContent = cellText(procedure[entry.key]);
      }
      row.appendChild(cell);
    }
    row.addEventListener('click', open);
    body.appendChild(row);
  }
  table.appendChild(body);

  const foot = el('tfoot');
  const footRow = el('tr');
  const footCell = el('td');
  footCell.setAttribute('colspan', String(LIBRARY_COLUMNS.length));
  /* The totals of the rows ACTUALLY SHOWN, not of the library, so a filtered table does not
   * report figures for procedures that are not on it. */
  const sum = (key) => ordered.reduce((total, row) => total + (Number(row[key]) || 0), 0);
  footCell.textContent = [
    `${ordered.length} of ${state.library.procedures.length} procedures`,
    `${sum('steps')} steps`,
    `${sum('decisions')} decisions`,
    `${sum('stops')} stops`,
    `${sum('onward')} onward links`,
  ].join(' \u00b7 ');
  footRow.appendChild(footCell);
  foot.appendChild(footRow);
  table.appendChild(foot);

  wrap.appendChild(table);
  host.appendChild(wrap);
}

/* The index in whichever layout is selected. One entry point, so the chips, the search box and
 * the status filter all repaint the same way and neither view can be left stale under the other. */
function renderLibraryIndex() {
  const cards = document.getElementById('library-grid');
  const table = document.getElementById('library-table');
  const asTable = state.library.layout === 'table';
  /* `hidden`, not a class: the view that is not showing must be gone from assistive technology
   * too, or a screen reader walks thirteen cards and then thirteen rows of the same thing. */
  cards.hidden = asTable;
  table.hidden = !asTable;
  renderLibraryLayoutChips();
  if (asTable) {
    clear(cards);
    renderLibraryTable();
  } else {
    clear(table);
    renderLibraryCards();
  }
}

function renderLibraryCards() {
  const grid = document.getElementById('library-grid');
  clear(grid);
  /* The SHARED filter. This was inline here, and the table's copy drifted from it the moment
   * either changed: switching layout would then silently change what was on screen. The local
   * `query` that stood beside it is gone. The engineering gate reported it as dead once the
   * filter moved; it was not - the empty state below still read it - and deleting it broke the
   * card grid's "No procedure matches" message. Caught immediately by a test, which is the
   * useful half: the empty state reads `state.library.query` directly now, matching the
   * table's version, so there is one source for it rather than a local that shadows it. */
  const shown = shownProcedures();
  for (const procedure of shown) {
    /* A BUTTON, not a div with a click handler: it is keyboard reachable and announces itself. */
    const card = el('button', 'proc');
    card.type = 'button';
    const top = el('div', 'top');
    top.appendChild(el('span', 'pid', procedure.id));
    /* Status as a dot AND a word. The dot is the quick scan across thirteen cards and the word
     * is what carries when the dot cannot: the same rule the flow's markers hold. */
    const mast = el('span', 'mast');
    const settled = String(procedure.status || '').toLowerCase() === 'active';
    mast.appendChild(el('i', settled ? 'dot on' : 'dot off'));
    mast.appendChild(el('span', null, procedure.status || 'status unstated'));
    top.appendChild(mast);
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
    card.appendChild(previewStrip(procedure));
    card.appendChild(shapeStats(procedure));
    card.appendChild(tags);
    card.addEventListener('click', () => openProcedure(procedure.id));
    grid.appendChild(card);
  }
  if (!shown.length) {
    const empty = el('button', 'proc empty');
    empty.type = 'button';
    empty.disabled = true;
    empty.appendChild(el('span', 'pid', 'nothing matches'));
    empty.appendChild(el('h3', null, state.library.query
      ? `No procedure matches \u201c${state.library.query}\u201d`
      : 'No procedure in this status'));
    empty.appendChild(el('p', null, 'Clear the search or pick another status.'));
    grid.appendChild(empty);
  }
}

/* ---------------------------------------------------------------- the procedure flow
 * The Library, redesigned at V0.28.0. What stood here rendered `Object.entries(procedure)` and
 * `JSON.stringify(value, null, 1)`, so a 21-step procedure arrived as one wall of text with the
 * exclusions and the reporting rules at the bottom - the paragraph an operator most needs first,
 * placed where they would reach it last.
 *
 * Everything below renders as TEXT through `el`, never as markup: every value is authored content
 * and `test_the_interface_never_writes_an_untrusted_value_as_markup` binds that. The only markup
 * this code constructs is the glyph geometry, which is a constant in this file. */

/* The seven markers. Each is a GLYPH, a WORD and a COLOUR, in that order of authority: nothing
 * in this library means anything by colour alone, so a monochrome print and a screen read
 * identically. `test_every_marker_carries_a_word_and_a_glyph` binds it. */
const GLYPHS = {
  /* An octagon with a bang. Stop and read the named product before going on. */
  stop: ['M7 2.2h6L17.8 7v6L13 17.8H7L2.2 13V7z', 'M10 6.4v4.2'],
  /* A triangle with a bang. The mistake people actually make here, named. */
  error: ['M10 2.6 18.4 17H1.6z', 'M10 7.6v4'],
  /* A bar chart with no numbers on it: the content carries the threshold's NAME, never its value. */
  threshold: ['M2.5 13h15', 'M6 13V8.5M10 13V5.5M14 13v-6'],
  /* A circle with a bang. The reason the step exists, and the quietest marker by design. */
  why: ['M10 9.2v4.4'],
  /* A clock hand. The time standard the step is worked to. */
  time: ['M10 5.6v4.8l3.2 2'],
  /* An arrow. Onward, and the only marker that draws an edge between procedures. */
  onward: ['M3 10h11', 'M10 6l4 4-4 4'],
  /* A cross. Not this procedure - open the one it names instead. */
  exclude: ['M5 5l10 10M15 5L5 15'],
  /* A diamond. The judgement the operator has to make and own. */
  decision: ['M10 2.4 17.6 10 10 17.6 2.4 10z'],
  /* A tick. Closure. */
  close: ['M4 10.5 L8 14.5 L16 5.5'],
  /* A downward arrow: what follows from a branch. */
  then: ['M10 3v11', 'M5.5 9.5 10 14l4.5-4.5'],
};

/* Markers whose glyph carries a filled dot for the bang. Drawn as a circle rather than a short
 * stroke so it reads as a full stop at 18px, which a 1px line does not. */
const DOTTED = { stop: [10, 13.6], error: [10, 14.4], why: [10, 6.4] };

/* A marker's glyph at a given size and stroke colour. `currentColor` is deliberate: the stroke
 * follows the marker's own text colour from the stylesheet, so the two cannot drift apart. */
function glyph(name, size) {
  const node = svg('svg', {
    width: size, height: size, viewBox: '0 0 20 20', fill: 'none',
    stroke: 'currentColor', 'stroke-width': 1.8,
    'stroke-linecap': 'round', 'stroke-linejoin': 'round',
    'aria-hidden': 'true', focusable: 'false',
  });
  if (name === 'why') node.appendChild(svg('circle', { cx: 10, cy: 10, r: 7.6 }));
  if (name === 'time') node.appendChild(svg('circle', { cx: 10, cy: 10, r: 7.6 }));
  for (const d of GLYPHS[name] || []) node.appendChild(svg('path', { d }));
  const dot = DOTTED[name];
  if (dot) {
    node.appendChild(svg('circle', { cx: dot[0], cy: dot[1], r: 0.9, fill: 'currentColor', stroke: 'none' }));
  }
  return node;
}

/* One marker row: glyph, word, then whatever the marker carries. `body` may be a paragraph of
 * authored prose, a monospaced reference, or a row of product chips - the three shapes the
 * content actually has. */
function marker(kind, word, build) {
  const row = el('div', `mk mk-${kind}`);
  row.appendChild(glyph(kind, 18));
  const hold = el('div', null);
  hold.appendChild(el('div', 'word', word));
  if (build) build(hold);
  row.appendChild(hold);
  return row;
}

/* The products a step names. A STOP, because the step cannot be completed from its text alone:
 * it names a plot or a table the operator has to actually look at. */
function stopMarker(products) {
  return marker('stop', 'Stop — read the product before you go on', (hold) => {
    const chips = el('div', 'products');
    for (const product of products) chips.appendChild(el('span', null, product));
    hold.appendChild(chips);
  });
}

/* One step of the procedure, as a card on the spine. Every marker the step carries appears
 * BESIDE the action rather than in a footnote nobody reaches. */
function actionCard(step) {
  const card = el('div', 'stepcard');
  const doing = el('div', 'doing');
  const who = el('div', 'who');
  if (step.role) who.appendChild(el('span', 'rolechip', step.role));
  who.appendChild(el('span', 'lab', 'acts'));
  doing.appendChild(who);
  doing.appendChild(el('p', 'action', step.action || ''));
  card.appendChild(doing);
  if (step.products && step.products.length) card.appendChild(stopMarker(step.products));
  if (step.threshold_ref) {
    card.appendChild(marker('threshold', 'Threshold', (hold) => {
      /* The NAME, not the value: the operational figures live in a file that does not ship, so
       * the marker names what to look up and does not invent a number to fill the space. */
      hold.appendChild(el('span', 'ref', step.threshold_ref));
    }));
  }
  if (step.time_standard) {
    card.appendChild(marker('time', 'Time standard', (hold) => {
      hold.appendChild(el('span', 'ref', step.time_standard));
    }));
  }
  if (step.common_error) {
    card.appendChild(marker('error', 'Common error', (hold) => {
      hold.appendChild(el('p', null, step.common_error));
    }));
  }
  if (step.why) {
    card.appendChild(marker('why', 'Why', (hold) => hold.appendChild(el('p', null, step.why))));
  }
  return card;
}

/* One rung of the flow: the rail with its numbered node and the spine, then the body beside it. */
function leg(rung, body, rungClass) {
  const row = el('div', 'leg');
  const rail = el('div', 'spinecol');
  const node = el('div', `rung ${rungClass || ''}`.trim());
  if (rungClass && rungClass.includes('gem')) node.appendChild(el('i', null));
  else node.textContent = String(rung);
  rail.appendChild(node);
  rail.appendChild(el('div', 'spine'));
  row.appendChild(rail);
  const hold = el('div', 'body');
  hold.appendChild(body);
  row.appendChild(hold);
  return row;
}

/* One decision. The only marker that is not an instruction: a judgement the operator makes and
 * owns, so it carries the question, every condition, and what follows from each. */
function decisionCard(point, onJump) {
  const card = el('div', 'dec');
  /* `askhead`, not `ask`: a bare `.ask` rule already exists in the stylesheet and the decision
   * header was inheriting its margin and letter-spacing. Two collisions in one release is why
   * the new classes are now checked against the old stylesheet rather than assumed distinct. */
  const ask = el('div', 'askhead');
  const top = el('div', 'asktop');
  top.appendChild(glyph('decision', 15));
  top.appendChild(el('span', 'word', point.id ? `Decision · ${point.id}` : 'Decision'));
  top.appendChild(el('span', 'rubric', 'stop · think · then choose'));
  ask.appendChild(top);
  ask.appendChild(el('p', 'question', point.question || ''));
  card.appendChild(ask);
  const branches = el('div', 'branches');
  for (const branch of point.branches || []) {
    const arm = el('div', 'branch');
    arm.appendChild(el('div', 'iff', 'If'));
    arm.appendChild(el('p', 'cond', branch.condition || ''));
    const thenRow = el('div', 'thenrow');
    thenRow.appendChild(glyph('then', 14));
    thenRow.appendChild(el('span', 'word', 'Then'));
    arm.appendChild(thenRow);
    arm.appendChild(el('p', 'then', branch.then || ''));
    if (branch.goto_procedure) {
      /* The content NAMES the procedure it hands over to, so this navigates there rather than
       * describing it. The thirteen procedures form a graph, not a list. */
      const jump = el('button', 'goto');
      jump.type = 'button';
      jump.appendChild(glyph('onward', 15));
      jump.appendChild(el('span', 'lead', 'Go to'));
      jump.appendChild(el('span', 'target', branch.goto_procedure));
      const named = onJump.name(branch.goto_procedure);
      if (named) jump.appendChild(el('span', 'naming', named));
      jump.addEventListener('click', () => onJump.open(branch.goto_procedure));
      arm.appendChild(jump);
    }
    branches.appendChild(arm);
  }
  card.appendChild(branches);
  return card;
}

/* How many steps a procedure may carry before its middle folds. Six, so the eight-step case the
 * design was drawn against folds to first two, rail, last one - and the thirteen procedures that
 * are shorter than this open whole. Launch carries 21 steps and is the reason the fold exists at
 * all: a flow nobody scrolls to the end of is a flow nobody reads. */
const FOLD_ABOVE_STEPS = 6;
const LEAD_STEPS = 2;
const TAIL_STEPS = 1;

/* The schematic map: the whole procedure on one line, before any of it is read in detail. Each
 * step is a pip, and a pip carries a dot for each marker class on that step, so the shape of the
 * work is visible at a glance - where the stops cluster, where the judgement sits. */
function procedureMap(procedure) {
  const steps = procedure.steps || [];
  const decisions = procedure.decision_points || [];
  const stops = steps.filter((step) => step.products && step.products.length).length;
  const jumps = decisions.reduce(
    (total, point) => total + (point.branches || []).filter((b) => b.goto_procedure).length, 0,
  );
  const wrap = el('div', 'procmap');
  const head = el('div', 'maphead');
  head.appendChild(el('span', 'lab', 'The whole procedure'));
  head.appendChild(el('span', 'tally', [
    `${steps.length} ${steps.length === 1 ? 'step' : 'steps'}`,
    `${decisions.length} ${decisions.length === 1 ? 'decision' : 'decisions'}`,
    `${stops} ${stops === 1 ? 'stop' : 'stops'}`,
    `${jumps} ${jumps === 1 ? 'onward link' : 'onward links'}`,
  ].join(' · ')));
  wrap.appendChild(head);

  const track = el('div', 'maptrack');
  const cap = (name, word) => {
    const node = el('div', 'mapnode');
    const pip = el('div', 'pip');
    pip.appendChild(glyph(name, 15));
    node.appendChild(pip);
    node.appendChild(el('div', 'flags'));
    node.appendChild(el('span', 'caption', word));
    return node;
  };
  track.appendChild(cap('onward', 'Enter'));
  track.appendChild(el('div', 'maplink'));
  steps.forEach((step, index) => {
    const node = el('div', 'mapnode');
    node.appendChild(el('div', `pip square${index < LEAD_STEPS ? '' : ' plain'}`, String(step.n ?? index + 1)));
    const flags = el('div', 'flags');
    /* One dot per marker class present, in the marker sheet's own order. A pip with three dots
     * is a step that cannot be done from its text: read the product, mind the figure, avoid the
     * error. Colour repeats the marker's colour and the dot count carries it without colour. */
    if (step.products && step.products.length) flags.appendChild(el('i', 'f-stop'));
    if (step.threshold_ref) flags.appendChild(el('i', 'f-threshold'));
    if (step.common_error) flags.appendChild(el('i', 'f-error'));
    node.appendChild(flags);
    node.appendChild(el('span', 'caption', step.role || ''));
    track.appendChild(node);
    if (index < steps.length - 1) track.appendChild(el('div', 'maplink'));
  });
  if (decisions.length) {
    track.appendChild(el('div', 'maplink'));
    decisions.forEach((point, index) => {
      const node = el('div', 'mapnode');
      const pip = el('div', 'pip diamond');
      pip.appendChild(el('i', null));
      node.appendChild(pip);
      node.appendChild(el('div', 'flags'));
      node.appendChild(el('span', 'caption', point.id || `D${index + 1}`));
      track.appendChild(node);
      if (index < decisions.length - 1) track.appendChild(el('div', 'maplink'));
    });
  }
  track.appendChild(el('div', 'maplink'));
  track.appendChild(cap('close', 'Close'));
  wrap.appendChild(track);
  return wrap;
}

/* A list gate: the heading states ANY or ALL, because the difference is the whole meaning and
 * leaving it to be inferred from a bullet is how the exclusions got ignored. */
function gate(kind, glyphName, heading, items) {
  const box = el('div', `gate ${kind}`);
  const head = el('div', 'gatehead');
  head.appendChild(glyph(glyphName, 15));
  head.appendChild(el('span', null, heading));
  box.appendChild(head);
  const list = el('ul', null);
  for (const item of items) list.appendChild(el('li', null, item));
  box.appendChild(list);
  return box;
}

/* The reporting block, which is an OBJECT and not a list. `[].concat(reporting)` wrapped the
 * whole dict in an array and rendered it as `[object Object]` - a field name in operator-facing
 * prose, which is the exact fault this redesign exists to remove, reintroduced by me while
 * removing it. Caught by asserting on the rendered text rather than by looking at a screen.
 *
 * All thirteen procedures carry the same six keys: `notso_required`, `time_standard`,
 * `must_state` (a list), `verbal_required` (a boolean), and `escalation` and `condition` on ten
 * and six of them. Read by NAME, so a key the content adds shows up as absent here rather than
 * as a stringified object on the page. */
function reportingCap(reporting) {
  const box = el('div', 'endcap report');
  const head = el('div', 'gatehead');
  head.appendChild(glyph('time', 15));
  head.appendChild(el('span', null, 'Reporting'));
  box.appendChild(head);

  const facts = el('div', 'reportfacts');
  const fact = (label, value) => {
    const row = el('div', 'fact');
    row.appendChild(el('span', 'lab', label));
    row.appendChild(el('span', 'val', value));
    facts.appendChild(row);
  };
  if (reporting.notso_required) fact('NOTSO', reporting.notso_required);
  if (reporting.time_standard) fact('Time standard', reporting.time_standard);
  /* A BOOLEAN rendered as a word. `verbal_required: false` printed nothing at all under a
   * truthiness test, so "no verbal report needed" and "the content is silent" looked identical -
   * and they are different instructions. */
  if (typeof reporting.verbal_required === 'boolean') {
    fact('Verbal', reporting.verbal_required ? 'required' : 'not required');
  }
  if (facts.children.length) box.appendChild(facts);

  if (reporting.condition) {
    box.appendChild(marker('threshold', 'Report when', (hold) => {
      hold.appendChild(el('p', null, reporting.condition));
    }));
  }
  if (reporting.escalation) {
    box.appendChild(marker('error', 'Escalate when', (hold) => {
      hold.appendChild(el('p', null, reporting.escalation));
    }));
  }
  const must = [].concat(reporting.must_state || []);
  if (must.length) {
    box.appendChild(el('div', 'gatehead sub', 'The report must state'));
    const list = el('ul', null);
    for (const item of must) list.appendChild(el('li', null, item));
    box.appendChild(list);
  }
  return box;
}

function endcap(kind, glyphName, heading, items) {
  const box = el('div', `endcap ${kind}`);
  const head = el('div', 'gatehead');
  head.appendChild(glyph(glyphName, 15));
  head.appendChild(el('span', null, heading));
  box.appendChild(head);
  const list = el('ul', null);
  for (const item of items) list.appendChild(el('li', null, item));
  box.appendChild(list);
  return box;
}

/* The header: what this procedure is for, its status, and the regimes it applies in. */
function procedureHeader(procedure) {
  const head = el('div', 'prochead');
  const lead = el('div', null);
  lead.appendChild(el('div', 'lab', `Procedure · ${procedure.id || ''}`));
  lead.appendChild(el('h2', null, procedure.name || procedure.id || ''));
  if (procedure.purpose) lead.appendChild(el('p', 'purpose', procedure.purpose));
  head.appendChild(lead);
  const aside = el('div', 'aside');
  if (procedure.status) {
    /* `provisional` gets the warn tone rather than the good one, because a procedure that is not
     * settled is a fact the operator needs before they work to it, not after. */
    const provisional = String(procedure.status).toLowerCase() !== 'active';
    const pill = el('span', `statuspill${provisional ? ' provisional' : ''}`);
    pill.appendChild(glyph(provisional ? 'error' : 'close', 13));
    pill.appendChild(el('span', null, procedure.status));
    aside.appendChild(pill);
  }
  const regimes = [].concat(procedure.regime || []);
  if (regimes.length) {
    const row = el('div', 'regimes');
    for (const regime of regimes) row.appendChild(el('span', null, regime));
    aside.appendChild(row);
  }
  if (procedure.status_note) aside.appendChild(el('span', 'lab', procedure.status_note));
  head.appendChild(aside);
  return head;
}

/* The steps, with the middle folded when there are more than `FOLD_ABOVE_STEPS`. Folded, never
 * hidden: the rail names how many are behind it, lists what they cover, and opens on a click. */
function flowLegs(host, steps, expanded) {
  const folding = steps.length > FOLD_ABOVE_STEPS && !expanded;
  const shown = folding ? steps.slice(0, LEAD_STEPS) : steps;
  for (const step of shown) {
    const index = steps.indexOf(step);
    host.appendChild(leg(step.n ?? index + 1, actionCard(step), index < LEAD_STEPS ? 'lead' : ''));
  }
  if (!folding) return;
  const middle = steps.slice(LEAD_STEPS, steps.length - TAIL_STEPS);
  const rail = el('button', 'fold');
  rail.type = 'button';
  rail.appendChild(el('span', 'count', `${middle.length} steps folded`));
  /* Named rather than counted alone. "Five steps folded" tells an operator nothing about whether
   * the part they need is inside; the actions do. */
  rail.appendChild(el('span', 'gist', middle.map((step) => firstClause(step.action)).join(' · ')));
  rail.appendChild(el('span', 'open', 'Open all'));
  rail.addEventListener('click', () => {
    const flow = host;
    clear(flow);
    flowLegs(flow, steps, true);
  });
  /* Both ends fall back to a NUMBER, and the first version fell back to `''` at the end, so an
   * unnumbered final middle step would have rendered "3-". No shipped content reaches it - `n`
   * is a contiguous integer on every step of all thirteen procedures - but an asymmetric
   * fallback is a latent difference between the two ends of one label.
   *
   * A plain hyphen, not an en dash: a numeric range is conventional typography either way, and
   * the house rule is easier to hold with one dash character in the interface than with two. */
  const opens = middle[0]?.n ?? LEAD_STEPS + 1;
  const closes = steps[steps.length - TAIL_STEPS - 1]?.n ?? steps.length - TAIL_STEPS;
  host.appendChild(leg(`${opens}-${closes}`, rail, 'folded'));
  for (const step of steps.slice(steps.length - TAIL_STEPS)) {
    host.appendChild(leg(step.n ?? steps.indexOf(step) + 1, actionCard(step), ''));
  }
}

/* The first clause of an action, for the folded rail. Cut at the first sentence end rather than
 * at a character count, so the summary is a phrase the author wrote and not a truncation. */
function firstClause(action) {
  const text = String(action || '').trim();
  const stop = text.search(/[.;]/);
  const clause = stop > 0 ? text.slice(0, stop) : text;
  return clause.length > 58 ? `${clause.slice(0, 57)}…` : clause;
}

/* One procedure, in full, fetched on demand from the route that serves the document. */
async function openProcedure(procedureId) {
  const host = document.getElementById('library-body');
  clear(host);
  try {
    /* **The index is HIDDEN while a procedure is open**, because the library is two screens and
     * not one stacked page. The first draft appended the flow below the grid, so opening a
     * procedure put 5,900 pixels of it under thirteen cards and an operator had to scroll past
     * the whole library to reach the step they came for. Every test passed; the page said
     * otherwise. Hidden with `hidden` rather than a class, so it is hidden from assistive
     * technology too and not merely painted away. */
    document.getElementById('library-index').hidden = true;
    const served = await api(`/api/v1/content/procedure/${encodeURIComponent(procedureId)}`);
    const procedure = served.procedure;
    const jumps = {
      open: openProcedure,
      name: (id) => (state.library.procedures.find((entry) => entry.id === id) || {}).name || '',
    };
    host.appendChild(procedureHeader(procedure));
    host.appendChild(procedureMap(procedure));

    const gates = el('div', 'gates');
    const entry = [].concat(procedure.entry_conditions || []);
    if (entry.length) {
      gates.appendChild(gate('enter', 'onward', 'Enter when any of these', entry));
    }
    const exclusions = [].concat(procedure.not_this_procedure_when || []);
    if (exclusions.length) {
      /* **The exclusions are at the TOP.** They are the most useful paragraph on the page and
       * the text dump had them last, under the reporting rules, where nobody reached them. */
      gates.appendChild(gate('exclude', 'exclude', 'Not this procedure when', exclusions));
    }
    if (gates.childElementCount) host.appendChild(gates);

    const steps = [].concat(procedure.steps || []);
    if (steps.length) {
      const head = el('div', 'flowhead');
      head.appendChild(el('h3', null, 'The flow'));
      head.appendChild(el('span', 'tally', `${steps.length} ${steps.length === 1 ? 'step' : 'steps'} · roles as authored`));
      host.appendChild(head);
      const flow = el('div', 'flow');
      flowLegs(flow, steps, false);
      host.appendChild(flow);
    }

    const decisions = [].concat(procedure.decision_points || []);
    if (decisions.length) {
      const head = el('div', 'flowhead');
      head.appendChild(el('h3', null, 'The decisions'));
      /* **The one refusal in this design, stated on the page rather than hidden.** The content
       * orders decision points but does not bind them to a step number, so a diamond placed
       * between step 6 and step 7 would be inventing a sequence the authors did not write. */
      head.appendChild(el('span', 'tally', 'on their own track: the content does not bind them to a step'));
      host.appendChild(head);
      const track = el('div', 'flow');
      decisions.forEach((point, index) => {
        track.appendChild(leg(index + 1, decisionCard(point, jumps), 'gem'));
      });
      host.appendChild(track);
    }

    const reporting = procedure.reporting;
    if (reporting && typeof reporting === 'object') host.appendChild(reportingCap(reporting));
    const closure = [].concat(procedure.closure_criteria || []);
    if (closure.length) {
      host.appendChild(endcap('close', 'close', 'Close when all of these', closure));
    }

    const covers = [].concat(procedure.competency_ids || []).concat(procedure.sparta_ids || []);
    if (covers.length) {
      const note = el('div', 'procnote');
      note.appendChild(el('div', 'lab', 'Trains'));
      note.appendChild(el('p', null, covers.join(' · ')));
      host.appendChild(note);
    }

    const back = el('div', 'backrow');
    const button = el('button', 'act ghost');
    button.type = 'button';
    button.textContent = 'Back to the library';
    button.addEventListener('click', () => {
      clear(host);
      document.getElementById('library-index').hidden = false;
      /* Back to whichever layout they left, not always the cards: switching to the table,
       * opening a procedure and returning to a card grid loses the view they chose. */
      renderLibraryIndex();
    });
    back.appendChild(button);
    host.appendChild(back);
    host.scrollIntoView({ block: 'nearest' });
  } catch (error) {
    banner(error.message);
  }
}

async function loadLibrary() {
  clear(document.getElementById('library-body'));
  /* Re-entering the view always shows the index. Without this, opening a procedure and then
   * navigating away and back left the library blank: the flow was cleared and the index was
   * still hidden, so the view had nothing in it at all. */
  document.getElementById('library-index').hidden = false;
  try {
    const index = await api('/api/v1/content/procedures');
    state.library.procedures = index.procedures;
    const search = document.getElementById('library-search');
    if (!search.dataset.wired) {
      search.addEventListener('input', () => {
        state.library.query = search.value;
        renderLibraryIndex();
      });
      search.dataset.wired = 'yes';
    }
    renderLibraryChips();
    renderLibraryIndex();
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

/* A band's tone, in the two vocabularies that need it. Four-deep ternary chains stood here
 * three times over, and two of them disagreed: the CSS CLASS for the middle band is `shaky`
 * while the CSS VARIABLE is `--warn`. Two maps make that difference visible rather than burying
 * it in the third arm of a chain nobody reads to the end. `|| 'bad'` keeps the chains' own
 * fallback, so an unrecognised band still paints. */
const BAND_CLASS_TONE = { strong: 'good', accent: 'accent', shaky: 'shaky', missed: 'bad' };
const BAND_VARIABLE = { strong: 'good', accent: 'accent', shaky: 'warn', missed: 'bad' };

function bandSuffix(estimate) {
  return band(estimate).cls.replace('s-', '');
}

function band(estimate) {
  return BANDS.find((entry) => estimate >= entry.floor) || BANDS.at(-1);
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
    const weak = weakest(me.competencies);
    paintSessionHeader(me, weak);
    paintRunCard(me);
    paintWeakestCard(weak);
    paintRecordedCard(me);
    paintCovers(me.competencies);
    document.getElementById('session-note').textContent = me.identity;
  } catch (error) {
    /* The caught error was discarded and a fixed sentence shown in its place, which is the one
     * handler in this file that told the operator less than it knew. Every other catch here
     * surfaces `error.message`, and that message is already the server's sanitised `detail`
     * rather than an internal one. The framing is kept because "the session" names what failed. */
    banner(`The session could not be loaded. ${error.message}`);
  }
}

/* The kicker, the title and the standfirst.
 *
 * No session NUMBER exists in the API and the mockup's is synthetic, so the kicker carries the
 * content hash instead: it is the one provenance string that makes a run reproducible, which is
 * what a session id would have been for. */
function paintSessionHeader(me, weak) {
  document.getElementById('session-kicker').textContent =
    `Session · content ${me.content_hash.slice(0, 8)}`;
  document.getElementById('session-title').textContent = weak
    ? `Today you are drilling ${weak.name.toLowerCase()}`
    : 'Today you are drilling from a clean sheet';
  document.getElementById('session-sub').textContent = weak
    ? 'The run leads with your weakest measured axis. Cues you have missed come back sooner and harder.'
    : 'Nothing is measured yet, so the first run establishes a baseline rather than correcting one.';
}

/* `due_now` is a real count. The mockup's run length in minutes is not derivable from this
 * payload, so it is omitted rather than guessed. */
function paintRunCard(me) {
  document.getElementById('run-count').textContent = String(me.due_now);
  document.getElementById('run-length').textContent =
    me.due_now === 1 ? 'cue due now' : 'cues due now';
  document.getElementById('run-blurb').textContent =
    'Spaced repetition decides the order. An item you got right moves further out; one you'
    + ' missed comes back inside a day.';
}

/* The weakest axis, or the honest absence of one. */
function paintWeakestCard(weak) {
  if (!weak) {
    document.getElementById('weak-name').textContent = 'Not measured yet';
    document.getElementById('weak-body').textContent =
      'No axis has an attempt against it, so there is no weakest. A figure here before the'
      + ' first call would be a claim the data cannot support.';
    return;
  }
  document.getElementById('weak-name').textContent = weak.name;
  const low = Math.round(weak.interval[0] * 100);
  const high = Math.round(weak.interval[1] * 100);
  document.getElementById('weak-body').textContent =
    `Estimated ${Math.round(weak.estimate * 100)} out of 100, interval ${low} to ${high},`
    + ` over ${weak.attempts} ${weak.attempts === 1 ? 'call' : 'calls'}.`;
  const bar = document.getElementById('weak-bar');
  bar.style.width = `${Math.round(weak.estimate * 100)}%`;
  bar.style.background = `var(--${BAND_VARIABLE[bandSuffix(weak.estimate)] || 'bad'})`;
}

/* What has actually been recorded, and what the mockup shows that this payload cannot support. */
function paintRecordedCard(me) {
  document.getElementById('recorded-n').textContent = String(me.runs_total);
  document.getElementById('recorded-body').textContent =
    `${me.runs_total} ${me.runs_total === 1 ? 'answer' : 'answers'} recorded, drill rating`
    + ` ${me.drill_rating}. The fourteen-day activity strip the mockup shows needs per-day`
    + ' history the dashboard does not expose yet, so it is left out rather than drawn from'
    + ' nothing.';
}

function paintCovers(competencies) {
  const covers = document.getElementById('covers');
  clear(covers);
  competencies.forEach((competency, index) => {
    covers.appendChild(competencyRow(competency, index));
  });
}

/* One competency row. The status carries the band WORD beside the figure, because the flight
 * plan forbids status by colour alone, and reads "not measured" rather than a zero. */
function competencyRow(competency, index) {
  const row = el('div', 'row');
  row.appendChild(el('span', 'idx', String(index + 1).padStart(2, '0')));
  row.appendChild(el('span', 'name', competency.name || competency.competency_id));
  row.appendChild(el('span', 'cues',
    `${competency.attempts} ${competency.attempts === 1 ? 'call' : 'calls'}`));
  if (!competency.measured) {
    row.appendChild(el('span', 'status', 'not measured'));
    return row;
  }
  const entry = band(competency.estimate);
  row.appendChild(el('span', `status ${entry.cls}`,
    `${entry.word} · ${Math.round(competency.estimate * 100)}`));
  return row;
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
