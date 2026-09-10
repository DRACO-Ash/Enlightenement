/* Line coverage for `ui/app.js`, computed from V8's own byte ranges.
 *
 * WHY THIS EXISTS RATHER THAN `--experimental-test-coverage`. The harness evaluates the shipped
 * script in a `vm` context, because the file must stay loadable by a plain `<script>` tag under
 * `script-src 'self'` and must not grow module exports it does not ship with. Node's built-in
 * coverage reporter does not attribute a vm-run script: it reported 97.96% while listing only
 * the test files themselves, which is a number about the tests and not about the interface.
 * Publishing that would have been worse than publishing nothing. V8's raw coverage DOES carry
 * the script - two process reports, 66 and 67 functions - so the figure is computed from that.
 *
 * THE METHOD, stated because a coverage percentage with an unstated method is not evidence.
 * V8 reports, per function, a set of byte RANGES each with an execution count, where a nested
 * range overrides the one containing it. So:
 *
 *   1. Paint a count per byte, outermost range first, letting inner ranges overwrite. A byte no
 *      range covers is NOT EXECUTABLE and is never counted in either the numerator or the
 *      denominator - that is what keeps comments and declarations out of the figure.
 *   2. Merge the process reports by taking the highest count for each byte, because a line
 *      executed in either process is executed.
 *   3. A LINE is executable if it holds at least one executable non-whitespace byte, and covered
 *      if at least one such byte has a count above zero.
 *
 * That is the same shape as the standard tools' own method. It is deliberately conservative in one
 * direction: a line that is only partly executed reads as covered, exactly as a Python statement
 * with a partly-taken branch does in the Cobertura report beside it. Branch coverage is NOT
 * claimed here, because this does not compute it.
 */

import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const APP_JS = join(HERE, '..', 'app.js');

/* The lowest acceptable line coverage for the interface script.
 *
 * Owner instruction of 2026-09-10 was a pass-mark over 90%, and the Python suite's own floor is
 * 95 for the same reason. The measured figure here is 100.00% of 1,225 executable lines, so this
 * holds five points of headroom: enough that a legitimate addition does not turn the loop red on
 * arrival, tight enough that a body of untested code cannot land quietly.
 */
export const FLOOR = 95;

const NOT_EXECUTABLE = -1;

function paint(source, script) {
  const counts = new Int32Array(source.length).fill(NOT_EXECUTABLE);
  const ranges = script.functions.flatMap((fn) => fn.ranges);
  //: Outermost first, so a nested range's count wins. Sorting by width rather than by nesting
  //: depth is what V8's own consumers do, and the two agree because ranges never partly overlap.
  ranges.sort((a, b) => b.endOffset - b.startOffset - (a.endOffset - a.startOffset));
  for (const range of ranges) {
    const end = Math.min(range.endOffset, source.length);
    counts.fill(range.count, range.startOffset, end);
  }
  return counts;
}

export function measure(coverageDirectory) {
  const source = readFileSync(APP_JS, 'utf8');
  let merged = null;
  let scripts = 0;
  for (const name of readdirSync(coverageDirectory)) {
    if (!name.endsWith('.json')) continue;
    const report = JSON.parse(readFileSync(join(coverageDirectory, name), 'utf8'));
    for (const script of report.result ?? []) {
      if (!script.url.endsWith('app.js')) continue;
      scripts += 1;
      const counts = paint(source, script);
      if (merged === null) {
        merged = counts;
        continue;
      }
      for (let i = 0; i < merged.length; i += 1) {
        if (counts[i] > merged[i]) merged[i] = counts[i];
      }
    }
  }
  if (merged === null) {
    throw new Error(
      `no coverage for app.js in ${coverageDirectory}. The harness evaluates it through vm with` +
        ' an explicit filename; if that filename changed, this reporter stops seeing the script' +
        ' and would otherwise report a clean 100% over nothing.',
    );
  }

  const lines = [];
  let offset = 0;
  for (const [index, text] of source.split('\n').entries()) {
    let executable = false;
    let covered = false;
    for (let i = offset; i < offset + text.length; i += 1) {
      if (/\s/.test(source[i]) || merged[i] === NOT_EXECUTABLE) continue;
      executable = true;
      if (merged[i] > 0) covered = true;
    }
    if (executable) lines.push({ number: index + 1, covered });
    offset += text.length + 1;
  }
  const covered = lines.filter((line) => line.covered);
  return {
    scripts,
    lines,
    total: lines.length,
    covered: covered.length,
    percent: lines.length ? (covered.length / lines.length) * 100 : 0,
  };
}

/* LCOV, for a tool that wants it. Not consumed by the App Store's quality gate: the interface
 * sits outside `sonar.sources` on purpose, and the platform's generated pipeline runs neither
 * Node nor this reporter. Written anyway because the alternative to a machine-readable report is
 * a number in a log that nobody can check. */
export function lcov(result) {
  const body = result.lines
    .map((line) => `DA:${line.number},${line.covered ? 1 : 0}`)
    .join('\n');
  return `TN:ui\nSF:ui/app.js\n${body}\nLF:${result.total}\nLH:${result.covered}\nend_of_record\n`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const directory = process.argv[2];
  if (!directory) {
    console.error('usage: node ui/tests/coverage.mjs <NODE_V8_COVERAGE directory> [lcov path]');
    process.exit(2);
  }
  const result = measure(directory);
  const percent = result.percent.toFixed(2);
  console.log(
    `ui/app.js: ${result.covered}/${result.total} executable lines covered (${percent}%),` +
      ` from ${result.scripts} process report(s)`,
  );
  if (process.argv[3]) writeFileSync(process.argv[3], lcov(result), 'utf8');
  if (result.percent < FLOOR) {
    const missed = result.lines.filter((line) => !line.covered).map((line) => line.number);
    console.error(`FAIL: ${percent}% is below the ${FLOOR}% floor for the interface script.`);
    console.error(`uncovered lines: ${missed.join(', ')}`);
    process.exit(1);
  }
  console.log(`PASS: at or above the ${FLOOR}% floor.`);
}
