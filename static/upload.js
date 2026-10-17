const storageStatus = document.getElementById('storage-status');
const savedImages = document.getElementById('saved-images');
let uploadPreviewURL;
// Bump this whenever the Python processing changes, so results saved by older code are redone.
const RESULT_VERSION = 3; // 3: results include related videos (redo ones saved without)

function showResult(result) {
  document.getElementById('process-output').textContent = result == null ? '' : (
    typeof result === 'string' ? result : JSON.stringify(result, null, 2)
  );
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
    link.textContent = valid.length ? `More videos on YouTube: ${search}` : `Watch tutorials on YouTube: ${search}`;
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
  return image.result != null && image.resultVersion === RESULT_VERSION;
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

document.getElementById('new-image').addEventListener('click', () => {
  latestRequest++; // ignore any upload still in progress
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
});

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

// Adds the server's result to an already-saved image record.
async function saveResult(id, result) {
  const record = await imageStore('readonly', store => store.get(id));
  if (!record) return; // image was deleted while processing
  record.result = result;
  record.resultVersion = RESULT_VERSION;
  await imageStore('readwrite', store => store.put(record));
}

function updateSelection(input) {
  input.form.querySelector('.selected-file').textContent = input.files[0]?.name || 'No image selected';
}

async function showSavedImages() {
  const images = await imageStore('readonly', store => store.getAll());
  savedImages.replaceChildren();
  storageStatus.textContent = '';

  for (const image of images.reverse()) {
    const item = document.createElement('li');
    item.className = 'saved-image';
    const menu = document.createElement('details');
    menu.className = 'image-menu';
    const summary = document.createElement('summary');
    summary.setAttribute('aria-label', `Actions for ${image.file.name}`);
    const name = document.createElement('span');
    name.textContent = image.file.name;
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
    use.title = image.file.name;
    use.addEventListener('click', () => {
      menu.open = false;
      if (hasSavedResult(image)) {
        // Already processed: show the saved result without asking the server again.
        latestRequest++; // ignore any upload still in progress
        document.getElementById('upload-error').hidden = true;
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
    remove.setAttribute('aria-label', `Delete ${image.file.name}`);
    remove.addEventListener('click', async () => {
      try {
        await imageStore('readwrite', store => store.delete(image.id));
        await showSavedImages();
      } catch {
        storageStatus.textContent = 'Could not delete this image. Please try again.';
      }
    });
    actions.append(remove);
    menu.append(summary, actions);
    item.append(use, menu);
    savedImages.append(item);
  }
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
    const requestId = ++latestRequest;
    const isLatest = () => requestId === latestRequest;
    const button = form.querySelector('.image-picker');
    const errorMessage = document.getElementById('upload-error');
    button.disabled = true;
    errorMessage.hidden = true;
    const preview = showUploadPreview(file);
    showVideos([]); // the previous problem's videos don't belong to this one
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
      // Only save complete results: if Gemini didn't answer (e.g. missing key), retry next time.
      if (imageId !== null && data.result != null && data.result.context != null) {
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
