document.querySelectorAll('.image-picker').forEach(button => {
  const input = document.getElementById(button.getAttribute('aria-controls'));
  const submit = input.form.querySelector('[type="submit"]');
  submit.disabled = !input.files.length;
  button.addEventListener('click', () => input.click());
  input.addEventListener('change', () => {
    input.form.querySelector('.selected-file').textContent = input.files[0]?.name || 'No image selected';
    submit.disabled = !input.files.length;
  });
});
