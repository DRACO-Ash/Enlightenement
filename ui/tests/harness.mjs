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
    this.children = [];
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
    if (this.children.length) return this.children.map((child) => child.textContent).join('');
    return this._text;
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  get firstChild() {
    return this.children[0] ?? null;
  }

  get value() {
    return this._value ?? '';
  }

  set value(next) {
    this._value = String(next);
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  remove() {
    const siblings = this.parentNode?.children;
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
   * without a value, and a class. Anything else throws. */
  querySelectorAll(selector) {
    const all = this.descendants();
    const attribute = selector.match(/^\[([\w-]+)(?:="([^"]*)")?\]$/);
    if (attribute) {
      return all.filter((node) => {
        const held = node.getAttribute(attribute[1]);
        return held !== null && (attribute[2] === undefined || held === attribute[2]);
      });
    }
    if (/^\.[\w-]+$/.test(selector)) {
      return all.filter((node) => node._classes.has(selector.slice(1)));
    }
    if (/^\w+$/.test(selector)) {
      return all.filter((node) => node.tagName === selector.toUpperCase());
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
    for (const child of this.children) {
      if (child._classes.has(className)) found.push(child);
      found.push(...child.find(className));
    }
    return found;
  }

  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
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
      if (selector === '#nav button') {
        return root.children.filter((node) => node.getAttribute('data-nav') === 'yes');
      }
      if (selector === 'main [data-view]') {
        return root.children.filter((node) => node.getAttribute('data-nav') === 'no');
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
