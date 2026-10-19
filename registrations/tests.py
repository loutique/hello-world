import csv
import io
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import RegistrationCampaign, Registration

@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class WorkflowTests(TestCase):
    def setUp(self):
        self.campaign = RegistrationCampaign.objects.create(internal_name="Volunteers", slug="volunteers", public_title="Волонтери", intro_text="Welcome", success_text="Дякуємо")
        self.other = RegistrationCampaign.objects.create(internal_name="Partners", slug="partners", public_title="Партнери", intro_text="Welcome", success_text="Дякуємо")
        self.data = {"first_name": "Олена", "last_name": "Коваль", "phone": "0502345678", "email": "Olena@example.org"}
        self.admin = get_user_model().objects.create_superuser("organizer", "admin@example.org", "test-password-8741")
        self.url = reverse("register", args=[self.campaign.slug])
        self.list_url = reverse("admin:registrations_registration_changelist")
    def submit(self, campaign=None, **changes):
        return self.client.post(reverse("register", args=[(campaign or self.campaign).slug]), self.data | changes)
    def login(self):
        self.client.force_login(self.admin)
    def test_active_page(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Волонтери")
        self.assertContains(response, 'lang="uk"')
    def test_success(self):
        response = self.submit()
        self.assertRedirects(response, self.url+"?submitted=1")
        record = Registration.objects.get()
        self.assertEqual(record.email, "olena@example.org")
        self.assertEqual(record.phone_normalized, "+972502345678")
        self.assertEqual(record.status, "PENDING")
        self.assertIsNone(record.ticket_sent_at)
    def test_invalid_data(self):
        for changes in [{"first_name": " "}, {"last_name": "x"*81}, {"email": "invalid"}, {"phone": "123"}]:
            with self.subTest(changes=changes):
                response = self.submit(**changes)
                self.assertTrue(response.context["form"].errors)
        self.assertEqual(Registration.objects.count(), 0)
    def test_duplicate_email(self):
        self.submit()
        response = self.submit(email=" OLENA@example.org ", phone="0522345678")
        self.assertContains(response, "вже отримано")
        self.assertEqual(Registration.objects.count(), 1)
    def test_duplicate_phone(self):
        self.submit()
        response = self.submit(email="another@example.org", phone="+972 50-234-5678")
        self.assertContains(response, "вже отримано")
        self.assertEqual(Registration.objects.count(), 1)
    def test_cross_campaign(self):
        self.submit()
        self.submit(self.other)
        self.assertEqual(Registration.objects.count(), 2)
    def test_inactive(self):
        self.campaign.is_active = False
        self.campaign.save()
        self.assertContains(self.client.get(self.url), "Реєстрацію завершено")
        self.assertEqual(self.submit().status_code, 403)
        self.assertFalse(Registration.objects.exists())
    def test_expiration(self):
        self.campaign.closes_at = timezone.now()-timedelta(seconds=1)
        self.campaign.save()
        self.assertEqual(self.submit().status_code, 403)
    def test_admin_authentication(self):
        self.assertEqual(self.client.get(self.list_url).status_code, 302)
        login_url = reverse("admin:login")
        response = self.client.post(login_url, {"username": "organizer", "password": "wrong", "next": self.list_url})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(login_url, {"username": "organizer", "password": "test-password-8741", "next": self.list_url})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(self.list_url).status_code, 200)
    def campaign_data(self):
        return {"event_title": "Про подію", "visual_style": "classic", "internal_name": "Guests", "slug": "guests", "public_title": "Гості", "intro_text": "Welcome", "success_text": "Thanks", "privacy_text": "Private", "closed_text": "Closed", "is_active": "on", "_save": "Save"}
    def test_campaign_creation(self):
        self.login()
        response = self.client.post(reverse("admin:registrations_registrationcampaign_add"), self.campaign_data())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RegistrationCampaign.objects.filter(slug="guests").exists())
    def test_campaign_and_slug_edit(self):
        self.login()
        data = self.campaign_data() | {"slug": "new-address", "public_title": "Новий заголовок"}
        response = self.client.post(reverse("admin:registrations_registrationcampaign_change", args=[self.campaign.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertContains(self.client.get('/r/new-address/'), "Новий заголовок")
    def test_invalid_and_duplicate_slug(self):
        self.login()
        for slug in ["partners", "Invalid_slug", "a--b"]:
            response = self.client.post(reverse("admin:registrations_registrationcampaign_add"), self.campaign_data() | {"slug": slug})
            self.assertEqual(response.status_code, 200)
            self.assertIn("slug", response.context["adminform"].form.errors)
    def test_status_actions(self):
        self.submit()
        self.login()
        obj = Registration.objects.get()
        for action, status, timestamp in [("approve", "APPROVED", "approved_at"), ("reject", "REJECTED", "rejected_at"), ("ticket_sent", "TICKET_SENT", "ticket_sent_at"), ("pending", "PENDING", None)]:
            with self.subTest(action=action):
                payload = {"action": action, "_selected_action": str(obj.pk)}
                previous_status = obj.status
                response = self.client.post(self.list_url, payload)
                self.assertContains(response, "Подтвердите изменение отметок")
                obj.refresh_from_db()
                self.assertEqual(obj.status, previous_status)
                self.client.post(self.list_url, payload | {"confirm_status": "yes"})
                obj.refresh_from_db()
                self.assertEqual(obj.status, status)
                if timestamp:
                    self.assertIsNotNone(getattr(obj, timestamp))
    def test_status_filter(self):
        self.submit()
        self.submit(self.other)
        record = Registration.objects.filter(campaign=self.other).get()
        record.status = "APPROVED"
        record.save()
        self.login()
        response = self.client.get(self.list_url, {"status__exact": "APPROVED"})
        self.assertEqual(list(response.context["cl"].queryset), [record])
    def test_campaign_filter(self):
        self.submit()
        self.submit(self.other)
        self.login()
        response = self.client.get(self.list_url, {"campaign__id__exact": self.campaign.pk})
        self.assertEqual(response.context["cl"].queryset.count(), 1)
        self.assertEqual(response.context["cl"].queryset.get().campaign, self.campaign)
    def test_search_and_sort(self):
        self.submit()
        self.login()
        response = self.client.get(self.list_url, {"q": "olena@example.org", "o": "1"})
        self.assertEqual(response.context["cl"].queryset.count(), 1)
    def test_notes(self):
        self.submit()
        self.login()
        obj = Registration.objects.get()
        response = self.client.post(reverse("admin:registrations_registration_change", args=[obj.pk]), {"status": "PENDING", "admin_notes": "Verified by organizer", "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertEqual(obj.admin_notes, "Verified by organizer")
    def test_csv_filtered_and_safe(self):
        self.submit(first_name="=SUM(1,2)")
        self.submit(self.other)
        self.login()
        response = self.client.post(self.list_url+f"?campaign__id__exact={self.campaign.pk}", {"action": "export_csv", "select_across": "1", "_selected_action": str(Registration.objects.first().pk)})
        self.assertEqual(response['Content-Type'], "text/csv; charset=utf-8")
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1][1].startswith("'="))
        self.assertEqual(rows[1][2], "Коваль")
    def test_unauthorized_reads_and_export(self):
        self.submit()
        for url in [self.list_url, reverse("admin:registrations_registration_change", args=[Registration.objects.get().pk])]:
            self.assertEqual(self.client.get(url).status_code, 302)
        response = self.client.post(self.list_url, {"action": "export_csv", "select_across": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(b"olena@example.org", response.content)
        user = get_user_model().objects.create_user("visitor", password="some-password")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.list_url).status_code, 302)
        self.assertNotContains(self.client.get(self.url), "olena@example.org")
    def test_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, self.data).status_code, 403)
    @override_settings(REGISTRATION_RATE_LIMIT=20)
    def test_rate_limit(self):
        for _ in range(20):
            self.submit(email="invalid")
        self.assertEqual(self.submit().status_code, 429)
    def test_seed_repeatable(self):
        from django.core.management import call_command
        call_command("seed_campaign")
        obj = RegistrationCampaign.objects.get(slug="zdybanky")
        response = self.client.get('/r/zdybanky/')
        self.assertContains(response, "CALLAS TLV")
        self.assertContains(response, "Menachem Begin 37")
        self.assertContains(response, "19:00")
        self.assertContains(response, "30 жовтня 2026")
        self.assertContains(response, "1000 ₪")
        self.assertContains(response, "SHO")
        obj.slug = "edited-slug"
        obj.public_title = "Edited"
        obj.save()
        call_command("seed_campaign")
        obj.refresh_from_db()
        self.assertEqual(obj.public_title, "Edited")

    def test_no_allocation_limit(self):
        Registration.objects.bulk_create([Registration(campaign=self.campaign, first_name="Test", last_name="Guest", phone=f"+97250234{i:04d}", phone_normalized=f"+97250234{i:04d}", email=f"guest{i}@example.org") for i in range(55)])
        self.login()
        self.client.post(self.list_url, {"action": "approve", "select_across": "1", "confirm_status": "yes", "_selected_action": str(Registration.objects.first().pk)})
        self.assertEqual(Registration.objects.filter(status="APPROVED").count(), 55)
        self.client.post(self.list_url, {"action": "ticket_sent", "select_across": "1", "confirm_status": "yes", "_selected_action": str(Registration.objects.first().pk)})
        self.assertEqual(Registration.objects.filter(status="TICKET_SENT").count(), 55)
    def test_login_lockout(self):
        for _ in range(5):
            self.client.post(reverse("admin:login"), {"username": "organizer", "password": "wrong"})
        response = self.client.post(reverse("admin:login"), {"username": "organizer", "password": "test-password-8741"})
        self.assertEqual(response.status_code, 429)

    def test_health(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
    def test_health_database_failure(self):
        from unittest.mock import patch
        from django.db import OperationalError
        with patch("django.db.connection.cursor", side_effect=OperationalError("private details")):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"private details", response.content)

    def test_admin_dashboard_and_language(self):
        self.submit()
        self.login()
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, 'lang="ru"')
        self.assertContains(response, "Скачать все заявки")
        self.assertContains(response, "Здесь нет автоматических рассылок")
        self.assertEqual(response.context["stats"]["pending"], 1)
        self.assertContains(response, "Volunteers")
        self.assertContains(self.client.get(self.url), 'lang="uk"')

    def test_export_button_respects_filters_and_search(self):
        self.submit()
        self.submit(self.other, first_name="Another", email="another@example.org")
        self.login()
        url = reverse("admin:registrations_registration_export")
        response = self.client.get(url, {"campaign__id__exact": self.campaign.pk, "q": "olena"})
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "Имя")
        self.assertEqual(rows[1][1], "Олена")
        self.assertEqual(rows[1][7], "На проверке")
        self.assertIn("no-store", response["Cache-Control"])
        page = self.client.get(self.list_url, {"campaign__id__exact": self.campaign.pk})
        self.assertIn("campaign__id__exact=", page.context["export_url"])

    def test_export_includes_all_pages(self):
        Registration.objects.bulk_create([Registration(campaign=self.campaign, first_name="Test", last_name="Guest", phone=str(i), phone_normalized=str(i), email=f"guest{i}@example.org") for i in range(55)])
        self.login()
        response = self.client.get(reverse("admin:registrations_registration_export"), {"p": "1"})
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 56)

    def test_confirmation_preserves_filtered_selection(self):
        self.submit()
        self.submit(self.other)
        self.login()
        url = self.list_url + f"?campaign__id__exact={self.campaign.pk}"
        data = {"action": "approve", "select_across": "1", "_selected_action": str(Registration.objects.first().pk)}
        response = self.client.post(url, data)
        self.assertContains(response, "Заявок в выбранной группе:")
        self.assertEqual(response.context["selection_count"], 1)
        self.assertEqual(Registration.objects.filter(status="APPROVED").count(), 0)
        self.client.post(url, data | {"confirm_status": "yes"})
        self.assertEqual(Registration.objects.get(campaign=self.campaign).status, "APPROVED")
        self.assertEqual(Registration.objects.get(campaign=self.other).status, "PENDING")
        from django.contrib.admin.models import LogEntry
        self.assertEqual(LogEntry.objects.filter(object_id=str(Registration.objects.get(campaign=self.campaign).pk)).count(), 1)

    def test_staff_permissions_cover_dashboard_export_and_actions(self):
        from django.contrib.auth.models import Permission
        self.submit()
        staff = get_user_model().objects.create_user("limited", is_staff=True)
        self.client.force_login(staff)
        export_url = reverse("admin:registrations_registration_export")
        response = self.client.get(reverse("admin:index"))
        self.assertNotIn("stats", response.context)
        self.assertNotContains(response, "Скачать все заявки")
        self.assertEqual(self.client.get(export_url).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_registration", content_type__app_label="registrations"))
        self.assertEqual(self.client.get(export_url).status_code, 200)
        actions = self.client.get(self.list_url).context["action_form"].fields["action"].choices
        self.assertNotIn("approve", [key for key, label in actions])
        obj = Registration.objects.get()
        self.client.post(self.list_url, {"action": "approve", "confirm_status": "yes", "_selected_action": obj.pk})
        obj.refresh_from_db()
        self.assertEqual(obj.status, "PENDING")

    def test_admin_help_and_field_explanations(self):
        self.assertEqual(self.client.get(reverse("admin:disco_help")).status_code, 302)
        self.assertEqual(self.client.get(reverse("admin:registrations_registration_export")).status_code, 302)
        self.login()
        self.assertContains(self.client.get(reverse("admin:disco_help")), "Какая кнопка что сохраняет?")
        response = self.client.get(reverse("admin:registrations_registrationcampaign_add"))
        self.assertContains(response, "После изменения старая ссылка перестанет работать")
        self.assertContains(response, "Уже собранные заявки сохранятся")

    def test_campaign_expiry_is_explained(self):
        self.campaign.closes_at = timezone.now() - timedelta(minutes=1)
        self.campaign.save()
        self.login()
        response = self.client.get(reverse("admin:registrations_registrationcampaign_changelist"))
        self.assertContains(response, "Закрыт по времени")

    def test_public_style_is_campaign_specific(self):
        self.campaign.visual_style = "veles2026"
        self.campaign.save()
        self.assertContains(self.client.get(self.url), 'class="theme-veles"')
        self.assertContains(self.client.get(self.url), "veles-2026.jpg")
        response = self.client.get(reverse("register", args=[self.other.slug]))
        self.assertContains(response, 'class="theme-classic"')
        self.assertNotContains(response, "veles-2026.jpg")

    def test_editable_event_information(self):
        self.campaign.event_title = "Про подію"
        self.campaign.event_description = "Вечір української музики. <script>alert(1)</script>"
        self.campaign.event_info_url = "https://example.org/event"
        self.campaign.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Вечір української музики")
        self.assertContains(response, "https://example.org/event")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def preview_metadata(self, response):
        from html.parser import HTMLParser

        class HeadParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.values = {}

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "meta":
                    self.values[attrs.get("property", attrs.get("name"))] = attrs.get("content")
                if tag == "link" and attrs.get("rel") == "canonical":
                    self.values["canonical"] = attrs.get("href")

        parser = HeadParser()
        parser.feed(response.content.decode())
        return parser.values

    def test_whatsapp_preview_is_public_and_has_absolute_image_url(self):
        self.campaign.visual_style = "veles2026"
        self.campaign.public_title = 'Волонтери "Здибанки"'
        self.campaign.event_summary = "Музика, танці та гарний настрій."
        self.campaign.save()
        response = self.client.get(self.url, secure=True, HTTP_USER_AGENT="WhatsApp/2")
        self.assertEqual(response.status_code, 200)
        meta = self.preview_metadata(response)
        self.assertEqual(meta["og:title"], 'Волонтери "Здибанки" · DISCO UKRAÏNA')
        self.assertEqual(meta["og:description"], "Музика, танці та гарний настрій.")
        self.assertEqual(meta["og:url"], "https://testserver" + self.url)
        self.assertEqual(meta["canonical"], meta["og:url"])
        self.assertEqual(meta["og:image"], "https://testserver/static/registrations/artwork/veles-2026-small.jpg")
        self.assertEqual(meta["og:image:type"], "image/jpeg")
        self.assertEqual(meta["og:image:width"], "569")
        self.assertEqual(meta["og:image:height"], "800")

    def test_preview_never_includes_query_or_submitted_contact_data(self):
        response = self.client.get(self.url, {"email": "private@example.org", "phone": "0502345678", "submitted": "1"})
        meta = self.preview_metadata(response)
        self.assertNotIn("private@example.org", str(meta))
        self.assertNotIn("0502345678", str(meta))
        self.assertNotIn("?", meta["og:url"])
        response = self.submit(email="private@example.org", phone="invalid")
        self.assertNotIn("private@example.org", str(self.preview_metadata(response)))

    def test_preview_matches_campaign_style_slug_and_closed_state(self):
        self.other.slug = "new-guests"
        self.other.save()
        response = self.client.get(reverse("register", args=[self.other.slug]))
        meta = self.preview_metadata(response)
        self.assertEqual(meta["og:title"], "Партнери · DISCO UKRAÏNA")
        self.assertNotIn("og:image", meta)
        self.assertTrue(meta["canonical"].endswith("/r/new-guests/"))
        self.campaign.is_active = False
        self.campaign.closed_text = "Реєстрацію завершено. До наступної зустрічі!"
        self.campaign.save()
        meta = self.preview_metadata(self.client.get(self.url))
        self.assertEqual(meta["og:description"], self.campaign.closed_text)

    def image_upload(self, width=1200, height=630, image_format="JPEG", color="orange", with_exif=False):
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = io.BytesIO()
        image = Image.new("RGB", (width, height), color)
        kwargs = {}
        if with_exif:
            exif = Image.Exif()
            exif[270] = "Private camera details"
            kwargs["exif"] = exif
        image.save(data, image_format, **kwargs)
        return SimpleUploadedFile("preview." + ("jpg" if image_format == "JPEG" else "png"), data.getvalue(), content_type="image/jpeg" if image_format == "JPEG" else "image/png")

    def test_admin_upload_is_persistent_and_used_in_link_preview(self):
        from PIL import Image
        self.login()
        url = reverse("admin:registrations_registrationcampaign_change", args=[self.campaign.pk])
        data = self.campaign_data() | {"slug": self.campaign.slug, "share_image": self.image_upload(with_exif=True), "share_image_alt": "Помаранчева афіша"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.campaign.refresh_from_db()
        self.assertTrue(self.campaign.share_image_data)
        self.assertEqual(self.campaign.share_image_width, 1200)
        self.assertEqual(self.campaign.share_image_height, 630)
        image = Image.open(io.BytesIO(bytes(self.campaign.share_image_data)))
        self.assertFalse(image.getexif())
        public = self.client.get(self.url)
        meta = self.preview_metadata(public)
        image_url = reverse("campaign_preview_image", args=[self.campaign.slug, self.campaign.share_image_hash])
        self.assertTrue(meta["og:image"].endswith(image_url))
        self.assertEqual(meta["og:image:alt"], "Помаранчева афіша")
        guest = Client()
        response = guest.get(image_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(Image.open(io.BytesIO(response.content)).size, (1200, 630))
        self.assertEqual(guest.head(image_url).status_code, 200)
        self.assertEqual(guest.get(image_url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code, 304)
        # Saving other fields must not erase the uploaded image.
        image_hash = self.campaign.share_image_hash
        response = self.client.post(url, self.campaign_data() | {"slug": self.campaign.slug})
        self.assertEqual(response.status_code, 302)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.share_image_hash, image_hash)

    def test_upload_replacement_removal_and_fallback(self):
        from registrations.forms import CampaignAdminForm
        from PIL import Image
        form = CampaignAdminForm(data=self.campaign_data(), files={"share_image": self.image_upload()}, instance=self.campaign)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        previous = self.campaign.share_image_hash
        form = CampaignAdminForm(data=self.campaign_data(), files={"share_image": self.image_upload(image_format="PNG", color="blue")}, instance=self.campaign)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertNotEqual(self.campaign.share_image_hash, previous)
        image_url = reverse("campaign_preview_image", args=[self.campaign.slug, self.campaign.share_image_hash])
        response = self.client.get(image_url)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(Image.open(io.BytesIO(response.content)).format, "PNG")
        old_url = reverse("campaign_preview_image", args=[self.campaign.slug, previous])
        self.assertEqual(self.client.get(old_url).status_code, 404)
        form = CampaignAdminForm(data=self.campaign_data() | {"remove_share_image": "on", "visual_style": "veles2026"}, instance=self.campaign)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertIsNone(self.campaign.share_image_data)
        self.assertEqual(self.client.get(image_url).status_code, 404)
        meta = self.preview_metadata(self.client.get(reverse("register", args=[self.campaign.slug])))
        self.assertIn("veles-2026-small.jpg", meta["og:image"])

    def test_invalid_images_and_conflicting_actions_are_rejected(self):
        from registrations.forms import CampaignAdminForm
        from django.core.files.uploadedfile import SimpleUploadedFile
        invalid = [
            SimpleUploadedFile("bad.jpg", b"<svg><script>alert(1)</script></svg>", content_type="image/jpeg"),
            SimpleUploadedFile("huge.jpg", b"x" * (1024 * 1024 + 1), content_type="image/jpeg"),
            self.image_upload(100, 100),
            self.image_upload(4200, 200),
        ]
        for image in invalid:
            with self.subTest(filename=image.name, size=image.size):
                form = CampaignAdminForm(data=self.campaign_data(), files={"share_image": image}, instance=self.campaign)
                self.assertFalse(form.is_valid())
                self.assertIn("share_image", form.errors)
        form = CampaignAdminForm(data=self.campaign_data() | {"remove_share_image": "on"}, files={"share_image": self.image_upload()}, instance=self.campaign)
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_image_upload_is_restricted_to_campaign_editors(self):
        from django.contrib.auth.models import Permission
        self.login()
        url = reverse("admin:registrations_registrationcampaign_change", args=[self.campaign.pk])
        self.assertContains(self.client.get(url), "1200 × 630")
        self.assertContains(self.client.get(url), 'enctype="multipart/form-data"')
        staff = get_user_model().objects.create_user("image-viewer", is_staff=True)
        staff.user_permissions.add(Permission.objects.get(codename="view_registrationcampaign", content_type__app_label="registrations"))
        self.client.force_login(staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'type="file"')
        self.assertEqual(self.client.post(url, self.campaign_data() | {"share_image": self.image_upload()}).status_code, 403)


class CampaignUpgradeTests(TransactionTestCase):
    """An existing event can upgrade without losing registrations or organizer edits."""

    migrate_from = ("registrations", "0003_registrationcampaign_seed_key")
    migrate_to = ("registrations", "0010_registrationcampaign_share_image_alt_and_more")

    def tearDown(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_upgrade_preserves_contacts_and_custom_copy(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        Campaign = old_apps.get_model("registrations", "RegistrationCampaign")
        Record = old_apps.get_model("registrations", "Registration")
        campaign = Campaign.objects.create(seed_key="initial-volunteers", internal_name="Custom internal name", slug="custom-volunteers", public_title="Мій заголовок", intro_text="Текст організатора", success_text="Моє повідомлення")
        other = Campaign.objects.create(internal_name="Another event", slug="another-event", public_title="Інша подія", intro_text="Another intro", success_text="Thanks")
        registration = Record.objects.create(campaign=campaign, first_name="Олена", last_name="Коваль", phone="0502345678", phone_normalized="+972502345678", email="upgrade@example.org", status="APPROVED", admin_notes="Preserve this note")
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        apps = executor.loader.project_state([self.migrate_to]).apps
        Campaign = apps.get_model("registrations", "RegistrationCampaign")
        Record = apps.get_model("registrations", "Registration")
        updated = Campaign.objects.get(pk=campaign.pk)
        self.assertEqual(updated.slug, "custom-volunteers")
        self.assertEqual(updated.public_title, "Мій заголовок")
        self.assertEqual(updated.intro_text, "Текст організатора")
        self.assertEqual(updated.success_text, "Моє повідомлення")
        self.assertEqual(updated.visual_style, "veles2026")
        self.assertEqual(updated.event_venue, "CALLAS TLV")
        self.assertEqual(updated.event_address, "Menachem Begin 37, Тель-Авів")
        self.assertIn("1000 ₪", updated.event_description)
        self.assertIn("SHO", updated.event_description)
        self.assertIn("10%", updated.event_description)
        self.assertEqual(updated.event_starts_at.isoformat(), "2026-10-30T17:00:00+00:00")
        self.assertEqual(Campaign.objects.get(pk=other.pk).event_summary, "")
        self.assertEqual(Campaign.objects.get(pk=other.pk).visual_style, "classic")
        updated_record = Record.objects.get(pk=registration.pk)
        self.assertEqual(updated_record.status, "APPROVED")
        self.assertEqual(updated_record.admin_notes, "Preserve this note")
        self.assertEqual(updated_record.email, "upgrade@example.org")
