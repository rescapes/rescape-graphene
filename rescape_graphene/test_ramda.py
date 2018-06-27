from snapshottest import TestCase
from .ramda import filter_dict


class TestRamda(TestCase):

    def test_filter_dict(self):
        dct = filter_dict(lambda keyvalue: keyvalue[0] == 'a', dict(a=1, b=2))
        assert dct == dict(a=1)
