import graphene
from ..django_helpers.write_helpers import increment_prop_until_unique

from rescape_python_helpers import ramda as R
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from graphene import InputObjectType
from graphene_django.types import DjangoObjectType
from ..graphql_helpers.schema_helpers import input_type_fields, REQUIRE, DENY, CREATE, \
    merge_with_django_properties, input_type_parameters_for_update_or_create, UPDATE, \
    guess_update_or_create, graphql_update_or_create, graphql_query

class UserType(DjangoObjectType):
    class Meta:
        model = get_user_model()


user_fields = merge_with_django_properties(UserType, dict(
    id=dict(create=DENY, update=[REQUIRE]),
    username=dict(create=[REQUIRE], unique_with=increment_prop_until_unique(get_user_model(), None, 'username')),
    password=dict(create=[REQUIRE], read=DENY),
    email=dict(create=[REQUIRE]),
    is_superuser=dict(),
    first_name=dict(create=REQUIRE),
    last_name=dict(create=REQUIRE),
    is_staff=dict(),
    is_active=dict(),
    date_joined=dict(create=DENY, update=DENY)
))

user_mutation_config = dict(
    class_name='User',
    crud={
        CREATE: 'createUser',
        UPDATE: 'updateUser'
    },
    resolve=guess_update_or_create
)


class UpsertUser(graphene.Mutation):
    """
        Abstract base class for mutation
    """
    user = graphene.Field(UserType)

    def mutate(self, info, user_data=None):
        user_model = get_user_model()
        data = R.merge(user_data, dict(password=make_password(R.prop('password', user_data), salt='not_random')) if
        R.prop_or(False, 'password', user_data) else
        {})
        update_or_create_values = input_type_parameters_for_update_or_create(user_fields, data)
        user, created = user_model.objects.update_or_create(**update_or_create_values)
        return UpsertUser(user=user)


class CreateUser(UpsertUser):
    """
        Create User mutation class
    """

    class Arguments:
        user_data = type('CreateUserInputType', (InputObjectType,), input_type_fields(user_fields, CREATE, UserType))(
            required=True)


class UpdateUser(UpsertUser):
    """
        Update User mutation class
    """

    class Arguments:
        user_data = type('UpdateUserInputType', (InputObjectType,), input_type_fields(user_fields, UPDATE, UserType))(
            required=True)


graphql_update_or_create_user = graphql_update_or_create(user_mutation_config, user_fields)
graphql_query_users = graphql_query('users', user_fields)



def graphql_authenticate_user(client, variables):
    """
        Executes an authentication with a username and password as variables
    :param client:
    :param variables:
    :return:
    """
    return client.execute('''
mutation TokenAuth($username: String!, $password: String!) {
  tokenAuth(username: $username, password: $password) {
    token
  }
}''', variable_values=variables)


def graphql_verify_user(client, variables):
    """
        Verifies an authentication with token
    :param client:
    :param variables: contains a token key that is the token to update
    :return:
    """
    return client.execute('''
    mutation VerifyToken($token: String!) {
  verifyToken(token: $token) {
    payload
  }
}''', variable_values=variables)


def graphql_refresh_token(client, variables):
    """
        Refreshes an auth token
    :param client:
    :param variables: contains a token key that is the token to update
    :return:
    """
    return client.execute('''
    mutation
    RefreshToken($token: String!) {
        refreshToken(token: $token) {
        token
    payload
    }
}''', variable_values=variables)
