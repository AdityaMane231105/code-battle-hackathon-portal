import os
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from portal.models import Challenge, Competition, Profile, Round, Submission


ROUNDS = [
    {
        "title": "Quiz Battle",
        "slug": "quiz-battle",
        "description": "Warm up with core programming concepts. Pick the best answer for every question.",
        "status": Round.Status.OPEN,
        "duration": 20,
        "passing": 20,
        "challenges": [
            ("Big-O basics", "What is the average lookup complexity of a hash table?", "objective", 10,
             ["O(1)", "O(log n)", "O(n)", "O(n log n)"], "O(1)"),
            ("Python collections", "Which Python structure preserves insertion order and maps keys to values?", "objective", 10,
             ["set", "dict", "tuple", "frozenset"], "dict"),
            ("Binary search", "What must be true of a collection before binary search can be used correctly?", "objective", 10,
             ["It must be sorted", "It must have unique values", "It must be a linked list", "It must contain an even number of items"], "It must be sorted"),
        ],
    },
    {
        "title": "Coding Battle",
        "slug": "coding-battle",
        "description": "Design a clear solution, explain its complexity, and submit your code for review.",
        "status": Round.Status.SCHEDULED,
        "duration": 45,
        "passing": 30,
        "challenges": [
            ("Pair sum", "Given an integer list and a target, return the indices of two distinct values that sum to the target. Describe your approach and include a working implementation.", "coding", 50,
             [], ""),
        ],
    },
    {
        "title": "Debugging Battle",
        "slug": "debugging-battle",
        "description": "Find the defect, explain the root cause, and submit a corrected implementation.",
        "status": Round.Status.SCHEDULED,
        "duration": 35,
        "passing": 30,
        "challenges": [
            ("Off-by-one search", "This binary search can loop forever when the target is absent. Identify the defect and submit a corrected version, including a brief explanation.", "debugging", 50,
             [], "def binary_search(items, target):\n    low, high = 0, len(items) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if items[mid] == target:\n            return mid\n        if items[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1"),
        ],
    },
    {
        "title": "Final Battle",
        "slug": "final-battle",
        "description": "A final algorithmic challenge for qualified participants. Explain trade-offs and edge cases.",
        "status": Round.Status.SCHEDULED,
        "duration": 60,
        "passing": 0,
        "challenges": [
            ("Shortest paths", "Given a weighted graph with non-negative edge weights, return shortest distances from a source node. Describe and implement an efficient algorithm, and discuss its complexity.", "coding", 100,
             [], ""),
        ],
    },
]


class Command(BaseCommand):
    help = "Create or update clearly labelled Code Battle sample rounds and challenges."

    def add_arguments(self, parser):
        parser.add_argument("--with-users", action="store_true", help="Create demo accounts from password environment variables.")
        parser.add_argument("--if-empty", action="store_true", help="Do not replace an existing competition setup.")
        parser.add_argument(
            "--open-demo-rounds",
            action="store_true",
            help="Keep the seeded demo rounds available for a full sample run-through.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        competition = Competition.objects.filter(pk=1).first()
        if options["if_empty"] and Round.objects.exists():
            if options["open_demo_rounds"] and competition and competition.demo_data:
                Round.objects.filter(slug__in=[item["slug"] for item in ROUNDS]).update(
                    status=Round.Status.OPEN,
                    opens_at=now - timedelta(days=1),
                    closes_at=now + timedelta(days=14),
                )
                self.stdout.write("Opened all sample rounds for the demo; qualification gates still apply.")
            self.stdout.write("Competition rounds already exist; preserving current event configuration.")
            return
        if competition is None:
            competition = Competition.objects.create(pk=1, name="Code Battle", demo_data=True)
        rounds = {}
        for index, item in enumerate(ROUNDS):
            open_demo_rounds = options["open_demo_rounds"] and competition.demo_data
            opens_at = now - timedelta(days=1) if open_demo_rounds or index == 0 else now + timedelta(days=index)
            closes_at = now + timedelta(days=14) if open_demo_rounds or index == 0 else opens_at + timedelta(days=2)
            round_obj, _ = Round.objects.update_or_create(
                slug=item["slug"],
                defaults={
                    "title": item["title"],
                    "description": item["description"],
                    "order": index + 1,
                    "status": Round.Status.OPEN if open_demo_rounds else item["status"],
                    "opens_at": opens_at,
                    "closes_at": closes_at,
                    "duration_minutes": item["duration"],
                    "passing_score": item["passing"],
                },
            )
            rounds[item["slug"]] = round_obj
            for order, challenge in enumerate(item["challenges"], 1):
                title, prompt, kind, points, choices, correct = challenge
                Challenge.objects.update_or_create(
                    round=round_obj,
                    order=order,
                    defaults={
                        "title": title,
                        "prompt": prompt,
                        "kind": kind,
                        "points": points,
                        "choices": choices,
                        "correct_answer": correct,
                        "starter_code": item["challenges"][0][5] if kind in {"coding", "debugging"} else "",
                    },
                )

        if options["with_users"]:
            admin_password = os.environ.get("DEMO_ADMIN_PASSWORD")
            participant_password = os.environ.get("DEMO_PARTICIPANT_PASSWORD")
            if not admin_password or not participant_password:
                raise CommandError("Set DEMO_ADMIN_PASSWORD and DEMO_PARTICIPANT_PASSWORD before using --with-users.")
            admin = self.create_user("admin@codebattle.local", "Demo Admin", admin_password, staff=True)
            admin.profile.role = Profile.Role.ADMIN
            admin.profile.save(update_fields=["role"])
            alex = self.create_user("alex@demo.codebattle.local", "Alex Morgan (sample)", participant_password)
            sam = self.create_user("sam@demo.codebattle.local", "Sam Rivera (sample)", participant_password)
            self.add_sample_score(alex, rounds["quiz-battle"], 30)
            self.add_sample_score(sam, rounds["quiz-battle"], 20)
            self.stdout.write("Created demo accounts. Sample participants are clearly labelled in the leaderboard.")

        self.stdout.write(self.style.SUCCESS(f"Seeded sample competition data: {competition.name}."))
        self.stdout.write("Sample data is not live competition activity.")

    def create_user(self, username, display_name, password, staff=False):
        user, created = User.objects.get_or_create(username=username, defaults={"email": username})
        user.is_staff = staff
        user.set_password(password)
        user.save()
        user.profile.display_name = display_name
        user.profile.role = Profile.Role.ADMIN if staff else Profile.Role.PARTICIPANT
        user.profile.save(update_fields=["display_name", "role"])
        return user

    def add_sample_score(self, user, round_obj, score):
        Submission.objects.update_or_create(
            user=user,
            round=round_obj,
            defaults={
                "status": Submission.Status.GRADED,
                "answers": {},
                "score": score,
                "started_at": timezone.now() - timedelta(days=1),
                "submitted_at": timezone.now() - timedelta(days=1),
                "graded_at": timezone.now() - timedelta(days=1),
            },
        )
