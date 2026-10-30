from .models import ChurchProfile, Leader


def about_chapters(request):
    profile = ChurchProfile.objects.first()
    chapters = [
        (
            'about:leadership',
            'ch-leadership',
            'Visionary Leadership',
            'Meet the people entrusted with carrying the vision.',
            Leader.objects.exists(),
        ),
        (
            'about:founder',
            'ch-founder',
            "Founder's Message",
            'A personal message from the vision bearer.',
            bool(profile and profile.founder_message),
        ),
        (
            'about:story',
            'ch-story',
            'Our Story',
            'How the ministry began and the journey since.',
            bool(profile and profile.story),
        ),
        (
            'about:vision',
            'ch-vision',
            'Our Vision',
            'The conviction that shapes everything we do.',
            bool(profile and profile.vision),
        ),
        (
            'about:mission',
            'ch-mission',
            'Our Mission',
            'How we pursue the vision in practical ways.',
            bool(profile and profile.mission),
        ),
    ]
    return {
        'about_chapters': [
            {
                'url_name': url_name,
                'id': anchor,
                'title': title,
                'blurb': blurb,
            }
            for url_name, anchor, title, blurb, show in chapters
            if show
        ]
    }
