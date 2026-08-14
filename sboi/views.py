from django.contrib import messages
from django.shortcuts import redirect


def csrf_failure(request, reason=""):
    messages.error(request, 'Your session expired. Please try again.')
    referer = request.META.get('HTTP_REFERER', '')
    if referer and referer.startswith(('http://', 'https://')):
        return redirect(referer)
    return redirect('home:home')
