const storageStatus = document.getElementById('storage-status');
const savedImages = document.getElementById('saved-images');
let uploadPreviewURL;
let activeImageId = null;
let deleteNotice = null;
let failedUpload = null;
let activeFile = null;
let activeQuestion = '';
const sidebar = document.querySelector('.saved-images');
const processingQuestions = new Map();
let sidebarCloseTimer;
const hoverSidebar = window.matchMedia('(hover: hover) and (pointer: fine)');
sidebar.addEventListener('pointerenter', () => {
  if (!hoverSidebar.matches) return;
  clearTimeout(sidebarCloseTimer);
  sidebar.classList.remove('is-collapsing');
  if (!sidebar.open) {
    sidebar.classList.add('is-preview', 'is-collapsing');
    sidebar.open = true;
    // Paint the collapsed edge first so hover expansion always transitions.
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (sidebar.classList.contains('is-preview')) sidebar.classList.remove('is-collapsing');
    }));
  }
});
sidebar.addEventListener('pointerleave', () => {
  if (!sidebar.classList.contains('is-preview')) return;
  clearTimeout(sidebarCloseTimer);
  sidebarCloseTimer = setTimeout(() => {
    sidebar.classList.add('is-collapsing');
    sidebarCloseTimer = setTimeout(() => {
      sidebar.open = false;
      sidebar.classList.remove('is-preview', 'is-collapsing');
    }, 180);
  }, 100);
});
sidebar.addEventListener('click', event => {
  if (!sidebar.classList.contains('is-preview')) return;
  // A preview already has open=true; keep the summary click from closing it.
  if (event.target.closest('summary') === sidebar.querySelector(':scope > summary')) event.preventDefault();
  clearTimeout(sidebarCloseTimer);
  sidebar.classList.remove('is-preview', 'is-collapsing');
});
sidebar.addEventListener('toggle', () => {
  if (!sidebar.open) {
    clearTimeout(sidebarCloseTimer);
    sidebar.classList.remove('is-preview', 'is-collapsing');
  }
});

function closeNameEditor() {
  document.getElementById('question-name-editor').hidden = true;
  document.getElementById('question-title').hidden = false;
  document.getElementById('rename-question').setAttribute('aria-expanded', 'false');
}

document.getElementById('rename-question').addEventListener('click', () => {
  if (!document.getElementById('question-name-editor').hidden) return;
  const field = document.getElementById('question-name');
  field.value = document.getElementById('question-title').textContent;
  document.getElementById('question-name-error').hidden = true;
  document.getElementById('question-name-editor').hidden = false;
  document.getElementById('question-title').hidden = true;
  document.getElementById('rename-question').setAttribute('aria-expanded', 'true');
  field.focus();
  field.select();
});
document.getElementById('question-name').addEventListener('blur', () => {
  const editor = document.getElementById('question-name-editor');
  if (!editor.hidden) editor.requestSubmit();
});
document.getElementById('question-name').addEventListener('input', event => event.target.setCustomValidity(''));
document.getElementById('question-name-editor').addEventListener('submit', async event => {
  event.preventDefault();
  const field = document.getElementById('question-name');
  if (field.disabled || event.currentTarget.hidden) return;
  const title = field.value.trim();
  if (!title) {
    closeNameEditor();
    return;
  }
  const imageId = activeImageId;
  field.disabled = true;
  try {
    await imageStore('readwrite', store => {
      const request = store.get(imageId);
      request.onsuccess = () => {
        if (!request.result) throw new Error('Question no longer exists');
        store.put({ ...request.result, title });
      };
      return request;
    });
    if (activeImageId === imageId) closeNameEditor();
    await showSavedImages();
  } catch {
    const error = document.getElementById('question-name-error');
    error.textContent = 'Could not save the name. Please try again.';
    error.hidden = false;
  } finally {
    field.disabled = false;
  }
});

function closeProblemEditor() {
  document.getElementById('problem-editor').hidden = true;
  document.getElementById('problem-title').hidden = false;
  document.getElementById('edit-problem').setAttribute('aria-expanded', 'false');
}

