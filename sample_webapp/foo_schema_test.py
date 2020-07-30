import logging

import pytest
import reversion
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from rescape_python_helpers import ramda as R
from rescape_python_helpers.geospatial.geometry_helpers import ewkt_from_feature_collection
from reversion.models import Version
from snapshottest import TestCase

from rescape_graphene.graphql_helpers.schema_validating_helpers import quiz_model_query, quiz_model_mutation_create, \
    quiz_model_mutation_update
from rescape_graphene.testcases import client_for_testing
from .foo_schema import graphql_query_foos, graphql_update_or_create_foo
from .models import Foo, Bar
from .sample_schema import create_default_schema

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
omit_props = ['createdAt', 'updatedAt']

geojson = {
    'type': 'FeatureCollection',
    'features': [{
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[49.5294835476, 2.51357303225], [51.4750237087, 2.51357303225],
                 [51.4750237087, 6.15665815596],
                 [49.5294835476, 6.15665815596], [49.5294835476, 2.51357303225]]]
        }
    }]
}

schema = create_default_schema()


def create_sample_foos(user, friend):
    bar = Bar(key='bar')
    with reversion.create_revision():
        bar.save()
    bar_barr = Bar(key='bar_barr')
    with reversion.create_revision():
        bar_barr.save()

    foo = Foo(
        key='foo',
        name="Foo",
        user=user,
        data=dict(example=2.2, friend=R.pick(['id'], friend)),
        geojson=geojson,
        geo_collection=ewkt_from_feature_collection(geojson)
    )
    with reversion.create_revision():
        foo.save()
    foo.bars.add(bar)
    foo.bars.add(bar_barr)
    boo = Foo(
        key='boo',
        name="Boo",
        user=user,
        data=dict(example=2.2, friend=R.pick(['id'], friend)),
        geojson=geojson,
        geo_collection=ewkt_from_feature_collection(geojson)
    )
    with reversion.create_revision():
        boo.save()
    boo.bars.add(bar)
    return [foo, boo]


@pytest.mark.django_db
class FooSchemaTestCase(TestCase):
    client = None

    def setUp(self):
        self.admin, _ = get_user_model().objects.update_or_create(username="admin",
                                                             defaults=dict(first_name='Ad', last_name='Min',
                                                                           password=make_password("cool",
                                                                                                  salt='not_random'),
                                                                           is_staff=True,
                                                                           is_superuser=True))
        self.client = client_for_testing(schema, self.admin)
        self.user, _ = get_user_model().objects.update_or_create(username="lion", first_name='Simba',
                                                                 last_name='The Lion',
                                                                 password=make_password("roar", salt='not_random'))
        get_user_model().objects.update_or_create(username="cat", first_name='Felix', last_name='The Cat',
                                                  password=make_password("meow", salt='not_random'))
        self.client = client_for_testing(schema, self.admin)
        self.foos = create_sample_foos(self.admin, self.user)

    def test_query(self):
        #quiz_model_query(self.client, graphql_query_foos, 'foos', dict(name='Foo'))
        quiz_model_query(self.client, graphql_query_foos, 'foos', dict(name='Foo', bars=[dict(key='bar')]))
        quiz_model_query(self.client, graphql_query_foos, 'foos', dict(name='Foo', bars=[dict(key='bar'), dict(key='bar_barr')]))

    def test_create(self):
        (result, new_result) = quiz_model_mutation_create(
            self.client, graphql_update_or_create_foo, 'createFoo.foo',
            dict(
                name='Luxembourg',
                key='luxembourg',
                user=R.pick(['id'], self.admin),
                geojson=geojson,
                data=dict(example=1.1, friend=R.pick(['id'], self.user))
            ),
            dict(key=r'luxembourg.+')
        )
        versions = Version.objects.get_for_object(Foo.objects.get(
            id=R.item_str_path('data.createFoo.foo.id', result)
        ))
        assert len(versions) == 1

    def test_update(self):
        (result, update_result) = quiz_model_mutation_update(
            self.client,
            graphql_update_or_create_foo,
            'createFoo.foo',
            'updateFoo.foo',
            dict(
                name='Luxembourg',
                key='luxembourg',
                user=R.pick(['id'], self.admin),
                geojson=geojson,
                data=dict(example=1.1, friend=R.pick(['id'], self.user))
            ),
            # Update the coords
            dict(
                geojson={
                    'features': [{
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[49.5294835476, 2.51357303225], [51.4750237087, 2.51357303225],
                                 [51.4750237087, 6.15665815596],
                                 [49.5294835476, 6.15665815596], [49.5294835476, 2.51357303225]]]
                        }
                    }]
                }
            )
        )
        versions = Version.objects.get_for_object(Foo.objects.get(
            id=R.item_str_path('data.updateFoo.foo.id', update_result)
        ))
        assert len(versions) == 2
