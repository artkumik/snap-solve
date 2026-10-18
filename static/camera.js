// Include iPads that identify as desktop Safari, without enabling touch laptops.
const mobileCamera = navigator.userAgentData?.mobile === true || /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
  || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const cameraButton = document.querySelector('[aria-controls="take-image"]');
cameraButton.form.hidden = !mobileCamera;
cameraButton.disabled = !mobileCamera;
cameraButton.title = mobileCamera ? 'Take a photo' : 'Camera is available on mobile devices';
