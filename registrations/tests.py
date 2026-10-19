import csv
import io
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
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
        return {"internal_name": "Guests", "slug": "guests", "public_title": "Гості", "intro_text": "Welcome", "success_text": "Thanks", "privacy_text": "Private", "closed_text": "Closed", "is_active": "on", "_save": "Save"}
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
                self.client.post(self.list_url, {"action": action, "_selected_action": str(obj.pk)})
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
        obj.slug = "edited-slug"
        obj.public_title = "Edited"
        obj.save()
        call_command("seed_campaign")
        obj.refresh_from_db()
        self.assertEqual(obj.public_title, "Edited")

    def test_no_allocation_limit(self):
        Registration.objects.bulk_create([Registration(campaign=self.campaign, first_name="Test", last_name="Guest", phone=f"+97250234{i:04d}", phone_normalized=f"+97250234{i:04d}", email=f"guest{i}@example.org") for i in range(55)])
        self.login()
        self.client.post(self.list_url, {"action": "approve", "select_across": "1", "_selected_action": str(Registration.objects.first().pk)})
        self.assertEqual(Registration.objects.filter(status="APPROVED").count(), 55)
        self.client.post(self.list_url, {"action": "ticket_sent", "select_across": "1", "_selected_action": str(Registration.objects.first().pk)})
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
