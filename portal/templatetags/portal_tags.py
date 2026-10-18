from django import template

register = template.Library()


@register.filter
def field_by_name(form, name):
    return form[name]


@register.filter
def answer_for(answers, challenge_id):
    return answers.get(str(challenge_id), "")


@register.filter
def score_for(submissions, round_id):
    return submissions.get(round_id)


@register.filter
def challenge_field(form, challenge):
    return form[f"answer_{challenge.pk}"]
