from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from portal.forms import ChallengeSubmissionForm, GradeSubmissionForm, ProfileForm, RegistrationForm
from portal.models import Profile, Round, Submission
from portal.services import can_enter_round, current_competition, finalize_timed_out_submission, grade_objective_answers


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "portal/home.html", {"rounds": Round.objects.all()})


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            user.profile.display_name = f"{user.first_name} {user.last_name}".strip() or user.username
            user.profile.institution = form.cleaned_data["institution"]
            user.profile.save(update_fields=["display_name", "institution"])
        login(request, user)
        messages.success(request, "Account created successfully! You are now signed in.")
        return redirect("dashboard")
    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard(request):
    competition = current_competition()
    rounds = list(Round.objects.prefetch_related("challenges").all())
    submissions = {submission.round_id: submission for submission in Submission.objects.filter(user=request.user)}
    cards = []
    for round_obj in rounds:
        submission = submissions.get(round_obj.pk)
        previous = Round.objects.filter(order__lt=round_obj.order).order_by("-order").first()
        previous_submission = submissions.get(previous.pk) if previous else None
        qualified = bool(
            previous is None
            or (
                previous_submission
                and previous_submission.status == Submission.Status.GRADED
                and previous_submission.score is not None
                and previous_submission.score >= previous.passing_score
            )
        )
        cards.append(
            {
                "round": round_obj,
                "submission": submission,
                "can_enter": can_enter_round(request.user, round_obj),
                "qualified": qualified,
            }
        )
    scored = Submission.objects.filter(user=request.user, status=Submission.Status.GRADED, score__isnull=False)
    total_score = sum(item.score for item in scored)
    graded_rounds = scored.count()
    leaderboard = leaderboard_rows()
    rank = (
        next((index for index, row in enumerate(leaderboard, 1) if row["user_id"] == request.user.pk), None)
        if graded_rounds
        else None
    )
    return render(
        request,
        "portal/dashboard.html",
        {
            "competition": competition,
            "cards": cards,
            "total_score": total_score,
            "graded_rounds": graded_rounds,
            "rank": rank,
        },
    )


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user.profile, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("profile")
    return render(request, "portal/profile.html", {"form": form})


@login_required
def round_detail(request, slug):
    round_obj = get_object_or_404(Round.objects.prefetch_related("challenges"), slug=slug)
    submission = Submission.objects.filter(user=request.user, round=round_obj).first()
    can_enter = can_enter_round(request.user, round_obj)
    previous_round = Round.objects.filter(order__lt=round_obj.order).order_by("-order").first()
    previous_submission = (
        Submission.objects.filter(user=request.user, round=previous_round).first() if previous_round else None
    )
    qualified = bool(
        previous_round is None
        or (
            previous_submission
            and previous_submission.status == Submission.Status.GRADED
            and previous_submission.score is not None
            and previous_submission.score >= previous_round.passing_score
        )
    )
    return render(
        request,
        "portal/round_detail.html",
        {
            "round": round_obj,
            "submission": submission,
            "can_enter": can_enter,
            "previous_round": previous_round,
            "qualified": qualified,
        },
    )


@login_required
@require_POST
def start_round(request, slug):
    round_obj = get_object_or_404(Round, slug=slug)
    existing = Submission.objects.filter(user=request.user, round=round_obj).first()
    if existing:
        if existing.status == Submission.Status.IN_PROGRESS:
            return redirect("play_round", slug=slug)
        messages.info(request, "You have already submitted this round. Each round allows one attempt.")
        return redirect("round_detail", slug=slug)
    if not can_enter_round(request.user, round_obj):
        messages.error(request, "This round is not open to you yet. Check its schedule and qualification requirements.")
        return redirect("round_detail", slug=slug)
    submission, created = Submission.objects.get_or_create(user=request.user, round=round_obj)
    if not created and submission.status != Submission.Status.IN_PROGRESS:
        messages.info(request, "You have already submitted this round.")
        return redirect("round_detail", slug=slug)
    return redirect("play_round", slug=slug)


@login_required
def play_round(request, slug):
    round_obj = get_object_or_404(Round, slug=slug)
    submission = get_object_or_404(Submission, user=request.user, round=round_obj)
    if submission.status != Submission.Status.IN_PROGRESS:
        return redirect("submission_result", pk=submission.pk)
    if submission.time_remaining_seconds == 0:
        finalize_timed_out_submission(submission)
        messages.warning(request, "Time expired before submission. Your attempt has been closed.")
        return redirect("submission_result", pk=submission.pk)
    challenges = list(round_obj.challenges.all())
    if not challenges:
        messages.error(request, "This round has no challenges yet. Please contact an administrator.")
        return redirect("round_detail", slug=slug)
    form = ChallengeSubmissionForm(request.POST or None, challenges=challenges)
    if request.method == "POST":
        if submission.time_remaining_seconds == 0:
            finalize_timed_out_submission(submission)
            messages.warning(request, "Time expired. Your attempt was closed without late answers.")
            return redirect("submission_result", pk=submission.pk)
        if form.is_valid():
            grade_objective_answers(submission, form.answers())
            messages.success(request, "Your answers were submitted successfully.")
            return redirect("submission_result", pk=submission.pk)
    return render(
        request,
        "portal/play_round.html",
        {
            "round": round_obj,
            "submission": submission,
            "form": form,
            "challenges": challenges,
            "remaining_seconds": submission.time_remaining_seconds,
        },
    )


