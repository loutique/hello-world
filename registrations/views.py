from django.db import IntegrityError, transaction
from django.conf import settings
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from .models import RegistrationCampaign, SubmissionWindow
from django.utils.crypto import salted_hmac
from django.utils import timezone
from datetime import timedelta
from .forms import RegistrationForm

@never_cache
@require_http_methods(["GET", "POST"])
def register(request, slug):
    campaign = get_object_or_404(RegistrationCampaign, slug=slug)
    form = RegistrationForm(request.POST or None)
    success = request.GET.get("submitted") == "1"
    if request.method == "POST":
        success = False
        if not campaign.is_open:
            return render(request, "registrations/register.html", {"campaign": campaign, "form": form}, status=403)
        # Use the actual peer address; trust forwarded client IP only through a configured proxy.
        bucket = int(timezone.now().timestamp()) // 600
        key = salted_hmac("submission", f"{request.META.get('REMOTE_ADDR', '')}:{bucket}").hexdigest()
        with transaction.atomic():
            window, _ = SubmissionWindow.objects.get_or_create(key=key)
            window = SubmissionWindow.objects.select_for_update().get(pk=window.pk)
            window.attempts += 1
            window.save(update_fields=["attempts"])
        SubmissionWindow.objects.filter(created_at__lt=timezone.now()-timedelta(hours=1)).delete()
        if window.attempts > settings.REGISTRATION_RATE_LIMIT:
            form.add_error(None, "Забагато спроб. Спробуйте ще раз за 10 хвилин.")
            return render(request, "registrations/register.html", {"campaign": campaign, "form": form}, status=429)
        if form.is_valid():
            try:
                with transaction.atomic():
                    campaign = RegistrationCampaign.objects.select_for_update().get(pk=campaign.pk)
                    if not campaign.is_open:
                        return render(request, "registrations/register.html", {"campaign": campaign, "form": form}, status=403)
                    registration = form.save(commit=False)
                    registration.campaign = campaign
                    registration.phone_normalized = form.phone_normalized
                    registration.save()
            except IntegrityError:
                form.add_error(None, "Заявку з таким email або телефоном для цієї сторінки вже отримано.")
            else:
                return redirect(request.path + "?submitted=1")
    return render(request, "registrations/register.html", {"campaign": campaign, "form": form, "success": success})


@never_cache
@require_http_methods(["GET"])
def health(request):
    from django.db import connection, DatabaseError
    from django.http import JsonResponse
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
