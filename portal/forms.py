from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator

from portal.models import Challenge, Profile, Submission


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(max_length=254)
    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    institution = forms.CharField(max_length=120, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "institution")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get("first_name", "")
        last_name = cleaned_data.get("last_name", "")
        if len(f"{first_name} {last_name}".strip()) > 80:
            self.add_error("last_name", "Your combined first and last name must fit within 80 characters.")
        return cleaned_data


class ProfileForm(forms.ModelForm):
    email = forms.EmailField(max_length=254)

    class Meta:
        model = Profile
        fields = ("display_name", "institution", "bio")
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["email"].initial = user.email

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if commit:
            self.user.email = self.cleaned_data["email"]
            self.user.save(update_fields=["email"])
        return profile


class ChallengeSubmissionForm(forms.Form):
    def __init__(self, *args, challenges, **kwargs):
        super().__init__(*args, **kwargs)
        self.challenges = list(challenges)
        for challenge in self.challenges:
            field_name = f"answer_{challenge.pk}"
            if challenge.kind == Challenge.Kind.OBJECTIVE:
                choices = [("", "Choose an answer")] + [(str(option), str(option)) for option in challenge.choices]
                self.fields[field_name] = forms.ChoiceField(
                    label=challenge.title,
                    choices=choices,
                    required=True,
                    widget=forms.RadioSelect,
                )
            else:
                self.fields[field_name] = forms.CharField(
                    label=challenge.title,
                    required=True,
                    validators=[MaxLengthValidator(10000)],
                    widget=forms.Textarea(attrs={"rows": 12, "spellcheck": "false"}),
                )

    def clean(self):
        cleaned_data = super().clean()
        for challenge in self.challenges:
            key = f"answer_{challenge.pk}"
            answer = cleaned_data.get(key)
            if answer is None:
                continue
            if challenge.kind == Challenge.Kind.OBJECTIVE and answer not in [str(option) for option in challenge.choices]:
                self.add_error(key, "Select one of the available options.")
        return cleaned_data

    def answers(self):
        return {
            str(challenge.pk): self.cleaned_data[f"answer_{challenge.pk}"].strip()
            for challenge in self.challenges
        }


class GradeSubmissionForm(forms.Form):
    score = forms.IntegerField(min_value=0)
    feedback = forms.CharField(required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, submission, **kwargs):
        super().__init__(*args, **kwargs)
        self.submission = submission
        self.fields["score"].label = "Manual review score"
        self.fields["score"].max_value = submission.round.max_score - submission.auto_score
        self.fields["score"].widget.attrs["max"] = self.fields["score"].max_value
        self.fields["score"].help_text = (
            f"Manual points remaining: {self.fields['score'].max_value}. "
            f"Automatic points already earned: {submission.auto_score}."
        )

    def clean_score(self):
        score = self.cleaned_data["score"]
        if score > self.submission.round.max_score - self.submission.auto_score:
            raise forms.ValidationError("Manual score cannot exceed the points remaining after automatic scoring.")
        return score
