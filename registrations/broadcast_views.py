"""Staff-managed stage links expose only the current public results frame."""
import json
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, path
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.template.response import TemplateResponse
from .models import CostumeBroadcast as Broadcast, CostumeVotingSession as Session, CostumeVotingPhoto as Photo, CostumeVotingBranding as Branding
from .voting_views import private, page
from .branding_images import StageBrandingForm
from .voting_engine import calculate, VotingError
from .broadcast_engine import public_frame, last_position


def current(broadcast):
    return broadcast.active and bool(broadcast.session.result) and broadcast.session.result == broadcast.snapshot


def secure_response(response):
    response["Cache-Control"] = "no-store, private"
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Referrer-Policy"] = "no-referrer"
    return response


def frame(show):
    payload = public_frame(show)
    featured = ([payload["current"]] if payload["current"] else []) + payload["winners"] + payload.get("awardees", [])
    ids = {r["number"]: r["id"] for r in show.snapshot["rows"] if r["eligible"]}
    photo_ids = {str(cid) for cid in Photo.objects.filter(session_id=show.session_id, contestant_id__in=[ids[r["number"]] for r in featured]).values_list("contestant_id", flat=True)}
    branding = Branding.objects.filter(session_id=show.session_id).values("logo_hash", "mascot_hash").first() or {}
    payload["branding"] = {kind: reverse("broadcast_artwork", args=[show.token, kind]) + "?v=" + branding[kind + "_hash"] if branding.get(kind + "_hash") else None for kind in ("logo", "mascot")}
    payload["brand_version"] = ":".join(branding.get(kind + "_hash", "") for kind in ("logo", "mascot"))
    for person in featured:
        person["photo"] = reverse("broadcast_photo", args=[show.token, person["number"]]) if ids[person["number"]] in photo_ids else None
    return payload


@private
@require_http_methods(["GET", "POST"])
def manage(request, pk):
    session = get_object_or_404(Session, pk=pk)
    error = ""
    branding_form = StageBrandingForm(request.POST or None, request.FILES or None) if request.POST.get("action") == "branding" else StageBrandingForm()
    if request.method == "POST":
        try:
            # Serialize against score changes before authorizing a fresh stage snapshot.
            with transaction.atomic():
                session = Session.objects.select_for_update().get(pk=pk)
                action = request.POST.get("action")
                if action == "revoke":
                    session.broadcasts.filter(active=True).update(active=False)
                elif action == "create":
                    calculated = calculate(session.state)
                    if not session.result or calculated != session.result:
                        raise VotingError("Спочатку перевірте й збережіть результати на кроці 6.")
                    theme = request.POST.get("theme", "ember")
                    if theme not in {"electric", "ember"}:
                        raise VotingError("Оберіть оформлення зі списку.")
                    session.broadcasts.filter(active=True).update(active=False)
                    Broadcast.objects.create(session=session, snapshot=calculated, title=session.name, theme=theme)
                elif action == "branding":
                    if not branding_form.is_valid():
                        raise VotingError("Перевірте файли оформлення нижче.")
                    branding, _ = Branding.objects.get_or_create(session=session)
                    for kind in ("logo", "mascot"):
                        image = branding_form.cleaned_data.get(kind)
                        if image:
                            setattr(branding, kind + "_data", image["data"])
                            setattr(branding, kind + "_hash", image["hash"])
                        elif branding_form.cleaned_data.get("remove_" + kind):
                            setattr(branding, kind + "_data", None)
                            setattr(branding, kind + "_hash", "")
                    branding.save()
                elif action == "restart":
                    show = session.broadcasts.select_for_update().filter(active=True).first()
                    if not show or not current(show):
                        raise VotingError("Створіть нове посилання для актуальних результатів.")
                    show.position = 0
                    show.flow_version = 2
                    show.revision += 1
                    show.save(update_fields=["position", "revision", "flow_version"])
                else:
                    raise VotingError("Невідома дія.")
            return redirect("admin:voting_broadcast", pk=pk)
        except VotingError as exc:
            error = str(exc)
    show = session.broadcasts.filter(active=True).order_by("-created_at").first()
    ready = show is not None and current(show)
    return page(request, "broadcast.html", title="Показ на екрані", session=session, show=show,
        valid=ready, error=error, branding_form=branding_form,
        branding=Branding.objects.filter(session=session).values("logo_hash", "mascot_hash").first(),
        show_url=request.build_absolute_uri(reverse("broadcast_screen", args=[show.token])) if ready else "",
        remote_url=request.build_absolute_uri(reverse("broadcast_remote", args=[show.token])) if ready else "")


