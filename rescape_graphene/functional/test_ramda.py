from snapshottest import TestCase
from . import ramda as R


class TestRamda(TestCase):

    def test_filter_dict(self):
        dct = R.filter_dict(lambda keyvalue: keyvalue[0] == 'a', dict(a=1, b=2))
        assert dct == dict(a=1)

    def test_map_prop_value_as_index(self):
        res = R.map_prop_value_as_index(
            'province',
            [
                dict(province="Alberta"),
                dict(province="Manitoba")
            ]
        )
        assert res == dict(Alberta=dict(province="Alberta"), Manitoba=dict(province="Manitoba"))

    def test_item_path_or(self):
        assert R.item_path_or('racehorse', ['one', 'one', 'was'], dict(one=dict(one=dict(was='a')))) == 'a'
        assert R.item_path_or('racehorse', ['one', 'one', 'is'], dict(one=dict(one=dict(was='a')))) == 'racehorse'
        assert R.item_path_or('racehorse', 'one.one.was', dict(one=dict(one=dict(was='a')))) == 'a'

        # Try with a mix of dict and obj
        class Fellow(object):
            def __init__(self, one):
                self.one = one
        assert R.item_path_or('racehorse', 'one.one.was', dict(one=Fellow(one=dict(was='a')))) == 'a'

    def test_omit_deep(self):
        omit_keys = ['foo', 'bar']
        dct = dict(foo=1, bar=2, car=dict(foo=3, bar=4, tar=5, pepper=[dict(achoo=1, bar=2), dict(kale=1, foo=2)]))
        assert R.omit_deep(omit_keys, dct) == dict(car=dict(tar=5, pepper=[dict(achoo=1), dict(kale=1)]))
