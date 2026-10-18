from django.shortcuts import render

from about.content import split_culture
from about.icons import icon_for
from about.models import ChurchProfile, CoreValue


def values(request):
    profile = ChurchProfile.objects.first()

    core_values = list(CoreValue.objects.all())
    for item in core_values:
        item.icon = icon_for(item.title)

    culture_intro, culture_items = split_culture(
        profile.culture_statement if profile else None
    )

    context = {
        'profile': profile,
        'values': core_values,
        'culture_intro': culture_intro,
        'culture_items': culture_items,
    }
    return render(request, 'values.html', context)
