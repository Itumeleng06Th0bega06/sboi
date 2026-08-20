from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

from .forms import ContactMessageForm
from .models import ContactInfo


def contact(request):
    info = ContactInfo.objects.first()
    if request.method == 'POST':
        form = ContactMessageForm(request.POST)
        if form.is_valid():
            form.save()
            message = 'Thank you for reaching out. We will respond as soon as possible.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'ok': True, 'message': message})
            messages.success(request, message)
            return redirect('contact:contact')
        elif request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'message': 'Please check the form and try again.'}, status=400)
    else:
        form = ContactMessageForm()
    context = {
        'info': info,
        'form': form,
    }
    return render(request, 'contact.html', context)
