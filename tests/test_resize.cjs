const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { runInNewContext } = require('node:vm');
const { join } = require('node:path');

const handlers = {};
const attributes = { 'aria-valuenow': 50 };
const properties = {};
let captured;
const divider = {
  addEventListener: (type, handler) => { handlers[type] = handler; },
  setAttribute: (key, value) => { attributes[key] = value; },
  getAttribute: key => attributes[key],
  getBoundingClientRect: () => ({ width: 16 }),
  setPointerCapture: id => { captured = id; },
  hasPointerCapture: id => captured === id,
  releasePointerCapture: () => { captured = null; },
  focus() {},
};
const elements = {
  'result-divider': divider,
  'image-result': {
    style: { setProperty: (key, value) => { properties[key] = value; } },
    classList: { add() {}, remove() {} },
  },
  'image-pane': { getBoundingClientRect: () => ({ left: 100 }) },
  'solution-pane': { getBoundingClientRect: () => ({ right: 1132 }) },
};
runInNewContext(readFileSync(join(__dirname, '../static/resize.js'), 'utf8'), {
  document: { getElementById: id => elements[id] },
  getComputedStyle: () => ({ columnGap: '8px' }),
});
handlers.keydown({ key: 'ArrowRight', preventDefault() {} });
assert.equal(attributes['aria-valuenow'], 55);
assert.equal(properties['--solution-share'], '45fr');
handlers.pointerdown({ button: 0, isPrimary: true, pointerId: 1 });
handlers.pointermove({ pointerId: 1, clientX: 816 });
assert.equal(attributes['aria-valuenow'], 70);
handlers.pointermove({ pointerId: 1, clientX: -100 });
assert.equal(attributes['aria-valuenow'], 25);
handlers.pointermove({ pointerId: 1, clientX: 2000 });
assert.equal(attributes['aria-valuenow'], 75);
handlers.pointerup();
assert.equal(captured, null);
handlers.dblclick();
assert.equal(attributes['aria-valuenow'], 50);
console.log('PASS: keyboard resize, pointer resize, width limits, release, and reset');
