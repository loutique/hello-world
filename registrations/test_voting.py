"""Business rules, private integration, recovery and public-report regression checks."""
import copy
import io
import json
import random
from fractions import Fraction
from django.test import TestCase, SimpleTestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from PIL import Image
from .models import CostumeVotingSession as Session, CostumeVotingAudit as Audit, CostumeVotingPhoto as Photo
from .voting_engine import initial_state, clean_state, validate, calculate, VotingError, key, allocate
from .voting_presenter import script, INTRO


def competition(count=4, jury_count=3):
    state = initial_state()
    for i in range(jury_count - 3):
        state["jury"].append({"id": key(), "code": chr(68 + i), "name": "", "active": True})
    for j in state["jury"]:
        j["name"] = "Суддя " + j["code"]
    state["contestants"] = [{"id": key(), "original": i + 1, "final": i + 1, "name": f"Учасник {i + 1}", "phone": "PRIVATE_PHONE", "instagram": "PRIVATE_INSTAGRAM", "finalist": True, "dq": False, "reason": ""} for i in range(count)]
    state["ballots"] = {"total": count * 10, "invalid": 0, "votes": {c["id"]: 10 for c in state["contestants"]}}
    state["scores"] = {j["id"]: {c["id"]: [5, 3, 1, 0][i] if i < 4 else 0 for i, c in enumerate(state["contestants"])} for j in state["jury"]}
    return state