document.getElementById('edit-problem').addEventListener('click', () => {
  if (!document.getElementById('problem-editor').hidden) return;
  const title = document.getElementById('problem-title');
  const width = title.getBoundingClientRect().width;
  document.getElementById('actual-problem').value = activeQuestion || document.getElementById('problem-title').textContent;
  document.getElementById('problem-edit-error').hidden = true;
  document.getElementById('problem-editor').hidden = false;
  title.hidden = true;
  const field = document.getElementById('actual-problem');
  field.style.width = `${width}px`;
  field.style.height = 'auto';
  field.style.height = `${field.scrollHeight}px`;
  document.getElementById('edit-problem').setAttribute('aria-expanded', 'true');
  document.getElementById('actual-problem').focus();
});
document.getElementById('cancel-problem-edit').addEventListener('click', () => {
  closeProblemEditor();
  document.getElementById('edit-problem').focus();
});
document.getElementById('actual-problem').addEventListener('input', event => {
  event.target.setCustomValidity('');
  event.target.style.height = 'auto';
  event.target.style.height = `${event.target.scrollHeight}px`;
});
document.getElementById('problem-editor').addEventListener('submit', async event => {
  event.preventDefault();
  if (!activeFile) return;
  const field = document.getElementById('actual-problem');
  const question = field.value.trim();
  if (!question) {
    field.setCustomValidity('Enter the actual problem.');
    field.reportValidity();
    return;
  }
  const file = activeFile;
  const imageId = activeImageId;
  const save = event.currentTarget.querySelector('[type="submit"]');
  save.disabled = true;
  try {
    if (imageId !== null) {
      await imageStore('readwrite', store => {
        const request = store.get(imageId);
        request.onsuccess = () => {
          const record = request.result;
          if (!record) return;
          record.question = question;
          delete record.result;
          delete record.resultVersion;
          store.put(record);
        };
        return request;
      });
    }
    if (activeImageId !== imageId || activeFile !== file) return;
    const input = document.getElementById('upload-image');
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    if (imageId !== null) input.form.dataset.imageId = imageId;
    input.form.dataset.question = question;
    input.form.requestSubmit();
  } catch {
    const error = document.getElementById('problem-edit-error');
    error.textContent = 'Could not save your problem. Please try again.';
    error.hidden = false;
  } finally {
    save.disabled = false;
  }
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !document.getElementById('delete-all-confirmation').hidden) {
    document.getElementById('cancel-delete-all').click();
    return;
  }
  if (event.key === 'Escape' && !document.getElementById('question-name-editor').hidden) {
    closeNameEditor();
    document.getElementById('rename-question').focus();
    return;
  }
  if (event.key === 'Escape' && !document.getElementById('problem-editor').hidden) {
    closeProblemEditor();
    document.getElementById('edit-problem').focus();
    return;
  }
  if (event.key === 'Escape' && sidebar.open) {
    sidebar.open = false;
    sidebar.querySelector('summary').focus({ preventScroll: true });
  }
});
document.addEventListener('pointerdown', event => {
  if (window.matchMedia('(max-width: 900px)').matches && sidebar.open && !sidebar.contains(event.target)) {
    sidebar.open = false;
  }
});

document.getElementById('retry-processing').addEventListener('click', () => {
  if (!failedUpload) return;
  const input = document.getElementById('upload-image');
  const transfer = new DataTransfer();
  transfer.items.add(failedUpload.file);
  input.files = transfer.files;
  if (failedUpload.imageId !== null) input.form.dataset.imageId = failedUpload.imageId;
  input.form.dataset.question = failedUpload.question || '';
  input.form.requestSubmit();
});

async function markQuestionOpened(imageId) {
  await imageStore('readwrite', store => {
    const request = store.get(imageId);
    request.onsuccess = () => {
      if (request.result) store.put({ ...request.result, opened: true });
    };
    return request;
  });
}

function setActiveQuestion(imageId) {
  if (activeImageId !== imageId) closeNameEditor();
  activeImageId = imageId;
  const current = [...savedImages.children].find(item => Number(item.dataset.imageId) === imageId);
  if (current?.classList.contains('is-unread')) {
    current.classList.remove('is-unread');
    current.querySelector('.saved-image-open')?.setAttribute('aria-label', current.dataset.title);
    markQuestionOpened(imageId).catch(() => {
      storageStatus.textContent = 'Could not save the opened status. The unread dot may return after reloading.';
    });
  }
  document.getElementById('question-title').textContent = current?.dataset.title || 'Untitled question';
  document.getElementById('rename-question').disabled = imageId === null;
  savedImages.querySelectorAll('.saved-image').forEach(item => {
    const active = Number(item.dataset.imageId) === imageId;
    item.classList.toggle('is-active', active);
    const button = item.querySelector('.saved-image-open');
    if (!button) return;
    if (active) button.setAttribute('aria-current', 'true');
    else button.removeAttribute('aria-current');
  });
}

