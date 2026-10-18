import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from portal.models import Profile


class Command(BaseCommand):
    help = "Create the initial staff account from ADMIN_USERNAME, ADMIN_EMAIL, and ADMIN_PASSWORD."

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        email = os.environ.get("ADMIN_EMAIL", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not username or not email or not password:
            raise CommandError("Set ADMIN_USERNAME, ADMIN_EMAIL, and ADMIN_PASSWORD to create the initial administrator.")
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Administrator {username} already exists; no changes made.")
            return
        user = User.objects.create_user(username=username, email=email, password=password, is_staff=True)
        user.profile.role = Profile.Role.ADMIN
        user.profile.save(update_fields=["role"])
        self.stdout.write(self.style.SUCCESS(f"Created initial administrator {username}."))
