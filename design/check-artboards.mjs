// Measure the artboards, rather than trusting how they look.
//
// Every plot in a PHOSPHOR artboard is an SVG with its own coordinate system,
// drawn into a column narrower or wider than that system. So a label declared
// at 9.5 units can render at 9.0 real pixels, or at 10.4, and reading the
// markup tells you neither. This loads each artboard in a real browser at two
// window widths and asserts three things about every piece of text inside a
// plot:
//
//   ● it renders at 12 CSS pixels or more
//   ● its bounding box sits inside the frame, so nothing is clipped away
//   ● it does not overlap another label
//
// It also asserts that a loaded artboard fetches nothing outside its own
// directory, which is how the vendored typefaces stay vendored, and that every
// typeface a page actually asks for is one that actually loaded.
//
// Not part of scripts/verify.sh: it needs Node and Playwright, and this is a
// Python project. Run it by hand when an artboard changes.
//
//   npm install playwright
//   node design/check-artboards.mjs        (add a path to check one directory)
//
// Exits non-zero on any failure.

import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const dir = path.resolve(process.argv[2] ?? 'design/phosphor');
const WIDTHS = [1440, 1180];
const FLOOR_PX = 12;

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});
let failures = 0;

for (const width of WIDTHS) {
  const page = await browser.newPage({ viewport: { width, height: 1000 } });
  const offsite = [];
  // Only a file: URL inside the artboard directory is served. An artboard is
  // repo-controlled, so this is defence in depth rather than a live threat, but
  // a page that can fetch('file:///etc/...') has no business in a check that
  // exists to prove a page fetches nothing.
  const root = dir.endsWith(path.sep) ? dir : dir + path.sep;
  await page.route('**', route => {
    const url = route.request().url();
    if (url.startsWith('file:')) {
      let target;
      // decodeURIComponent, because a directory with a space in its name arrives
      // percent-encoded and would otherwise resolve outside root and read as offsite.
      try { target = path.resolve(decodeURIComponent(new URL(url).pathname)); }
      catch { target = ''; }
      if (target === dir || target.startsWith(root)) return route.continue();
    }
    offsite.push(url);
    return route.abort();
  });
  console.log(`\n=== window ${width}px`);
  for (const file of fs.readdirSync(dir).filter(f => f.endsWith('.dc.html')).sort()) {
    await page.goto('file://' + path.join(dir, file), { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    const found = await page.evaluate(floor => {
      const small = [], clipped = [], overlapping = [], unloaded = [];
      for (const svg of document.querySelectorAll('svg')) {
        const box = svg.viewBox.baseVal, rect = svg.getBoundingClientRect();
        if (!box || !box.width || rect.width === 0) continue;
        const scale = rect.width / box.width;
        const texts = [...svg.querySelectorAll('text')]
          .filter(t => (t.textContent || '').trim());
        for (const t of texts) {
          const rendered = parseFloat(getComputedStyle(t).fontSize) * scale;
          const label = JSON.stringify(t.textContent.slice(0, 30));
          if (rendered < floor) small.push(`${rendered.toFixed(1)}px ${label}`);
          const bb = t.getBBox();
          if (bb.x < box.x - 0.5 || bb.y < box.y - 0.5 ||
              bb.x + bb.width > box.x + box.width + 0.5 ||
              bb.y + bb.height > box.y + box.height + 0.5) clipped.push(label);
        }
        for (let i = 0; i < texts.length; i++) {
          for (let j = i + 1; j < texts.length; j++) {
            const a = texts[i].getBBox(), b = texts[j].getBBox();
            const dx = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
            const dy = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
            if (dx > 1 && dy > 1) overlapping.push(
              JSON.stringify(texts[i].textContent.slice(0, 24)) + ' over ' +
              JSON.stringify(texts[j].textContent.slice(0, 24)));
          }
        }
      }
      // Asserted positively against document.fonts, never through fonts.check():
      // check() returns TRUE when no @font-face rule matches the family at all, so
      // a dropped stylesheet - the likeliest regression, and the exact state this
      // direction moved away from - would read as a pass. And no allowlist of
      // expected family names: every first-choice family that is not a generic
      // keyword must resolve to a face that actually loaded, so a typo or a rename
      // fails too rather than being skipped for not matching the list.
      const GENERIC = new Set(['system-ui', 'ui-sans-serif', 'ui-serif', 'ui-monospace',
        'ui-rounded', 'sans-serif', 'serif', 'monospace', 'cursive', 'fantasy', 'math',
        'emoji', 'fangsong', 'inherit', 'initial', 'unset', 'revert']);
      const declared = [...document.fonts].map(face => {
        const bounds = String(face.weight).trim().split(/\s+/).map(Number);
        return { family: face.family.replace(/["']/g, '').trim(),
                 lo: bounds[0], hi: bounds[bounds.length - 1], status: face.status };
      });
      for (const el of document.querySelectorAll('*')) {
        if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
        const style = getComputedStyle(el);
        const family = style.fontFamily.split(',')[0].replace(/["']/g, '').trim();
        if (family === '' || GENERIC.has(family.toLowerCase())) continue;
        const weight = Number(style.fontWeight);
        const face = declared.find(f => f.family === family && weight >= f.lo && weight <= f.hi);
        if (face === undefined) unloaded.push(`${family} ${weight}: nothing declares it`);
        else if (face.status !== 'loaded') unloaded.push(`${family} ${weight}: ${face.status}`);
      }
      return { small: [...new Set(small)], clipped: [...new Set(clipped)],
               overlapping: [...new Set(overlapping)], unloaded: [...new Set(unloaded)] };
    }, FLOOR_PX);

    const problems = [
      [`text under ${FLOOR_PX}px`, found.small],
      ['clipped by its frame', found.clipped],
      ['overlapping labels', found.overlapping],
      ['typeface never loaded', found.unloaded],
    ].filter(([, list]) => list.length);
    if (problems.length) {
      failures += problems.length;
      console.log(`FAIL ${file}`);
      for (const [what, list] of problems) console.log(`   ${what}: ${list.join(' | ')}`);
    } else {
      console.log(` ok  ${file}`);
    }
  }
  if (offsite.length) {
    failures += 1;
    console.log(`FAIL an artboard fetched outside its own directory: ${[...new Set(offsite)].join(', ')}`);
  }
  await page.close();
}

await browser.close();
console.log(failures ? `\n${failures} failing check(s)` : '\nall artboards pass');
process.exit(failures ? 1 : 0);