function showDeleteNotice(imageId, message) {
  deleteNotice = message ? { imageId, message } : null;
  savedImages.querySelectorAll('.saved-image').forEach(item => {
    const notice = item.querySelector('.delete-notice');
    const matches = deleteNotice && Number(item.dataset.imageId) === imageId;
    notice.textContent = matches ? message : '';
    notice.hidden = !matches;
    if (matches) notice.scrollIntoView({ block: 'nearest' });
  });
}
// Bump this whenever the Python processing changes, so results saved by older code are redone.
const RESULT_VERSION = 10; // 10: explicit processing success with detected line bounds

function isIncorrect(line) {
  return line.valid === false || line.follows_from_previous === false || !!line.error;
}

function selectStep(index) {
  document.querySelector('.selection-hint')?.remove();
  document.querySelectorAll('.solution-line').forEach((item, i) => {
    item.hidden = i !== index;
    item.classList.toggle('is-selected', i === index);
  });
  document.querySelectorAll('.line-box').forEach(button => {
    button.setAttribute('aria-pressed', String(Number(button.dataset.step) === index));
  });
  const item = document.getElementById(`solution-step-${index}`);
  item.focus({ preventScroll: true });
  item.scrollIntoView({ block: 'nearest', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
}

function showLineBoxes(lines) {
  const overlay = document.getElementById('line-overlays');
  overlay.replaceChildren();
  lines.forEach((line, index) => {
    const bounds = line.bounds;
    if (!bounds) return;
    const { left, right, top, bottom } = bounds;
    if (![left, right, top, bottom].every(value => Number.isFinite(value) && value >= 0 && value <= 1)
        || right <= left || bottom <= top) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'line-box';
    if (!isIncorrect(line)) button.classList.add(line.valid === true ? 'is-correct' : 'is-unchecked');
    button.dataset.step = index;
    button.setAttribute('aria-label', `Show details for line ${line.line ?? index + 1}`);
    button.setAttribute('aria-controls', `solution-step-${index}`);
    button.setAttribute('aria-pressed', 'false');
    button.style.setProperty('--box-left', `${left * 100}%`);
    button.style.setProperty('--box-top', `${top * 100}%`);
    button.style.setProperty('--box-width', `${(right - left) * 100}%`);
    button.style.setProperty('--box-height', `${(bottom - top) * 100}%`);
    button.addEventListener('click', () => selectStep(index));
    button.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
      event.preventDefault();
      const boxes = [...overlay.querySelectorAll('.line-box')];
      const direction = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
      const next = boxes[(boxes.indexOf(button) + direction + boxes.length) % boxes.length];
      next.click();
      next.focus({ preventScroll: true });
    });
    overlay.append(button);
  });
}

function showResult(result) {
  const output = document.getElementById('process-output');
  output.replaceChildren();
  showLineBoxes(Array.isArray(result?.lines) ? result.lines : []);
  if (typeof result === 'string') output.textContent = result;
  const context = result?.context;
  document.getElementById('problem-summary').hidden = false;
  document.getElementById('problem-label').textContent = activeQuestion ? 'Your problem' : 'Problem';
  document.getElementById('problem-title').textContent = activeQuestion || context?.goal || context?.task || 'Add the original problem';
  if (result?.context_error) {
    const warning = document.createElement('p');
    warning.className = 'result-warning';
    warning.textContent = result.context_error;
    output.append(warning);
  }
  if (Array.isArray(result?.lines)) {
    const lines = document.createElement('ol');
    lines.className = 'solution-lines';
    result.lines.forEach((line, index) => {
      const item = document.createElement('li');
      item.className = 'solution-line';
      item.hidden = true;
      item.id = `solution-step-${index}`;
      item.tabIndex = -1;
      const heading = document.createElement('div');
      heading.className = 'line-heading';
      const title = document.createElement('strong');
      title.textContent = `Line ${line.line ?? index + 1}`;
      const invalid = isIncorrect(line);
      const status = document.createElement('span');
      status.className = `line-status ${invalid ? 'is-invalid' : line.valid === true ? 'is-valid' : 'is-unchecked'}`;
      status.textContent = invalid ? 'Invalid' : line.valid === true ? 'Valid' : 'Not checked';
      heading.append(title, status);
      const equation = document.createElement('p');
      equation.className = 'line-math';
      equation.textContent = line.latex || '';
      item.append(heading, equation);
      const error = line.error || line.transition_error || (line.follows_from_previous === false
        ? 'This step does not follow from the previous line; the two lines are not equivalent.' : '');
      if (error) {
        const message = document.createElement('p');
        message.className = 'line-error';
        message.textContent = error;
        item.append(message);
      } else if (result.mode !== 'line_detection' && index > 0 && line.follows_from_previous == null) {
        const message = document.createElement('p');
        message.className = 'line-note';
        message.textContent = 'The step from the previous line could not be verified.';
        item.append(message);
      }
      lines.append(item);
    });
    output.append(lines);
    if (result.lines.length) {
      const hint = document.createElement('p');
      hint.className = 'selection-hint';
      hint.textContent = result.mode === 'line_detection' ? 'Select a highlighted line.' : 'Select a step on your work to see feedback.';
      output.append(hint);
    } else if (result.mode === 'line_detection') {
      output.textContent = 'No lines detected.';
    }
  }
  showVideos(result?.videos, result?.context?.video_query);
}

