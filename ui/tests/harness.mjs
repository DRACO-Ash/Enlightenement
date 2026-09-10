/* Load the SHIPPED interface script and hand back its functions, without changing it.
 *
 * `ui/app.js` is a browser script served under `script-src 'self'`. It has no module exports and
 * it must not gain any: adding `export` breaks a plain `<script>` tag, and a build step to strip
 * them again would mean the tested file is not the shipped file. So it is evaluated in a `vm`
 * context, where its top-level function declarations become properties of that context and its
 * top-level `const`s stay reachable by evaluating an expression in the same context. The bytes
 * under test are byte-for-byte the bytes the server sends.
 *
 * The script self-boots on its last two lines. With `readyState: 'loading'` the document's
 * `addEventListener` records rather than calls, so `boot()` is registered and never runs. Pass
 * `readyState: 'complete'` to let it run, which is what the view tests do.
 *
 * WHAT THIS FAKE DOM IS FOR, and where it stops. It records what the interface asked for so a
 * test can assert on it. It is not a browser and it must never become one: the moment it starts
 * implementing layout or the cascade, the tests are asserting its behaviour rather than the
 * interface's. Three deliberate exceptions, each because a real defect hides behind it.
 * `getElementById` REFUSES an id the shipped markup does not declare, because a mistyped lookup
 * is invisible until the view that uses it is opened. `querySelectorAll` understands exactly the
 * selector shapes `app.js` uses and THROWS on any other, because a selector a harness silently
 * does not understand is a test that proves nothing. And `requestAnimationFrame` calls back
 * synchronously, because a stub that never calls back leaves the whole text-refit path
 * unexercised while the suite reports green.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
export const APP_JS = join(HERE, '..', 'app.js');
export const INDEX_HTML = join(HERE, '..', 'index.html');

/** Every `id` the shipped document declares. A lookup outside this set is a defect. */
/* A `NodeList`, as far as this harness needs to model one: `length`, index access, iteration and
 * `forEach`, and deliberately NO array methods. Real DOM code has to spread a query result before
 * mapping or filtering it, and so does test code here - which is the whole reason this exists.
 * See the note on `querySelectorAll`. */
/* An `HTMLCollection`, as far as this harness needs one: `length`, index access, `item` and
 * `namedItem`, and NOT `forEach` - which a real one genuinely lacks. Live-ness is not modelled
 * and does not need to be: nothing here holds a collection across a mutation. */
function htmlCollection(nodes) {
  const list = {
    length: nodes.length,
    item: (index) => nodes[index] ?? null,
    namedItem: (name) => nodes.find((node) => node.getAttribute('id') === name) ?? null,
    [Symbol.iterator]: () => nodes[Symbol.iterator](),
  };
  nodes.forEach((node, index) => { list[index] = node; });
  return list;
}

function nodeList(nodes) {
  const list = {
    length: nodes.length,
    item: (index) => nodes[index] ?? null,
    /* The third callback argument is the LIST, as a real `NodeList` passes, and was the backing
     * array: generosity one argument deep. */
    forEach: (visit, thisArg) => nodes.forEach((node, index) => visit.call(thisArg, node, index, list)),
    entries: () => nodes.entries(),
    keys: () => nodes.keys(),
    values: () => nodes.values(),
    [Symbol.iterator]: () => nodes[Symbol.iterator](),
  };
  nodes.forEach((node, index) => { list[index] = node; });
  return list;
}

export function declaredIds(markup = readFileSync(INDEX_HTML, 'utf8')) {
  return new Set([...markup.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));
}

/* Every control carrying `data-view`, with whether it sits inside the nav.
 *
 * Two regexes rather than a parser, and the limit is stated: this reads attribute order as the
 * document happens to write it. It exists so `boot()` wires the REAL controls instead of an
 * invented pair, which is what makes "the nav and the hero share one path" testable.
 */
function declaredViewControls(markup) {
  return [...markup.matchAll(/<(\w+)[^>]*\bdata-view="([^"]+)"[^>]*>/g)].map((match) => {
    const before = markup.slice(0, match.index);
    return {
      tag: match[1],
      view: match[2],
      inNav: before.lastIndexOf('<nav') > before.lastIndexOf('</nav>'),
    };
  });
}

