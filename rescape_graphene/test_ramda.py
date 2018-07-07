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

    def test_item_path_or(self):
        assert item_path_or('racehorse', ['one', 'one', 'was'], dict(one=dict(one=dict(was='a')))) == 'a'
        assert item_path_or('racehorse', ['one', 'one', 'is'], dict(one=dict(one=dict(was='a')))) == 'racehorse'
        assert item_path_or('racehorse', 'one.one.was', dict(one=dict(one=dict(was='a')))) == 'a'

        # Try with a mix of dict and obj
        class Fellow(object):
            def __init__(self, one):
                self.one = one
        assert item_path_or('racehorse', 'one.one.was', dict(one=Fellow(one=dict(was='a')))) == 'a'
