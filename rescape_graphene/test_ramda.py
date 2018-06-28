from snapshottest import TestCase
from ramda import *


class TestRamda(TestCase):

    def test_filter_dict(self):
        dct = filter_dict(lambda keyvalue: keyvalue[0] == 'a', dict(a=1, b=2))
        assert dct == dict(a=1)

    def test_map_prop_value_as_index(self):
        res = map_prop_value_as_index(
            'province',
            [
                dict(province="Alberta"),
                dict(province="Manitoba")
            ]
        )
        assert res == dict(Alberta=dict(province="Alberta"), Manitoba=dict(province="Manitoba"))