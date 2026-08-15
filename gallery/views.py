from django.shortcuts import render

from .models import SliderImage


def gallery(request):
    context = {
        'slides': SliderImage.objects.filter(is_active=True, placement__in=['gallery', 'both']),
    }
    return render(request, 'gallery.html', context)
