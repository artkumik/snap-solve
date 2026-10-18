const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/upload.js'), 'utf8');
const start = source.indexOf('const closingMenus = new WeakMap();');
const end = source.indexOf('\nconst processingQuestions', start);
assert.ok(start >= 0 && end > start);
let click, reducedMotion = false, animationCount = 0, finish;
const inside = {};
const actions = {
  animate(frames, options) {
    animationCount++;
    assert.equal(options.duration, 120);
    let resolve, reject;
    const finished = new Promise((yes, no) => { resolve = yes; reject = no; });
    finish = resolve;
    return { finished, cancel: () => reject(new Error('cancelled')) };
  },
};
const menu = { open: true, contains: target => target === inside, querySelector: () => actions };
vm.runInNewContext(source.slice(start, end), {
  window: { matchMedia: () => ({ matches: reducedMotion }) },
  getComputedStyle: () => ({ opacity: '1' }),
  document: {
    addEventListener: (type, handler) => { click = handler; },
    querySelectorAll: () => menu.open ? [menu] : [],
  },
});
(async () => {
  click({ target: inside });
  assert.equal(animationCount, 0);
  click({ target: {} });
  assert.equal(menu.open, true, 'Stays open during fade');
  click({ target: {} });
  assert.equal(animationCount, 1, 'Repeated outside clicks do not restart fade');
  finish();
  await Promise.resolve();
  assert.equal(menu.open, false);
  menu.open = true;
  click({ target: {} });
  click({ target: inside });
  finish();
  await Promise.resolve();
  assert.equal(menu.open, true, 'Clicking back inside cancels dismissal');
  reducedMotion = true;
  click({ target: {} });
  assert.equal(menu.open, false, 'Reduced motion closes immediately');
  console.log('Menu fade checks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
