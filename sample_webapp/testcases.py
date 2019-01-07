import traceback

import six
from django.test import Client, RequestFactory, testcases
from graphene.test import Client as GrapheneTestClient, default_format_error
from unittest import mock
import graphene
from graphql import GraphQLError
from graphql.error import format_error as format_graphql_error

from rescape_python_helpers import ramda as R


# https://github.com/flavors/django-graphql-jwt/blob/master/tests/testcases.py
class GraphQLRequestFactory(RequestFactory):

    def execute(self, query, **variables):
        return self.schema.execute(
            query,
            variables=variables['variables'] if R.has('variables', variables) else None,
            context_value=mock.MagicMock())


def client_for_testing(schema):
    """
    Creates a Graphql Test Client which adds in stack traces, which absurdly aren't part of the original
    :param schema:
    :return:
    """

    def format_error(error):
        # Why don't other people care about stack traces? It's absurd to have add this myself
        trace = traceback.format_exception(etype=type(error), value=error, tb=error.__traceback__)
        if isinstance(error, GraphQLError):
            return R.merge(dict(trace=trace), format_graphql_error(error))
        return {"message": six.text_type(error), "trace": trace}

    """
    Creates a test client with an error formatter that shows the stack trace, amazing
    """
    return GrapheneTestClient(
        schema, format_error=format_error
    )


class GraphQLClient(GraphQLRequestFactory, Client):

    def __init__(self, **defaults):
        super(GraphQLClient, self).__init__(**defaults)
        self._schema = None

    def schema(self, schema):
        self._schema = schema


class GraphQLJWTTestCase(testcases.TestCase):
    client_class = GraphQLClient
