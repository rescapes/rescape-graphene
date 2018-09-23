import logging

import pytest
from rescape_python_helpers import ramda as R, ewkt_from_feature
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from graphene.test import Client
from rescape_python_helpers.geospatial.geometry_helpers import ewkt_from_feature_collection

from sample_webapp.sample_schema import schema, graphql_query_foos, Foo
from snapshottest import TestCase
from rescape_graphene.schema_models.user_schema import graphql_update_or_create_user, graphql_query_users

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

geo_collection = ewkt_from_feature_collection({
    'type': 'FeatureCollection',
    'features': [{
        "type": "Feature",
        "geometry": {
            "type": "Polygon", "coordinates": [[[-85, -180], [85, -180], [85, 180], [-85, 180], [-85, -180]]]
        }
    }]
})


def smart_execute(schema, *args, **kwargs):
    """
    Smarter version of graphene's test execute which stupidly hides exceptions
    This doesn't deal with Promises
    :param schema:
    :param args:
    :param kwargs:
    :return:
    """
    return schema.schema.execute(*args, **dict(schema.execute_options, **kwargs))


@pytest.mark.django_db
class GenaralTypeCase(TestCase):
    """
        Tests the query methods. This uses User but could be anything
    """
    client = None

    def setUp(self):
        self.client = Client(schema)
        Foo.objects.all().delete()
        User.objects.all().delete()
        self.lion, _ = User.objects.update_or_create(
            username="lion", first_name='Simba', last_name='The Lion',
            password=make_password("roar", salt='not_random'),
        )
        self.cat, _ = User.objects.update_or_create(
            username="cat", first_name='Felix', last_name='The Cat',
            password=make_password("meow", salt='not_random'))
        Foo.objects.update_or_create(
            key="foolio", name="Foolio", user=self.lion,
            data=dict(example=2.14, friend=dict(id=self.cat.id)),
            geo_collection=geo_collection
        )
        Foo.objects.update_or_create(
            key="fookit", name="Fookit", user=self.cat,
            data=dict(example=9.01, friend=dict(id=self.lion.id)),
            geo_collection=geo_collection
        )

    def test_query(self):
        user_results = graphql_query_users(self.client)
        assert not R.has('errors', user_results), R.dump_json(R.prop('errors', user_results))
        assert 2 == R.length(R.map(R.omit(['dateJoined', 'password']), R.item_path(['data', 'users'], user_results)))

        # Query using for foos based on the related User
        foo_results = graphql_query_foos(self.client,
                                         dict(user='UserTypeofFooTypeRelatedReadInputType'),
                                         variable_values=dict(user=R.pick(['id'], self.lion.__dict__))
                                         )
        assert not R.has('errors', foo_results), R.dump_json(R.prop('errors', foo_results))
        assert 1 == R.length(R.map(R.omit(['dateJoined', 'password']), R.item_path(['data', 'foos'], foo_results)))
        # Make sure the Django instance in the json blob was resolved
        assert str(self.cat.id) == R.item_path(['data', 'foos', 0, 'data', 'friend', 'id'], foo_results)

    def test_create(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        result = graphql_update_or_create_user(self.client, values)
        assert not R.has('errors', result), R.dump_json(R.prop('errors', result))
        # look at the users added and omit the non-determinant dateJoined
        self.assertMatchSnapshot(
            R.omit(['dateJoined', 'password'], R.item_path(['data', 'createUser', 'user'], result)))

    def test_update(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        # Here is our create
        create_result = graphql_update_or_create_user(self.client, values)

        # Unfortunately Graphene returns the ID as a string, even when its an int
        id = int(R.prop('id', R.item_path(['data', 'createUser', 'user'], create_result)))

        # Here is our update
        result = graphql_update_or_create_user(
            self.client,
            dict(id=id, firstName='Al', lastName="Lissaurus")
        )
        assert not R.has('errors', result), R.dump_json(R.prop('errors', result))
        self.assertMatchSnapshot(R.omit(['dateJoined'], R.item_path(['data', 'updateUser', 'user'], result)))

        # def test_delete(self):
        #     self.assertMatchSnapshot(self.client.execute('''{
        #         users {
        #             username,
        #             first_name,
        #             last_name,
        #             password
        #         }
        #     }'''))
