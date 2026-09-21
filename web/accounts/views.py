"""Register / login / logout. Login and logout use Django's built-in views."""

from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render


def register(request):
    """Create a new user, then send them to login."""
    if request.user.is_authenticated:
        return redirect("run_list")
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("login")
    return render(request, "accounts/register.html", {"form": form})
