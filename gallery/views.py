from django.shortcuts import render

from .models import GalleryImage, SliderImage


def gallery(request):
    context = {
        'slides': SliderImage.objects.filter(is_active=True, placement__in=['gallery', 'both']),
        'images': GalleryImage.objects.filter(is_active=True),
    }
    return render(request, 'gallery.html', context)
