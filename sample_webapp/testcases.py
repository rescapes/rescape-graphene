from django.test import Client, RequestFactory, testcases
from unittest import mock
import graphene

from rescape_python_helpers import ramda as R

# https://github.com/flavors/django-graphql-jwt/blob/master/tests/testcases.py
class GraphQLRequestFactory(RequestFactory):

    def execute(self, query, **variables):
        return self._schema.execute(
            query,
            variable_values=variables['variable_values'] if R.has('variable_values', variables) else None,
            context_value=mock.MagicMock())


class GraphQLClient(GraphQLRequestFactory, Client):

    def __init__(self, **defaults):
        super(GraphQLClient, self).__init__(**defaults)
        self._schema = None

    def schema(self, schema):
        self._schema = schema


class GraphQLJWTTestCase(testcases.TestCase):
    client_class = GraphQLClient
