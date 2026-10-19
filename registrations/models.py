from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone

class RegistrationCampaign(models.Model):
    class VisualStyle(models.TextChoices):
        CLASSIC = "classic", "Универсальное — без афиши события"
        VELES = "veles2026", "Велесова ніч 2026 — с афишей мероприятия"

    visual_style = models.CharField("Оформление страницы", max_length=20, choices=VisualStyle.choices, default=VisualStyle.CLASSIC, help_text="Выберите оформление с афишей для ближайшей вечеринки или универсальное для других событий. Тексты ниже можно менять в обоих вариантах.")
    page_texts = models.JSONField(default=dict, blank=True, editable=False)
    share_image_data = models.BinaryField(null=True, blank=True, editable=False)
    share_image_hash = models.CharField(max_length=64, blank=True, editable=False)
    share_image_size = models.PositiveIntegerField(default=0, editable=False)
    share_image_mime = models.CharField(max_length=32, blank=True, editable=False)
    share_image_width = models.PositiveIntegerField(null=True, blank=True, editable=False)
    share_image_height = models.PositiveIntegerField(null=True, blank=True, editable=False)
    share_image_alt = models.CharField("Описание картинки", max_length=200, blank=True, help_text="Необязательно. Коротко опишите изображение на украинском для доступности. Если оставить пустым, используем заголовок страницы.")
    seed_key = models.CharField(max_length=80, null=True, blank=True, unique=True, editable=False)
    internal_name = models.CharField("Название для команды", max_length=160, help_text="Видно только в админке. Например: Здибанки — волонтёры, 30 октября.")
    slug = models.SlugField("Адрес страницы", unique=True, help_text="Часть ссылки после /r/. Только маленькие латинские буквы, цифры и одиночные дефисы: zdybanky, special-guests. После изменения старая ссылка перестанет работать.", validators=[RegexValidator(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "Используйте маленькие латинские буквы, цифры и одиночные дефисы.")])
    public_title = models.CharField("Заголовок страницы", max_length=200, help_text="Главный заголовок, который увидят посетители. Пишите по-украински.")
    public_subtitle = models.CharField("Подзаголовок", max_length=200, blank=True, help_text="Необязательно. Например: название события, дата и город.")
    event_title = models.CharField("Заголовок блока о мероприятии", max_length=160, default="Про подію", help_text="Публичный заголовок на украинском. Например: Про Велесову ніч.")
    event_starts_at = models.DateTimeField("Начало мероприятия", null=True, blank=True, help_text="Необязательно. Покажем дату и время перед формой. Укажите время Израиля (Asia/Jerusalem). Это не дата закрытия регистрации.")
    event_venue = models.CharField("Название места", max_length=160, blank=True, help_text="Например: CALLAS TLV. Будет видно посетителям рядом с датой.")
    event_address = models.CharField("Адрес мероприятия", max_length=240, blank=True, help_text="Только адрес площадки, не личные адреса участников. Например: Menachem Begin 37, Тель-Авів.")
    event_summary = models.TextField("Коротко о мероприятии", blank=True, help_text="Два-три предложения на украинском, которые видны сразу перед формой.")
    event_description = models.TextField("Подробности для участников", blank=True, help_text="Программа, костюмы, еда и другие полезные детали на украинском. Посетитель сможет раскрыть этот текст перед формой. Пустая строка разделяет абзацы.")
    event_info_url = models.URLField("Ссылка на подробности", blank=True, help_text="Необязательно. Обычная страница с информацией о событии. Не вставляйте сюда персональные ссылки или ссылки на бесплатные билеты.")
    intro_text = models.TextField("Текст перед формой", help_text="Объясните, для кого регистрация и что произойдёт после неё. Пустая строка разделяет абзацы. HTML не нужен.")
    success_text = models.TextField("Сообщение после регистрации", help_text="Посетитель увидит этот текст на сайте после сохранения заявки. Это не письмо: система ничего не отправляет.")
    privacy_text = models.TextField("Уведомление о данных", help_text="Коротко объясните, зачем собираются имя, телефон и email. Текст показывается под формой.", default="Ваші дані використовуються лише для опрацювання цієї заявки та зв’язку щодо запрошення.")
    closed_text = models.TextField("Сообщение о закрытии", help_text="Показывается вместо формы, если приём отключён или наступило время закрытия.", default="Реєстрацію завершено.")
    is_active = models.BooleanField("Принимать заявки", default=True, help_text="Снимите галочку, чтобы закрыть форму. Уже собранные заявки сохранятся.")
    closes_at = models.DateTimeField("Автоматически закрыть", null=True, blank=True, help_text="Необязательно. Дата и время по часовому поясу Израиля (Asia/Jerusalem). Оставьте пустым для ручного закрытия.")
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Последнее изменение", auto_now=True)

    class Meta:
        verbose_name = "страница регистрации"
        verbose_name_plural = "Страницы регистрации"

    @property
    def public_copy(self):
        from .public_copy import resolved_public_copy
        return resolved_public_copy(self.page_texts)

    @property
    def is_open(self):
        return self.is_active and (self.closes_at is None or timezone.now() < self.closes_at)

    def __str__(self):
        return self.internal_name

class Registration(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "На проверке"
        APPROVED = "APPROVED", "Подтверждено"
        REJECTED = "REJECTED", "Не подтверждено"
        TICKET_SENT = "TICKET_SENT", "Билет отправлен отдельно"
    campaign = models.ForeignKey(RegistrationCampaign, verbose_name="Страница регистрации", on_delete=models.PROTECT, related_name="registrations")
    first_name = models.CharField("Имя", max_length=80)
    last_name = models.CharField("Фамилия", max_length=80)
    phone = models.CharField("Телефон", max_length=40)
    phone_normalized = models.CharField("Телефон для проверки дублей", max_length=16)
    email = models.EmailField("Email", max_length=254)
    status = models.CharField("Результат проверки", max_length=16, choices=Status.choices, default=Status.PENDING, help_text="Внутренняя отметка для вашей команды. Изменение статуса не отправляет человеку ни письмо, ни билет. Если вы работаете только с файлом, статус можно не менять.")
    admin_notes = models.TextField("Заметки команды", blank=True, help_text="Только для организаторов: например, с кем сверили человека. Посетители сайта этих заметок не видят.")
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Последнее изменение", auto_now=True)
    approved_at = models.DateTimeField("Последнее подтверждение", null=True, blank=True)
    rejected_at = models.DateTimeField("Последний отказ", null=True, blank=True)
    ticket_sent_at = models.DateTimeField("Последняя отметка об отправке", null=True, blank=True)
    class Meta:
        verbose_name = "заявка"
        verbose_name_plural = "Заявки"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["campaign", "email"], name="campaign_email_unique"), models.UniqueConstraint(fields=["campaign", "phone_normalized"], name="campaign_phone_unique")]
        indexes = [models.Index(fields=["campaign", "status", "created_at"])]
    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        old = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first() if self.pk else None
        if old != self.status:
            field = {"APPROVED": "approved_at", "REJECTED": "rejected_at", "TICKET_SENT": "ticket_sent_at"}.get(self.status)
            if field:
                setattr(self, field, timezone.now())
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class SubmissionWindow(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