// Fills the "Related videos" cards from the server's list of {id, title, channel}, plus a
// button that opens the same search on YouTube. Without embedded videos (e.g. no YouTube key)
// the button still shows; the section hides only when there is nothing to search for.
const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;
function showVideos(videos, query) {
  const valid = (Array.isArray(videos) ? videos : []).filter(video => YOUTUBE_ID.test(video?.id));
  const section = document.getElementById('video-recommendations');
  const search = typeof query === 'string' ? query.trim() : '';
  section.hidden = valid.length === 0 && !search;
  section.querySelector('.video-grid').hidden = valid.length === 0;
  let link = section.querySelector('.video-search');
  if (!link) {
    link = document.createElement('a');
    link.className = 'video-search';
    link.target = '_blank';
    link.rel = 'noopener';
    section.append(link);
  }
  link.hidden = !search;
  if (search) {
    link.href = `https://www.youtube.com/results?search_query=${encodeURIComponent(search)}`;
    link.textContent = valid.length ? 'More on YouTube ↗' : 'Search YouTube ↗';
    link.title = search;
    link.setAttribute('aria-label', `Search YouTube for ${search} (opens in a new tab)`);
  }
  document.querySelectorAll('#video-recommendations .video-card').forEach((card, i) => {
    const video = valid[i];
    const frame = card.querySelector('.video-embed');
    let caption = card.querySelector('.video-caption');
    if (!caption) {
      caption = document.createElement('p');
      caption.className = 'video-caption';
      card.append(caption);
    }
    card.hidden = !video;
    if (!video) {
      if (frame.getAttribute('src') !== 'about:blank') frame.src = 'about:blank'; // stops playback
      caption.replaceChildren();
      return;
    }
    const src = `https://www.youtube-nocookie.com/embed/${video.id}`;
    if (frame.src !== src) frame.src = src;
    frame.title = video.title || `Related video ${i + 1}`;
    const title = document.createElement('span');
    title.className = 'video-title';
    title.textContent = video.title || '';
    const channel = document.createElement('span');
    channel.className = 'video-channel';
    channel.textContent = video.channel || '';
    caption.replaceChildren(title, channel);
  });
}

function hasSavedResult(image) {
  return image.result?.success === true && image.result.mode === 'line_detection'
    && Array.isArray(image.result.lines)
    && !image.result.context_error
    && image.resultVersion === RESULT_VERSION;
}

function questionTitle(image) {
  if (image.title) return image.title;
  if (image.question) return image.question;
  const context = image.result?.context;
  const title = [context?.goal, context?.task, context?.problem_latex]
    .find(value => typeof value === 'string' && value.trim());
  return title ? title.trim().replace(/\s+/g, ' ') : image.file.name;
}

// Only the most recent request may update the screen, so a slow earlier upload
// can't overwrite the result of the image you're looking at now.
let latestRequest = 0;

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
// Longest side, in pixels, that photos are shrunk to before they are saved and uploaded.
// Phone photos are often 4000+ px; this is plenty for reading handwriting and makes them
// several times smaller to send, store in the browser, and decode on the server.
const MAX_SIDE = 2048;

