from crispy_forms.layout import Button, Submit
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm as AuthForm
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework.authtoken.models import Token

from my_router.utils import StyledFormMixin


class AuthenticationForm(StyledFormMixin, AuthForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        self.helper.add_input(
                Submit("login", _("Sign in")))


class UserForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        token = kwargs.pop("token", None)
        super().__init__(*args, **kwargs)

        self.fields["api_token"] = forms.CharField()
        self.fields["api_token"].disabled = True
        self.fields["api_token"].required = False
        self.fields["api_token"].initial = token

        self.fields["username"].required = False
        self.fields["username"].disabled = True

        self.helper.add_input(
            Submit("submit", _("Submit")))

        self.helper.add_input(
                Button("logout", _("Sign out"), css_class="btn btn-danger",
                       onclick=(
                           "window.location.href='%s'"
                           % reverse("logout"))))


@login_required(login_url='/login/')
def user_profile(request):
    user_form = None

    user = request.user
    tokens = Token.objects.filter(user=user)  # noqa
    token = None
    if tokens.count():
        token = tokens[0]

    if request.method == "POST":
        if "submit" in request.POST:
            user_form = UserForm(
                    request.POST,
                    instance=user,
                    token=token,
            )
            if user_form.is_valid():
                user_form.save(commit=True)

    if user_form is None:
        request.user.refresh_from_db()
        user_form = UserForm(
            instance=user,
            token=token,
        )

    return render(request, "generic-form-page.html", {
        "form": user_form,
        "form_description": _("User Profile"),
        })
