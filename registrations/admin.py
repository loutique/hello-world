import csv

from django.contrib import admin, messages
from django.contrib.admin.views.main import IncorrectLookupParameters
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import RegistrationCampaign, Registration
from .forms import CampaignAdminForm


STATUS_HELP = {
    Registration.Status.PENDING: "Человек зарегистрировался, но список ещё не сверили. Можно оставить этот статус и просто выгрузить файл.",
    Registration.Status.APPROVED: "Вы сверили человека с организаторами и подтвердили его участие. Билет отправляется отдельно в другой программе.",
    Registration.Status.REJECTED: "После сверки участие не подтверждено. Заявка сохраняется, человек не получает уведомления.",
    Registration.Status.TICKET_SENT: "Вы уже отправили билет в другой программе и отмечаете это здесь для себя. Эта кнопка ничего не отправляет.",
}


def status_badge(status):
    return format_html('<span class="status-badge status-{}">{}</span>', status.lower(), Registration.Status(status).label)


def csv_response(queryset):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="registrations.csv"'
    response["Cache-Control"] = "no-store"
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["ID", "Имя", "Фамилия", "Телефон", "Email", "Страница регистрации", "Дата регистрации (Израиль)", "Результат проверки", "Заметки команды"])
    for obj in queryset.select_related("campaign").iterator():
        values = [obj.pk, obj.first_name, obj.last_name, obj.phone, obj.email, obj.campaign.internal_name,
                  timezone.localtime(obj.created_at).isoformat(), obj.get_status_display(), obj.admin_notes]
        row = []
        for value in values:
            value = str(value)
            if value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            row.append(value)
        writer.writerow(row)
    return response