async function shrinkImage(file) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    return file; // can't decode here; the server will report the problem
  }
  const scale = MAX_SIDE / Math.max(bitmap.width, bitmap.height);
  if (scale >= 1) {
    bitmap.close();
    return file; // already small enough: keep the original exactly
  }
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const context = canvas.getContext('2d');
  context.fillStyle = '#fff'; // transparent areas become white instead of black
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
  if (!blob || blob.size >= file.size) return file;
  const name = file.name.replace(/\.[^.]*$/, '') + '.jpg';
  return new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified });
}

// Ask the browser not to clear saved images when the device is low on space.
async function keepStoragePersistent() {
  try {
    if (navigator.storage?.persist && !(await navigator.storage.persisted())) {
      await navigator.storage.persist();
    }
  } catch {
    // Not supported; images are still saved, just evictable.
  }
}

function showUploadPreview(file, question = '') {
  activeFile = file;
  activeQuestion = question;
  closeProblemEditor();
  document.getElementById('problem-summary').hidden = false;
  document.getElementById('problem-label').textContent = question ? 'Your problem' : 'Problem';
  document.getElementById('problem-title').textContent = question || 'Add the original problem';
  failedUpload = null;
  document.getElementById('retry-processing').hidden = true;
  document.getElementById('line-overlays').replaceChildren();
  const preview = document.getElementById('upload-preview');
  preview.onload = () => document.getElementById('image-result').scrollIntoView({
    block: 'start',
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
  });
  if (uploadPreviewURL) URL.revokeObjectURL(uploadPreviewURL);
  uploadPreviewURL = URL.createObjectURL(file);
  preview.src = uploadPreviewURL;
  preview.hidden = false;
  document.getElementById('image-result').hidden = false;
  document.getElementById('launch-screen').hidden = true;
  document.getElementById('process-output').textContent = '';
  return preview;
}

function showHome() {
  activeFile = null;
  activeQuestion = '';
  closeProblemEditor();
  document.getElementById('launch-feedback').textContent = '';
  failedUpload = null;
  document.getElementById('retry-processing').hidden = true;
  setActiveQuestion(null);
  showDeleteNotice(null, '');
  storageStatus.textContent = '';
  latestRequest++; // ignore any upload still in progress
  const preview = document.getElementById('upload-preview');
  preview.onload = null;
  preview.removeAttribute('src');
  preview.hidden = true;
  if (uploadPreviewURL) URL.revokeObjectURL(uploadPreviewURL);
  uploadPreviewURL = null;
  document.getElementById('line-overlays').replaceChildren();
  document.getElementById('process-output').replaceChildren();
  document.getElementById('image-result').hidden = true;
  showVideos([]);
  document.getElementById('upload-error').hidden = true;
  document.getElementById('launch-screen').hidden = false;
  document.querySelectorAll('.panel input[type="file"]').forEach(input => {
    input.value = '';
    updateSelection(input);
  });
  document.querySelector('.image-picker').focus({ preventScroll: true });
  document.getElementById('launch-screen').scrollIntoView({
    block: 'start',
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
  });
}

document.getElementById('new-image').addEventListener('click', showHome);

const database = new Promise((resolve, reject) => {
  const request = indexedDB.open('snap-solve', 1);
  request.onupgradeneeded = () => {
    request.result.createObjectStore('images', { keyPath: 'id', autoIncrement: true });
  };
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error);
  request.onblocked = () => {
    storageStatus.textContent = 'Close other snap solve tabs to enable saved images.';
  };
});

async function imageStore(mode, action) {
  const db = await database;
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('images', mode);
    const request = action(transaction.objectStore('images'));
    transaction.oncomplete = () => resolve(request.result);
    transaction.onabort = () => reject(transaction.error);
    transaction.onerror = () => reject(transaction.error);
  });
}

async function deleteSavedImage(imageId) {
  await imageStore('readwrite', store => store.delete(imageId));
  if (imageId === activeImageId) showHome();
}

document.getElementById('delete-all-questions').addEventListener('click', () => {
  document.getElementById('delete-all-confirmation').hidden = false;
  document.getElementById('cancel-delete-all').focus();
});
document.getElementById('cancel-delete-all').addEventListener('click', () => {
  document.getElementById('delete-all-confirmation').hidden = true;
  document.getElementById('delete-all-questions').focus();
});
document.getElementById('confirm-delete-all').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await imageStore('readwrite', store => store.clear());
    document.getElementById('delete-all-confirmation').hidden = true;
    showHome();
    await showSavedImages();
  } catch {
    storageStatus.textContent = 'Could not delete all questions. Please try again.';
  } finally {
    button.disabled = false;
  }
});

