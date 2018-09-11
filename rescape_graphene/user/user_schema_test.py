import logging

from sample_webapp.test_schema_helpers import assert_no_errors
from sample_webapp.testcases import GraphQLJWTTestCase, GraphQLClient
from rescape_python_helpers import ramda as R
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from graphene.test import Client
from snapshottest import TestCase
from .user_schema import graphql_update_or_create_user, graphql_query_users, \
    graphql_authenticate_user, graphql_verify_user, graphql_refresh_token

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

omit_props = ['dateJoined']


class UserTypeCase(GraphQLJWTTestCase):

    def setUp(self):
        # Prevent a circular dependency
        from sample_webapp.sample_schema import schema
        self.client = GraphQLClient()
        self.client.schema(schema)
        self.user, _ = User.objects.update_or_create(username="lion", first_name='Simba', last_name='The Lion',
                                      password=make_password("roar", salt='not_random'))
        User.objects.update_or_create(username="cat", first_name='Felix', last_name='The Cat',
                                      password=make_password("meow", salt='not_random'))

    def test_authenticate(self):
        values = dict(username=self.user.username, password='roar')
        result = graphql_authenticate_user(self.client, values)
        assert_no_errors(result)
        auth_token = R.item_str_path('tokenAuth.token', result.data)
        assert auth_token
        verify_result = graphql_verify_user(self.client, dict(token=auth_token))
        assert_no_errors(verify_result)
        refresh_result = graphql_refresh_token(self.client, dict(token=auth_token))
        assert_no_errors(refresh_result)

    def test_query(self):
        result = graphql_query_users(self.client)
        assert_no_errors(result)
        assert 2 == R.length(R.prop('users', result.data))

    def test_create(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        result = graphql_update_or_create_user(self.client, values)
        assert_no_errors(result)
        # look at the users added and omit the non-determinant dateJoined
        assert R.item_str_path('createUser.user', result.data)

    def test_update(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        # Here is our create
        create_result = graphql_update_or_create_user(self.client, values)

        # Unfortunately Graphene returns the ID as a string, even when its an int
        id = int(R.prop('id', R.item_str_path('createUser.user', create_result.data)))

        # Here is our update
        result = graphql_update_or_create_user(
            self.client,
            dict(id=id, firstName='Al', lastName="Lissaurus")
        )
        assert_no_errors(result)
        assert R.item_str_path('updateUser.user', result.data)

    # def test_delete(self):
    #     self.assertMatchSnapshot(self.client.execute('''{
    #         users {
    #             username,
    #             first_name,
    #             last_name,
    #             password
    #         }
    #     }'''))
