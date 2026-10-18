from django.contrib import admin

from portal.models import Challenge, Competition, Profile, Round, Submission


class ChallengeInline(admin.TabularInline):
    model = Challenge
    extra = 0
    fields = ("order", "title", "kind", "points", "prompt", "choices", "correct_answer", "starter_code")


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ("order", "title", "status", "opens_at", "closes_at", "duration_minutes", "passing_score")
    list_editable = ("status", "passing_score")
    list_filter = ("status",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ChallengeInline]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "round", "status", "score", "started_at", "submitted_at", "graded_at", "graded_by")
    list_filter = ("status", "round")
    search_fields = ("user__username", "user__email", "round__title")
    readonly_fields = ("user", "round", "answers", "response_text", "started_at", "submitted_at", "graded_at", "graded_by")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "institution", "role")
    list_filter = ("role",)
    search_fields = ("display_name", "user__username", "user__email", "institution")


@admin.register(Challenge)
class ChallengeAdmin(admin.ModelAdmin):
    list_display = ("title", "round", "kind", "order", "points")
    list_filter = ("round", "kind")


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "results_published", "demo_data", "updated_at")
    list_editable = ("results_published", "demo_data")

    def has_add_permission(self, request):
        return not Competition.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = "Code Battle operations"
admin.site.site_title = "Code Battle admin"
admin.site.index_title = "Manage the competition"
