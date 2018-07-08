import graphene
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from graphene.test import Client
from rescape_graphene import UserType

from .sample_schema import user_fields, FooType

from .sample_schema import schema, foo_fields
from .schema_helpers import allowed_query_arguments, input_type_fields, CREATE, UPDATE, \
    input_type_parameters_for_update_or_create, merge_with_django_properties, REQUIRE, DENY
from snapshottest import TestCase
from ..functional import ramda as R

class SchemaHelpersTypeCase(TestCase):
    client = None

    def setUp(self):
        self.client = Client(schema)

    def test_merge_with_django_properties(self):

        user_results = R.map_dict(
            lambda value: R.merge(value, dict(type=R.prop('type', value).__name__)),
            user_fields
        )
        self.assertMatchSnapshot(user_results)
        foo_results = R.map_dict(
            lambda value: R.merge(value, dict(type=R.prop('type', value).__name__)),
            foo_fields
        )
        self.assertMatchSnapshot(foo_results)

    # context_value={'user': 'Peter'}
    # root_value={'user': 'Peter'}
    # variable_values={'user': 'Peter'}
    def test_query_fields(self):
        self.assertMatchSnapshot(list(R.keys(allowed_query_arguments(user_fields, UserType))))
        self.assertMatchSnapshot(list(R.keys(allowed_query_arguments(foo_fields, UserType))))

    def test_create_fields(self):
        self.assertMatchSnapshot(list(R.keys(input_type_fields(user_fields, CREATE, UserType))))
        self.assertMatchSnapshot(list(R.keys(input_type_fields(foo_fields, CREATE, FooType))))

    def test_update_fields(self):
        self.assertMatchSnapshot(list(R.keys(input_type_fields(user_fields, UPDATE, UserType))))
        self.assertMatchSnapshot(list(R.keys(input_type_fields(foo_fields, UPDATE, FooType))))

    def test_update_fields_for_create_or_update(self):
        values = dict(email="dino@barn.farm", username="dino", first_name='T', last_name='Rex',
                      # Normally we'd use make_password here
                      password=make_password("rrrrhhh", salt='not_random'))
        self.assertMatchSnapshot(input_type_parameters_for_update_or_create(user_fields, values))

        values = dict(key='fooKey',
                      name='Foo Name',
                      user=get_user_model()(**values),
                      data =dict(example=2.2))
        self.assertMatchSnapshot(input_type_parameters_for_update_or_create(user_fields, values))
        # def test_delete(self):
        #    self.assertMatchSnapshot(delete_fields(user_fields))
