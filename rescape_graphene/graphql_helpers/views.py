# https://gist.githubusercontent.com/smmoosavi/033deffe834e6417ed6bb55188a05c88/raw/3393e415f9654f849a89d7e33cfcacaff0372cdd/views.py
import json
import logging
import traceback

from django.conf import settings
from graphene_django.views import GraphQLView
from graphql.error import GraphQLSyntaxError
from graphql.error import format_error as format_graphql_error
from graphql.error.located_error import GraphQLLocatedError

from rescape_python_helpers import ramda as R
from .exceptions import ResponseError
from .str_converters import to_kebab_case, dict_key_to_camel_case

log = logging.getLogger('rescape_graphene')

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

    def execute_graphql_request(self, *args, **kwargs):
        result = super().execute_graphql_request(*args, **kwargs)
        if result.errors:
            log.error(json.dumps(R.pick(['operationName', 'variables'], args[1]), indent=4))
            for error in result.errors:
                if hasattr(error, 'source'):
                    log.error(error.source.body)
                # NO way to get stack trace of the original error grrrr
                log.exception(error)

        return result

    @staticmethod
    def format_error(error):
        try:
            if isinstance(error, GraphQLLocatedError):
                return format_located_error(error)
            elif isinstance(error, GraphQLSyntaxError):
                return format_graphql_error(error)
            else:
                return GraphQLView.format_error(error)
        except Exception as e:
            return format_internal_error(e)