async function saveProcessingStatus(id, question, status, error = '') {
  if (id === null) return;
  await imageStore('readwrite', store => {
    const request = store.get(id);
    request.onsuccess = () => {
      const record = request.result;
      if (record && (record.question || '') === question) store.put({ ...record, status, processingError: error });
    };
    return request;
  });
}

// Adds the server's result to an already-saved image record.
async function saveResult(id, result, question = '') {
  // Keep the read and write atomic so a late result cannot recreate a deleted question.
  await imageStore('readwrite', store => {
    const request = store.get(id);
    request.onsuccess = () => {
      const record = request.result;
      if (!record || (record.question || '') !== question) return;
      record.result = result;
      record.resultVersion = RESULT_VERSION;
      record.status = 'ready';
      delete record.processingError;
      store.put(record);
    };
    return request;
  });
}

function updateSelection(input) {
  input.form.querySelector('.selected-file').textContent = input.files[0]?.name || 'No image selected';
}

async function showSavedImages() {
  const images = await imageStore('readonly', store => store.getAll());
  document.getElementById('delete-all-questions').disabled = images.length === 0;
  if (!images.length) document.getElementById('delete-all-confirmation').hidden = true;
  savedImages.replaceChildren();
  storageStatus.textContent = '';

  for (const image of images.reverse()) {
    const title = questionTitle(image);
    const item = document.createElement('li');
    item.className = 'saved-image';
    item.classList.toggle('is-unread', image.opened === false);
    item.dataset.imageId = image.id;
    item.dataset.title = title;
    const notice = document.createElement('p');
    notice.className = 'delete-notice';
    notice.setAttribute('role', 'status');
    notice.textContent = deleteNotice?.imageId === image.id ? deleteNotice.message : '';
    notice.hidden = !notice.textContent;
    const menu = document.createElement('details');
    menu.className = 'image-menu';
    const summary = document.createElement('summary');
    summary.setAttribute('aria-label', `Actions for ${title}`);
    const name = document.createElement('span');
    name.textContent = title;
    const dots = document.createElement('span');
    dots.className = 'image-menu-dots';
    dots.textContent = '⋮';
    dots.setAttribute('aria-hidden', 'true');
    summary.append(dots);
    const actions = document.createElement('div');
    actions.className = 'image-menu-actions';
    const use = document.createElement('button');
    use.type = 'button';
    use.className = 'saved-image-open';
    if (image.opened === false) use.setAttribute('aria-label', `${title}, unopened`);
    use.append(name);
    const state = image.status || (hasSavedResult(image) ? 'ready' : 'failed');
    item.dataset.status = state;
    const statusLabel = { queued: 'Queued', processing: 'Processing', failed: 'Failed', ready: 'Ready' }[state] || 'Failed';
    if (image.opened === false) {
      use.setAttribute('aria-label', `${title}, unopened, ${statusLabel.toLowerCase()}`);
      use.title = `${title} — ${statusLabel}`;
    }
    if (Number.isFinite(image.savedAt)) {
      const created = document.createElement('time');
      const date = new Date(image.savedAt);
      created.className = 'question-created';
      created.dateTime = date.toISOString();
      created.textContent = date.toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: 'numeric', minute: '2-digit',
      });
      created.title = `Created ${date.toLocaleString()}`;
      use.append(created);
    }
    if (image.opened !== false) use.title = title;
    use.addEventListener('click', () => {
      menu.open = false;
      setActiveQuestion(image.id);
      showDeleteNotice(null, '');
      storageStatus.textContent = '';
      if (processingQuestions.has(image.id)) {
        latestRequest++;
        showUploadPreview(image.file, image.question || '');
        document.getElementById('process-output').textContent = 'Processing…';
        return;
      }
      if (hasSavedResult(image)) {
        // Already processed: show the saved result without asking the server again.
        latestRequest++; // ignore any upload still in progress
        document.getElementById('upload-error').hidden = true;
        showUploadPreview(image.file, image.question || '');
        showResult(image.result);
        return;
      }
      const input = document.getElementById('upload-image');
      const transfer = new DataTransfer();
      transfer.items.add(image.file);
      input.files = transfer.files;
      updateSelection(input);
      input.form.dataset.imageId = image.id;
      input.form.dataset.question = image.question || '';
      input.form.requestSubmit();
    });
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Delete';
    remove.setAttribute('aria-label', `Delete ${title}`);
    remove.className = 'delete-question-action';
    remove.addEventListener('click', async () => {
      remove.disabled = true;
      try {
        await deleteSavedImage(image.id);
        await showSavedImages();
      } catch {
        menu.open = false;
        showDeleteNotice(image.id, 'Could not delete this image. Please try again.');
      } finally {
        remove.disabled = false;
      }
    });
    const rename = document.createElement('button');
    rename.type = 'button';
    rename.textContent = 'Rename';
    rename.addEventListener('click', () => {
      menu.open = false;
      if (item.querySelector('.sidebar-name-editor')) return;
      const editor = document.createElement('form');
      editor.className = 'sidebar-name-editor';
      const field = document.createElement('input');
      field.type = 'text';
      field.value = title;
      field.maxLength = 120;
      field.required = true;
      field.setAttribute('aria-label', 'Question name');
      editor.append(field);
      const created = use.querySelector('time');
      if (created) editor.append(created.cloneNode(true));
      use.replaceWith(editor);
      let finished = false;
      const cancel = () => {
        finished = true;
        editor.replaceWith(use);
      };
      const save = async () => {
        if (finished) return;
        const newTitle = field.value.trim();
        if (!newTitle || newTitle === title) {
          cancel();
          return;
        }
        finished = true;
        field.disabled = true;
        try {
          await imageStore('readwrite', store => {
            const request = store.get(image.id);
            request.onsuccess = () => {
              if (request.result) store.put({ ...request.result, title: newTitle });
            };
            return request;
          });
          await showSavedImages();
        } catch {
          editor.replaceWith(use);
          showDeleteNotice(image.id, 'Could not save the name. Please try again.');
        }
      };
      editor.addEventListener('submit', event => {
        event.preventDefault();
        save();
      });
      field.addEventListener('blur', save);
      field.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          cancel();
          use.focus();
        }
      });
      field.focus();
      field.select();
    });
    actions.append(rename, remove);
    menu.append(summary, actions);
    item.append(use, menu, notice);
    if (state === 'failed') {
      const failure = document.createElement('div');
      failure.className = 'question-failure';
      const message = document.createElement('p');
      message.textContent = image.processingError || 'Processing did not finish. Try again.';
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.textContent = 'Retry';
      retry.setAttribute('aria-label', `Retry ${title}`);
      retry.addEventListener('click', () => {
        retry.disabled = true;
        processUpload(document.getElementById('upload-image').form, image.file, image.id, image.question || '', activeImageId === image.id);
      });
      failure.append(message, retry);
      item.append(failure);
    }
    savedImages.append(item);
  }
  setActiveQuestion(activeImageId);
}

