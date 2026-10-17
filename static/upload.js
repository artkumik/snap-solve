const storageStatus = document.getElementById('storage-status');
const savedImages = document.getElementById('saved-images');
let uploadPreviewURL;
let activeImageId = null;
let deleteNotice = null;

function setActiveQuestion(imageId) {
  activeImageId = imageId;
  savedImages.querySelectorAll('.saved-image').forEach(item => {
    const active = Number(item.dataset.imageId) === imageId;
    item.classList.toggle('is-active', active);
    const button = item.querySelector('.saved-image-open');
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
const RESULT_VERSION = 2;

function showResult(result) {
  document.getElementById('process-output').textContent = result == null ? '' : (
    typeof result === 'string' ? result : JSON.stringify(result, null, 2)
  );
}

function hasSavedResult(image) {
  return image.result != null && !image.result.context_error && image.resultVersion === RESULT_VERSION;
}

function questionTitle(image) {
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

function showUploadPreview(file) {
  const preview = document.getElementById('upload-preview');
  preview.onload = null;
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
  setActiveQuestion(null);
  showDeleteNotice(null, '');
  storageStatus.textContent = '';
  latestRequest++; // ignore any upload still in progress
  document.getElementById('image-result').hidden = true;
  document.getElementById('video-recommendations').hidden = true;
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

// Adds the server's result to an already-saved image record.
async function saveResult(id, result) {
  // Keep the read and write atomic so a late result cannot recreate a deleted question.
  await imageStore('readwrite', store => {
    const request = store.get(id);
    request.onsuccess = () => {
      const record = request.result;
      if (!record) return;
      record.result = result;
      record.resultVersion = RESULT_VERSION;
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
  savedImages.replaceChildren();
  storageStatus.textContent = '';

  for (const image of images.reverse()) {
    const title = questionTitle(image);
    const item = document.createElement('li');
    item.className = 'saved-image';
    item.dataset.imageId = image.id;
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
    use.append(name);
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
    use.title = title;
    use.addEventListener('click', () => {
      menu.open = false;
      setActiveQuestion(image.id);
      showDeleteNotice(null, '');
      storageStatus.textContent = '';
      if (hasSavedResult(image)) {
        // Already processed: show the saved result without asking the server again.
        latestRequest++; // ignore any upload still in progress
        document.getElementById('upload-error').hidden = true;
        document.getElementById('video-recommendations').hidden = false;
        showUploadPreview(image.file);
        showResult(image.result);
        return;
      }
      const input = document.getElementById('upload-image');
      const transfer = new DataTransfer();
      transfer.items.add(image.file);
      input.files = transfer.files;
      updateSelection(input);
      input.form.dataset.imageId = image.id;
      input.form.requestSubmit();
    });
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'Delete';
    remove.setAttribute('aria-label', `Delete ${title}`);
    remove.addEventListener('click', async () => {
      try {
        await deleteSavedImage(image.id);
        await showSavedImages();
      } catch {
        menu.open = false;
        showDeleteNotice(image.id, 'Could not delete this image. Please try again.');
      }
    });
    actions.append(remove);
    menu.append(summary, actions);
    item.append(use, menu, notice);
    savedImages.append(item);
  }
  setActiveQuestion(activeImageId);
}

document.querySelectorAll('.image-picker').forEach(button => {
  const input = document.getElementById(button.getAttribute('aria-controls'));
  updateSelection(input);
  button.addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {
    const picked = input.files[0];
    updateSelection(input);
    if (!picked) return;
    const rejectFile = () => {
      input.value = '';
      updateSelection(input);
      storageStatus.textContent = 'Choose a JPEG, PNG, or WebP image, 10 MB or smaller.';
    };
    if (!ALLOWED_TYPES.includes(picked.type)) return rejectFile();
    // Shrink before the size check, so a large phone photo still works once it's resized.
    const file = await shrinkImage(picked);
    if (file.size > MAX_UPLOAD_BYTES) return rejectFile();
    if (file !== picked) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files; // the submit handler uploads whatever is in the input
      updateSelection(input);
    }
    // Save first so the upload knows which saved record its result belongs to.
    try {
      const id = await imageStore('readwrite', store => store.add({ file, savedAt: Date.now() }));
      input.form.dataset.imageId = id;
      await showSavedImages();
      keepStoragePersistent();
    } catch {
      storageStatus.textContent = 'Could not save locally. Browser storage may be unavailable or full. The image will still be uploaded.';
    }
    input.form.requestSubmit();
  });
});

showSavedImages().catch(() => {
  storageStatus.textContent = 'Browser storage is unavailable. You can still upload images.';
});

document.querySelectorAll('.panel form').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const input = form.querySelector('[type="file"]');
    const file = input.files[0];
    // dataset values are strings, but IndexedDB ids are numbers.
    const imageId = form.dataset.imageId ? Number(form.dataset.imageId) : null;
    delete form.dataset.imageId;
    if (!file) return;
    setActiveQuestion(imageId);
    showDeleteNotice(null, '');
    const requestId = ++latestRequest;
    const isLatest = () => requestId === latestRequest;
    const button = form.querySelector('.image-picker');
    const errorMessage = document.getElementById('upload-error');
    button.disabled = true;
    errorMessage.hidden = true;
    const preview = showUploadPreview(file);
    document.getElementById('video-recommendations').hidden = false;
    preview.onload = () => document.getElementById('image-result').scrollIntoView({
      block: 'start',
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
    });
    document.getElementById('process-output').textContent = 'Processing…';
    try {
      const response = await fetch(form.action, {
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
      if (isLatest()) {
        showResult(data.result);
        input.value = '';
        updateSelection(input);
      }
      // Save the result even if the user moved on, so it's ready next time.
      if (imageId !== null && data.result != null) {
        try {
          await saveResult(imageId, data.result);
          await showSavedImages();
        } catch {
          storageStatus.textContent = 'Could not save the result locally. It will be processed again next time.';
        }
      }
    } catch (error) {
      if (!isLatest()) return;
      document.getElementById('process-output').textContent = '';
      errorMessage.textContent = error.name === 'TimeoutError'
        ? 'Processing took too long. Please try again.'
        : error.message || 'Could not process the image. Please try again.';
      errorMessage.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
});
