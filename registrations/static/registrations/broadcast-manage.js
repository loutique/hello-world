(() => {
  document.querySelectorAll('[data-copy-target]').forEach(button => {
    button.addEventListener('click', async () => {
      const input=document.getElementById(button.dataset.copyTarget);
      const status=document.getElementById('copy-status');
      try { await navigator.clipboard.writeText(input.value);status.textContent='Посилання скопійовано ✓'; }
      catch (_) { input.focus();input.select();status.textContent='Адресу виділено. Натисніть Ctrl+C або оберіть «Копіювати».'; }
    });
  });
})();
