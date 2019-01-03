from graphql.language.ast import ListValue
from rescape_python_helpers import ramda as R
import graphene


__all__ = [
    'GeometryCoordinates'
]


class GeometryCoordinates(graphene.Scalar):
    """
        Graphene representation for a GeoDjango GeometryField, which can contain the feature of a geojson blob
    """

    class Meta:
        description = """
Coordinates respresent a Point, LineString, Polygon, Multipolygon, etc features of a blob. It thus supports
and arbitrary number of embedded arrays with endpoints being Floats to represent coordinates
"""

    @classmethod
    def serialize(cls, value):
        # Do nothing, let the view serializer to the arrays to json
        return value

    @classmethod
    def parse_literal(cls, node):
        """
            Parses any array string
        :param node:
        :return:
        """

        def map_value(value):
            """
                value is either a ListValue with values that are ListValues or a ListValue with values that
                are FloatValues
            :param value:
            :return:
            """

            def handle_floats(v):
                if hasattr(v, 'values'):
                    # Multiple floats:w
                    return R.map(
                        lambda fv: float(fv.value),
                        v.values
                    )
                else:
                    # Single float
                    return float(v.value)

            return R.if_else(
                lambda v: R.isinstance(ListValue, R.head(v.values) if hasattr(v, 'values') else v),
                # ListValues
                lambda v: [reduce(v.values)],
                # FloatValues or single FloatValue
                lambda v: [handle_floats(v)]
            )(value)

        def reduce(values):
            return R.reduce(
                lambda accum, list_values: R.concat(accum, map_value(list_values)),
                [],
                values
            )

        # Create the coordinates by reducing node.values=[node.values=[node.floats], node.value, ...]
        return R.reduce(
            lambda accum, list_values: reduce(node.values),
            [],
            reduce(node.values)
        )

    @classmethod
    def parse_value(cls, value):
        return value
