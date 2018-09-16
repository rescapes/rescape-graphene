import inspect

from django.contrib.auth.hashers import make_password
from graphene.test import Client
from rescape_graphene.schema_models.user_schema import UserType

from sample_webapp.sample_schema import user_fields, FooType

from sample_webapp.sample_schema import schema, foo_fields
from rescape_graphene.graphql_helpers.schema_helpers import allowed_query_arguments, input_type_fields, CREATE, UPDATE, \
    input_type_parameters_for_update_or_create
from snapshottest import TestCase
from rescape_python_helpers import ramda as R


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
        def map_type(t):
            return t.__name__ if inspect.isclass(t) else t

        self.assertMatchSnapshot(R.map_deep(dict(type=map_type, graphene_type=map_type, django_type=map_type), R.omit_deep(['default', 'type_modifier'], foo_results)))

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

        foo_values = dict(key='fooKey',
                      name='Foo Name',
                      # Pretend this is a saved user id
                      user=dict(id=5),
                      data =dict(example=2.2))
        self.assertMatchSnapshot(input_type_parameters_for_update_or_create(foo_fields, foo_values))

    # def test_delete(self):
    #    self.assertMatchSnapshot(delete_fields(user_fields))



def assert_no_errors(result):
    """
        Assert no graphql request errors
    :param result: The request Result
    :return: None
    """
    assert not (R.has('errors', result) and R.prop('errors', result)), R.dump_json(R.prop('errors', result))