/* A DOM node, to the depth this interface actually uses: a tag, a class, text, attributes,
 * children, and a classList that can toggle.
 */
class FakeNode {
  constructor(tag, namespace = null) {
    this.tagName = String(tag).toUpperCase();
    this.namespaceURI = namespace;
    this._children = [];
    this.attributes = new Map();
    this.dataset = {};
    this.style = {};
    this.listeners = new Map();
    this._text = '';
    this._classes = new Set();
    this.type = '';
    this.tabIndex = 0;
    this.hidden = false;
    /* Focus is BEHAVIOUR, not decoration: the debrief moves focus to its primary button so a
     * keyboard operator is not left at the top of a replaced view. Recorded rather than stubbed
     * away, so a test can assert which node was given focus. */
    this.focused = false;
    /* Geometry, for the text-refit path. Settable per node because the whole point of that code
     * is to react to a measurement, so a test that cannot set one cannot reach it. */
    this.box = { x: 0, y: 0, width: 40, height: 12 };
    this.rect = { width: 620, height: 260 };
  }

  get className() {
    return [...this._classes].join(' ');
  }

  set className(value) {
    this._classes = new Set(String(value).split(/\s+/).filter(Boolean));
  }

  get classList() {
    const classes = this._classes;
    return {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, force) => {
        const on = force === undefined ? !classes.has(name) : Boolean(force);
        if (on) classes.add(name);
        else classes.delete(name);
        return on;
      },
    };
  }

  /* `textContent` on a parent returns its subtree's text, which is how the real thing behaves
   * and what the assertions need: a card's text is the sum of the spans inside it. */
  get textContent() {
    if (this._children.length) return this._children.map((child) => child.textContent).join('');
    return this._text;
  }

  set textContent(value) {
    this._text = String(value);
    this._children = [];
  }

  get firstChild() {
    return this._children[0] ?? null;
  }

  /* **A real DOM property this harness did not model, and the omission hid a whole section.**
   * `openProcedure` guards the gates block with `if (gates.childElementCount)`, which is
   * undefined here, so the entry conditions and the exclusions were dropped from every render
   * the tests could see - while rendering correctly in a browser. That is the third harness gap
   * of this kind: `requestAnimationFrame` not calling back hid 68 lines and a missing
   * `viewBox.baseVal` hid 38. A harness that does not understand the DOM produces tests that
   * prove nothing, so the fix is always to mirror the real thing rather than to bend the app
   * around the fake. Element-only here because `children` holds elements. */
  /* **`children` is an HTMLCollection-LIKE, for the same reason `querySelectorAll` is a
   * NodeList-like.** It was a plain array, which is more permissive than the platform in the
   * direction that surfaces as nothing: an `HTMLCollection` has `length`, indexing, `item` and
   * `namedItem` and NOT `forEach`, so it is narrower still than a NodeList. Shipped code touches
   * it in exactly one place and only for `.length`, so nothing exploited it - but
   * `children.forEach` is the specific trap, and it would have passed here and thrown in
   * Chromium exactly as `.filter` on a query result did. Closing the class rather than
   * documenting it, because half-fixing a class is how the second instance arrives. */
  get children() {
    return htmlCollection(this._children);
  }

  get childElementCount() {
    return this._children.length;
  }

  get value() {
    return this._value ?? '';
  }

  set value(next) {
    this._value = String(next);
  }

  appendChild(child) {
    child.parentNode = this;
    this._children.push(child);
    return child;
  }

  remove() {
    const siblings = this.parentNode?._children;
    if (siblings) siblings.splice(siblings.indexOf(this), 1);
    this.parentNode = null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name.startsWith('data-')) {
      const key = name.slice(5).replace(/-(\w)/g, (_, letter) => letter.toUpperCase());
      this.dataset[key] = String(value);
    }
    /* An `<svg>` exposes its viewBox as a PROPERTY as well as an attribute, and the refit path
     * reads `frame.viewBox.baseVal`. Without this the property is undefined, the refit decides
     * it cannot measure, and every line of it stays unexecuted while the suite reports green -
     * measured, as 68 uncovered lines. The fake mirrors the real DOM here because the code
     * under test depends on that shape, not because a fuller fake is better. */
    if (name === 'viewBox') {
      const [x, y, width, height] = String(value).trim().split(/\s+/).map(Number);
      this.viewBox = { baseVal: { x, y, width, height } };
    }
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  addEventListener(name, handler) {
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push(handler);
  }

  /* Fire a recorded handler. The interface wires behaviour through listeners, so a test that
   * cannot fire one can only assert on markup. */
  fire(name, event = {}) {
    const fired = { preventDefault() {}, ...event };
    for (const handler of this.listeners.get(name) ?? []) handler(fired);
    return fired;
  }

  focus() {
    this.focused = true;
  }

  getBBox() {
    if (this.box === null) throw new Error('getBBox is not available on an unrendered subtree');
    return this.box;
  }

  getBoundingClientRect() {
    return this.rect;
  }

  /* The selector shapes `app.js` uses, and no more: a bare tag, an attribute selector with or
   * without a value, and a class. Anything else throws.
   *
   * **Returns a NodeList-LIKE, not an array, and that is the point.** It returned a plain array
   * for months, which made the harness MORE permissive than the DOM in a way that let a crash
   * ship: `strip.querySelectorAll('span').filter(...)` passed all 56 interface tests and threw
   * `filter is not a function` in Chromium, because a real `NodeList` has `length`, indexing,
   * iteration and `forEach` and no array methods at all. The whole library screen rendered as a
   * single error banner.
   *
   * Every previous harness gap ran the other way - `requestAnimationFrame` not calling back hid
   * 68 lines, a missing `viewBox.baseVal` hid 38, a missing `childElementCount` hid a whole
   * section - and those show up as coverage or as a failing assertion. A harness that is more
   * generous than the platform shows up as nothing at all, which makes it the worse direction
   * and the one worth naming here. Tests spread it (`[...node.querySelectorAll('x')]`) exactly
   * as real DOM code has to. */
  querySelectorAll(selector) {
    const all = this.descendants();
    const attribute = selector.match(/^\[([\w-]+)(?:="([^"]*)")?\]$/);
    if (attribute) {
      return nodeList(all.filter((node) => {
        const held = node.getAttribute(attribute[1]);
        return held !== null && (attribute[2] === undefined || held === attribute[2]);
      }));
    }
    if (/^\.[\w-]+$/.test(selector)) {
      return nodeList(all.filter((node) => node._classes.has(selector.slice(1))));
    }
    if (/^\w+$/.test(selector)) {
      return nodeList(all.filter((node) => node.tagName === selector.toUpperCase()));
    }
    throw new Error(`the harness does not understand the selector "${selector}"`);
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] ?? null;
  }

  /* Every descendant carrying a class, flattened. The assertions ask "what did this build",
   * which is a question about the subtree rather than about one node. */
  find(className) {
    const found = [];
    for (const child of this._children) {
      if (child._classes.has(className)) found.push(child);
      found.push(...child.find(className));
    }
    return found;
  }

  descendants() {
    return this._children.flatMap((child) => [child, ...child.descendants()]);
  }
}

