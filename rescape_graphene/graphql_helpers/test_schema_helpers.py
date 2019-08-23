from rescape_graphene.graphql_helpers.schema_helpers import merge_data_fields_on_update
from snapshottest import TestCase, pytest


class TestGrapheneHelpers(TestCase):
    def test_merge_data_fields_on_update(self):
        data = dict(
            data=dict(jump=['jive'], then=dict(you='wail'), hold=dict(on=1)),
            also=1
        )

        class Object:
            def __init__(self, data, also):
                self.data = data
                self.aslo = also

        instance = Object(
            dict(jump=['jive'], then=dict(you='wail'), hold=dict(off=1)),
            2
        )
        assert merge_data_fields_on_update(['data'], instance, data) == dict(
            data=dict(jump=['jive'], then=dict(you='wail'), hold=dict(on=1, off=1)),
            also=1,
        )