class VotingMathTests(SimpleTestCase):
    def test_exact_banks_and_audit_fractions(self):
        r = calculate(competition())
        self.assertEqual(sum(c["audience_points"] for c in r["rows"]), 750)
        self.assertEqual(sum(c["jury_points"] for c in r["rows"]), 250)
        self.assertEqual(sum(Fraction(c["combined_exact"]["fraction"]) for c in r["rows"]), 1000)
        self.assertNotIn("PRIVATE_", json.dumps(r))

    def test_randomized_hamilton_conserves_banks(self):
        rng = random.Random(41)
        for n in range(3, 40):
            state = competition(n)
            votes = {c["id"]: rng.randrange(1000) for c in state["contestants"]}
            state["ballots"].update(votes=votes, total=sum(votes.values()))
            result = calculate(state)
            for field, bank in [("audience_points", 750), ("jury_points", 250)]:
                self.assertEqual(sum(r[field] for r in result["rows"]), bank)

    def test_disqualification_keeps_counts_and_excludes_both_bases(self):
        state = competition(4, 4)
        c = state["contestants"][0]
        c.update(dq=True, reason="Порушення правил")
        result = calculate(state)
        self.assertEqual(result["eligible_votes"], 30)
        self.assertEqual(result["excluded_votes"], 10)
        self.assertEqual(result["invalid_ballots"], 0)
        self.assertEqual(result["eligible_jury"], 16)
        excluded = next(r for r in result["rows"] if r["id"] == c["id"])
        self.assertEqual(excluded["jury_raw"], 20)
        self.assertEqual(excluded["votes"], 10)
        self.assertEqual(excluded["total"], 0)
        self.assertEqual(excluded["number"], 1)

    def test_jury_rejects_missing_and_duplicate_awards(self):
        state = competition()
        jid = state["jury"][0]["id"]
        cid = state["contestants"][2]["id"]
        state["scores"][jid][cid] = 0
        with self.assertRaisesRegex(VotingError, "ще не поставлено 1"):
            calculate(state)
        state["scores"][jid][cid] = 5
        with self.assertRaisesRegex(VotingError, "кільком"):
            calculate(state)

    def test_shortlist_manual_exact_and_preserves_original(self):
        state = competition(7)
        state["shortlist"] = {"enabled": True, "target": 3, "confirmed": False}
        for c in state["contestants"]:
            c["finalist"] = c["original"] in [2, 5, 7]
        normalized = clean_state(state, state)
        validate(normalized, 3)
        self.assertEqual([(c["original"], c["final"]) for c in normalized["contestants"] if c["final"]], [(2, 1), (5, 2), (7, 3)])
        state["shortlist"]["target"] = 4
        with self.assertRaisesRegex(VotingError, "рівно 4"):
            validate(state, 3)

    def test_without_shortlist_keep_registration_numbers_and_dq_never_renumbers(self):
        state = competition(4)
        for c in state["contestants"]:
            c["original"] += 10
        normalized = clean_state(state, state)
        self.assertEqual([c["final"] for c in normalized["contestants"]], [11, 12, 13, 14])
        normalized["contestants"][0]["dq"] = True
        again = clean_state(normalized, normalized)
        self.assertEqual([c["final"] for c in again["contestants"]], [11, 12, 13, 14])

    def test_reconciliation_separates_invalid_and_disqualified(self):
        state = competition()
        state["ballots"]["total"] = 42
        state["ballots"]["invalid"] = 2
        validate(state, 4)
        state["ballots"]["invalid"] = 5
        with self.assertRaisesRegex(VotingError, "на 3 голосів більше"):
            validate(state, 4)

    def test_zero_pools_and_too_few_contestants_block(self):
        state = competition()
        state["ballots"] = {"total": 0, "invalid": 0, "votes": {}}
        with self.assertRaisesRegex(VotingError, "Немає голосів"):
            calculate(state)
        with self.assertRaisesRegex(VotingError, "щонайменше троє"):
            validate(competition(2), 2)

    def test_complete_tie_has_shared_rank(self):
        state = competition(3)
        for i, j in enumerate(state["jury"]):
            state["scores"][j["id"]] = {c["id"]: [5, 3, 1][(k + i) % 3] for k, c in enumerate(state["contestants"])}
        result = calculate(state)
        self.assertEqual([r["rank"] for r in result["rows"]], [1, 1, 1])
        self.assertTrue(result["warnings"])
        self.assertIn("Перше місце ділять", script(result)["ending"])

    def test_rounding_ties_use_specified_meaningful_criteria(self):
        rows = [{"id": str(i), "original": i, "votes": v} for i, v in enumerate([1, 3, 8])]
        _, points, notices = allocate(rows, 750, "votes", lambda r: (r["votes"],))
        self.assertEqual(points["1"], 188)
        self.assertEqual(points["0"], 62)
        self.assertTrue(notices)
        rows = [{"id": str(i), "original": i, "jury_raw": 5, "fives": f, "threes": t, "ones": o} for i, (f, t, o) in enumerate([(0, 1, 2), (1, 0, 0), (0, 0, 5)])]
        _, points, _ = allocate(rows, 250, "jury_raw", lambda r: (r["fives"], r["threes"], r["ones"]))
        self.assertEqual(points["1"], 84)

    def test_exact_ranking_tie_uses_audience_not_registration_order(self):
        state = competition(3)
        state["ballots"]["votes"] = {c["id"]: v for c, v in zip(state["contestants"], [8, 10, 9])}
        state["ballots"]["total"] = 27
        result = calculate(state)
        self.assertEqual(result["rows"][0]["number"], 2)
        self.assertEqual(result["rows"][0]["combined_exact"], result["rows"][1]["combined_exact"])
        self.assertTrue(any("тай-брейку" in w for w in result["warnings"]))

    def test_script_fixed_order_breakdown_and_exact_intro(self):
        result = calculate(competition())
        generated = script(result)
        self.assertEqual([b["id"] for b in generated["blocks"]], result["reveal_order"])
        self.assertIn("ми порахували", INTRO.lower())
        self.assertNotIn("розподілилили", INTRO)
        for block in generated["blocks"]:
            self.assertIn("Від журі —", block["spoken"])
            self.assertIn("Від глядачів —", block["spoken"])
            self.assertIn("Разом —", block["spoken"])
        self.assertIn("LAST_RESULT", generated["blocks"][-1]["states"])

    def test_schema_rejects_bad_values_and_changed_jury_identifiers(self):
        state = competition()
        state["ballots"]["total"] = -1
        with self.assertRaises(VotingError):
            clean_state(state, state)
        state = competition()
        previous = copy.deepcopy(state)
        state["jury"][0]["code"] = "Z"
        with self.assertRaises(VotingError):
            clean_state(state, previous)


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class VotingIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("voting-owner", "owner@example.org", "test-password-foo")
        self.client.force_login(self.user)
        self.session = Session.objects.create(name="Тестовий конкурс", state=competition(), phase=4)

    def post(self, state=None, action="save", step=4, revision=None):
        return self.client.post(reverse("admin:voting_save", args=[self.session.pk]), json.dumps({"state": state or self.session.state, "action": action, "step": step, "revision": self.session.revision if revision is None else revision}), content_type="application/json")

    def test_every_route_private_and_hidden_from_public(self):
        self.client.logout()
        for name in ["voting_detail", "voting_save", "voting_photo", "voting_pdf", "voting_history"]:
            response = self.client.get(reverse("admin:" + name, args=[self.session.pk]))
            self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("admin:voting_create")).status_code, 302)

    def test_no_module_links_on_public_registration(self):
        from .models import RegistrationCampaign
        RegistrationCampaign.objects.create(internal_name="Guests", slug="voting-privacy", public_title="Гості", intro_text="Welcome", success_text="Thanks")
        response = self.client.get("/r/voting-privacy/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "costume-voting")
        self.assertNotContains(response, "Конкурс костюмів")

    def test_permissions_and_csrf(self):
        viewer = get_user_model().objects.create_user("viewer", is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse("admin:voting_detail", args=[self.session.pk])).status_code, 403)
        viewer.user_permissions.add(Permission.objects.get(codename="operate_costume_voting"))
        self.assertEqual(self.client.get(reverse("admin:voting_detail", args=[self.session.pk])).status_code, 200)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        self.assertEqual(secure.post(reverse("admin:voting_save", args=[self.session.pk]), "{}", content_type="application/json").status_code, 403)

    def test_creation_defaults_and_independence(self):
        response = self.client.post(reverse("admin:voting_create"), {"name": "Репетиція"})
        self.assertEqual(response.status_code, 302)
        created = Session.objects.exclude(pk=self.session.pk).get()
        self.assertEqual(len(created.state["jury"]), 3)
        self.assertEqual(created.history.count(), 1)
        self.session.refresh_from_db()
        self.assertEqual(self.session.name, "Тестовий конкурс")

    def test_all_steps_render_in_ukrainian(self):
        self.session.result = calculate(self.session.state)
        self.session.phase = 7
        self.session.save()
        for step in range(1, 8):
            response = self.client.get(reverse("admin:voting_detail", args=[self.session.pk]), {"step": step})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "КРОК")
            self.assertContains(response, 'lang="uk"')
            self.assertNotContains(response, "Кабинет организатора")
            self.assertNotContains(response, "Сменить пароль")

    def test_autosave_refresh_and_conflict_do_not_overwrite(self):
        state = copy.deepcopy(self.session.state)
        state["ballots"]["invalid"] = 3
        response = self.post(state)
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state["ballots"]["invalid"], 3)
        self.assertEqual(self.session.history.count(), 1)
        conflict = self.post(action="save", revision=0)
        self.assertEqual(conflict.status_code, 409)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state["ballots"]["invalid"], 3)

    def test_next_validation_and_lock_are_atomic(self):
        state = copy.deepcopy(self.session.state)
        state["ballots"]["total"] += 1
        self.assertEqual(self.post(state, "next").status_code, 400)
        self.session.refresh_from_db()
        self.assertFalse(self.session.locked)
        self.assertEqual(self.session.revision, 0)
        self.assertEqual(self.post(action="next").status_code, 200)
        self.session.refresh_from_db()
        self.assertTrue(self.session.locked)
        self.assertEqual(self.session.phase, 5)
        changed = copy.deepcopy(self.session.state)
        changed["contestants"][0]["name"] = "Forged"
        self.assertEqual(self.post(changed, step=5).status_code, 400)

    def test_result_snapshot_invalidation_and_completion(self):
        self.session.locked = True
        self.session.phase = 5
        self.session.save()
        self.assertEqual(self.post(action="next", step=5).status_code, 200)
        self.session.refresh_from_db()
        self.assertTrue(self.session.result)
        changed = copy.deepcopy(self.session.state)
        changed["contestants"][0].update(dq=True, reason="Порушення")
        self.assertEqual(self.post(changed, step=6).status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.result, {})
        self.assertEqual(self.session.phase, 6)
        self.assertEqual(self.post(action="complete", step=5).status_code, 200)
        self.session.refresh_from_db()
        self.assertTrue(self.session.completed)
        self.assertEqual(self.post(step=5).status_code, 400)

    def test_pdf_private_public_contents_and_no_contacts(self):
        self.session.phase = 6
        self.session.result = calculate(self.session.state)
        self.session.save()
        response = self.client.get(reverse("admin:voting_pdf", args=[self.session.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertNotIn(b"PRIVATE_PHONE", response.content)
        self.assertNotIn(b"PRIVATE_INSTAGRAM", response.content)
        self.assertIn("no-store", response["Cache-Control"])

    def test_photos_saved_and_locked_and_cross_session_isolation(self):
        image = io.BytesIO()
        Image.new("RGB", (500, 600), "blue").save(image, "JPEG")
        from django.core.files.uploadedfile import SimpleUploadedFile
        cid = self.session.state["contestants"][0]["id"]
        url = reverse("admin:voting_photo", args=[self.session.pk])
        response = self.client.post(url, {"contestant": cid, "revision": 0, "photo": SimpleUploadedFile("photo.jpg", image.getvalue(), "image/jpeg")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Photo.objects.count(), 1)
        self.assertEqual(self.client.get(url, {"contestant": cid}).status_code, 200)
        other = Session.objects.create(name="Other", state=initial_state())
        self.assertEqual(self.client.get(reverse("admin:voting_photo", args=[other.pk]), {"contestant": cid}).status_code, 404)
        self.session.refresh_from_db()
        self.session.locked = True
        self.session.save()
        self.assertEqual(self.client.post(url, {"contestant": cid, "revision": self.session.revision, "remove": "1"}).status_code, 400)