export { FakeNode };

/* An array from the vm, as a host array.
 *
 * A value built inside the context carries THAT realm's prototypes: an array literal in
 * `app.js` is not an instance of the test file's `Array`, so `assert.deepStrictEqual` reports
 * "same structure but not reference-equal" and a reader spends ten minutes on a passing
 * assertion. Normalised at the boundary rather than by loosening the assertion to a
 * non-strict compare, which would also stop noticing a string where a number belongs.
 */
export function plain(value) {
  return Array.isArray(value) ? [...value] : value;
}

/* A fetch stub over a path-prefix map.
 *
 * An unmapped path answers 404 with the server's own error shape, because that is what the real
 * one does and `api()` reads `detail.message` out of it. A payload carrying `__status` answers
 * that status, and an `Error` rejects, so both failure paths are drivable.
 */
function stubFetch(routes, calls) {
  return (path, options) => {
    calls.push({ path, options });
    const entry = Object.entries(routes).find(([pattern]) => path.startsWith(pattern));
    if (!entry) {
      return Promise.resolve({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: { error: 'not_found', message: 'No such route.' } }),
      });
    }
    const body = typeof entry[1] === 'function' ? entry[1](path, options) : entry[1];
    if (body instanceof Error) return Promise.reject(body);
    if (body && body.__status) {
      return Promise.resolve({
        ok: false,
        status: body.__status,
        json: () => Promise.resolve(body),
      });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
  };
}

