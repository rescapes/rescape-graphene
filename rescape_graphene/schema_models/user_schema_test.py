import logging

import pytest
from django.contrib.auth import get_user_model
from reversion.models import Version

from sample_webapp.test_schema_helpers import assert_no_errors
from rescape_graphene.testcases import client_for_testing
from rescape_python_helpers import ramda as R
from django.contrib.auth.hashers import make_password
from snapshottest import TestCase

from . import user_schema
from .user_schema import graphql_update_or_create_user, graphql_query_users, \
    graphql_authenticate_user, graphql_verify_user, graphql_refresh_token
from ..graphql_helpers.schema_validating_helpers import quiz_model_query

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

omit_props = ['dateJoined']


@pytest.mark.django_db
class UserTypeCase(TestCase):

    def setUp(self):
        # Prevent a circular dependency
        from sample_webapp.sample_schema import schema
        admin, _ = get_user_model().objects.update_or_create(username="admin",
                                                             defaults=dict(first_name='Ad', last_name='Min',
                                                                           password=make_password("cool",
                                                                                                  salt='not_random'),
                                                                           is_staff=True,
                                                                           is_superuser=True))
        self.client = client_for_testing(schema, admin)
        self.user, _ = get_user_model().objects.update_or_create(username="lion", first_name='Simba',
                                                                 last_name='The Lion',
                                                                 password=make_password("roar", salt='not_random'))
        get_user_model().objects.update_or_create(username="cat", first_name='Felix', last_name='The Cat',
                                                  password=make_password("meow", salt='not_random'))

    def test_authenticate(self):
        values = dict(username=self.user.username, password='roar')
        result = graphql_authenticate_user(self.client, values)
        assert_no_errors(result)
        auth_token = R.item_str_path('data.tokenAuth.token', result)
        assert auth_token
        verify_result = graphql_verify_user(self.client, dict(token=auth_token))
        assert_no_errors(verify_result)
        refresh_result = graphql_refresh_token(self.client, dict(token=auth_token))
        assert_no_errors(refresh_result)

    def test_query(self):
        quiz_model_query(
            self.client,
            user_schema.graphql_query_users,
            'users',
            dict(id=R.prop('id', self.user))
        )

    def test_create(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        result = graphql_update_or_create_user(self.client, values)
        assert_no_errors(result)
        # look at the users added and omit the non-determinant dateJoined
        assert R.item_str_path('data.createUser.user', result)
        versions = Version.objects.get_for_object(get_user_model().objects.get(
            id=R.item_str_path('data.createUser.user.id', result)
        ))
        assert len(versions) == 1

    def test_update(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        # Here is our create
        create_result = graphql_update_or_create_user(self.client, values)

        # Unfortunately Graphene returns the ID as a string, even when its an int
        id = int(R.prop('id', R.item_str_path('data.createUser.user', create_result)))

        # Here is our update
        result = graphql_update_or_create_user(
            self.client,
            dict(id=id, firstName='Al', lastName="Lissaurus")
        )
        assert_no_errors(result)
        assert R.item_str_path('data.updateUser.user', result)
        versions = Version.objects.get_for_object(get_user_model().objects.get(
            id=R.item_str_path('data.updateUser.user.id', result)
        ))
        assert len(versions) == 2

    # def test_delete(self):
    #     self.assertMatchSnapshot(self.client.execute('''{
    #         users {
    #             username,
    #             first_name,
    #             last_name,
    #             password
    #         }
    #     }'''))
