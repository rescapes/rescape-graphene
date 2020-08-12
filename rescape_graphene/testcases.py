import traceback

import six
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from graphene.test import Client as GrapheneTestClient
from graphql import GraphQLError
from graphql.error import format_error as format_graphql_error
from rescape_python_helpers import ramda as R


def client_for_testing(schema, user=None):
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
    return MyGrapheneTestClient(
        schema, user, format_error=format_error
    )


class MyGrapheneTestClient(GrapheneTestClient):

    def __init__(self, schema, user, format_error=None, **execute_options):
        self.user = user
        super(MyGrapheneTestClient, self).__init__(schema, format_error, **execute_options)

    def execute(self, *args, **kwargs):
        req = RequestFactory().get('/')
        req.user = self.user or AnonymousUser()
        return super(MyGrapheneTestClient, self).execute(*args, context_value=req, **kwargs)
