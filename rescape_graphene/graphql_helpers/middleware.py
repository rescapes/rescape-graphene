# https://github.com/graphql-python/graphene-django/issues/124
import logging
import sys

from rescape_python_helpers import ramda as R
from django.conf import settings
from graphql import GraphQLObjectType, GraphQLField, GraphQLString, GraphQLSchema


class ErrorMiddleware(object):
    def on_error(self, error):
        err = sys.exc_info()
        logging.error(error)
        return err[1]

    def resolve(self, next, root, args, context, info):
        return next(root, args, context, info).catch(self.on_error)


class DisableIntrospectionMiddleware:
    """
    This class hides the introspection.
    """

    def resolve(self, next, root, info, **kwargs):
        # Block introspection in PROD to save time unless the param forceIntrospection=true is passed
        block_introspection = True or not R.prop_or(False, 'forceIntrospection', info.context.GET) and settings.PROD
        if block_introspection and info.field_name.lower() in ['__schema', '_introspection']:
            query = GraphQLObjectType(
                "Query", lambda: {"Introspection": GraphQLField(GraphQLString, resolver=lambda *_: "Disabled")}
            )
            info.schema = GraphQLSchema(query=query)
            return next(root, info, **kwargs)
        return next(root, info, **kwargs)
