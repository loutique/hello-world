from django.db import models
from django.core.validators import RegexValidator
from django.utils import timezone

class RegistrationCampaign(models.Model):
    seed_key = models.CharField(max_length=80, null=True, blank=True, unique=True, editable=False)
    internal_name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True, validators=[RegexValidator(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "Use lowercase letters, numbers and single hyphens.")])
    public_title = models.CharField(max_length=200)
    public_subtitle = models.CharField(max_length=200, blank=True)
    intro_text = models.TextField()
    success_text = models.TextField()
    privacy_text = models.TextField(default="Ваші дані використовуються лише для опрацювання цієї заявки та зв’язку щодо запрошення.")
    closed_text = models.TextField(default="Реєстрацію завершено.")
    is_active = models.BooleanField(default=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_open(self):
        return self.is_active and (self.closes_at is None or timezone.now() < self.closes_at)

    def __str__(self):
        return self.internal_name

class Registration(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Очікує"
        APPROVED = "APPROVED", "Схвалено"
        REJECTED = "REJECTED", "Відхилено"
        TICKET_SENT = "TICKET_SENT", "Квиток надіслано"
    campaign = models.ForeignKey(RegistrationCampaign, on_delete=models.PROTECT, related_name="registrations")
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=40)
    phone_normalized = models.CharField(max_length=16)
    email = models.EmailField(max_length=254)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    ticket_sent_at = models.DateTimeField(null=True, blank=True)
    class Meta:
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
    created_at = models.DateTimeField(auto_now_add=True)
