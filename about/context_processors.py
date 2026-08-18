from .models import ChurchProfile, CoreValue, Leader


def about_chapters(request):
    profile = ChurchProfile.objects.first()
    chapters = [
        ('ch-leadership', 'Visionary Leadership', Leader.objects.exists()),
        ('ch-founder', "Founder's Message", bool(profile and profile.founder_message)),
        ('ch-story', 'Our Story', bool(profile and profile.story)),
        ('ch-vision', 'Our Vision', bool(profile and profile.vision)),
        ('ch-mission', 'Our Mission', bool(profile and profile.mission)),
        ('ch-values', 'Core Values', CoreValue.objects.exists()),
    ]
    return {'about_chapters': [{'id': cid, 'title': title} for cid, title, show in chapters if show]}