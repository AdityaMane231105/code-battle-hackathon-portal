from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from portal.models import Challenge, Competition, Profile, Round, Submission
from portal.services import can_enter_round, grade_objective_answers


class CompetitionFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="rhea",
            email="rhea@example.test",
            password="A-long-test-password-981",
            first_name="Rhea",
        )
        self.quiz = Round.objects.create(
            title="Quiz Battle",
            slug="quiz-battle",
            description="Core concepts",
            order=1,
            status=Round.Status.OPEN,
            opens_at=timezone.now() - timedelta(minutes=2),
            closes_at=timezone.now() + timedelta(hours=2),
            duration_minutes=20,
            passing_score=10,
        )
        self.question = Challenge.objects.create(
            round=self.quiz,
            title="Complexity",
            prompt="Pick an answer.",
            kind=Challenge.Kind.OBJECTIVE,
            order=1,
            points=10,
            choices=["O(1)", "O(n)"],
            correct_answer="O(1)",
        )
        self.coding_round = Round.objects.create(
            title="Coding Battle",
            slug="coding-battle",
            description="Write a solution",
            order=2,
            status=Round.Status.OPEN,
            opens_at=timezone.now() - timedelta(minutes=2),
            closes_at=timezone.now() + timedelta(hours=2),
            duration_minutes=30,
            passing_score=0,
        )
        self.coding = Challenge.objects.create(
            round=self.coding_round,
            title="Pair sum",
            prompt="Return the indices.",
            kind=Challenge.Kind.CODING,
            order=1,
            points=50,
        )

    def test_registration_creates_participant_and_logs_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "new-builder",
                "first_name": "New",
                "last_name": "Builder",
                "email": "builder@example.test",
                "institution": "Open Lab",
                "password1": "A-long-password-981",
                "password2": "A-long-password-981",
            },
            follow=True,
        )
        self.assertEqual(response.redirect_chain, [(reverse("dashboard"), 302)])
        self.assertContains(response, "Account created successfully! You are now signed in.")
        profile = Profile.objects.get(user__username="new-builder")
        self.assertEqual(profile.role, Profile.Role.PARTICIPANT)
        self.assertEqual(profile.institution, "Open Lab")
        self.assertIn("_auth_user_id", self.client.session)

    def test_sign_in_redirects_to_participant_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.user.username, "password": "A-long-test-password-981"},
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertIn("_auth_user_id", self.client.session)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Your rounds")
        self.assertContains(dashboard, "Enter round")

    def test_registration_rejects_display_names_longer_than_profile_limit(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "long-builder",
                "first_name": "First" * 10,
                "last_name": "Last" * 10,
                "email": "long@example.test",
                "password1": "A-long-password-981",
                "password2": "A-long-password-981",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "combined first and last name must fit")
        self.assertFalse(User.objects.filter(username="long-builder").exists())

    def test_quiz_submission_is_auto_scored_and_shown_on_dashboard(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("start_round", args=[self.quiz.slug]))
        self.assertRedirects(response, reverse("play_round", args=[self.quiz.slug]))
        attempt = Submission.objects.get(user=self.user, round=self.quiz)
        response = self.client.post(
            reverse("play_round", args=[self.quiz.slug]),
            {f"answer_{self.question.pk}": "O(1)"},
        )
        attempt.refresh_from_db()
        self.assertRedirects(response, reverse("submission_result", args=[attempt.pk]))
        self.assertEqual(attempt.status, Submission.Status.GRADED)
        self.assertEqual(attempt.score, 10)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, "10")

    def test_objective_scoring_is_case_insensitive_and_manual_answer_retained(self):
        answers = {
            str(self.question.pk): "o(1)",
            str(self.coding.pk): "def pair_sum(values, target): return [0, 1]",
        }
        attempt = Submission.objects.create(user=self.user, round=self.coding_round)
        attempt = grade_objective_answers(attempt, answers)
        self.assertEqual(attempt.status, Submission.Status.SUBMITTED)
        self.assertIsNone(attempt.score)
        self.assertEqual(attempt.auto_score, 0)
        self.assertEqual(attempt.answers[str(self.coding.pk)], "def pair_sum(values, target): return [0, 1]")

    def test_auto_score_is_preserved_while_manual_review_is_pending(self):
        objective = Challenge.objects.create(
            round=self.coding_round,
            title="Quick check",
            prompt="Choose.",
            kind=Challenge.Kind.OBJECTIVE,
            order=2,
            points=5,
            choices=["yes", "no"],
            correct_answer="yes",
        )
        attempt = Submission.objects.create(user=self.user, round=self.coding_round)
        attempt = grade_objective_answers(
            attempt,
            {str(self.coding.pk): "answer", str(objective.pk): "yes"},
        )
        self.assertEqual(attempt.status, Submission.Status.SUBMITTED)
        self.assertEqual(attempt.auto_score, 5)
        self.assertIsNone(attempt.score)

    def test_later_round_requires_passing_previous_round(self):
        self.assertFalse(can_enter_round(self.user, self.coding_round))
        Submission.objects.create(
            user=self.user,
            round=self.quiz,
            status=Submission.Status.GRADED,
            score=10,
        )
        self.assertTrue(can_enter_round(self.user, self.coding_round))

    def test_later_round_is_locked_when_previous_score_is_below_threshold(self):
        Submission.objects.create(
            user=self.user,
            round=self.quiz,
            status=Submission.Status.GRADED,
            score=9,
        )
        self.assertFalse(can_enter_round(self.user, self.coding_round))

    def test_round_must_be_open_and_within_its_time_window(self):
        self.quiz.status = Round.Status.SCHEDULED
        self.quiz.save()
        self.assertFalse(can_enter_round(self.user, self.quiz))
        self.quiz.status = Round.Status.OPEN
        self.quiz.opens_at = timezone.now() + timedelta(hours=1)
        self.quiz.save()
        self.assertFalse(can_enter_round(self.user, self.quiz))

    def test_participant_can_finish_an_attempt_started_before_round_closed(self):
        attempt = Submission.objects.create(user=self.user, round=self.quiz)
        self.quiz.status = Round.Status.CLOSED
        self.quiz.closes_at = timezone.now()
        self.quiz.save()
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("play_round", args=[self.quiz.slug]),
            {f"answer_{self.question.pk}": "O(1)"},
        )
        attempt.refresh_from_db()
        self.assertRedirects(response, reverse("submission_result", args=[attempt.pk]))
        self.assertEqual(attempt.score, 10)

    def test_expired_post_closes_attempt_even_when_answers_are_invalid(self):
        attempt = Submission.objects.create(
            user=self.user,
            round=self.quiz,
            started_at=timezone.now() - timedelta(minutes=21),
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("play_round", args=[self.quiz.slug]), {})
        attempt.refresh_from_db()
        self.assertRedirects(response, reverse("submission_result", args=[attempt.pk]))
        self.assertEqual(attempt.status, Submission.Status.GRADED)
        self.assertEqual(attempt.score, 0)

    def test_another_participant_cannot_read_submission(self):
        attempt = Submission.objects.create(
            user=self.user,
            round=self.quiz,
            status=Submission.Status.GRADED,
            score=0,
        )
        other = User.objects.create_user(username="other", password="Another-long-password-123")
        self.client.force_login(other)
        response = self.client.get(reverse("submission_result", args=[attempt.pk]))
        self.assertEqual(response.status_code, 404)

    def test_timed_out_attempt_is_closed_with_zero_for_objective_round(self):
        attempt = Submission.objects.create(
            user=self.user,
            round=self.quiz,
            started_at=timezone.now() - timedelta(minutes=21),
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("play_round", args=[self.quiz.slug]))
        attempt.refresh_from_db()
        self.assertRedirects(response, reverse("submission_result", args=[attempt.pk]))
        self.assertEqual(attempt.status, Submission.Status.GRADED)
        self.assertEqual(attempt.score, 0)

    def test_staff_reviews_submission_and_combines_automatic_points(self):
        objective = Challenge.objects.create(
            round=self.coding_round,
            title="Quick check",
            prompt="Choose.",
            kind=Challenge.Kind.OBJECTIVE,
            order=2,
            points=5,
            choices=["yes", "no"],
            correct_answer="yes",
        )
        attempt = Submission.objects.create(user=self.user, round=self.coding_round)
        attempt = grade_objective_answers(
            attempt,
            {str(self.coding.pk): "answer", str(objective.pk): "yes"},
        )
        staff = User.objects.create_user(username="staff", password="Another-long-password-123", is_staff=True)
        staff.profile.role = Profile.Role.ADMIN
        staff.profile.save(update_fields=["role"])
        self.client.force_login(staff)
        response = self.client.post(
            reverse("review_submission", args=[attempt.pk]),
            {"score": 30, "feedback": "Clear algorithm and explanation."},
        )
        attempt.refresh_from_db()
        self.assertRedirects(response, reverse("staff_dashboard"))
        self.assertEqual(attempt.status, Submission.Status.GRADED)
        self.assertEqual(attempt.score, 35)
        self.assertEqual(attempt.graded_by, staff)

    def test_participant_cannot_open_staff_console(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("staff_dashboard")).status_code, 302)

    def test_leaderboard_renders_with_sample_data_notice(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("leaderboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sample leaderboard.")
        self.assertContains(response, "Rhea")

    def test_health_endpoint_and_static_assets_are_available(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIsNotNone(finders.find("portal/app.css"))
        self.assertIsNotNone(finders.find("portal/app.js"))
        self.assertIsNotNone(finders.find("portal/favicon.svg"))

    def test_results_cannot_be_published_before_rounds_close(self):
        competition = Competition.objects.create(pk=1)
        staff = User.objects.create_user(username="admin", password="Another-long-password-123", is_staff=True)
        self.client.force_login(staff)
        response = self.client.post(reverse("publish_results"))
        competition.refresh_from_db()
        self.assertRedirects(response, reverse("staff_dashboard"))
        self.assertFalse(competition.results_published)
        self.assertContains(self.client.get(reverse("staff_dashboard")), "Close every round")

    def test_results_publish_after_rounds_close_and_reviews_clear(self):
        competition = Competition.objects.create(pk=1)
        Round.objects.filter(status=Round.Status.OPEN).update(status=Round.Status.CLOSED)
        staff = User.objects.create_user(username="admin", password="Another-long-password-123", is_staff=True)
        self.client.force_login(staff)
        response = self.client.post(reverse("publish_results"))
        competition.refresh_from_db()
        self.assertRedirects(response, reverse("staff_dashboard"))
        self.assertTrue(competition.results_published)

    def test_demo_seed_opens_existing_sample_rounds_for_qualification_gated_play(self):
        Competition.objects.create(pk=1, demo_data=True)
        Round.objects.filter(pk__in=[self.quiz.pk, self.coding_round.pk]).update(status=Round.Status.SCHEDULED)
        call_command(
            "seed_demo",
            "--if-empty",
            "--open-demo-rounds",
            stdout=StringIO(),
        )
        self.quiz.refresh_from_db()
        self.coding_round.refresh_from_db()
        self.assertTrue(self.quiz.is_open_now)
        self.assertTrue(self.coding_round.is_open_now)
        self.assertFalse(can_enter_round(self.user, self.coding_round))

    def test_demo_seed_does_not_open_rounds_when_demo_data_is_disabled(self):
        Competition.objects.create(pk=1, demo_data=False)
        Round.objects.filter(pk__in=[self.quiz.pk, self.coding_round.pk]).update(status=Round.Status.SCHEDULED)
        call_command(
            "seed_demo",
            "--if-empty",
            "--open-demo-rounds",
            stdout=StringIO(),
        )
        self.quiz.refresh_from_db()
        self.coding_round.refresh_from_db()
        self.assertEqual(self.quiz.status, Round.Status.SCHEDULED)
        self.assertEqual(self.coding_round.status, Round.Status.SCHEDULED)