export function load({ readyState = 'loading', routes = {}, extraIds = [] } = {}) {
  const markup = readFileSync(INDEX_HTML, 'utf8');
  const ids = declaredIds(markup);
  for (const id of extraIds) ids.add(id);
  const registry = new Map();
  const calls = [];

  const root = new FakeNode('body');
  for (const control of declaredViewControls(markup)) {
    const button = new FakeNode(control.tag);
    button.setAttribute('data-view', control.view);
    button.setAttribute('data-nav', control.inNav ? 'yes' : 'no');
    root.appendChild(button);
  }

  const document = {
    readyState,
    body: root,
    createElement: (tag) => new FakeNode(tag),
    createElementNS: (namespace, tag) => new FakeNode(tag, namespace),
    createTextNode: (text) => {
      const node = new FakeNode('#text');
      node._text = String(text);
      return node;
    },
    getElementById: (id) => {
      if (!ids.has(id)) {
        throw new Error(
          `app.js looked up #${id}, which ui/index.html does not declare. In a browser this` +
            ' returns null and the next property access throws, in whichever view uses it.',
        );
      }
      if (!registry.has(id)) registry.set(id, new FakeNode('div'));
      return registry.get(id);
    },
    /* `#nav button` and `main [data-view]` are the two document-level selectors `boot` uses.
     * Both resolve against the controls parsed out of the shipped markup. */
    querySelectorAll: (selector) => {
      /* Wrapped like every other query result, so the document-level selectors are no more
       * permissive than the element-level ones. Two paths returning two different shapes for
       * one method is exactly how a gap like this survives. */
      if (selector === '#nav button') {
        return nodeList(root._children.filter((node) => node.getAttribute('data-nav') === 'yes'));
      }
      if (selector === 'main [data-view]') {
        return nodeList(root._children.filter((node) => node.getAttribute('data-nav') === 'no'));
      }
      return root.querySelectorAll(selector);
    },
    querySelector: (selector) => {
      if (selector.startsWith('#confidence-group')) {
        const group = registry.get('confidence-group');
        return group ? group.querySelector('[aria-checked="true"]') : null;
      }
      return root.querySelector(selector);
    },
    addEventListener: (name, handler) => root.addEventListener(name, handler),
    fonts: { check: () => true },
  };

  const context = {
    document,
    console,
    Math,
    JSON,
    Number,
    String,
    Object,
    Array,
    Set,
    Map,
    Date,
    Promise,
    Error,
    Infinity,
    NaN,
    isFinite,
    parseInt,
    parseFloat,
    encodeURIComponent,
    requestAnimationFrame: (callback) => {
      callback(0);
      return 1;
    },
    setTimeout: (callback) => context.__timers.push(callback),
    clearTimeout: () => {},
    setInterval: (callback) => context.__intervals.push(callback),
    clearInterval: () => {},
    ResizeObserver: class {
      constructor(callback) {
        this.callback = callback;
        context.__observers.push(this);
      }

      observe(target) {
        this.target = target;
      }

      disconnect() {
        this.disconnected = true;
      }
    },
    fetch: stubFetch(routes, calls),
  };
  context.__timers = [];
  context.__intervals = [];
  context.__observers = [];
  context.window = context;
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(readFileSync(APP_JS, 'utf8'), context, { filename: 'ui/app.js' });

  return {
    app: context,
    document,
    root,
    calls,
    observers: context.__observers,
    element: (id) => document.getElementById(id),
    /* Read a top-level `const`. They live in the context's lexical scope rather than on the
     * context object, so they are reached by evaluating an expression in the same context. */
    value: (expression) => vm.runInContext(expression, context),
    /* Drain the queued callbacks. The interface schedules a countdown repaint; a test that
     * cannot run it cannot reach the paint. */
    tick: () => {
      for (const callback of context.__timers.splice(0)) callback();
      for (const callback of context.__intervals.splice(0)) callback();
    },
    /* Let every pending promise settle. `api` is async, so a view's DOM does not exist until
     * the microtask queue drains. */
    settle: async (turns = 8) => {
      for (let i = 0; i < turns; i += 1) await Promise.resolve();
    },
  };
}
