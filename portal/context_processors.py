from portal.models import Competition


def competition_context(request):
    return {"competition": Competition.objects.filter(pk=1).first()}
