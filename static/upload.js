const storageStatus = document.getElementById('storage-status');
const savedImages = document.getElementById('saved-images');
let uploadPreviewURL;

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
      const input = document.getElementById('upload-image');
      const transfer = new DataTransfer();
      transfer.items.add(image.file);
      input.files = transfer.files;
      updateSelection(input);
      menu.open = false;
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
    const file = input.files[0];
    updateSelection(input);
    if (!file) return;
    if (file.size > 10 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      input.value = '';
      updateSelection(input);
      storageStatus.textContent = 'Choose a JPEG, PNG, or WebP image, 10 MB or smaller.';
      return;
    }
    input.form.requestSubmit();
    try {
      await imageStore('readwrite', store => store.add({ file, savedAt: Date.now() }));
      await showSavedImages();
    } catch {
      storageStatus.textContent = 'Could not save locally. Browser storage may be unavailable or full. The image will still be uploaded.';
    }
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
    if (!file) return;
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
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Image processing failed.');
      }
      document.getElementById('process-output').textContent = data.result == null ? '' : (
        typeof data.result === 'string' ? data.result : JSON.stringify(data.result)
      );
      input.value = '';
      updateSelection(input);
    } catch (error) {
      errorMessage.textContent = error.message || 'Could not process the image. Please try again.';
      errorMessage.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
});
