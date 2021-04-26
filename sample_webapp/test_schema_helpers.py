from django.contrib.auth.hashers import make_password

from rescape_graphene.schema_models.user_schema import UserType, user_fields

from sample_webapp.sample_schema import FooType, create_default_schema

from sample_webapp.sample_schema import foo_fields
from rescape_graphene.graphql_helpers.schema_helpers import allowed_read_fields, input_type_fields, CREATE, UPDATE, \
    input_type_parameters_for_update_or_create, allowed_filter_arguments
from snapshottest import TestCase
from rescape_python_helpers import ramda as R

from rescape_graphene.testcases import client_for_testing

schema = create_default_schema()

class SchemaHelpersTypeCase(TestCase):
    client = None

    def setUp(self):
        self.client = client_for_testing(schema)

    def test_variable_fields(self):
        # Make sure we generate the variable and the filters
        self.assertTrue(R.contains('key', list(allowed_filter_arguments(foo_fields, FooType))))
        self.assertTrue(R.contains('key_contains', list(allowed_filter_arguments(foo_fields, FooType))))
        self.assertTrue(R.contains('key_contains_not', list(allowed_filter_arguments(foo_fields, FooType))))

    def test_query_fields(self):
        self.assertMatchSnapshot(list(R.keys(allowed_read_fields(user_fields, UserType))))
        self.assertMatchSnapshot(list(R.keys(allowed_read_fields(foo_fields, UserType))))

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

        foo_values = dict(key='fooKey',
                      name='Foo Name',
                      # Pretend this is a saved user id
                      user=dict(id=5),
                      data =dict(example=2.2))
        self.assertMatchSnapshot(R.omit(['password'], input_type_parameters_for_update_or_create(foo_fields, foo_values)))


    # def test_delete(self):
    #    self.assertMatchSnapshot(delete_fields(user_fields))



def assert_no_errors(result):
    """
        Assert no graphql request errors
    :param result: The request Result
    :return: None
    """
    assert not (R.prop_or(False, 'errors', result) and R.prop('errors', result)), R.dump_json(R.map(lambda e: format_error(e), R.dump_json(R.prop('errors', result))))
