import graphene
from graphene import ObjectType, Schema
from rescape_graphene.schema import Query, Mutation
from rescape_graphene.graphql_helpers.schema_helpers import stringify_query_kwargs, \
    allowed_filter_arguments, process_filter_kwargs
from sample_webapp.foo_schema import foo_fields, FooType, CreateFoo, UpdateFoo
from sample_webapp.models import Foo
from rescape_python_helpers import ramda as R


class LocalQuery(ObjectType):
    foos = graphene.List(
        FooType,
        **allowed_filter_arguments(foo_fields, FooType)
    )
    foo = graphene.Field(
        FooType,
        **allowed_filter_arguments(foo_fields, FooType)
    )

    def resolve_foos(self, info, **kwargs):
        modified_kwargs = process_filter_kwargs(Foo, kwargs)
        return Foo.objects.filter(**modified_kwargs)

    def resolve_foo(self, info, **kwargs):
        return Foo.objects.get(**kwargs)


class LocalMutation(graphene.ObjectType):
    create_foo = CreateFoo.Field()
    update_foo = UpdateFoo.Field()


class Query(LocalQuery, Query):
    pass


class Mutation(LocalMutation, Mutation):
    pass


schema = Schema(query=Query, mutation=Mutation)