"""Stage links, persisted click progression, controlled disclosure and result integrity."""
import copy
import json
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, Client, override_settings
from django.urls import reverse
from .models import CostumeVotingSession as Session, CostumeBroadcast as Broadcast, CostumeVotingPhoto as Photo
from .test_voting import competition
from .voting_engine import calculate
from .broadcast_engine import public_frame, last_position, audience_start, jury_top_count, results_position, podium_places


class BroadcastFrameTests(SimpleTestCase):
    def setUp(self):
        state = competition()
        state["ballots"]["votes"] = {c["id"]: v for c, v in zip(state["contestants"], [11, 17, 8, 4])}
        self.result = calculate(state)
        self.show = SimpleNamespace(snapshot=self.result, title="Велесова ніч", theme="ember", position=0, revision=0)

    def test_welcome_and_jury_never_include_unrevealed_audience(self):
        self.assertEqual(public_frame(self.show)["board"], [])
        self.show.position = 1
        frame = public_frame(self.show)
        self.assertTrue(all(r["audience"] is None for r in frame["board"]))
        self.assertNotIn("reveal_order", frame)
        self.assertNotIn("jury_table", frame)
        self.assertNotIn("PRIVATE_", json.dumps(frame))
        for r in frame["board"]:
            self.assertEqual(r["total"], r["jury"])

    def test_jury_lower_group_then_top_five_are_revealed_individually(self):
        self.show.snapshot = calculate(competition(9))
        result = self.show.snapshot
        self.show.position = 1
        initial = public_frame(self.show)
        self.assertEqual(sum(not r["hidden"] for r in initial["board"]), 4)
        jury_order = list(reversed(result["reveal_order"]))
        expected = list(reversed(jury_order[:5]))
        for i, cid in enumerate(expected):
            self.show.position = i + 2
            frame = public_frame(self.show)
            number = next(r["number"] for r in result["rows"] if r["id"] == cid)
            self.assertEqual(frame["scene"], "jury_top")
            self.assertEqual(frame["current"]["number"], number)
            self.assertEqual(sum(not r["hidden"] for r in frame["board"]), 5 + i)
            self.assertTrue(all(r["audience"] is None for r in frame["board"]))
        self.show.position = audience_start(result)
        self.assertEqual(public_frame(self.show)["scene"], "contestant")

    def test_three_click_sequence_preserves_fixed_jury_order_and_breakdown(self):
        for i, cid in enumerate(self.result["reveal_order"]):
            contestant = next(r for r in self.result["rows"] if r["id"] == cid)
            for substep, scene in enumerate(["contestant", "audience", "combined"]):
                self.show.position = audience_start(self.result) + 3 * i + substep
                frame = public_frame(self.show)
                self.assertEqual(frame["scene"], scene)
                self.assertEqual(frame["current"]["number"], contestant["number"])
                self.assertEqual(frame["current"]["jury"], contestant["jury_points"])
                self.assertEqual(frame["current"]["audience"], contestant["audience_points"] if substep else None)
                self.assertEqual(frame["current"]["total"], contestant["total"] if substep == 2 else None)
                self.assertEqual(frame["revealed"], i + (substep == 2))
        self.show.position = results_position(self.result)
        final = public_frame(self.show)
        self.assertEqual(final["scene"], "final")
        self.assertEqual(sum(r["total"] for r in final["board"]), 1000)
        self.assertEqual([(r["number"], r["rank"]) for r in final["board"]], [(r["number"], r["rank"]) for r in self.result["rows"]])

    def test_podium_follows_table_and_winner_celebration_is_separate(self):
        table = results_position(self.result)
        self.show.position = table
        self.assertEqual(public_frame(self.show)["scene"], "final")
        for offset, place in enumerate([3, 2, 1], 1):
            self.show.position = table + offset
            frame = public_frame(self.show)
            self.assertEqual(frame["scene"], "podium")
            self.assertEqual(frame["award_place"], place)
            self.assertTrue(frame["awardees"])
            self.assertTrue(all(r["rank"] == place for r in frame["awardees"]))
            self.assertEqual(sum(r["total"] for r in frame["board"]), 1000)
        self.show.position = last_position(self.result)
        winner = public_frame(self.show)
        self.assertEqual(winner["scene"], "victory")
        self.assertEqual(winner["headline"], "Вітаємо переможця!")
        self.assertEqual(winner["awardees"], winner["winners"])

    def test_final_excludes_disqualified_and_keeps_actual_final_numbers(self):
        state = competition()
        state["contestants"][0].update(dq=True, reason="Порушення")
        self.show.snapshot = calculate(state)
        self.show.position = last_position(self.show.snapshot)
        frame = public_frame(self.show)
        self.assertEqual({r["number"] for r in frame["board"]}, {2, 3, 4})
        self.assertEqual(sum(r["jury"] for r in frame["board"]), 250)
        self.assertEqual(sum(r["audience"] for r in frame["board"]), 750)

    def test_equal_results_show_all_shared_winners(self):
        state = competition(3)
        for i, j in enumerate(state["jury"]):
            state["scores"][j["id"]] = {c["id"]: [5, 3, 1][(k + i) % 3] for k, c in enumerate(state["contestants"])}
        self.show.snapshot = calculate(state)
        self.show.position = last_position(self.show.snapshot)
        frame = public_frame(self.show)
        self.assertEqual(len(frame["winners"]), 3)
        self.assertEqual(frame["scene"], "victory")
        self.assertEqual(podium_places(self.show.snapshot), [1])
        self.assertEqual(frame["headline"], "Вітаємо переможців!")
        self.show.position = results_position(self.show.snapshot) + 1
        self.assertEqual(len(public_frame(self.show)["awardees"]), 3)


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class BroadcastAccessTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser("show-owner", "show@example.org", "test-password-333")
        self.session = Session.objects.create(name="Конкурс", state=competition(), phase=6, locked=True)
        self.session.result = calculate(self.session.state)
        self.session.save()
        self.manage = reverse("admin:voting_broadcast", args=[self.session.pk])
        self.staff = Client()
        self.staff.force_login(self.owner)

    def create_show(self):
        response = self.staff.post(self.manage, {"action": "create", "theme": "ember"})
        self.assertEqual(response.status_code, 302)
        self.show = Broadcast.objects.get(active=True)
        self.url = reverse("broadcast_state", args=[self.show.token])
        return self.show

    def test_staff_only_creation_and_no_calculation_without_valid_snapshot(self):
        self.assertEqual(self.client.get(self.manage).status_code, 302)
        user = get_user_model().objects.create_user("plain-staff", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.post(self.manage, {"action": "create"}).status_code, 403)
        self.session.result = {}
        self.session.save()
        response = self.staff.post(self.manage, {"action": "create"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Broadcast.objects.exists())

    def test_capability_link_contains_no_admin_state_and_needs_no_login(self):
        self.create_show()
        response = self.client.get(reverse("broadcast_screen", args=[self.show.token]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "PRIVATE_PHONE")
        self.assertNotContains(response, "PRIVATE_INSTAGRAM")
        self.assertNotContains(response, "voting-data")
        self.assertContains(response, 'lang="uk"')
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.get(reverse("broadcast_state", args=["unknown"])).status_code, 404)

    def test_click_persists_and_stale_double_click_does_not_skip(self):
        self.create_show()
        response = self.client.post(self.url, json.dumps({"revision": 0, "action": "next"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["frame"]["position"], 1)
        self.assertEqual(self.client.post(self.url, json.dumps({"revision": 0, "action": "next"}), content_type="application/json").status_code, 409)
        self.assertEqual(Client().get(self.url).json()["frame"]["position"], 1)
        self.show.refresh_from_db()
        self.assertEqual(self.show.position, 1)
        self.session.refresh_from_db()
        self.assertEqual(self.session.result, self.show.snapshot)
        self.assertEqual(self.session.revision, 0)

    def test_anonymous_click_still_requires_csrf(self):
        self.create_show()
        browser = Client(enforce_csrf_checks=True)
        browser.get(reverse("broadcast_screen", args=[self.show.token]))
        payload = json.dumps({"revision": 0, "action": "next"})
        self.assertEqual(browser.post(self.url, payload, content_type="application/json").status_code, 403)
        response = browser.post(self.url, payload, content_type="application/json", HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 200)

    def test_revoke_replacement_and_result_changes_stop_old_links(self):
        self.create_show()
        old = self.url
        self.staff.post(self.manage, {"action": "revoke"})
        self.assertEqual(self.client.get(old).status_code, 410)
        self.create_show()
        previous = self.url
        self.create_show()
        self.assertEqual(self.client.get(previous).status_code, 410)
        self.session.result = {}
        self.session.save()
        self.assertEqual(self.client.get(self.url).status_code, 410)

    def test_photos_appear_only_for_announced_contestant_and_stop_when_revoked(self):
        self.create_show()
        self.show.position = 2
        current_number = public_frame(self.show)["current"]["number"]
        contestant = next(r for r in self.show.snapshot["rows"] if r["number"] == current_number)
        Photo.objects.create(session=self.session, contestant_id=contestant["id"], data=b"stage-jpeg")
        photo_url = reverse("broadcast_photo", args=[self.show.token, current_number])
        self.assertEqual(self.client.get(photo_url).status_code, 404)
        self.show.save()
        payload = self.client.get(self.url).json()["frame"]
        self.assertEqual(payload["current"]["photo"], photo_url)
        self.assertEqual(self.client.get(photo_url).content, b"stage-jpeg")
        self.show.position = last_position(self.show.snapshot)
        self.show.save()
        winner = next(r for r in self.show.snapshot["rows"] if r["rank"] == 1)
        Photo.objects.get_or_create(session=self.session, contestant_id=winner["id"], defaults={"data": b"winner-jpeg"})
        final = self.client.get(self.url).json()["frame"]
        winner_url = reverse("broadcast_photo", args=[self.show.token, winner["number"]])
        self.assertEqual(final["winners"][0]["photo"], winner_url)
        self.assertEqual(self.client.get(winner_url).status_code, 200)
        self.staff.post(self.manage, {"action": "revoke"})
        self.assertEqual(self.client.get(photo_url).status_code, 410)

    def test_restart_changes_revision_and_csrf_protects_admin_controls(self):
        self.create_show()
        self.show.position = 4
        self.show.save()
        self.staff.post(self.manage, {"action": "restart"})
        self.show.refresh_from_db()
        self.assertEqual(self.show.position, 0)
        self.assertEqual(self.show.revision, 1)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.owner)
        self.assertEqual(secure.post(self.manage, {"action": "revoke"}).status_code, 403)
