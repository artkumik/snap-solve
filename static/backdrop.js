// Launch-screen background: a wave drawn as a pixel-dither pattern.
//
// Every dot uses one of the theme's own colors (--background, --surface, --panel, --inset),
// read live from style.css, so the pattern always matches the palette exactly. Dots are a
// whole number of device pixels, so they stay perfectly square and sharp on any screen.
(() => {
  const PALETTE = ['--background', '--surface', '--panel', '--inset'];
  const DOT = 3; // dot size in CSS pixels
  // Wave shape, measured from the original design, as fractions of the launch area's size.
  const CENTER = 0.486, AMPLITUDE = 0.132, PHASE = -0.594, SPREAD = 0.081;
  // Brightness across the wave, in palette steps above --background: PEAK at the center,
  // fading as exp(-(distance / FALLOFF) ^ SHARPNESS). Fitted to the original design's look.
  const PEAK = 2.286, FALLOFF = 1.763, SHARPNESS = 2.091;
  // 4x4 ordered-dither thresholds: blends two neighboring palette colors as an even dot pattern.
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];

  const launch = document.getElementById('launch-screen');
  const canvas = document.createElement('canvas');
  canvas.className = 'backdrop';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);

  // Resolve each CSS variable to [r, g, b], whatever color syntax style.css uses.
  function readPalette() {
    const probe = document.createElement('span');
    document.body.append(probe);
    const colors = PALETTE.map(name => {
      probe.style.color = `var(${name})`;
      return getComputedStyle(probe).color.match(/[\d.]+/g).slice(0, 3).map(Number);
    });
    probe.remove();
    return colors;
  }

  function draw() {
    if (launch.hidden) return;
    const dpr = window.devicePixelRatio || 1;
    const dot = Math.max(1, Math.round(DOT * dpr)); // whole device pixels per dot
    // Anchor the pattern to the viewport so sidebar and content changes cannot shift it.
    const frameWidth = Math.max(document.documentElement.clientWidth, 1);
    const frameHeight = Math.max(window.innerHeight, 1);
    const cols = Math.ceil((frameWidth * dpr) / dot);
    const rows = Math.ceil((frameHeight * dpr) / dot);
    canvas.width = cols;
    canvas.height = rows;
    canvas.style.width = `${(cols * dot) / dpr}px`;
    canvas.style.height = `${(rows * dot) / dpr}px`;

    const colors = readPalette();
    const top = colors.length - 1;
    const cssPerDot = dot / dpr;

    const context = canvas.getContext('2d');
    const image = context.createImageData(cols, rows);
    const pixels = image.data;
    for (let c = 0; c < cols; c++) {
      const x = (c + 0.5) * cssPerDot / frameWidth;
      const centerY = CENTER + AMPLITUDE * Math.sin(2 * Math.PI * x + PHASE);
      for (let r = 0; r < rows; r++) {
        const distance = ((r + 0.5) * cssPerDot / frameHeight - centerY) / SPREAD;
        const level = PEAK * Math.exp(-Math.pow(Math.abs(distance) / FALLOFF, SHARPNESS));
        const base = Math.floor(level);
        const threshold = (BAYER[(r % 4) * 4 + (c % 4)] + 0.5) / 16;
        const [red, green, blue] = colors[Math.min(base + (level - base > threshold ? 1 : 0), top)];
        const i = (r * cols + c) * 4;
        pixels[i] = red;
        pixels[i + 1] = green;
        pixels[i + 2] = blue;
        pixels[i + 3] = 255;
      }
    }
    context.putImageData(image, 0, 0);
  }

  let queued = false;
  function redraw() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      draw();
    });
  }

  window.addEventListener('resize', redraw);
  new MutationObserver(redraw).observe(launch, { attributes: true, attributeFilter: ['hidden'] });
  draw();
})();
