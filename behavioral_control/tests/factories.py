import factory
from django.contrib.auth import get_user_model

from my_router.models import Router


class UserFactory(factory.django.DjangoModelFactory):
    # https://stackoverflow.com/a/54584075/3437454

    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    username = factory.Sequence(lambda n: 'demo-user-%d' % n)
    is_staff = False
    is_superuser = False
    password = 'secret'

    @factory.lazy_attribute
    def email(self):
        return '%s@test.com' % self.username

    class Meta:
        model = get_user_model()

    class Params:
        # declare a trait that adds relevant parameters for admin users
        flag_is_superuser = factory.Trait(
            is_superuser=True,
            is_staff=True,
            username=factory.Sequence(lambda n: 'admin-%d' % n),
        )

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", None)
        obj = super(UserFactory, cls)._create(model_class, *args, **kwargs)
        # ensure the raw password gets set after the initial save
        obj.set_password(password)
        obj.save()
        return obj


class RouterFactory(factory.django.DjangoModelFactory):
    name = factory.Sequence(lambda n: "router_%02d" % n)
    description = factory.Faker('name')
    admin_username = factory.Faker('name')
    url = factory.Sequence(lambda n: "http://testrouter%d.com" % n)
    admin_password = factory.Faker('name')
    fetch_interval = factory.Faker('random_int', min=0, max=100)

    class Meta:
        model = Router