@login_required
def submission_result(request, pk):
    submission = get_object_or_404(
        Submission.objects.select_related("round", "graded_by"), pk=pk, user=request.user
    )
    return render(request, "portal/submission_result.html", {"submission": submission})


def leaderboard_rows():
    participants = User.objects.filter(is_active=True, is_staff=False, profile__role=Profile.Role.PARTICIPANT).select_related("profile")
    rows = []
    for user in participants:
        submissions = {
            submission.round_id: submission
            for submission in Submission.objects.filter(user=user, status=Submission.Status.GRADED, score__isnull=False)
        }
        total = sum(submission.score for submission in submissions.values())
        rows.append(
            {
                "user_id": user.pk,
                "name": user.profile.display_name,
                "institution": user.profile.institution,
                "score": total,
                "completed": len(submissions),
                "round_scores": submissions,
            }
        )
    return sorted(rows, key=lambda row: (-row["score"], row["name"].casefold()))


@login_required
def leaderboard(request):
    competition = current_competition()
    rounds = list(Round.objects.all())
    rows = leaderboard_rows()
    last_updated = Submission.objects.filter(
        status=Submission.Status.GRADED, graded_at__isnull=False
    ).aggregate(timestamp=Max("graded_at"))["timestamp"]
    return render(
        request,
        "portal/leaderboard.html",
        {"competition": competition, "rounds": rounds, "rows": rows, "last_updated": last_updated},
    )


def is_competition_admin(user):
    return user.is_authenticated and user.is_active and (user.is_superuser or user.is_staff)


staff_required = user_passes_test(is_competition_admin, login_url="login")


@staff_required
def staff_dashboard(request):
    competition = current_competition()
    queue = Submission.objects.filter(status=Submission.Status.SUBMITTED).select_related(
        "user", "user__profile", "round"
    )
    return render(
        request,
        "portal/staff_dashboard.html",
        {
            "competition": competition,
            "rounds": Round.objects.all(),
            "queue": queue,
            "participants": Profile.objects.filter(role=Profile.Role.PARTICIPANT).count(),
            "submissions": Submission.objects.count(),
        },
    )


@staff_required
@require_POST
def publish_results(request):
    competition = current_competition()
    if not competition.results_published:
        if Round.objects.exclude(status=Round.Status.CLOSED).exists():
            messages.error(request, "Close every round before publishing final results.")
            return redirect("staff_dashboard")
        if Submission.objects.filter(
            status__in=[Submission.Status.IN_PROGRESS, Submission.Status.SUBMITTED]
        ).exists():
            messages.error(request, "Finish timed attempts and grade every pending submission before publishing final results.")
            return redirect("staff_dashboard")
    competition.results_published = not competition.results_published
    competition.save(update_fields=["results_published", "updated_at"])
    action = "published" if competition.results_published else "unpublished"
    messages.success(request, f"Final results {action}.")
    return redirect("staff_dashboard")


@staff_required
def review_submission(request, pk):
    submission = get_object_or_404(
        Submission.objects.select_related("user", "user__profile", "round"),
        pk=pk,
        status=Submission.Status.SUBMITTED,
    )
    form = GradeSubmissionForm(request.POST or None, submission=submission)
    challenges = list(submission.round.challenges.all())
    if request.method == "POST" and form.is_valid():
        submission.score = submission.auto_score + form.cleaned_data["score"]
        submission.feedback = form.cleaned_data["feedback"]
        submission.status = Submission.Status.GRADED
        submission.graded_at = timezone.now()
        submission.graded_by = request.user
        submission.save(update_fields=["score", "feedback", "status", "graded_at", "graded_by"])
        messages.success(request, f"Submission for {submission.user.profile.display_name} graded.")
        return redirect("staff_dashboard")
    return render(
        request,
        "portal/review_submission.html",
        {"submission": submission, "form": form, "challenges": challenges},
    )


@staff_required
def staff_participants(request):
    participants = Profile.objects.filter(role=Profile.Role.PARTICIPANT).select_related("user").order_by("display_name")
    return render(request, "portal/staff_participants.html", {"participants": participants})
