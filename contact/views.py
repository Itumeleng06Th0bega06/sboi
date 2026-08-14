from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import ContactMessageForm
from .models import ContactInfo


def contact(request):
    info = ContactInfo.objects.first()
    if request.method == 'POST':
        form = ContactMessageForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Thank you for reaching out. We will respond as soon as possible.')
            return redirect('contact:contact')
    else:
        form = ContactMessageForm()
    context = {
        'info': info,
        'form': form,
    }
    return render(request, 'contact.html', context)
