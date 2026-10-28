"""Private organizer endpoints. Every mutation is CSRF protected and version checked."""
import io
import json
from functools import wraps
from uuid import UUID
from PIL import Image, ImageOps, UnidentifiedImageError
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.translation import override
from .models import CostumeVotingSession as Session, CostumeVotingAudit as Audit, CostumeVotingPhoto as Photo
from .voting_engine import initial_state, clean_state, validate, calculate, VotingError, STEPS
from .voting_presenter import script


def allowed(user):
    return user.is_active and user.is_staff and user.has_perm("registrations.operate_costume_voting")


def private(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not allowed(request.user):
            raise PermissionDenied
        with override("uk"):
            response = view(request, *args, **kwargs)
            if hasattr(response, "render"):
                response.render()
        response["Cache-Control"] = "no-store, private"
        response["X-Robots-Tag"] = "noindex, nofollow"
        return response
    return admin.site.admin_view(wrapped)


def page(request, template, **context):
    return TemplateResponse(request, "admin/voting/" + template, {**admin.site.each_context(request), **context})


def record(session, user, action):
    session.revision += 1
    session.save()
    Audit.objects.create(session=session, revision=session.revision, actor=user, action=action,
        state={"data": session.state, "phase": session.phase, "locked": session.locked, "completed": session.completed}, result=session.result)


@private
def index(request):
    return page(request, "index.html", title="Голосування за костюми", sessions=Session.objects.order_by("-created_at"))


@private
def create(request):
    error = ""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name or len(name) > 200:
            error = "Вкажіть назву голосування (до 200 символів)."
        else:
            with transaction.atomic():
                session = Session.objects.create(name=name, state=initial_state())
                record(session, request.user, "create")
            return redirect("admin:voting_detail", pk=session.pk)
    return page(request, "create.html", title="Нове голосування", error=error)


@private
def detail(request, pk):
    session = get_object_or_404(Session, pk=pk)
    try:
        step = int(request.GET.get("step", session.phase))
    except ValueError:
        step = session.phase
    step = max(1, min(step, session.phase, 7))
    return page(request, "detail.html", title=session.name, session=session, data=session.state,
        step=step, steps=enumerate(STEPS, 1), step_name=STEPS[step - 1],
        payload={"state": session.state, "revision": session.revision, "step": step,
                 "phase": session.phase, "locked": session.locked, "completed": session.completed,
                 "saveUrl": reverse("admin:voting_save", args=[pk]), "photoUrl": reverse("admin:voting_photo", args=[pk]),
                 "detailUrl": reverse("admin:voting_detail", args=[pk])},
        presenter=script(session.result) if session.result and step == 7 else None,
        result=session.result)


def frozen_part(state):
    return {"jury": state["jury"], "shortlist": state["shortlist"], "ballots": state["ballots"],
        "contestants": [{k: v for k, v in c.items() if k not in {"dq", "reason"}} for c in state["contestants"]]}


@private
def save(request, pk):
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        if len(request.body) > 3 * 1024 * 1024:
            raise VotingError("Забагато даних в одному запиті.")
        body = json.loads(request.body)
        with transaction.atomic():
            session = get_object_or_404(Session.objects.select_for_update(), pk=pk)
            if body.get("revision") != session.revision:
                return JsonResponse({"error": "Цю сесію вже змінили в іншій вкладці. Скопіюйте незбережені дані, а потім оновіть сторінку. Ваші зміни не перезаписали збережені."}, status=409)
            if session.completed:
                raise VotingError("Голосування завершено. Дані захищено від змін.")
            stage = body.get("step")
            if type(stage) is not int or not 1 <= stage <= min(session.phase, 7):
                raise VotingError("Спочатку завершіть попередній крок.")
            state = clean_state(body.get("state"), session.state)
            if session.locked and frozen_part(state) != frozen_part(session.state):
                raise VotingError("Оцінювання журі вже розпочато. Попередні етапи заблоковано; можна змінювати лише оцінки та дискваліфікації.")
            action = body.get("action", "save")
            if action not in {"save", "next", "calculate", "complete"}:
                raise VotingError("Невідома дія.")
            changed = state != session.state
            if changed and session.result:
                session.result = {}
                session.phase = min(session.phase, 6) if session.locked else min(session.phase, stage)
            if not session.locked and changed:
                session.phase = min(session.phase, stage)
            session.state = state
            destination = None
            if action == "next":
                validate(state, stage)
                if stage == 3:
                    state["shortlist"]["confirmed"] = True
                if stage == 4:
                    session.locked = True
                if stage >= 5:
                    session.result = calculate(state)
                session.phase = max(session.phase, min(stage + 1, 7))
                destination = min(stage + 1, 7)
            if action in {"calculate", "complete"}:
                if not session.locked:
                    raise VotingError("Спочатку завершіть введення голосів глядачів і перейдіть до журі.")
                session.result = calculate(state)
                session.phase = max(session.phase, 6)
                destination = 6
                if action == "complete":
                    if any(c["dq"] and c["name"] and not c["reason"] for c in state["contestants"]):
                        raise VotingError("Перед завершенням додайте причини дискваліфікацій для публічного звіту.")
                    session.completed = True
            if changed or action != "save":
                record(session, request.user, action)
            return JsonResponse({"revision": session.revision, "state": session.state, "saved": True,
                "destination": reverse("admin:voting_detail", args=[pk]) + f"?step={destination}" if destination else None,
                "invalidated": changed and stage < 6})
    except (VotingError, ValueError, TypeError, KeyError, AttributeError) as exc:
        message = str(exc) if isinstance(exc, VotingError) else "Не вдалося прочитати дані. Оновіть сторінку та повторіть спробу."
        return JsonResponse({"error": message}, status=400)


@private
def photo(request, pk):
    session = get_object_or_404(Session, pk=pk)
    cid = request.GET.get("contestant") if request.method in {"GET", "HEAD"} else request.POST.get("contestant")
    try:
        cid = str(UUID(cid))
    except (ValueError, TypeError, AttributeError):
        return HttpResponseBadRequest("Невідомий учасник.")
    if request.method in {"GET", "HEAD"}:
        image = get_object_or_404(Photo, session=session, contestant_id=cid)
        return HttpResponse(bytes(image.data) if request.method == "GET" else b"", content_type="image/jpeg")
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        with transaction.atomic():
            session = Session.objects.select_for_update().get(pk=pk)
            if session.locked or session.completed:
                raise VotingError("Фотографії заблоковано після початку оцінювання журі.")
            if str(session.revision) != request.POST.get("revision"):
                return JsonResponse({"error": "Дані вже змінилися. Оновіть сторінку перед завантаженням фото."}, status=409)
            if cid not in {c["id"] for c in session.state["contestants"]}:
                raise VotingError("Спочатку збережіть учасника.")
            if request.POST.get("remove") == "1":
                Photo.objects.filter(session=session, contestant_id=cid).delete()
            else:
                upload = request.FILES.get("photo")
                if not upload or upload.size > 5 * 1024 * 1024:
                    raise VotingError("Оберіть JPEG, PNG або WebP до 5 МБ. Якщо камера зберігає HEIC, оберіть формат JPEG.")
                with Image.open(upload) as image:
                    if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > 25000000 or getattr(image, "is_animated", False):
                        raise VotingError("Потрібне звичайне фото JPEG, PNG або WebP, не більше 25 мегапікселів.")
                    image.load()
                    pixels = ImageOps.exif_transpose(image).convert("RGB")
                    pixels.thumbnail((1000, 1000))
                    pixels.info.clear()
                    buffer = io.BytesIO()
                    pixels.save(buffer, "JPEG", quality=85, optimize=True)
                Photo.objects.update_or_create(session=session, contestant_id=cid, defaults={"data": buffer.getvalue()})
            record(session, request.user, "photo")
            return JsonResponse({"revision": session.revision})
    except (VotingError, UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        return JsonResponse({"error": str(exc) if isinstance(exc, VotingError) else "Не вдалося прочитати фото. Спробуйте JPEG або PNG."}, status=400)


@private
def pdf(request, pk):
    session = get_object_or_404(Session, pk=pk)
    try:
        result = calculate(session.state)
        if not session.result or result != session.result:
            raise VotingError("Спочатку перевірте та збережіть результати на кроці 6.")
        if any(r["status"] == "Дискваліфіковано" and not r["reason"] for r in result["rows"]):
            raise VotingError("Додайте причини дискваліфікацій перед створенням публічного звіту.")
    except VotingError as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
    from .voting_pdf import report
    response = HttpResponse(report(session.name, result), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="costume-voting-{session.pk}.pdf"'
    return response


@private
def history(request, pk):
    session = get_object_or_404(Session, pk=pk)
    return page(request, "history.html", title="Історія збережень", session=session, history=session.history.select_related("actor").order_by("-revision")[:200])


def broadcast_manage(request, pk):
    from .broadcast_views import manage
    return manage(request, pk)


def broadcast_remote_qr(request, pk):
    from .broadcast_views import remote_qr
    return remote_qr(request, pk)


urlpatterns = [path("<int:pk>/broadcast/remote-qr.svg", broadcast_remote_qr, name="voting_remote_qr"), path("<int:pk>/broadcast/", broadcast_manage, name="voting_broadcast"), path("", index, name="voting_index"), path("new/", create, name="voting_create"),
    path("<int:pk>/", detail, name="voting_detail"), path("<int:pk>/save/", save, name="voting_save"),
    path("<int:pk>/photo/", photo, name="voting_photo"), path("<int:pk>/report.pdf", pdf, name="voting_pdf"),
    path("<int:pk>/history/", history, name="voting_history")]
