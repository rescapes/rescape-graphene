from graphql.language.ast import ListValue
from rescape_python_helpers import ramda as R
import graphene


__all__ = [
    'Parameters'
]


class Parameters(graphene.Scalar):
    """
        Graphene representation for arbitrary key value parameters
    """

    class Meta:
        description = """
Arbitrary key value pairs for queries, filter, etc
"""

    @classmethod
    def serialize(cls, value):
        # Do nothing, let the view serializer to the arrays to json
        return value

    @classmethod
    def parse_literal(cls, node):
        """
            Parses any dict string
        :param node:
        :return:
        """
        return node

    @classmethod
    def parse_value(cls, value):
        return value