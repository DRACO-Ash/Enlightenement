/*
 * ENLIGHTENMENT operator interface. No framework, no build step, no external request.
 *
 * Three rules this file holds, each from the flight plan:
 *
 * 1. EVERY untrusted value is written with textContent, never innerHTML. Content is authored by a
 *    human and served as JSON, and "authored by us" is not a reason to skip escaping: the content
 *    tree is edited without a code deployment, so an authoring mistake would otherwise become a
 *    scripting bug. No markup-parsing sink is used anywhere in this file, and a test asserts
 *    their absence by name - including the two dynamic-code sinks, which would defeat the strict
 *    script-src by another route.
 * 2. The answer key is never requested before an answer is committed. The drill payload has no
 *    answer field; the reveal arrives as the response to the POST.
 * 3. Status is never colour alone. Every verdict sets a shape glyph and a text label as well as a
 *    class.
 */
'use strict';

const state = {
  drill: null,
  answered: false,
  procedures: [],
  confidenceSteps: {},
};

const $ = (id) => document.getElementById(id);

function announce(message) {
  // One live region, updated deliberately and sparingly: the accessibility standard here warns
  // against a chatty live region, and a drill that narrated every keystroke would be unusable.
  $('live').textContent = message;
}

async function api(path, options) {
  const response = await fetch(path, {
    ...options,
    headers: { 'content-type': 'application/json', ...(options && options.headers) },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && body.detail;
    const message =
      (detail && (detail.message || detail.error)) ||
      (body && body.error) ||
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }
  return body;
}

/* ------------------------------------------------------------------ plotting */

/*
 * Drawn from scratch on a canvas. The palette constants are duplicated from the stylesheet on
 * purpose: a canvas cannot read a CSS custom property without a getComputedStyle round trip per
 * frame, and a stale duplicate here is a visual bug rather than an accessibility one. The rule
 * that matters is honoured either way - Blue 1 is a structural stroke and never a status colour.
 */
const PALETTE = {
  grid: '#385FAF',
  axis: '#739BCF',
  ink: '#E8EDF5',
  series: ['#739BCF', '#27AE60', '#E06C69', '#9FB0CC'],
};

function drawPlot(canvas, plot) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 900;
  const height = canvas.clientHeight || 320;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const pad = { left: 74, right: 18, top: 16, bottom: 42 };
  const inner = { w: width - pad.left - pad.right, h: height - pad.top - pad.bottom };

  const xs = plot.series.flatMap((s) => s.x);
  const ys = plot.series.flatMap((s) => s.y);
  if (!xs.length || !ys.length) { return; }

  // A degenerate range would divide by zero and paint a flat line at the top of the box. Padding a
  // zero span by a unit keeps a genuinely constant series readable instead of invisible.
  let [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  if (x1 - x0 === 0) { x0 -= 1; x1 += 1; }
  if (y1 - y0 === 0) { y0 -= 1; y1 += 1; }
  const yPad = (y1 - y0) * 0.08;
  y0 -= yPad; y1 += yPad;

  const sx = (v) => pad.left + ((v - x0) / (x1 - x0)) * inner.w;
  const sy = (v) => pad.top + inner.h - ((v - y0) / (y1 - y0)) * inner.h;

  ctx.font = '12px "Segoe UI", system-ui, sans-serif';
  ctx.lineWidth = 1;

  // Grid and tick labels. Blue 1 for the grid lines, which is a structural fill; the LABELS use
  // Blue 2, because Blue 1 at 2.45:1 never carries text.
  for (let i = 0; i <= 4; i += 1) {
    const value = y0 + ((y1 - y0) * i) / 4;
    const y = sy(value);
    ctx.strokeStyle = PALETTE.grid;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
    ctx.fillStyle = PALETTE.axis;
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ctx.fillText(formatTick(value), pad.left - 8, y);
  }
  for (let i = 0; i <= 4; i += 1) {
    const value = x0 + ((x1 - x0) * i) / 4;
    const x = sx(value);
    ctx.fillStyle = PALETTE.axis;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText(formatTick(value), x, pad.top + inner.h + 8);
  }

  ctx.strokeStyle = PALETTE.axis;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top); ctx.lineTo(pad.left, pad.top + inner.h);
  ctx.lineTo(width - pad.right, pad.top + inner.h);
  ctx.stroke();

  ctx.fillStyle = PALETTE.axis;
  ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  ctx.fillText(plot.x_label, pad.left + inner.w / 2, height - 6);
  ctx.save();
  ctx.translate(14, pad.top + inner.h / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(plot.y_label, 0, 0);
  ctx.restore();

  // A relative track is a path in space, so it is drawn as a path with points; a time series is
  // drawn as a line. Both get markers when the series is sparse, because the RPO item whose
  // correct answer is "indeterminate" IS sparse and a smoothed line would hide that.
  plot.series.forEach((series, index) => {
    const colour = PALETTE.series[index % PALETTE.series.length];
    ctx.strokeStyle = colour;
    ctx.fillStyle = colour;
    ctx.lineWidth = 2;
    ctx.beginPath();
    series.x.forEach((xv, i) => {
      const px = sx(xv); const py = sy(series.y[i]);
      if (i === 0) { ctx.moveTo(px, py); } else { ctx.lineTo(px, py); }
    });
    ctx.stroke();
    if (series.x.length <= 24) {
      series.x.forEach((xv, i) => {
        ctx.beginPath();
        ctx.arc(sx(xv), sy(series.y[i]), 3.5, 0, Math.PI * 2);
        ctx.fill();
      });
    }
  });
}

function formatTick(value) {
  const magnitude = Math.abs(value);
  if (magnitude >= 100) { return value.toFixed(0); }
  if (magnitude >= 1) { return value.toFixed(1); }
  return value.toFixed(3);
}

function renderPlotTable(plot) {
  // The keyboard and screen-reader path to the same data. Not a fallback: an operator who wants
  // the numbers should be able to have the numbers.
  const host = $('plot-table');
  host.textContent = '';
  plot.series.forEach((series) => {
    const table = document.createElement('table');
    const caption = document.createElement('caption');
    caption.className = 'hint';
    caption.style.textAlign = 'left';
    caption.textContent = series.label;
    table.appendChild(caption);
    const head = document.createElement('thead');
    const headRow = document.createElement('tr');
    [plot.x_label, plot.y_label].forEach((text) => {
      const th = document.createElement('th');
      th.textContent = text;
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    table.appendChild(head);
    const body = document.createElement('tbody');
    // Every eighth point when the series is dense: a 96-row table read aloud is not accessible,
    // it is only complete. The shape is what the operator needs and eight-point sampling keeps it.
    const stride = series.x.length > 24 ? 8 : 1;
    series.x.forEach((xv, i) => {
      if (i % stride !== 0) { return; }
      const row = document.createElement('tr');
      [formatTick(xv), formatTick(series.y[i])].forEach((text) => {
        const td = document.createElement('td');
        td.className = 'num';
        td.textContent = text;
        row.appendChild(td);
      });
      body.appendChild(row);
    });
    table.appendChild(body);
    host.appendChild(table);
  });
}

/* --------------------------------------------------------------------- drill */

function renderConfidence() {
  const host = $('confidence');
  host.textContent = '';
  const labels = { 1: 'Guessing', 2: 'Leaning', 3: 'Fairly sure', 4: 'Confident', 5: 'Certain' };
  Object.keys(state.confidenceSteps).sort().forEach((step) => {
    const probability = state.confidenceSteps[step];
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'radio';
    input.name = 'confidence';
    input.value = step;
    if (step === '3') { input.checked = true; }
    const text = document.createElement('span');
    text.textContent = labels[step] || `Step ${step}`;
    const pct = document.createElement('span');
    pct.className = 'pct';
    pct.textContent = `${Math.round(probability * 100)}%`;
    label.append(input, text, pct);
    host.appendChild(label);
  });
}

async function loadDrill() {
  $('reveal').hidden = true;
  state.answered = false;
  $('submit-answer').disabled = false;
  $('classification').value = '';
  $('first-action').value = '';
  $('drill-title').textContent = 'Loading a drill…';
  try {
    const drill = await api('/api/v1/drill/next');
    state.drill = drill;
    $('drill-title').textContent = drill.title;
    $('drill-procedure').textContent = drill.procedure_title;
    $('drill-axis').textContent = drill.axis;
    $('drill-difficulty').textContent = String(drill.difficulty);
    $('drill-rating').textContent = String(drill.operator_rating);
    $('drill-prompt').textContent = drill.prompt;
    $('plot-desc').textContent = drill.plot.description;
    drawPlot($('plot'), drill.plot);
    renderPlotTable(drill.plot);
    $('classification').focus();
    announce(`New drill: ${drill.title}. ${drill.plot.description}`);
  } catch (error) {
    $('drill-title').textContent = 'No drill available';
    $('drill-prompt').textContent = error.message;
    announce(`Could not load a drill. ${error.message}`);
  }
}

function renderReveal(result) {
  const verdict = $('verdict');
  verdict.className = `verdict ${result.correct ? 'hit' : 'miss'}`;
  // Shape AND text AND colour. The glyph is the part that survives deuteranopia and a monochrome
  // screenshot, which is why it is not decoration.
  verdict.querySelector('.glyph').textContent = result.correct ? '▲' : '▼';
  verdict.querySelector('.text').textContent = result.correct
    ? `Correct. ${result.calibration}.`
    : result.confused_with
      ? `Not this one. You called it "${result.confused_with}", which is the look-alike this item discriminates against. ${result.calibration}.`
      : `Not this one. ${result.calibration}.`;

  $('reveal-points').textContent = `${result.points.toFixed(2)} of 100`;
  const delta = result.rating_delta >= 0 ? `+${result.rating_delta}` : String(result.rating_delta);
  $('reveal-rating').textContent = `${result.rating_after} (${delta})`;
  $('reveal-due').textContent = `${result.next_due_in_days} day(s)`;
  $('reveal-cue').textContent = result.expert_cue;

  const body = $('reveal-lines');
  body.textContent = '';
  result.lines.forEach((line) => {
    const row = document.createElement('tr');
    const cells = [
      line.rule,
      line.axis,
      line.available > 0 ? `${line.awarded} / ${line.available}` : '—',
      line.evidence,
    ];
    cells.forEach((text, index) => {
      const td = document.createElement('td');
      if (index === 2) { td.className = 'num'; }
      td.textContent = text;
      row.appendChild(td);
    });
    body.appendChild(row);
  });

  const accepted = result.accepted_classifications.slice(0, 3).join(', ');
  $('reveal-procedure').textContent =
    `${result.procedure_title}. Step one: ${result.first_step} ` +
    `Accepted answers for this item included: ${accepted}.`;

  $('reveal').hidden = false;
  $('next-drill').focus();
  announce(
    `${result.correct ? 'Correct' : 'Incorrect'}. ${result.points.toFixed(0)} points. ` +
    `Expert cue: ${result.expert_cue}`,
  );
}

async function submitAnswer(event) {
  event.preventDefault();
  if (!state.drill || state.answered) { return; }
  const classification = $('classification').value.trim();
  const firstAction = $('first-action').value.trim();
  if (!classification || !firstAction) {
    announce('Both the event name and the first action are needed before committing.');
    return;
  }
  const chosen = document.querySelector('input[name="confidence"]:checked');
  $('submit-answer').disabled = true;
  try {
    const result = await api('/api/v1/drill/answer', {
      method: 'POST',
      body: JSON.stringify({
        item_id: state.drill.item_id,
        classification,
        first_action: firstAction,
        confidence: chosen ? Number(chosen.value) : 3,
      }),
    });
    state.answered = true;
    renderReveal(result);
  } catch (error) {
    $('submit-answer').disabled = false;
    announce(`Could not score that answer. ${error.message}`);
  }
}

/* ----------------------------------------------------------------- dashboard */

async function loadDashboard() {
  const data = await api('/api/v1/dashboard');
  $('dash-rating').textContent = String(data.rating);
  $('dash-runs').textContent = String(data.runs_total);
  $('dash-due').textContent = String(data.due_now.length);
  $('dash-items').textContent = String(data.items_total);

  const axes = $('dash-axes');
  axes.textContent = '';
  data.axes.forEach((axis) => {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = axis.axis;
    const attempts = document.createElement('td');
    attempts.className = 'num';
    attempts.textContent = String(axis.attempts);
    const accuracy = document.createElement('td');
    accuracy.className = 'num';
    accuracy.textContent = axis.accuracy === null ? 'not measured' : `${Math.round(axis.accuracy * 100)}%`;
    const interval = document.createElement('td');
    if (axis.interval) {
      const track = document.createElement('div');
      track.className = 'bar-track';
      const fill = document.createElement('div');
      fill.className = 'bar-fill';
      fill.style.width = `${Math.round((axis.accuracy || 0) * 100)}%`;
      const band = document.createElement('div');
      band.className = 'bar-ci';
      band.style.left = `${Math.round(axis.interval[0] * 100)}%`;
      band.style.width = `${Math.max(2, Math.round((axis.interval[1] - axis.interval[0]) * 100))}%`;
      track.append(fill, band);
      interval.appendChild(track);
      const text = document.createElement('span');
      text.className = 'hint';
      text.textContent = `${Math.round(axis.interval[0] * 100)}% to ${Math.round(axis.interval[1] * 100)}%`;
      interval.appendChild(text);
    } else {
      interval.className = 'empty';
      interval.textContent = 'no attempts yet';
    }
    const brier = document.createElement('td');
    brier.className = 'num';
    brier.textContent = axis.mean_brier === null ? '—' : axis.mean_brier.toFixed(3);
    row.append(name, attempts, accuracy, interval, brier);
    axes.appendChild(row);
  });

  const coverage = $('dash-coverage');
  coverage.textContent = '';
  data.coverage.forEach((entry) => {
    const row = document.createElement('tr');
    [entry.procedure_id, entry.items, entry.attempted, entry.demonstrated].forEach((value, index) => {
      const td = document.createElement('td');
      if (index > 0) { td.className = 'num'; }
      td.textContent = String(value);
      row.appendChild(td);
    });
    coverage.appendChild(row);
  });

  const recent = $('dash-recent');
  recent.textContent = '';
  if (!data.recent.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 5;
    cell.className = 'empty';
    cell.textContent = 'Nothing recorded yet. Answer a drill and it appears here.';
    row.appendChild(cell);
    recent.appendChild(row);
  }
  data.recent.forEach((run) => {
    const row = document.createElement('tr');
    const when = document.createElement('td');
    when.textContent = run.answered_at.slice(0, 16).replace('T', ' ');
    const item = document.createElement('td');
    item.textContent = run.item_id;
    const outcome = document.createElement('td');
    outcome.className = run.correct ? 'verdict hit' : 'verdict miss';
    outcome.textContent = run.correct ? '▲ correct' : '▼ missed';
    const confidence = document.createElement('td');
    confidence.className = 'num';
    confidence.textContent = String(run.confidence);
    const points = document.createElement('td');
    points.className = 'num';
    points.textContent = run.points.toFixed(1);
    row.append(when, item, outcome, confidence, points);
    recent.appendChild(row);
  });
}

/* ------------------------------------------------------------------- library */

function renderLibrary() {
  const list = $('library-list');
  list.textContent = '';
  state.procedures.forEach((procedure) => {
    const row = document.createElement('tr');
    const name = document.createElement('td');
    const button = document.createElement('button');
    button.className = 'ghost';
    button.textContent = procedure.title;
    button.addEventListener('click', () => loadProcedure(procedure.id));
    name.appendChild(button);
    const steps = document.createElement('td');
    steps.className = 'num';
    steps.textContent = String(procedure.steps);
    const status = document.createElement('td');
    status.textContent = procedure.status;
    row.append(name, steps, status);
    list.appendChild(row);
  });
  // The honest statement of the content gap, on screen rather than only in a commit message.
  $('library-gap').textContent =
    `${state.procedures.length} procedures loaded. The flight plan's definition of done requires ` +
    'all fifteen seeded as data; the remaining twelve are not named in the plan, so they are not ' +
    'invented here. Ash to supply the names and content.';
}

async function loadProcedure(id) {
  const host = $('procedure-detail');
  try {
    const procedure = await api(`/api/v1/library/${encodeURIComponent(id)}`);
    host.textContent = '';
    const heading = document.createElement('h2');
    heading.textContent = procedure.title;
    const meta = document.createElement('p');
    meta.className = 'meta-row';
    meta.textContent =
      `${procedure.id} ${procedure.version} · ${procedure.status} · authored by ` +
      `${procedure.authored_by} on ${procedure.authored_on}`;
    const purpose = document.createElement('p');
    purpose.textContent = procedure.purpose;
    host.append(heading, meta, purpose);

    appendList(host, 'Entry conditions', procedure.entry_conditions);

    const stepsHeading = document.createElement('h3');
    stepsHeading.textContent = 'Steps';
    host.appendChild(stepsHeading);
    const ol = document.createElement('ol');
    ol.className = 'steps';
    procedure.steps.forEach((step) => {
      const li = document.createElement('li');
      const action = document.createElement('div');
      action.textContent = step.action;
      const role = document.createElement('div');
      role.className = 'step-role';
      role.textContent = step.responsible_role;
      li.append(action, role);
      if (step.warning) {
        const warning = document.createElement('div');
        warning.className = 'step-warning';
        // Prefixed with a word, not only a colour: the alert red is text-safe at 4.66:1 but the
        // meaning must not depend on it.
        warning.textContent = `Warning: ${step.warning}`;
        li.appendChild(warning);
      }
      if (step.note) {
        const note = document.createElement('div');
        note.className = 'step-note';
        note.textContent = `Note: ${step.note}`;
        li.appendChild(note);
      }
      ol.appendChild(li);
    });
    host.appendChild(ol);

    if (procedure.threshold_criteria.length) {
      const thresholds = procedure.threshold_criteria.map((item) => `${item.name}: ${item.condition}`);
      appendList(host, 'Threshold criteria', thresholds);
    }
    appendList(host, 'Reporting requirements', procedure.reporting_requirements);
    appendList(host, 'Closure criteria', procedure.closure_criteria);
    announce(`Loaded procedure ${procedure.title}.`);
  } catch (error) {
    host.textContent = '';
    const heading = document.createElement('h2');
    heading.textContent = 'Could not load that procedure';
    const detail = document.createElement('p');
    detail.className = 'empty';
    detail.textContent = error.message;
    host.append(heading, detail);
  }
}

function appendList(host, title, values) {
  if (!values || !values.length) { return; }
  const heading = document.createElement('h3');
  heading.textContent = title;
  const ul = document.createElement('ul');
  values.forEach((value) => {
    const li = document.createElement('li');
    li.textContent = value;
    ul.appendChild(li);
  });
  host.append(heading, ul);
}

/* ---------------------------------------------------------------- navigation */

const VIEWS = [
  ['tab-drill', 'view-drill', null],
  ['tab-dashboard', 'view-dashboard', loadDashboard],
  ['tab-library', 'view-library', null],
];

function show(targetTab, options) {
  VIEWS.forEach(([tabId, viewId, onShow]) => {
    const selected = tabId === targetTab;
    $(tabId).setAttribute('aria-selected', String(selected));
    $(viewId).hidden = !selected;
    if (selected && onShow) {
      onShow().catch((error) => announce(`Could not load that view. ${error.message}`));
    }
  });
  // The hash carries the view, so a screen is linkable and the back button works. Written with
  // replaceState rather than assigning location.hash: assigning would fire hashchange and re-enter
  // this function, and a tab switch that recursed once would eventually recurse always.
  if (!options || !options.fromHash) {
    history.replaceState(null, '', `#${targetTab.replace('tab-', '')}`);
  }
}

function viewFromHash() {
  const wanted = `tab-${window.location.hash.replace('#', '')}`;
  return VIEWS.some(([tabId]) => tabId === wanted) ? wanted : 'tab-drill';
}

async function boot() {
  VIEWS.forEach(([tabId]) => $(tabId).addEventListener('click', () => show(tabId)));
  $('answer-form').addEventListener('submit', submitAnswer);
  $('next-drill').addEventListener('click', loadDrill);
  $('open-procedure').addEventListener('click', () => {
    if (state.drill) { show('tab-library'); loadProcedure(state.drill.procedure_id); }
  });
  $('toggle-table').addEventListener('click', () => {
    const table = $('plot-table');
    const open = table.hidden;
    table.hidden = !open;
    $('toggle-table').setAttribute('aria-expanded', String(open));
    $('toggle-table').textContent = open ? 'Hide the data table' : 'Read the data as a table';
  });
  window.addEventListener('resize', () => {
    if (state.drill) { drawPlot($('plot'), state.drill.plot); }
  });

  window.addEventListener('hashchange', () => show(viewFromHash(), { fromHash: true }));

  try {
    const content = await api('/api/v1/content');
    state.procedures = content.procedures;
    state.confidenceSteps = content.confidence_steps;
    $('build').textContent = `build ${content.version}`;
    $('foot-identity').textContent = `${content.operator_id} · ${content.identity}`;
    const provenance = $('provenance');
    provenance.textContent = '';
    const strong = document.createElement('strong');
    strong.textContent = 'Illustrative content. ';
    provenance.append(strong, document.createTextNode(content.content_provenance));
    if (!content.ok) {
      const errors = document.createElement('div');
      errors.textContent = `Content errors: ${content.errors.join(' | ')}`;
      provenance.appendChild(errors);
    }
    renderConfidence();
    renderLibrary();
  } catch (error) {
    announce(`Could not read content status. ${error.message}`);
  }
  await loadDrill();
  show(viewFromHash(), { fromHash: true });
}

boot();
