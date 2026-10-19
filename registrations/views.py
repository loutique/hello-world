from django.db import IntegrityError, transaction
from django.conf import settings
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods, require_safe
from django.views.decorators.cache import never_cache
from .models import RegistrationCampaign, SubmissionWindow
from django.utils.crypto import salted_hmac
from django.utils import timezone
from datetime import timedelta
from .forms import RegistrationForm
from .link_preview import link_preview

@never_cache
@require_http_methods(["GET", "HEAD", "POST"])
def register(request, slug):
    campaign = get_object_or_404(RegistrationCampaign.objects.defer("share_image_data"), slug=slug)
    form = RegistrationForm(request.POST or None)
    success = request.GET.get("submitted") == "1"
    if request.method == "POST":
        success = False
        if not campaign.is_open:
            return render(request, "registrations/register.html", {"campaign": campaign, "form": form, **link_preview(request, campaign)}, status=403)
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
            return render(request, "registrations/register.html", {"campaign": campaign, "form": form, **link_preview(request, campaign)}, status=429)
        if form.is_valid():
            try:
                with transaction.atomic():
                    campaign = RegistrationCampaign.objects.defer("share_image_data").select_for_update().get(pk=campaign.pk)
                    if not campaign.is_open:
                        return render(request, "registrations/register.html", {"campaign": campaign, "form": form, **link_preview(request, campaign)}, status=403)
                    registration = form.save(commit=False)
                    registration.campaign = campaign
                    registration.phone_normalized = form.phone_normalized
                    registration.save()
            except IntegrityError:
                form.add_error(None, "Заявку з таким email або телефоном для цієї сторінки вже отримано.")
            else:
                return redirect(request.path + "?submitted=1")
    return render(request, "registrations/register.html", {"campaign": campaign, "form": form, "success": success, **link_preview(request, campaign)})


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


@require_safe
def campaign_preview_image(request, slug, version):
    from django.http import HttpResponse, HttpResponseNotModified, Http404
    from django.utils.http import parse_etags
    campaign = get_object_or_404(
        RegistrationCampaign.objects.only("share_image_data", "share_image_hash", "share_image_mime"),
        slug=slug, share_image_hash=version,
    )
    if not campaign.share_image_data:
        raise Http404
    etag = '"' + campaign.share_image_hash + '"'
    matches = parse_etags(request.headers.get("If-None-Match", ""))
    if etag in matches or "*" in matches:
        response = HttpResponseNotModified()
    else:
        data = bytes(campaign.share_image_data)
        response = HttpResponse(data, content_type=campaign.share_image_mime)
        response["Content-Length"] = str(len(data))
        extension = "jpg" if campaign.share_image_mime == "image/jpeg" else "png"
        response["Content-Disposition"] = f'inline; filename="preview.{extension}"'
    response["ETag"] = etag
    response["Cache-Control"] = "public, max-age=86400, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response
