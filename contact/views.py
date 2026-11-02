from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ContactMessageForm
from .models import ContactInfo, ContactMessage


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


@login_required
def message_attachment(request, pk):
    """Stream a private attachment only to its owner or an authorised admin.

    ``ContactMessage.attachment`` uses ``PrivateMediaStorage`` with no base URL,
    so this permission-checked response is the only way to read the file.
    """
    message = get_object_or_404(ContactMessage, pk=pk)
    allowed = (
        message.user_id == request.user.pk
        or request.user.has_perm('contact.manage_contact_messages')
        or request.user.is_superuser
    )
    if not allowed:
        raise Http404('Attachment not found.')
    if not message.attachment:
        raise Http404('No attachment on this message.')
    content_type = getattr(message.attachment.file, 'content_type', None)
    return FileResponse(
        message.attachment.open('rb'),
        as_attachment=True,
        filename=message.attachment_name,
        content_type=content_type or 'application/octet-stream',
    )