document.querySelectorAll('.image-picker').forEach(button => {
  const input = document.getElementById(button.getAttribute('aria-controls'));
  updateSelection(input);
  button.addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {
    const picked = Array.from(input.files);
    if (!picked.length) return;
    document.getElementById('launch-feedback').textContent = '';
    input.value = '';
    updateSelection(input);
    button.disabled = true;
    const rejected = [];
    const uploads = [];
    try {
      for (const original of picked) {
        if (!ALLOWED_TYPES.includes(original.type)) {
          rejected.push(original.name);
          continue;
        }
        const file = await shrinkImage(original);
        if (file.size > MAX_UPLOAD_BYTES) {
          rejected.push(original.name);
          continue;
        }
        let imageId = null;
        try {
          imageId = await imageStore('readwrite', store => store.add({ file, savedAt: Date.now(), opened: false, status: 'queued' }));
        } catch {
          storageStatus.textContent = 'Could not save locally. The image will still be uploaded.';
        }
        uploads.push({ file, imageId });
      }
      await showSavedImages().catch(() => {});
      if (uploads.length) keepStoragePersistent();
      // Each file gets its own question and request; keep later uploads in the background.
      for (const [index, upload] of uploads.entries()) {
        button.disabled = true;
        await processUpload(input.form, upload.file, upload.imageId, '', index === 0);
      }
    } finally {
      button.disabled = false;
      if (rejected.length) {
        const message = `Skipped ${rejected.join(', ')}. Each image must be JPEG, PNG, or WebP and 10 MB or smaller after resizing.`;
        document.getElementById('launch-feedback').textContent = message;
        if (uploads.length) {
          const error = document.getElementById('upload-error');
          error.textContent = message;
          error.hidden = false;
        }
      }
    }
  });
});

