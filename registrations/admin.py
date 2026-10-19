import csv
from django.contrib import admin
from django.db.models import Count, Q
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html
from .models import RegistrationCampaign, Registration

admin.site.site_header = "DISCO UKRAÏNA — керування"
admin.site.site_title = "DISCO UKRAÏNA"
admin.site.index_title = "Кампанії та заявки"

@admin.register(RegistrationCampaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ["internal_name", "public_page", "is_active", "total", "pending", "approved", "rejected", "ticket_sent", "registration_list"]
    list_filter = ["is_active"]
    search_fields = ["internal_name", "slug"]
    prepopulated_fields = {"slug": ["internal_name"]}
    readonly_fields = ["created_at", "updated_at"]
    def has_delete_permission(self, request, obj=None):
        return False
    def get_queryset(self, request):
        return super().get_queryset(request).annotate(total_count=Count("registrations"), **{s.lower()+"_count": Count("registrations", filter=Q(registrations__status=s)) for s in Registration.Status.values})
    @admin.display(description="Сторінка")
    def public_page(self, obj):
        return format_html('<a href="{}">/r/{}/</a>', reverse("register", args=[obj.slug]), obj.slug)
    def total(self, obj): return obj.total_count
    def pending(self, obj): return obj.pending_count
    def approved(self, obj): return obj.approved_count
    def rejected(self, obj): return obj.rejected_count
    def ticket_sent(self, obj): return obj.ticket_sent_count
    @admin.display(description="Заявки")
    def registration_list(self, obj):
        return format_html('<a href="{}?campaign__id__exact={}">Переглянути</a>', reverse("admin:registrations_registration_changelist"), obj.pk)

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ["id", "first_name", "last_name", "phone", "email", "campaign", "created_at", "status", "admin_notes"]
    list_filter = ["campaign", "status", ("created_at", admin.DateFieldListFilter)]
    search_fields = ["first_name", "last_name", "phone", "phone_normalized", "email"]
    date_hierarchy = "created_at"
    list_select_related = ["campaign"]
    readonly_fields = ["campaign", "first_name", "last_name", "phone", "phone_normalized", "email", "created_at", "updated_at", "approved_at", "rejected_at", "ticket_sent_at"]
    actions = ["approve", "reject", "ticket_sent", "pending", "export_csv"]
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    def change_status(self, queryset, status):
        for registration in queryset.iterator():
            registration.status = status
            registration.save()
    @admin.action(description="Схвалити")
    def approve(self, request, queryset): self.change_status(queryset, Registration.Status.APPROVED)
    @admin.action(description="Відхилити")
    def reject(self, request, queryset): self.change_status(queryset, Registration.Status.REJECTED)
    @admin.action(description="Позначити: квиток надіслано")
    def ticket_sent(self, request, queryset): self.change_status(queryset, Registration.Status.TICKET_SENT)
    @admin.action(description="Повернути в очікування")
    def pending(self, request, queryset): self.change_status(queryset, Registration.Status.PENDING)
    @admin.action(description="Експортувати вибірку в CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="registrations.csv"'
        response["Cache-Control"] = "no-store"
        response.write("\ufeff")
        writer = csv.writer(response)
        fields = ["id", "first_name", "last_name", "phone", "email", "campaign", "created_at", "status", "admin_notes"]
        writer.writerow(fields)
        for obj in queryset.select_related("campaign").iterator():
            row = []
            for field in fields:
                value = str(getattr(obj, field))
                if value.lstrip().startswith(("=", "+", "-", "@")):
                    value = "'" + value
                row.append(value)
            writer.writerow(row)
        return response
