(() => {
  const button = document.getElementById('copy-show-link');
  if (!button) return;
  button.addEventListener('click', async () => {
    const input = document.getElementById('show-link');
    try { await navigator.clipboard.writeText(input.value); document.getElementById('copy-status').textContent = 'Посилання скопійовано ✓'; }
    catch (_) { input.focus(); input.select(); document.getElementById('copy-status').textContent = 'Адресу виділено. Натисніть Ctrl+C або оберіть «Копіювати».'; }
  });
})();
