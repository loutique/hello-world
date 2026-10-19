from django.contrib.admin.apps import AdminConfig


class DiscoAdminConfig(AdminConfig):
    default_site = "registrations.admin_site.DiscoAdminSite"
