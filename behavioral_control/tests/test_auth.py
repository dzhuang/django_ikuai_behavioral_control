from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from tests.factories import UserFactory
from tests.mixins import RequestTestMixin


class UserTokenAutoCreateTest(TestCase):
    # This actually tests jvtransport/serializers.py
    def test_token_generated(self):
        exist_token_counts = Token.objects.count()  # noqa
        test_user = UserFactory()
        self.assertTrue(
            Token.objects.filter(user=test_user).count() > 0  # noqa
        )
        self.assertEqual(
            Token.objects.count(), exist_token_counts + 1  # noqa
        )


class AuthTest(RequestTestMixin, TestCase):
    @property
    def profile_url(self):
        return reverse("profile")

    @property
    def home_url(self):
        return reverse("home")

    def test_non_user_get_login(self):
        self.client.logout()
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)

    def test_user_get_login(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 302)

    def test_user_without_token_get_login(self):
        # Make sure this rendered without problem
        user = UserFactory()
        Token.objects.filter(user=user).delete()  # noqa

        self.client.force_login(user)
        response = self.client.get(self.login_url)

        self.assertEqual(response.status_code, 302)

    def test_user_post_update_email(self):
        # Only email is writable
        self.client.force_login(self.user)

        user_email = self.user.email
        new_email = "blabla@bla.com"
        assert user_email != new_email

        # no submit, not updated {{{
        response = self.client.post(
            self.profile_url, data={"email": new_email})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(user_email, self.user.email)

        # }}}

        response = self.client.post(
            self.profile_url, data={
                "email": new_email,
                "submit": ""})

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(user_email, self.user.email)

    def test_user_post_invalid_email(self):
        self.client.force_login(self.user)

        user_email = self.user.email
        invalid_email = "blabla.bla.com"
        assert user_email != invalid_email

        response = self.client.post(
            self.profile_url, data={
                "email": invalid_email,
                "submit": ""})

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 200)

        # not updated
        self.assertEqual(user_email, self.user.email)

    def test_username_token_not_editable(self):
        self.client.force_login(self.user)

        user_name = self.user.username
        new_username = "foo_bar"
        assert new_username != user_name

        response = self.client.post(
            self.profile_url, data={
                "username": new_username,
                "submit": ""})

        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, user_name)

        exist_token = Token.objects.get(user=self.user).key  # noqa
        new_token = "asdfasfasdfadasdf"
        assert exist_token != new_token

        response = self.client.post(
            self.profile_url, data={
                "token": "asdfasfasdfadasdf",
                "submit": ""})

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            exist_token, Token.objects.get(user=self.user).key)  # noqa