async function restoreSavedQuestions() {
  // Requests do not survive a reload. Preserve their images and offer a retry.
  await imageStore('readwrite', store => {
    const request = store.getAll();
    request.onsuccess = () => {
      for (const record of request.result) {
        if (record.status === 'queued' || record.status === 'processing') {
          store.put({ ...record, status: 'failed', processingError: 'Upload interrupted. Please retry.' });
        }
      }
    };
    return request;
  });
  await showSavedImages();
}
const restoredQuestions = restoreSavedQuestions();
restoredQuestions.catch(() => {
  storageStatus.textContent = 'Browser storage is unavailable. You can still upload images.';
});

document.querySelectorAll('.panel form').forEach(form => {
  form.addEventListener('submit', event => {
    event.preventDefault();
    const file = form.querySelector('[type="file"]').files[0];
    const imageId = form.dataset.imageId ? Number(form.dataset.imageId) : null;
    const question = form.dataset.question || '';
    delete form.dataset.imageId;
    delete form.dataset.question;
    if (file) processUpload(form, file, imageId, question);
  });
});

async function processUpload(form, file, imageId = null, question = '', display = true) {
  await restoredQuestions.catch(() => {});
  if (imageId !== null) {
    if (processingQuestions.get(imageId) === question) return;
    const record = await imageStore('readonly', store => store.get(imageId)).catch(() => null);
    if (!record || (record.question || '') !== question) return;
    if (!display && record.status === 'ready' && hasSavedResult(record)) return;
    // Recheck after the asynchronous read to prevent a duplicate queued request.
    if (processingQuestions.get(imageId) === question) return;
    processingQuestions.set(imageId, question);
  }
  const input = form.querySelector('[type="file"]');
  if (display) setActiveQuestion(imageId);
  showDeleteNotice(null, '');
  const requestId = display ? ++latestRequest : latestRequest;
  const isLatest = () => (display && requestId === latestRequest) || (imageId !== null && activeImageId === imageId && activeQuestion === question);
  const button = form.querySelector('.image-picker');
  const errorMessage = document.getElementById('upload-error');
  button.disabled = true;
  if (display) {
    errorMessage.hidden = true;
    showUploadPreview(file, question);
    showVideos([]); // the previous problem's videos don't belong to this one
    document.getElementById('process-output').textContent = 'Processing…';
  }
  try {
    await saveProcessingStatus(imageId, question, 'processing').catch(() => {});
    await showSavedImages().catch(() => {});
    const url = new URL(form.action);
    if (question) url.searchParams.set('question', question);
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
      signal: AbortSignal.timeout(90_000), // stop waiting after 90 s
    });
    // Errors from a hosting proxy (e.g. 502) are HTML pages, not JSON.
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `Image processing failed (error ${response.status}).`);
    }
    if (data.result?.success !== true || data.result.mode !== 'line_detection' || !Array.isArray(data.result.lines) || data.result.context_error) {
      throw new Error(data.result?.context_error || 'No processing result was returned. Please retry.');
    }
    if (isLatest()) {
      showResult(data.result);
      input.value = '';
      updateSelection(input);
    }
    // Save the result even if the user moved on, so it's ready next time.
    if (imageId !== null) {
      try {
        await saveResult(imageId, data.result, question);
        await showSavedImages();
      } catch {
        storageStatus.textContent = 'Could not save the result locally. It will be processed again next time.';
      }
    }
  } catch (error) {
    const message = error.name === 'TimeoutError'
      ? 'Processing took too long. Please try again.'
      : error.message || 'Could not process the image. Please try again.';
    await saveProcessingStatus(imageId, question, 'failed', message).catch(() => {});
    await showSavedImages().catch(() => {});
    if (!isLatest()) return;
    document.getElementById('process-output').textContent = '';
    errorMessage.textContent = message;
    errorMessage.hidden = false;
    failedUpload = { file, imageId, question };
    document.getElementById('retry-processing').hidden = false;
  } finally {
    if (processingQuestions.get(imageId) === question) processingQuestions.delete(imageId);
    button.disabled = false;
  }
}
