"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const hint = document.getElementById("disco-action-hint");
  const actions = document.querySelectorAll('select[name="action"]');
  const descriptions = {
    approve: "Подтвердит выбранные заявки после вашей сверки с организаторами. Сначала появится экран подтверждения. Билеты и письма не отправляются.",
    reject: "Отметит выбранные заявки как неподтверждённые. Записи сохранятся, уведомления людям не отправляются. Сначала проверьте выбор на экране подтверждения.",
    ticket_sent: "Только отметка о том, что вы уже отправили билеты в другой программе. Система ничего не отправляет. Сначала появится подтверждение.",
    pending: "Вернёт выбранные заявки в статус «На проверке». Можно использовать, если решение нужно пересмотреть. Сначала появится подтверждение.",
    delete_selected: "Удалит выбранные заявки без возможности восстановления. Сначала появится экран с количеством и именами: проверьте его перед подтверждением. Страницы регистрации сохранятся.",
    export_csv: "Скачает CSV только с выбранными заявками. Чтобы скачать весь список с учётом фильтров, используйте кнопку «Скачать список» выше.",
  };
  actions.forEach((select) => {
    select.addEventListener("change", () => {
      if (hint) hint.textContent = descriptions[select.value] || "Выберите строки и действие. Перед изменением статуса появится пояснение и подтверждение.";
    });
  });
  const currentPath = window.location.pathname;
  document.querySelectorAll(".disco-nav a").forEach((link) => {
    const path = new URL(link.href).pathname;
    if ((path === "/admin/" && currentPath === path) || (path !== "/admin/" && currentPath.startsWith(path))) {
      link.setAttribute("aria-current", "page");
    }
  });
});
