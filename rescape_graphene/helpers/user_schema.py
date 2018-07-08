import graphene
from functional import ramda as R
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from graphene import InputObjectType
from graphene_django.types import DjangoObjectType
from .schema_helpers import input_type_fields, REQUIRE, DENY, CREATE, \
    merge_with_django_properties, input_type_parameters_for_update_or_create, UPDATE, \
    guess_update_or_create, graphql_update_or_create, graphql_query

import django
django.setup()

class UserType(DjangoObjectType):
    class Meta:
        model = get_user_model()


user_fields = merge_with_django_properties(UserType, dict(
    id=dict(create=DENY, update=[REQUIRE]),
    username=dict(create=[REQUIRE]),
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
        user_data = type('CreateUserInputType', (InputObjectType,), input_type_fields(user_fields, CREATE))(
            required=True)


class UpdateUser(UpsertUser):
    """
        Update User mutation class
    """

    class Arguments:
        user_data = type('UpdateUserInputType', (InputObjectType,), input_type_fields(user_fields, UPDATE))(
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


# None of this should be needed
# Special case where only username and password can be used for CREATE to get an auth token back
# login_fields = merge_with_django_properties(UserType, dict(
#     id=dict(create=DENY),
#     username=dict(create=REQUIRE),
#     password=dict(create=REQUIRE),
#     email=dict(create=DENY),
#     is_superuser=dict(CREATE=DENY),
#     first_name=dict(create=DENY),
#     last_name=dict(create=DENY),
#     is_staff=dict(create=DENY),
#     is_active=dict(create=DENY),
#     date_joined=dict(create=DENY)
# ))
#
# login_mutation_config = dict(
#     class_name='Login',
#     crud={
#         CREATE: 'createLogin'
#     },
#     resolve=guess_update_or_create
#)
#
# class LoginMutation(SerializerMutation):
#     token = graphene.String(description='JWT token')
#
#     @classmethod
#     def perform_mutate(cls, serializer, info):
#         return cls(errors=[], token=serializer.object['token'])
#
#     class Meta:
#         serializer_class = JSONWebTokenSerializer
#
#
# class LoginInput(graphene.InputObjectType):
#     email = graphene.String(requred=True)
#     password = graphene.String(required=True)
#
#
# class Login(graphene.Mutation):
#     user = graphene.Field(MyuserType)
#
#     class Arguments:
#         login_data = LoginInput(required=True)
#
#     @staticmethod
#     def mutate(root, info, login_data):
#         user = authenticate(
#             email=login_data.email,
#             password=login_data.password
#         )
#
#         if not user:
#             raise Exception('Invalid username or password!')
#
#         info.context.session['token'] = user.auth_token.key
#         return Login(user=user)
#
