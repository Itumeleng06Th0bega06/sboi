from django.contrib import messages
from django.shortcuts import redirect, render


def csrf_failure(request, reason=""):
    messages.error(request, 'Your session expired. Please try again.')
    referer = request.META.get('HTTP_REFERER', '')
    if referer and referer.startswith(('http://', 'https://')):
        return redirect(referer)
    return redirect('home:home')


def handler404(request, exception):
    return render(request, '404.html', status=404)


def handler500(request):
    return render(request, '500.html', status=500)


def handler403(request, exception):
    return render(request, '403.html', status=403)


def handler400(request, exception):
    return render(request, '400.html', status=400)
