import graphene
from . import ramda as R
from django.contrib.auth.hashers import make_password
from graphene.test import Client
from .sample_schema import schema
from .schema_helpers import allowed_query_arguments, input_type_fields, CREATE, UPDATE, \
    input_type_parameters_for_update_or_create, merge_with_django_properties, REQUIRE, DENY
from snapshottest import TestCase
from .user_schema import UserType, user_fields


class SchemaHelpersTypeCase(TestCase):
    client = None

    def setUp(self):
        self.client = Client(schema)

    def test_merge_with_django_properties(self):
        results = merge_with_django_properties(UserType, dict(
            id=dict(type=graphene.String, create=DENY, update=[REQUIRE]),
            username=dict(type=graphene.String, create=[REQUIRE]),
            password=dict(type=graphene.String, create=[REQUIRE], read=DENY),
            email=dict(type=graphene.String, create=[REQUIRE]),
            is_superuser=dict(type=graphene.String),
            first_name=dict(type=graphene.String, create=REQUIRE),
            last_name=dict(type=graphene.String, create=REQUIRE),
            is_staff=dict(type=graphene.Boolean),
            is_active=dict(type=graphene.Boolean),
            date_joined=dict(type=graphene.Boolean, create=DENY, update=DENY)
        ))
        cleaner_results = R.map_dict(
            lambda value: R.merge(value, dict(type=R.prop('type', value).__name__)),
            results
        )
        self.assertMatchSnapshot(cleaner_results)

    # context_value={'user': 'Peter'}
    # root_value={'user': 'Peter'}
    # variable_values={'user': 'Peter'}
    def test_query_fields(self):
        self.assertMatchSnapshot(R.keys(allowed_query_arguments(user_fields)))

    def test_create_fields(self):
        self.assertMatchSnapshot(R.keys(input_type_fields(user_fields, CREATE)))

    def test_update_fields(self):
        self.assertMatchSnapshot(R.keys(input_type_fields(user_fields, UPDATE)))

    def test_update_fields_for_create_or_update(self):
        values = dict(email="dino@barn.farm", username="dino", first_name='T', last_name='Rex',
                      # Normally we'd use make_password here
                      password=make_password("rrrrhhh", salt='not_random'))
        self.assertMatchSnapshot(input_type_parameters_for_update_or_create(user_fields, values))

        # def test_delete(self):
        #    self.assertMatchSnapshot(delete_fields(user_fields))
