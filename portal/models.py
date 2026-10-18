from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class Competition(models.Model):
    name = models.CharField(max_length=120, default="Code Battle")
    results_published = models.BooleanField(default=False)
    demo_data = models.BooleanField(default=True, help_text="Show a banner marking sample/demo data.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "competition settings"
        verbose_name_plural = "competition settings"

    def __str__(self):
        return self.name


class Profile(models.Model):
    class Role(models.TextChoices):
        PARTICIPANT = "participant", "Participant"
        ADMIN = "admin", "Administrator"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=80)
    institution = models.CharField(max_length=120, blank=True)
    bio = models.CharField(max_length=240, blank=True)
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.PARTICIPANT)

    def __str__(self):
        return self.display_name


class Round(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    title = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    order = models.PositiveSmallIntegerField(unique=True, validators=[MinValueValidator(1), MaxValueValidator(4)])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)
    opens_at = models.DateTimeField(null=True, blank=True)
    closes_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveSmallIntegerField(default=30, validators=[MinValueValidator(1), MaxValueValidator(240)])
    passing_score = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValidationError({"closes_at": "The close time must be after the open time."})
        if self.pk and self.challenges.exists() and self.passing_score > self.max_score:
            raise ValidationError({"passing_score": "The passing score cannot exceed this round's total points."})

    @property
    def is_open_now(self):
        now = timezone.now()
        return (
            self.status == self.Status.OPEN
            and (self.opens_at is None or self.opens_at <= now)
            and (self.closes_at is None or self.closes_at > now)
        )

    @property
    def max_score(self):
        return sum(challenge.points for challenge in self.challenges.all())


class Challenge(models.Model):
    class Kind(models.TextChoices):
        OBJECTIVE = "objective", "Multiple choice"
        CODING = "coding", "Coding"
        DEBUGGING = "debugging", "Debugging"
        WRITTEN = "written", "Written response"

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="challenges")
    title = models.CharField(max_length=120)
    prompt = models.TextField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    order = models.PositiveSmallIntegerField(default=1)
    points = models.PositiveSmallIntegerField(default=10, validators=[MinValueValidator(1), MaxValueValidator(1000)])
    choices = models.JSONField(default=list, blank=True, help_text="For multiple choice, enter a JSON list of options.")
    correct_answer = models.CharField(max_length=200, blank=True, help_text="Only used for objective challenges; never shown to participants.")
    starter_code = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["round", "order"], name="unique_challenge_order_per_round"),
        ]

    def __str__(self):
        return f"{self.round.title}: {self.title}"

    def clean(self):
        if self.kind == self.Kind.OBJECTIVE:
            options = [str(option) for option in self.choices]
            if len(options) < 2:
                raise ValidationError({"choices": "Multiple-choice challenges need at least two options."})
            if self.correct_answer not in options:
                raise ValidationError({"correct_answer": "The correct answer must match one of the options."})
        elif self.choices:
            raise ValidationError({"choices": "Only multiple-choice challenges may have answer options."})

    @property
    def is_auto_graded(self):
        return self.kind == self.Kind.OBJECTIVE


class Submission(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Awaiting review"
        GRADED = "graded", "Graded"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    round = models.ForeignKey(Round, on_delete=models.PROTECT, related_name="submissions")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    answers = models.JSONField(default=dict, blank=True)
    response_text = models.TextField(blank=True)
    auto_score = models.PositiveSmallIntegerField(default=0)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="graded_submissions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "round"], name="one_submission_per_user_round"),
        ]
        ordering = ["-submitted_at", "-started_at"]

    def __str__(self):
        return f"{self.user.username} · {self.round.title} · {self.get_status_display()}"

    @property
    def time_remaining_seconds(self):
        elapsed = (timezone.now() - self.started_at).total_seconds()
        return max(0, self.round.duration_minutes * 60 - int(elapsed))

    @property
    def has_manual_challenges(self):
        return self.round.challenges.exclude(kind=Challenge.Kind.OBJECTIVE).exists()