@ensure_csrf_cookie
@require_http_methods(["GET", "HEAD"])
def screen(request, token):
    show = get_object_or_404(Broadcast.objects.select_related("session"), token=token)
    return secure_response(TemplateResponse(request, "registrations/broadcast.html", {
        "config": {"url": reverse("broadcast_state", args=[token])},
    }))


@ensure_csrf_cookie
@require_http_methods(["GET", "HEAD"])
def remote(request, token):
    get_object_or_404(Broadcast.objects.only("pk"), token=token)
    return secure_response(TemplateResponse(request, "registrations/broadcast_remote.html", {
        "config": {"url": reverse("broadcast_state", args=[token])},
    }))


@private
@require_http_methods(["GET"])
def remote_qr(request, pk):
    show = get_object_or_404(Broadcast.objects.select_related("session").filter(active=True), session_id=pk)
    if not current(show):
        return secure_response(HttpResponse("Підготуйте актуальне посилання.", status=410))
    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing, Rect
    from reportlab.lib import colors
    drawing = Drawing(240, 240)
    drawing.add(Rect(0, 0, 240, 240, fillColor=colors.white, strokeColor=colors.white))
    drawing.add(QrCodeWidget(request.build_absolute_uri(reverse("broadcast_remote", args=[show.token])), barWidth=240, barHeight=240, barBorder=4))
    return secure_response(HttpResponse(renderSVG.drawToString(drawing), content_type="image/svg+xml"))


@require_http_methods(["GET", "POST"])
def state(request, token):
    with transaction.atomic():
        reference = get_object_or_404(Broadcast.objects.only("pk", "session_id"), token=token)
        session = Session.objects.select_for_update().get(pk=reference.session_id)
        show = Broadcast.objects.select_for_update().get(pk=reference.pk)
        show.session = session
        if not current(show):
            return secure_response(JsonResponse({"error": "Показ недоступний. Організатор має створити нове посилання після перевірки результатів."}, status=410))
        if request.method == "POST":
            try:
                body = json.loads(request.body)
            except (ValueError, TypeError):
                return secure_response(JsonResponse({"error": "Не вдалося прочитати команду."}, status=400))
            if not isinstance(body, dict) or type(body.get("revision")) is not int or body["revision"] != show.revision:
                return secure_response(JsonResponse({"error": "Екран уже змінився. Синхронізуємо показ…", "frame": frame(show)}, status=409))
            action = body.get("action")
            if action not in {"next", "previous"}:
                return secure_response(JsonResponse({"error": "Невідома дія."}, status=400))
            destination = max(0, min(last_position(show.snapshot, show.flow_version), show.position + (1 if action == "next" else -1)))
            if destination != show.position:
                show.position = destination
                show.revision += 1
                show.save(update_fields=["position", "revision"])
        return secure_response(JsonResponse({"frame": frame(show)}))


@require_http_methods(["GET", "HEAD"])
def photo(request, token, number):
    show = get_object_or_404(Broadcast.objects.select_related("session"), token=token)
    if not current(show):
        return secure_response(HttpResponse(status=410))
    payload = public_frame(show)
    visible = ([payload["current"]] if payload["current"] else []) + payload["winners"] + payload.get("awardees", [])
    if number not in {r["number"] for r in visible}:
        return secure_response(HttpResponse(status=404))
    contestant = next(r for r in show.snapshot["rows"] if r["eligible"] and r["number"] == number)
    image = get_object_or_404(Photo, session=show.session, contestant_id=contestant["id"])
    return secure_response(HttpResponse(bytes(image.data) if request.method == "GET" else b"", content_type="image/jpeg"))


@require_http_methods(["GET", "HEAD"])
def artwork(request, token, kind):
    if kind not in {"logo", "mascot"}:
        return secure_response(HttpResponse(status=404))
    show = get_object_or_404(Broadcast.objects.select_related("session"), token=token)
    if not current(show):
        return secure_response(HttpResponse(status=410))
    image = Branding.objects.filter(session_id=show.session_id).values_list(kind + "_data", flat=True).first()
    if not image:
        return secure_response(HttpResponse(status=404))
    return secure_response(HttpResponse(bytes(image) if request.method == "GET" else b"", content_type="image/png"))


urlpatterns = [path("show/<str:token>/remote/", remote, name="broadcast_remote"), path("show/<str:token>/artwork/<str:kind>/", artwork, name="broadcast_artwork"), path("show/<str:token>/photo/<int:number>/", photo, name="broadcast_photo"), path("show/<str:token>/", screen, name="broadcast_screen"),
               path("show/<str:token>/state/", state, name="broadcast_state")]
