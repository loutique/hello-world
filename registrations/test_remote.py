"""Separate phone controls reuse the stage capability without granting admin access."""
import json
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .models import CostumeVotingSession as Session, CostumeBroadcast as Broadcast
from .test_voting import competition
from .voting_engine import calculate


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PhoneRemoteTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_superuser("remote-owner", "remote@example.org", "test-password-for-phone")
        state=competition()
        self.session=Session.objects.create(name="Конкурс", state=state, result=calculate(state), phase=7, locked=True)
        self.show=Broadcast.objects.create(session=self.session, snapshot=self.session.result, title=self.session.name)
        self.remote=reverse("broadcast_remote", args=[self.show.token])
        self.endpoint=reverse("broadcast_state", args=[self.show.token])
        self.manage=reverse("admin:voting_broadcast", args=[self.session.pk])
        self.qr=reverse("admin:voting_remote_qr", args=[self.session.pk])

    def test_phone_page_needs_no_login_but_contains_no_contacts_or_admin_data(self):
        response=self.client.get(self.remote)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'lang="uk"')
        self.assertContains(response,"Пульт показу")
        self.assertContains(response,"Далі")
        self.assertContains(response,"Назад")
        self.assertNotContains(response,"PRIVATE_PHONE")
        self.assertNotContains(response,"PRIVATE_INSTAGRAM")
        self.assertNotContains(response,"remote-owner")
        self.assertIn("csrftoken",response.cookies)
        self.assertIn("no-store",response["Cache-Control"])
        self.assertEqual(response["Referrer-Policy"],"no-referrer")
        self.assertEqual(self.client.get(reverse("broadcast_remote",args=["unknown"])).status_code,404)

    def test_phone_controls_projector_and_rejects_duplicate_without_editing_scores(self):
        phone=Client(enforce_csrf_checks=True)
        phone.get(self.remote)
        payload=json.dumps({"revision":0,"action":"next"})
        self.assertEqual(phone.post(self.endpoint,payload,content_type="application/json").status_code,403)
        token=phone.cookies["csrftoken"].value
        response=phone.post(self.endpoint,payload,content_type="application/json",HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200)
        projector=Client()
        self.assertEqual(projector.get(self.endpoint).json()["frame"]["position"],1)
        self.assertEqual(phone.post(self.endpoint,payload,content_type="application/json",HTTP_X_CSRFTOKEN=token).status_code,409)
        self.assertEqual(projector.get(self.endpoint).json()["frame"]["position"],1)
        phone.post(self.endpoint,json.dumps({"revision":1,"action":"previous"}),content_type="application/json",HTTP_X_CSRFTOKEN=token)
        self.assertEqual(projector.get(self.endpoint).json()["frame"]["position"],0)
        self.session.refresh_from_db()
        self.assertEqual(self.session.revision,0)
        self.assertEqual(self.session.result,self.show.snapshot)

    def test_private_management_has_both_links_and_local_qr(self):
        self.assertEqual(self.client.get(self.qr).status_code,302)
        self.client.force_login(self.owner)
        response=self.client.get(self.manage)
        self.assertContains(response,self.remote)
        self.assertContains(response,self.qr)
        response=self.client.get(self.qr)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response["Content-Type"],"image/svg+xml")
        self.assertIn(b"<svg",response.content)
        self.assertIn("no-store",response["Cache-Control"])
        viewer=get_user_model().objects.create_user("remote-viewer",is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.qr).status_code,403)

    def test_remote_state_stops_on_revocation(self):
        self.show.active=False
        self.show.save()
        self.assertEqual(self.client.get(self.endpoint).status_code,410)
        self.assertEqual(self.client.post(self.endpoint,json.dumps({"revision":0,"action":"next"}),content_type="application/json").status_code,410)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.qr).status_code,404)
