import logging

import pytest
from graphql.error import format_error
from graphql_jwt.testcases import JSONWebTokenTestCase
from rescape_python_helpers import ramda as R
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from rescape_python_helpers.geospatial.geometry_helpers import ewkt_from_feature_collection

from sample_webapp.foo_schema import graphql_query_foos, graphql_update_or_create_foo
from sample_webapp.models import Foo
from snapshottest import TestCase
from rescape_graphene.schema_models.user_schema import graphql_update_or_create_user, graphql_query_users

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Keep these out of snapshot comparisons since they change depending on what tests are run and/or when
omit_props = ['id', 'createdAt', 'updatedAt', 'dateJoined', 'password']

initial_geojson = {
    'type': 'FeatureCollection',
    'features': [{
        "type": "Feature",
        "geometry": {
            "type": "Polygon", "coordinates": [[[-85, -180], [85, -180], [85, 180], [-85, 180], [-85, -180]]]
        }
    }]
}


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
class TestSchema(JSONWebTokenTestCase, TestCase):
    client = None

    def setUp(self):
        Foo.objects.all().delete()
        User.objects.all().delete()
        self.lion, _ = User.objects.update_or_create(
            username="lion", first_name='Simba', last_name='The Lion',
            password=make_password("roar", salt='not_random'),
            is_staff=True
        )
        self.cat, _ = User.objects.update_or_create(
            username="cat", first_name='Felix', last_name='The Cat',
            password=make_password("meow", salt='not_random'))
        Foo.objects.update_or_create(
            key="foolio", name="Foolio", user=self.lion,
            data=dict(example=2.14, friend=dict(id=self.cat.id)),
            geo_collection=ewkt_from_feature_collection(initial_geojson),
            geojson=initial_geojson
        )
        Foo.objects.update_or_create(
            key="fookit", name="Fookit", user=self.cat,
            data=dict(example=9.01, friend=dict(id=self.lion.id)),
            geo_collection=ewkt_from_feature_collection(initial_geojson),
            geojson=initial_geojson
        )
        self.client.authenticate(self.lion)

    def test_query(self):
        user_results = graphql_query_users(self.client)
        format_error(R.prop('errors', user_results)[0])
        assert not R.prop('errors', user_results), R.dump_json(R.map(lambda e: format_error(e), R.prop('errors', user_results)))
        assert 2 == R.length(R.map(R.omit_deep(omit_props), R.item_path(['data', 'users'], user_results)))

        # Query using for foos based on the related User
        foo_results = graphql_query_foos(
            self.client,
            variables=dict(
                user=R.pick(['id'], self.lion.__dict__),
                # Test filters
                name_contains='oo',
                name_contains_not='jaberwaki'
            )
        )
        assert not R.prop('errors', foo_results), R.dump_json(R.map(lambda e: format_error(e), R.prop('errors', foo_results)))
        assert 1 == R.length(R.map(R.omit_deep(omit_props), R.item_path(['data', 'foos'], foo_results)))
        # Make sure the Django instance in the json blob was resolved
        assert self.cat.id == R.item_path(['data', 'foos', 0, 'data', 'friend', 'id'], foo_results)

    def test_query_foo_with_null_geojson(self):
        # Query using for foos based on the related User
        foo_results = graphql_query_foos(self.client,
                                         variables=dict(key='fookit')
                                         )
        assert not R.prop('errors', foo_results), R.dump_json(R.map(lambda e: format_error(e), R.prop('errors', foo_results)))
        assert 1 == R.length(R.map(R.omit_deep(omit_props), R.item_path(['data', 'foos'], foo_results)))

    def test_create_user(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        result = graphql_update_or_create_user(self.client, values)
        assert not R.prop('errors', result), R.dump_json(R.map(lambda e: format_error(e), R.prop('errors', result)))
        # look at the users added and omit the non-determinant values
        self.assertMatchSnapshot(
            R.omit_deep(omit_props, R.item_path(['data', 'createUser', 'user'], result)))

    def test_create_foo(self):
        values = dict(
            name='Luxembourg',
            key='luxembourg',
            user=dict(id=self.lion.id),
            data=dict(
                example=1.5,
                friend=dict(id=self.lion.id)  # self love
            ),
            geojson={
                'type': 'FeatureCollection',
                'generator': 'Open Street Map',
                'copyright': '2018',
                'features': [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[49.5294835476, 2.51357303225], [51.4750237087, 2.51357303225],
                                 [51.4750237087, 6.15665815596],
                                 [49.5294835476, 6.15665815596], [49.5294835476, 2.51357303225]]]
                        },
                    },
                    {
                        "type": "Feature",
                        "id": "node/367331193",
                        "properties": {
                            "type": "node",
                            "id": 367331193,
                            "tags": {

                            },
                            "relations": [

                            ],
                            "meta": {

                            }
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [
                                5.7398201,
                                58.970167
                            ]
                        }
                    }
                ]
            }
        )
        result = graphql_update_or_create_foo(self.client, values)
        result_path_partial = R.item_path(['data', 'createFoo', 'foo'])
        assert not R.prop('errors', result), R.dump_json(R.map(lambda e: format_error(e), R.prop('errors', result)))
        created = result_path_partial(result)
        # look at the Foo added and omit the non-determinant dateJoined
        self.assertMatchSnapshot(R.omit_deep(omit_props, created))

        # Try creating the same Foo again, because of the unique constraint on key and the unique_with property
        # on its field definition value, it will increment to luxembourg1
        new_result = graphql_update_or_create_foo(self.client, values)
        assert not R.prop('errors', new_result), R.dump_json(R.map(lambda e: format_error(e), R.prop('errors', new_result)))
        created_too = result_path_partial(new_result)
        assert created['id'] != created_too['id']
        assert created_too['key'].startswith('luxembourg') and created_too['key'] != 'luxembourg'

    def test_update(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        # Here is our create
        create_result = graphql_update_or_create_user(self.client, values)

        id = R.prop('id', R.item_path(['data', 'createUser', 'user'], create_result))

        # Here is our update
        result = graphql_update_or_create_user(
            self.client,
            dict(id=id, firstName='Al', lastName="Lissaurus")
        )
        assert not R.prop('errors', result), R.dump_json(R.map(lambda e: format_error(e), R.prop('errors', result)))
        self.assertMatchSnapshot(R.omit_deep(omit_props, R.item_path(['data', 'updateUser', 'user'], result)))
