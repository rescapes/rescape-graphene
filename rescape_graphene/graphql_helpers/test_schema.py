import logging

from ..functional import ramda as R
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from graphene.test import Client
from .sample_schema import schema
from snapshottest import TestCase
from ..user.user_schema import graphql_update_or_create_user, graphql_query_users

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


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


class GenaralTypeCase(TestCase):
    """
        Tests the query methods. This uses User but could be anything
    """
    client = None

    def setUp(self):
        self.client = Client(schema)
        User.objects.all().delete()
        User.objects.update_or_create(username="lion", first_name='Simba', last_name='The Lion',
                                      password=make_password("roar", salt='not_random'))
        User.objects.update_or_create(username="cat", first_name='Felix', last_name='The Cat',
                                      password=make_password("meow", salt='not_random'))

    # context_values={'user': 'Peter'}
    # root_values={'user': 'Peter'}
    # variable_values={'user': 'Peter'}
    def test_query(self):
        result = graphql_query_users(self.client)
        assert not R.has('errors', result), R.dump_json(R.prop('errors', result))
        self.assertMatchSnapshot(R.map(R.omit(['dateJoined', 'password']), R.item_path(['data', 'users'], result)))

    def test_create(self):
        values = dict(username="dino", firstName='T', lastName='Rex',
                      password=make_password("rrrrhhh", salt='not_random'))
        result = graphql_update_or_create_user(self.client, values)
        assert not R.has('errors', result), R.dump_json(R.prop('errors', result))
        # look at the users added and omit the non-determinant dateJoined
        self.assertMatchSnapshot(R.omit(['dateJoined', 'password'], R.item_path(['data', 'createUser', 'user'], result)))

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
