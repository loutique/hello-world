from django.conf import settings
from django.utils import translation


class AdminLanguageMiddleware:
    """Keep the organizer workspace language separate from public pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith("/admin/"):
            with translation.override(settings.ADMIN_LANGUAGE):
                return self.get_response(request)
        return self.get_response(request)
