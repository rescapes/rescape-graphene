import graphene
import graphql_jwt
from django.contrib.auth.models import AnonymousUser
from graphene.types.generic import GenericScalar
from graphql_jwt.settings import jwt_settings
from rescape_python_helpers import ramda as R


class RescapeTokenMutation(graphene.ObjectType):
    token_auth = graphql_jwt.ObtainJSONWebToken.Field()
    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()
    delete_token_cookie = graphql_jwt.DeleteJSONWebTokenCookie.Field()
    # Long running refresh tokens
    delete_refresh_token_cookie = graphql_jwt.DeleteRefreshTokenCookie.Field()


class RescapeTokenQuery(graphene.ObjectType):
    current_token = graphene.Field(
        graphql_jwt.ObtainJSONWebToken,
        payload=GenericScalar(required=True),
        refresh_expires_in=graphene.Int(required=True),
        **R.merge(
            dict(
                token=graphene.Field(graphene.String, required=True)
            ) if jwt_settings.JWT_HIDE_TOKEN_FIELDS else {},
            dict(
                refresh_token=graphene.Field(graphene.String, required=True)
            ) if jwt_settings.JWT_HIDE_TOKEN_FIELDS and jwt_settings.JWT_LONG_RUNNING_REFRESH_TOKEN else {}
        )
    )

    def resolve_current_token(self, info):
        """
            Resolve the current user or return None if there isn't one
        :param self:
        :param info:
        :return: The current user or None
        """
        context = info.context
        user = R.prop_or(None, 'user', context)
        return user if not isinstance(user, AnonymousUser) else None