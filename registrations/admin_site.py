from django.contrib.admin import AdminSite
from django.db.models import Count, Q
from django.template.response import TemplateResponse
from django.urls import path


class DiscoAdminSite(AdminSite):
    site_header = "DISCO UKRAÏNA"
    site_title = "Кабинет организатора"
    index_title = "Обзор регистраций"
    site_url = None
    enable_nav_sidebar = False
    index_template = "admin/disco/index.html"

    def each_context(self, request):
        context = super().each_context(request)
        context.update({
            "can_view_registrations": request.user.has_perm("registrations.view_registration") or request.user.has_perm("registrations.change_registration"),
            "can_view_campaigns": request.user.has_perm("registrations.view_registrationcampaign") or request.user.has_perm("registrations.change_registrationcampaign"),
            "can_add_campaigns": request.user.has_perm("registrations.add_registrationcampaign"),
        })
        return context

    def index(self, request, extra_context=None):
        from .models import Registration, RegistrationCampaign
        context = self.each_context(request)
        if context["can_view_registrations"]:
            context["stats"] = Registration.objects.aggregate(total=Count("id"), **{
                status.lower(): Count("id", filter=Q(status=status))
                for status in Registration.Status.values
            })
        if context["can_view_campaigns"]:
            context["campaigns"] = RegistrationCampaign.objects.defer("share_image_data").annotate(total=Count("registrations")).order_by("-created_at")[:8]
        context.update({"title": self.index_title, "app_list": self.get_app_list(request), **(extra_context or {})})
        return TemplateResponse(request, self.index_template, context)

    def get_urls(self):
        return [path("help/", self.admin_view(self.help_view), name="disco_help")] + super().get_urls()

    def help_view(self, request):
        return TemplateResponse(request, "admin/disco/help.html", {
            **self.each_context(request), "title": "Как пользоваться кабинетом",
        })
