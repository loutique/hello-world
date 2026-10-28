"""Stage artwork storage, access, transparency and broadcast independence."""
import io
from types import SimpleNamespace
from PIL import Image
from django import forms
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from .branding_images import prepare_artwork
from .models import CostumeVotingSession as Session, CostumeBroadcast as Broadcast, CostumeVotingBranding as Branding
from .test_voting import competition
from .voting_engine import calculate


def image_file(name="logo.png", color=(255, 210, 40, 0)):
    output = io.BytesIO()
    Image.new("RGBA", (1200, 600), color).save(output, "PNG")
    return SimpleUploadedFile(name, output.getvalue(), "image/png")


class ArtworkTests(SimpleTestCase):
    def test_preserves_original_alpha_color_and_aspect(self):
        result = prepare_artwork(image_file(color=(255, 200, 30, 140)))
        with Image.open(io.BytesIO(result["data"])) as image:
            self.assertEqual(image.size, (1200, 600))
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((500, 300)), (255, 200, 30, 140))
        self.assertEqual(len(result["hash"]), 64)

    def test_invalid_or_oversize_upload_rejected(self):
        for upload in [SimpleUploadedFile("logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'), SimpleUploadedFile("huge.png", b"x" * (4 * 1024 * 1024 + 1))]:
            with self.assertRaises(forms.ValidationError):
                prepare_artwork(upload)


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class BrandingIntegrationTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser("brand-owner", "brand@example.org", "test-password-long")
        state = competition()
        self.session = Session.objects.create(name="Подія", state=state, phase=7, locked=True, completed=True, result=calculate(state))
        self.show = Broadcast.objects.create(session=self.session, title=self.session.name, snapshot=self.session.result, position=3, revision=4)
        self.manage = reverse("admin:voting_broadcast", args=[self.session.pk])
        self.url = reverse("broadcast_state", args=[self.show.token])
        self.logo_url = reverse("broadcast_artwork", args=[self.show.token, "logo"])
        self.client.force_login(self.owner)

    def test_uploads_work_after_completion_without_changing_result_or_show_position(self):
        before = self.session.result.copy()
        old = self.client.get(self.url).json()["frame"]
        response = self.client.post(self.manage, {"action": "branding", "logo": image_file(), "mascot": image_file("mascot.png", (250, 100, 10, 255))})
        self.assertEqual(response.status_code, 302)
        self.session.refresh_from_db()
        self.show.refresh_from_db()
        self.assertEqual(self.session.result, before)
        self.assertEqual(self.show.position, 3)
        self.assertEqual(self.show.revision, 4)
        payload = self.client.get(self.url).json()["frame"]
        self.assertNotEqual(payload["brand_version"], old["brand_version"])
        self.assertTrue(payload["branding"]["logo"].startswith(self.logo_url))
        self.assertTrue(payload["branding"]["mascot"])
        self.client.logout()
        response = self.client.get(self.logo_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("no-store", response["Cache-Control"])
        self.show.active = False
        self.show.save()
        self.assertEqual(self.client.get(self.logo_url).status_code, 410)

    def test_remove_or_invalid_upload_keeps_other_artwork_and_data(self):
        self.client.post(self.manage, {"action": "branding", "logo": image_file(), "mascot": image_file()})
        branding = Branding.objects.get(session=self.session)
        original = branding.logo_hash
        response = self.client.post(self.manage, {"action": "branding", "logo": SimpleUploadedFile("bad.png", b"not an image")})
        self.assertEqual(response.status_code, 200)
        branding.refresh_from_db()
        self.assertEqual(branding.logo_hash, original)
        self.client.post(self.manage, {"action": "branding", "remove_logo": "on"})
        branding.refresh_from_db()
        self.assertFalse(branding.logo_data)
        self.assertTrue(branding.mascot_data)
        self.assertEqual(self.client.get(self.logo_url).status_code, 404)

    def test_artwork_access_is_scoped_and_no_staff_access_granted(self):
        self.client.post(self.manage, {"action": "branding", "logo": image_file()})
        other = Session.objects.create(name="Other", state=self.session.state, result=self.session.result)
        show = Broadcast.objects.create(session=other, title=other.name, snapshot=other.result)
        self.assertEqual(self.client.get(reverse("broadcast_artwork", args=[show.token, "logo"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("broadcast_artwork", args=[self.show.token, "anything"])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.post(self.manage, {"action": "branding", "logo": image_file()}).status_code, 302)
