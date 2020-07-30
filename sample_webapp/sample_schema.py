import graphene

from rescape_graphene.schema import create_schema
from sample_webapp.foo_schema import foo_fields, FooType, CreateFoo, UpdateFoo, FooQuery, FooMutation
from sample_webapp.models import Foo


class LocalMutation(graphene.ObjectType):
    create_foo = CreateFoo.Field()
    update_foo = UpdateFoo.Field()


default_class_config = dict(
    foo=dict(
        model_class=Foo,
        graphene_class=FooType,
        graphene_fields=foo_fields,
        query=FooQuery,
        mutation=FooMutation,
    )
)


def create_default_schema():
    return create_schema(default_class_config)
