# https://gist.githubusercontent.com/smmoosavi/033deffe834e6417ed6bb55188a05c88/raw/3393e415f9654f849a89d7e33cfcacaff0372cdd/views.py
import traceback

from django.conf import settings
from graphql.error import GraphQLSyntaxError
from graphql.error.located_error import GraphQLLocatedError
from graphql.error import format_error as format_graphql_error
from .exceptions import ResponseError
from .str_converters import to_kebab_case, dict_key_to_camel_case
from django.http import HttpResponse
from rest_framework import exceptions
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from graphene_django.views import GraphQLView
import simplejson as json

def encode_code(code):
    if code is None:
        return None
    return to_kebab_case(code)


def encode_params(params):
    if params is None:
        return None
    return dict_key_to_camel_case(params)


def format_response_error(error: ResponseError):
    return {
        'message': error.message,
        'code': encode_code(error.code),
        'params': encode_params(error.params),
    }


def format_internal_error(error: Exception):
    message = 'Internal server error'
    code = 'internal-server-error'
    if settings.DEBUG:
        params = {
            'exception': type(error).__name__,
            'message': str(error),
            'trace': traceback.format_list(traceback.extract_tb(error.__traceback__)),
        }
        return {
            'code': code,
            'message': message,
            'params': params,
        }
    return {
        'code': code,
        'message': message,
    }


def format_located_error(error):
    if isinstance(error.original_error, GraphQLLocatedError):
        return format_located_error(error.original_error)
    if isinstance(error.original_error, ResponseError):
        return format_response_error(error.original_error)
    return format_internal_error(error.original_error)


class SafeGraphQLView(GraphQLView):
    @staticmethod
    def format_error(error):
        try:
            if isinstance(error, GraphQLLocatedError):
                return format_located_error(error)
            if isinstance(error, GraphQLSyntaxError):
                return format_graphql_error(error)
        except Exception as e:
            return format_internal_error(e)


# https://github.com/graphql-python/graphene-django/issues/264
class JWTGraphQLView(JSONWebTokenAuthentication, SafeGraphQLView):

    def dispatch(self, request, *args, **kwargs):
        try:
            # if not already authenticated by django cookie sessions
            # check the JWT token by re-using our DRF JWT
            if not request.user.is_authenticated:
                request.user, request.token = self.authenticate(request)
        except exceptions.AuthenticationFailed as e:
            response = HttpResponse(
                json.dumps({
                    'errors': [str(e)]
                }),
                status=401,
                content_type='application/json'
            )
            return response
        return super(JWTGraphQLView, self).dispatch(request, *args, **kwargs)
