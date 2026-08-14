from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from blackboard.models import MemberProfile

from .forms import MemberRegistrationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('blackboard:blackboard')
    if request.method == 'POST':
        form = MemberRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            MemberProfile.objects.create(user=user)
            login(request, user)
            messages.success(
                request,
                'Your account has been created. Welcome to the Shekinah Blaze family!',
            )
            return redirect('blackboard:blackboard')
    else:
        form = MemberRegistrationForm()
    return render(request, 'members/register.html', {'form': form})


@login_required
def members_home(request):
    return redirect('blackboard:blackboard')
