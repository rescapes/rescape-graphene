from .graphene_helpers import quote
from snapshottest import TestCase

class TestGrapheneHelpers(TestCase):

    def test_quote_unless_number(self):
        str = quote(dict(
            a=1,
            b='a',
            c=dict(
                d=1,
                e='a'
            ),
            f=[
                'a',
                'b',
                3.1
            ]
        ))
        assert str == '''{
a: 1
b: "a"
c:
	{
	d: 1
	e: "a"
	}
f: [
	"a"
	"b"
	3.1
]
}'''

