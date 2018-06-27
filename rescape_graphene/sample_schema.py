import graphene
import graphql_jwt
from django.contrib.auth import get_user_model, get_user
from graphene import ObjectType, Schema
from graphene_django.debug import DjangoDebug
from graphql_jwt.decorators import login_required
from .user_schema import UserType, user_fields, CreateUser, UpdateUser
from .schema_helpers import allowed_query_arguments


class Query(ObjectType):
    debug = graphene.Field(DjangoDebug, name='__debug')
    users = graphene.List(UserType)
    viewer = graphene.Field(
        UserType,
        **allowed_query_arguments(user_fields)
    )

    @login_required
    def resolve_viewer(self, info, **kwargs):
       return info.context.user

    def resolve_users(self, info, **kwargs):
        return get_user_model().objects.filter(**kwargs)

    def resolve_current_user(self, info):
        context = info.context
        user = get_user(context)
        if not user:
            raise Exception('Not logged in!')

        return user

class Mutation(graphene.ObjectType):
    create_user = CreateUser.Field()
    update_user = UpdateUser.Field()
    token_auth = graphql_jwt.ObtainJSONWebToken.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()

schema = Schema(query=Query, mutation=Mutation)
