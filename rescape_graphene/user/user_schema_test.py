import logging

from ..functional import ramda as R
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from graphene.test import Client
from snapshottest import TestCase
from .user_schema import graphql_update_or_create_user, graphql_query_users, \
    graphql_authenticate_user, graphql_verify_user, graphql_refresh_token

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

omit_props = ['dateJoined']


class UserTypeCase(TestCase):
    client = None

    def setUp(self):
        # Prevent a circular dependency
        from .sample_schema import schema
        self.client = Client(schema)
        User.objects.update_or_create(username="lion", first_name='Simba', last_name='The Lion',
                                      password=make_password("roar", salt='not_random'))
        User.objects.update_or_create(username="cat", first_name='Felix', last_name='The Cat',
                                      password=make_password("meow", salt='not_random'))

    def test_authenticate(self):
        values = dict(username="test", password="testpass")
        result = graphql_authenticate_user(self.client, values)
        assert not R.has('errors', result), R.dump_json(R.prop('errors', result))
        self.assertMatchSnapshot(R.map(R.omit(omit_props), R.item_path(['data', 'users'], result)))
        verifyResult = graphql_verify_user(self.client, dict(token=result.token_value))
        assert not R.has('errors', verifyResult), R.dump_json(R.prop('errors', result))
        refreshResult = graphql_refresh_token(self.client, dict(token=result.token_value))
        assert not R.has('errors', refreshResult), R.dump_json(R.prop('errors', result))

    def test_query(self):
        result = graphql_query_users(self.client)
        assert not R.has('errors', result), R.dump_json(R.prop('errors', result))
        self.assertMatchSnapshot(R.map(R.omit(omit_props), R.item_path(['data', 'users'], result)))

    def test_create(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        result = graphql_update_or_create_user(self.client, values)
        assert not R.has('errors', result), R.dump_json(R.prop('errors', result))
        # look at the users added and omit the non-determinant dateJoined
        self.assertMatchSnapshot(R.omit(omit_props, R.item_path(['data', 'createUser', 'user'], result)))

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
        self.assertMatchSnapshot(R.omit(omit_props, R.item_path(['data', 'updateUser', 'user'], result)))

    # def test_delete(self):
    #     self.assertMatchSnapshot(self.client.execute('''{
    #         users {
    #             username,
    #             first_name,
    #             last_name,
    #             password
    #         }
    #     }'''))