@admin.register(RegistrationCampaign)
class CampaignAdmin(admin.ModelAdmin):
    form = CampaignAdminForm
    change_list_template = "admin/disco/campaign_list.html"
    change_form_template = "admin/disco/campaign_form.html"
    list_display = ["internal_name", "public_page", "availability", "total", "pending", "approved", "rejected", "ticket_sent", "registration_list"]
    list_filter = ["is_active"]
    search_fields = ["internal_name", "slug"]
    search_help_text = "Поиск по внутреннему названию или адресу страницы."
    readonly_fields = ["created_at", "updated_at", "public_page", "share_image_preview"]
    list_per_page = 30
    fieldsets = [
        ("1. Название и ссылка", {"fields": ["internal_name", "slug"], "description": "Внутреннее название — для команды. Адрес страницы — для ссылки, которую вы отправите людям."}),
        ("2. Что увидят посетители", {"fields": ["visual_style", "public_title", "public_subtitle", "intro_text", "success_text", "privacy_text"], "description": "Публичные тексты пишите по-украински. После сохранения они сразу появятся на странице регистрации."}),
        ("3. О мероприятии", {"fields": ["event_title", "event_starts_at", "event_venue", "event_address", "event_summary", "event_description", "event_info_url"], "description": "Этот блок объяснит участникам, куда они регистрируются. Он расположен перед формой отдельно от обращения к волонтёрам."}),
        ("4. Открыть или закрыть регистрацию", {"fields": ["is_active", "closes_at", "closed_text"], "description": "Закрытие убирает форму, но сохраняет все собранные заявки. Ограничений количества регистраций нет."}),
        ("5. Картинка при отправке ссылки в WhatsApp", {"fields": ["share_image_preview", "share_image", "share_image_alt", "remove_share_image"], "description": "Это картинка для превью ссылки в мессенджерах. Она не заменяет афишу внутри страницы и не отправляется людям автоматически."}),
        ("Служебная информация", {"fields": ["public_page", "created_at", "updated_at"], "classes": ["collapse"]}),
    ]

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Текущая картинка")
    def share_image_preview(self, obj):
        if not obj or not obj.share_image_hash:
            return "Отдельная картинка не загружена. Для оформления «Велесова ніч» используется афиша; в универсальном оформлении пока будет только текстовое превью."
        url = reverse("campaign_preview_image", args=[obj.slug, obj.share_image_hash])
        return format_html('<a href="{}" target="_blank" rel="noopener"><img src="{}" alt="{}" style="max-width:260px;max-height:170px;width:auto;height:auto;border-radius:6px"></a><p>{} × {} пикселей · {} КБ после обработки. Открыть картинку можно нажатием на неё.</p>', url, url, obj.share_image_alt or obj.public_title, obj.share_image_width, obj.share_image_height, (obj.share_image_size + 1023) // 1024)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not self.has_change_permission(request, obj) and not (obj is None and self.has_add_permission(request)):
            return [(name, {**options, "fields": [field for field in options["fields"] if field not in {"share_image", "remove_share_image"}]}) for name, options in fieldsets]
        return fieldsets

    def get_list_display(self, request):
        fields = list(super().get_list_display(request))
        if not (request.user.has_perm("registrations.view_registration") or request.user.has_perm("registrations.change_registration")):
            fields.remove("registration_list")
        return fields

    def get_queryset(self, request):
        return super().get_queryset(request).defer("share_image_data").annotate(total_count=Count("registrations"), **{
            status.lower() + "_count": Count("registrations", filter=Q(registrations__status=status))
            for status in Registration.Status.values
        })

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(request, object_id, form_url, {"campaign_id": object_id, **(extra_context or {})})

    @admin.display(description="Публичная ссылка")
    def public_page(self, obj):
        if not obj or not obj.pk:
            return "Появится после сохранения страницы."
        url = reverse("register", args=[obj.slug])
        return format_html('<a href="{}" target="_blank" rel="noopener">/r/{}/</a>', url, obj.slug)

    @admin.display(description="Приём заявок")
    def availability(self, obj):
        if not obj.is_active:
            return format_html('<span class="status-badge status-rejected">Отключён вручную</span>')
        if not obj.is_open:
            return format_html('<span class="status-badge status-pending">Закрыт по времени</span>')
        return format_html('<span class="status-badge status-approved">Открыт</span>')

    @admin.display(description="Всего", ordering="total_count")
    def total(self, obj): return obj.total_count

    @admin.display(description="На проверке", ordering="pending_count")
    def pending(self, obj): return obj.pending_count

    @admin.display(description="Подтверждено", ordering="approved_count")
    def approved(self, obj): return obj.approved_count

    @admin.display(description="Не подтверждено", ordering="rejected_count")
    def rejected(self, obj): return obj.rejected_count

    @admin.display(description="Билет отправлен отдельно", ordering="ticket_sent_count")
    def ticket_sent(self, obj): return obj.ticket_sent_count

    @admin.display(description="Список людей")
    def registration_list(self, obj):
        return format_html('<a class="disco-inline-link" href="{}?campaign__id__exact={}">Посмотреть заявки →</a>', reverse("admin:registrations_registration_changelist"), obj.pk)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    change_list_template = "admin/disco/registration_list.html"
    change_form_template = "admin/disco/registration_form.html"
    list_display = ["id", "first_name", "last_name", "phone", "email", "campaign", "created_at", "status_label", "admin_notes"]
    list_display_links = ["id", "first_name", "last_name"]
    list_filter = ["campaign", "status", ("created_at", admin.DateFieldListFilter)]
    search_fields = ["first_name", "last_name", "phone", "phone_normalized", "email"]
    search_help_text = "Введите имя, фамилию, телефон или email. Чтобы ограничить список, выберите страницу, статус или дату в фильтрах."
    date_hierarchy = "created_at"
    list_select_related = ["campaign"]
    readonly_fields = ["campaign", "first_name", "last_name", "phone", "phone_normalized", "email", "created_at", "updated_at", "approved_at", "rejected_at", "ticket_sent_at"]
    actions = ["approve", "reject", "ticket_sent", "pending", "export_csv"]
    list_per_page = 50
    fieldsets = [
        ("Данные из формы", {"fields": ["first_name", "last_name", "phone", "email", "campaign", "created_at"]}),
        ("Проверка с организаторами", {"fields": ["status", "admin_notes"], "description": "Эти поля видны только команде. Посетитель не получает уведомлений об изменениях."}),
        ("Даты внутренних отметок", {"fields": ["updated_at", "approved_at", "rejected_at", "ticket_sent_at"], "classes": ["collapse"], "description": "Здесь хранятся последние даты соответствующих отметок. Это не подтверждение автоматической отправки билетов."}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).defer("campaign__share_image_data")

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.display(description="Результат проверки", ordering="status")
    def status_label(self, obj):
        return status_badge(obj.status)

    def get_urls(self):
        return [path("export/", self.admin_site.admin_view(self.export_filtered), name="registrations_registration_export")] + super().get_urls()

    def export_filtered(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        try:
            changelist = self.get_changelist_instance(request)
        except IncorrectLookupParameters:
            return HttpResponseBadRequest("Не удалось применить фильтр. Вернитесь к списку заявок и выберите фильтры заново.")
        return csv_response(changelist.queryset)

    def changelist_view(self, request, extra_context=None):
        query = request.GET.urlencode()
        export_url = reverse("admin:registrations_registration_export") + ("?" + query if query else "")
        return super().changelist_view(request, {"export_url": export_url, "status_help": STATUS_HELP, **(extra_context or {})})

    def confirm_status_action(self, request, queryset, status, action):
        count = queryset.count()
        label = Registration.Status(status).label
        if request.POST.get("confirm_status") != "yes":
            return TemplateResponse(request, "admin/disco/confirm_status.html", {
                **self.admin_site.each_context(request), "title": "Подтвердите изменение отметок",
                "opts": self.model._meta, "status_label": label, "status_description": STATUS_HELP[status],
                "selection_count": count, "selection_preview": queryset[:5], "action": action,
                "selected_ids": request.POST.getlist("_selected_action"),
                "select_across": request.POST.get("select_across", "0"),
                "cancel_url": request.get_full_path(),
            })
        with transaction.atomic():
            for registration in queryset.select_for_update().order_by("pk").iterator():
                previous = registration.get_status_display()
                registration.status = status
                registration.save()
                self.log_change(request, registration, f"Результат проверки: {previous} → {label}")
        self.message_user(request, f"Обновлено заявок: {count}. Отметка: «{label}». Письма и билеты никому не отправлялись.", messages.SUCCESS)

    @admin.action(description="Подтвердить после сверки с организаторами", permissions=["change"])
    def approve(self, request, queryset):
        return self.confirm_status_action(request, queryset, Registration.Status.APPROVED, "approve")

    @admin.action(description="Отметить: участие не подтверждено", permissions=["change"])
    def reject(self, request, queryset):
        return self.confirm_status_action(request, queryset, Registration.Status.REJECTED, "reject")

    @admin.action(description="Отметить: билет уже отправлен в другой программе", permissions=["change"])
    def ticket_sent(self, request, queryset):
        return self.confirm_status_action(request, queryset, Registration.Status.TICKET_SENT, "ticket_sent")

    @admin.action(description="Вернуть на проверку", permissions=["change"])
    def pending(self, request, queryset):
        return self.confirm_status_action(request, queryset, Registration.Status.PENDING, "pending")

    @admin.action(description="Скачать только выбранные заявки (CSV)", permissions=["view"])
    def export_csv(self, request, queryset):
        return csv_response(queryset)
