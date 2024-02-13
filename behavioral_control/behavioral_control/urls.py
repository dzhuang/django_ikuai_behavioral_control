from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.utils.translation import gettext_lazy as _
from django.views.i18n import JavaScriptCatalog

from my_router import auth, views

urlpatterns = [
    path(r'jsi18n/',
         JavaScriptCatalog.as_view(),
         name='javascript-catalog'),
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(
        redirect_authenticated_user=True,
        template_name='generic-form-page.html',
        form_class=auth.AuthenticationForm,
        extra_context={"form_description": _("Sign in")}),
         name='login'),
    path('logout/', auth_views.LogoutView.as_view(
        template_name='registration/logged_out.html'),
         name='logout'),
    path('profile/', auth.user_profile, name='profile'),
    path('', views.home, name='home'),
]
