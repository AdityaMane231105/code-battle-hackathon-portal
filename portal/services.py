from django.db import transaction
from django.utils import timezone

from portal.models import Challenge, Competition, Round, Submission


def can_enter_round(user, round_obj):
    if not user.is_authenticated or not round_obj.is_open_now:
        return False
    previous = Round.objects.filter(order__lt=round_obj.order).order_by("-order").first()
    if previous is None:
        return True
    previous_submission = Submission.objects.filter(user=user, round=previous).first()
    return bool(
        previous_submission
        and previous_submission.status == Submission.Status.GRADED
        and previous_submission.score is not None
        and previous_submission.score >= previous.passing_score
    )


@transaction.atomic
def grade_objective_answers(submission, answers, response_text=""):
    challenges = list(submission.round.challenges.all())
    automatic_score = 0
    manual_exists = False
    clean_answers = {}
    for challenge in challenges:
        answer = str(answers.get(str(challenge.pk), "")).strip()
        clean_answers[str(challenge.pk)] = answer
        if challenge.is_auto_graded:
            if answer.casefold() == challenge.correct_answer.strip().casefold():
                automatic_score += challenge.points
        else:
            manual_exists = True

    submission.answers = clean_answers
    submission.response_text = response_text
    submission.auto_score = automatic_score
    submission.submitted_at = timezone.now()
    if manual_exists:
        submission.status = Submission.Status.SUBMITTED
        submission.score = None
    else:
        submission.status = Submission.Status.GRADED
        submission.score = automatic_score
        submission.graded_at = submission.submitted_at
    submission.save(
        update_fields=["answers", "response_text", "auto_score", "submitted_at", "status", "score", "graded_at"]
    )
    return submission


@transaction.atomic
def finalize_timed_out_submission(submission):
    if submission.status != Submission.Status.IN_PROGRESS or submission.time_remaining_seconds > 0:
        return submission
    submission.answers = {}
    submission.submitted_at = timezone.now()
    if submission.round.challenges.exclude(kind=Challenge.Kind.OBJECTIVE).exists():
        submission.status = Submission.Status.SUBMITTED
        submission.auto_score = 0
        submission.score = None
    else:
        submission.status = Submission.Status.GRADED
        submission.score = 0
        submission.graded_at = submission.submitted_at
    submission.save(update_fields=["answers", "auto_score", "submitted_at", "status", "score", "graded_at"])
    return submission


def current_competition():
    competition, _created = Competition.objects.get_or_create(pk=1)
    return competition
