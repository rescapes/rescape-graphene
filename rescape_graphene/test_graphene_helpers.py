from graphene_helpers import quote
from snapshottest import TestCase
from ramda import *


class TestGrapheneHelpers(TestCase):

    def test_quote_unless_number(self):
        str = quote(dict(
            a=1,
            b='a',
            c=dict(
                d=1,
                e='a'
            )
        ))
        assert str == 'a: 1\nb: "a"\nc:\nd: 1\ne: "a"'
