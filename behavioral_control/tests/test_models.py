from django.test import TestCase
from unittest.mock import patch
from django_celery_beat.models import PeriodicTask, IntervalSchedule
from my_router.models import Router
from tests.factories import RouterFactory


class RouterModelTest(TestCase):
    def setUp(self):
        # Setup run before every test method.
        self.router = RouterFactory()

    def test_router_creation(self):
        self.assertTrue(isinstance(self.router, Router))
        self.assertEqual(self.router.__str__(), self.router.name)

    @patch('my_router.models.IKuaiClient')
    def test_get_client(self, MockClient):
        # Test the get_client method
        client = self.router.get_client()
        MockClient.assert_called_with(
            url=self.router.url, username=self.router.admin_username,
            password=self.router.admin_password)
        self.assertIsNotNone(client)

    @patch('my_router.models.PeriodicTask.objects.create')
    @patch('my_router.models.IntervalSchedule.objects.get_or_create')
    def test_setup_task(self, mock_get_or_create, mock_create):
        # Mock the IntervalSchedule and PeriodicTask creation
        mock_schedule_instance = mock_get_or_create.return_value[0]
        self.router.setup_task()
        mock_get_or_create.assert_called_with(
            every=self.router.fetch_interval, period="seconds")
        mock_create.assert_called_with(
            name="Fetch info and set cache",
            task="fetch_devices_and_set_cache",
            interval=mock_schedule_instance,
            args='["{}"]'.format(self.router.id),
            start_time=patch.ANY  # Ignore checking the start_time value
        )

    def test_interval_schedule(self):
        # Test that interval_schedule creates or gets an IntervalSchedule instance
        schedule, created = IntervalSchedule.objects.get_or_create(
            every=self.router.fetch_interval, period="seconds")
        self.assertEqual(self.router.interval_schedule, schedule)
        self.assertTrue(IntervalSchedule.objects.filter(
            every=self.router.fetch_interval, period="seconds").exists())

    def test_custom_delete(self):
        # Test the custom delete method
        # First, ensure a PeriodicTask is associated with the router
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=self.router.fetch_interval, period="seconds")
        task = PeriodicTask.objects.create(
            interval=schedule, name="Test Task", task="test_task")
        self.router.task = task
        self.router.save()

        self.router.delete()
        self.assertFalse(PeriodicTask.objects.filter(id=task.id).exists())
