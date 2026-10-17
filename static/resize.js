const resultLayout = document.getElementById('image-result');
const divider = document.getElementById('result-divider');
let activePointer = null;

function resizePanes(share) {
  share = Math.round(Math.max(25, Math.min(75, share)));
  resultLayout.style.setProperty('--image-share', `${share}fr`);
  resultLayout.style.setProperty('--solution-share', `${100 - share}fr`);
  divider.setAttribute('aria-valuenow', share);
}

divider.addEventListener('pointerdown', event => {
  if (event.button !== 0 || !event.isPrimary) return;
  activePointer = event.pointerId;
  divider.setPointerCapture(activePointer);
  divider.focus({ preventScroll: true });
  resultLayout.classList.add('resizing');
});

divider.addEventListener('pointermove', event => {
  if (event.pointerId !== activePointer) return;
  const left = document.getElementById('image-pane').getBoundingClientRect().left;
  const right = document.getElementById('solution-pane').getBoundingClientRect().right;
  const gap = parseFloat(getComputedStyle(resultLayout).columnGap);
  const handle = divider.getBoundingClientRect().width;
  const available = right - left - handle - gap * 2;
  if (available > 0) resizePanes((event.clientX - left - gap - handle / 2) / available * 100);
});

for (const eventName of ['pointerup', 'pointercancel', 'lostpointercapture']) {
  divider.addEventListener(eventName, () => {
    if (activePointer !== null && divider.hasPointerCapture(activePointer)) {
      divider.releasePointerCapture(activePointer);
    }
    activePointer = null;
    resultLayout.classList.remove('resizing');
  });
}

divider.addEventListener('keydown', event => {
  const current = Number(divider.getAttribute('aria-valuenow'));
  const next = { ArrowLeft: current - 5, ArrowRight: current + 5, Home: 25, End: 75 }[event.key];
  if (next === undefined) return;
  event.preventDefault();
  resizePanes(next);
});

divider.addEventListener('dblclick', () => resizePanes(50));
