"""
Shared fixtures. Factories build rows with sensible defaults so each test
only spells out the fields it actually cares about.
"""

from datetime import timedelta
from decimal import Decimal

import factory
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import PanProfile, User
from ipos.models import IPO, Registrar


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = "Test User"

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or "s3cure-Passw0rd")
        if create:
            obj.save()


class RegistrarFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Registrar
        django_get_or_create = ["slug"]

    name = "KFin Technologies"
    slug = "kfintech"


class IPOFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IPO

    name = factory.Sequence(lambda n: f"Sample Issue {n}")
    registrar = factory.SubFactory(RegistrarFactory)
    status = IPO.Status.OPEN
    price_band_low = Decimal("95")
    price_band_high = Decimal("100")
    lot_size = 150
    open_date = factory.LazyFunction(lambda: timezone.localdate() - timedelta(days=1))
    close_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=2))


def make_pan(owner, pan="ABCDE1234F", label="Self"):
    obj = PanProfile(owner=owner, label=label)
    obj.set_pan(pan)
    obj.save()
    return obj


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def other_user(db):
    return UserFactory()


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture
def ipo(db):
    return IPOFactory()
