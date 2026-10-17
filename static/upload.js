const storageStatus = document.getElementById('storage-status');
const savedImages = document.getElementById('saved-images');
const previewURLs = [];

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
  input.form.querySelector('[type="submit"]').disabled = !input.files.length;
}

async function showSavedImages() {
  const images = await imageStore('readonly', store => store.getAll());
  previewURLs.splice(0).forEach(url => URL.revokeObjectURL(url));
  savedImages.replaceChildren();
  storageStatus.textContent = images.length ? 'Images stay here until you delete them or browser storage is cleared.' : 'No saved images yet.';

  for (const image of images.reverse()) {
    const item = document.createElement('li');
    item.className = 'saved-image';
    const preview = document.createElement('img');
    preview.src = URL.createObjectURL(image.file);
    previewURLs.push(preview.src);
    preview.alt = image.file.name;
    const name = document.createElement('span');
    name.textContent = image.file.name;
    const use = document.createElement('button');
    use.type = 'button';
    use.textContent = 'Use image';
    use.addEventListener('click', () => {
      const input = document.getElementById('upload-image');
      const transfer = new DataTransfer();
      transfer.items.add(image.file);
      input.files = transfer.files;
      updateSelection(input);
      input.form.querySelector('[type="submit"]').focus();
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
    item.append(preview, name, use, remove);
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
    const submit = input.form.querySelector('[type="submit"]');
    submit.disabled = true;
    button.disabled = true;
    try {
      await imageStore('readwrite', store => store.add({ file, savedAt: Date.now() }));
      await showSavedImages();
    } catch {
      storageStatus.textContent = 'Could not save locally. Browser storage may be unavailable or full. You can still Continue to upload.';
    } finally {
      button.disabled = false;
      updateSelection(input);
    }
  });
});

showSavedImages().catch(() => {
  storageStatus.textContent = 'Browser storage is unavailable. You can still upload images.';
});

let uploadPreviewURL;
document.querySelectorAll('.panel form').forEach(form => {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const file = form.querySelector('[type="file"]').files[0];
    if (!file) return;
    const submit = form.querySelector('[type="submit"]');
    const errorMessage = document.getElementById('upload-error');
    submit.disabled = true;
    errorMessage.hidden = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file,
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Image processing failed.');
      }
      const preview = document.getElementById('upload-preview');
      if (uploadPreviewURL) URL.revokeObjectURL(uploadPreviewURL);
      uploadPreviewURL = URL.createObjectURL(file);
      preview.src = uploadPreviewURL;
      preview.hidden = false;
    } catch (error) {
      errorMessage.textContent = error.message || 'Could not process the image. Please try again.';
      errorMessage.hidden = false;
    } finally {
      submit.disabled = false;
    }
  });
});
