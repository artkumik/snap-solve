const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const source = readFileSync(require('node:path').join(__dirname, '../static/camera.js'), 'utf8');

for (const [userAgent, platform, maxTouchPoints, enabled, mobile] of [
  ['Reduced user agent', '', 5, true, true],
  ['Mozilla/5.0 (iPhone)', 'iPhone', 5, true],
  ['Mozilla/5.0 (Linux; Android 14)', 'Linux', 5, true],
  ['Mozilla/5.0 (iPad)', 'iPad', 5, true],
  ['Mozilla/5.0 (Macintosh)', 'MacIntel', 5, true],
  ['Mozilla/5.0 (Macintosh)', 'MacIntel', 0, false],
  ['Mozilla/5.0 (Windows NT 10.0)', 'Win32', 10, false],
  ['Mozilla/5.0 (X11; Linux x86_64)', 'Linux x86_64', 0, false],
]) {
  const button = { form: {} };
  vm.runInNewContext(source, {
    navigator: { userAgent, platform, maxTouchPoints, userAgentData: { mobile } },
    document: { querySelector: () => button },
  });
  assert.equal(button.form.hidden, !enabled, userAgent + ' / ' + platform);
  assert.equal(button.disabled, !enabled, userAgent + ' / ' + platform);
}
console.log('Camera availability checks passed for phones, tablets, desktops, and touch laptops.');
