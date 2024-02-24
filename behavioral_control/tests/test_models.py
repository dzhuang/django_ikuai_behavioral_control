from unittest.mock import patch

from django.test import TestCase
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from tests.mixins import CacheMixin, MockRouterClientMixin

from my_router.models import Router


class RouterModelTest(CacheMixin, MockRouterClientMixin, TestCase):
    def tearDown(self):
        # This method is called after each test
        Router.objects.all().delete()

    def test_router_creation(self):
        self.assertTrue(isinstance(self.router, Router))
        self.assertEqual(self.router.__str__(), self.router.name)

    @patch('my_router.models.IKuaiClient')
    def test_get_client(self, MockClient):
        client = self.router.get_client()
        MockClient.assert_called_with(
            url=self.router.url, username=self.router.admin_username,
            password=self.router.admin_password)
        self.assertIsNotNone(client)

    def test_interval_schedule(self):
        interval_schedule = self.router.interval_schedule
        self.assertIsInstance(interval_schedule, IntervalSchedule)
        self.assertEqual(interval_schedule.every, self.router.fetch_interval)

    def test_custom_delete(self):
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=self.router.fetch_interval, period="seconds")
        task = PeriodicTask.objects.create(
            interval=schedule, name="Test Task", task="test_task")
        self.router.task = task
        self.router.save()

        self.router.delete()
        self.assertFalse(PeriodicTask.objects.filter(id=task.id).exists())
