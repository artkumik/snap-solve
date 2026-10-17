// Launch-screen background: an ocean swell, bobbing in place, drawn as a pixel-dither pattern.
//
// Every dot uses one of the theme's own colors (--background, --surface, --panel, --inset),
// read live from style.css, so the pattern always matches the palette exactly. Dots are a
// whole number of device pixels on a fixed grid: the wave moves, but the dots never do;
// each frame only changes which palette color each dot shows.
(() => {
  const PALETTE = ['--background', '--surface', '--panel', '--inset'];
  const DOT = 3; // dot size in CSS pixels
  // Wave shape, measured from the original design, as fractions of the viewport's size.
  const CENTER = 0.486, AMPLITUDE = 0.132, PHASE = -0.594, SPREAD = 0.081;
  // Brightness across the wave, in palette steps above --background: PEAK at the center,
  // fading as exp(-(distance / FALLOFF) ^ SHARPNESS). Fitted to the original design's look.
  const PEAK = 2.286, FALLOFF = 1.763, SHARPNESS = 2.091;
  // 4x4 ordered-dither thresholds: blends two neighboring palette colors as an even dot pattern.
  const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];

  // Motion: the wave only moves up and down, never sideways, but its shape keeps changing.
  // It's built from standing waves: each bumps up and down in place at its own rhythm (a
  // fixed shape along x, times a pulse in time), so parts of the wave rise while others dip,
  // like sloshing water. Heights are fractions of the screen height; periods are seconds.
  // At time 0 it matches the still design.
  const BOB_HEIGHT = 0.03, BOB_PERIOD = 5;        // the whole wave bobs
  const SWELL_AMOUNT = 0.2, SWELL_PERIOD = 7;     // the main crest and trough deepen and flatten
  const RIPPLES = [                               // extra bumps: [height, bumps across, offset, period, timing]
    [0.020, 2, 0.4, 5.5, 0.0],
    [0.010, 3, 1.9, 4.3, 0.0],
  ];
  const BREATHE_AMOUNT = 0.08, BREATHE_PERIOD = 6; // the band thickens and thins
  // The clock advances by at most this much per frame, so a hiccup (a slow frame, the window
  // losing focus, a remote-desktop stall) slows the wave for a moment instead of making it jump.
  const MAX_STEP = 0.05; // seconds
  const TAU = 2 * Math.PI;

  // Brightness falloff precomputed in a table, so each frame does no exp/pow per dot.
  const STEPS = 256, REACH = 6; // table resolution; beyond REACH spreads the wave is invisible
  const falloff = new Float32Array(REACH * STEPS);
  for (let i = 0; i < falloff.length; i++) {
    falloff[i] = Math.exp(-Math.pow(i / STEPS / FALLOFF, SHARPNESS));
  }
  const thresholds = Float32Array.from(BAYER, value => (value + 0.5) / 16);

  const launch = document.getElementById('launch-screen');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const canvas = document.createElement('canvas');
  canvas.className = 'backdrop';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const context = canvas.getContext('2d');

  // Resolve each CSS variable to a packed RGBA pixel, whatever color syntax style.css uses.
  function readPalette() {
    const probe = document.createElement('span');
    document.body.append(probe);
    const colors = PALETTE.map(name => {
      probe.style.color = `var(${name})`;
      const [red, green, blue] = getComputedStyle(probe).color.match(/[\d.]+/g).map(Number);
      return ((255 << 24) | (blue << 16) | (green << 8) | red) >>> 0; // RGBA bytes, little-endian
    });
    probe.remove();
    return Uint32Array.from(colors);
  }

  let cols = 0, rows = 0, image = null, pixels = null, colors = null;
  let rowY = null, columnX = null, centers = null, scales = null, peaks = null;

  // Size the dot grid to the viewport. Called on start and whenever the window changes.
  function setup() {
    const dpr = window.devicePixelRatio || 1;
    const dot = Math.max(1, Math.round(DOT * dpr)); // whole device pixels per dot
    const width = Math.max(document.documentElement.clientWidth, 1);
    const height = Math.max(window.innerHeight, 1);
    cols = Math.ceil((width * dpr) / dot);
    rows = Math.ceil((height * dpr) / dot);
    canvas.width = cols;
    canvas.height = rows;
    canvas.style.width = `${(cols * dot) / dpr}px`;
    canvas.style.height = `${(rows * dot) / dpr}px`;
    const cssPerDot = dot / dpr;
    columnX = Float32Array.from({ length: cols }, (_, c) => ((c + 0.5) * cssPerDot) / width);
    rowY = Float32Array.from({ length: rows }, (_, r) => ((r + 0.5) * cssPerDot) / height);
    centers = new Float32Array(cols);
    scales = new Float32Array(cols);
    peaks = new Float32Array(cols);
    image = context.createImageData(cols, rows);
    pixels = new Uint32Array(image.data.buffer);
    colors = readPalette();
  }

  function render(seconds) {
    const top = colors.length - 1;
    const bob = BOB_HEIGHT * Math.sin((TAU * seconds) / BOB_PERIOD);
    const swell = AMPLITUDE * (1 + SWELL_AMOUNT * Math.sin((TAU * seconds) / SWELL_PERIOD));
    const ripples = RIPPLES.map(([height, bumps, offset, period, timing]) =>
      [height * Math.sin((TAU * seconds) / period + timing), bumps, offset]);
    const scale = STEPS / (SPREAD * (1 + BREATHE_AMOUNT * Math.sin((TAU * seconds) / BREATHE_PERIOD)));
    // Per column: where the wave's center is. Every term is (fixed shape along x) x (pulse in
    // time), so nothing travels sideways; each part of the wave just moves up and down.
    for (let c = 0; c < cols; c++) {
      const x = columnX[c];
      let center = CENTER + bob + swell * Math.sin(TAU * x + PHASE);
      for (const [height, bumps, offset] of ripples) center += height * Math.sin(TAU * bumps * x + offset);
      centers[c] = center;
      scales[c] = scale;
      peaks[c] = PEAK;
    }
    for (let r = 0, i = 0; r < rows; r++) {
      const y = rowY[r];
      const bayerRow = (r & 3) << 2;
      for (let c = 0; c < cols; c++, i++) {
        const index = (Math.abs(y - centers[c]) * scales[c]) | 0;
        const level = index < falloff.length ? peaks[c] * falloff[index] : 0;
        const base = level | 0;
        // The threshold depends only on the dot's fixed grid position, so the dither pattern
        // stays locked to the grid while the wave moves through it.
        const shade = base + (level - base > thresholds[bayerRow | (c & 3)] ? 1 : 0);
        pixels[i] = colors[shade > top ? top : shade];
      }
    }
    context.putImageData(image, 0, 0);
  }

  // Animation time: only advances while the wave is animating, and by small steps, so
  // pausing and resuming (switching tabs or windows) picks up exactly where it left off.
  let running = false, clock = 0, lastNow = null;

  // Draws on every screen refresh (each frame takes ~1-2 ms), so the motion is evenly paced on
  // 60, 120 or 144 Hz screens alike.
  function tick(now) {
    if (!running) return;
    requestAnimationFrame(tick);
    if (lastNow !== null) clock += Math.min((now - lastNow) / 1000, MAX_STEP);
    lastNow = now;
    render(clock);
  }

  // Animate only while the launch screen is showing, the tab is visible, and the visitor
  // hasn't asked their device for reduced motion (then the wave is drawn once, still).
  function update() {
    if (launch.hidden) {
      running = false;
      return;
    }
    if (!image) setup();
    const animate = !document.hidden && !reducedMotion.matches;
    if (animate && !running) {
      running = true;
      lastNow = null; // don't count the time spent paused
      requestAnimationFrame(tick);
    } else if (!animate) {
      running = false;
      render(clock);
    }
  }

  let resizeQueued = false;
  window.addEventListener('resize', () => {
    if (resizeQueued) return;
    resizeQueued = true;
    requestAnimationFrame(() => {
      resizeQueued = false;
      if (launch.hidden) {
        image = null; // set up again when the launch screen comes back
        return;
      }
      setup();
      render(clock);
    });
  });
  document.addEventListener('visibilitychange', update);
  reducedMotion.addEventListener('change', update);
  new MutationObserver(update).observe(launch, { attributes: true, attributeFilter: ['hidden'] });
  update();
})();
