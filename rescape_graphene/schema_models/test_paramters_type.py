from django.test import TestCase
from rescape_graphene.schema_models import parameters_type
from rescape_graphene.schema_models.parameters_type import Parameters


class TypesTests(TestCase):

    def test_feature_collection_geojson_input(self):
        params = dict(one_one='was a racehorse', two_two=12)
        serialized = Parameters.serialize(params)
        self.assertEqual('', serialized['type'])

        # Go backwards and parse
        params_parsed = parameters_type.parse_value(serialized)
        self.assertEqual(params_parsed, params)