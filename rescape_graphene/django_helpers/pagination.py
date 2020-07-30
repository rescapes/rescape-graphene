from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from rescape_python_helpers import ramda as R
from graphene import Int, Boolean, ObjectType, List

from rescape_graphene.graphql_helpers.schema_helpers import DENY


def get_paginator(qs, page_size, page, paginated_type, **kwargs):
    """
    Adapted from https://gist.github.com/mbrochh/f92594ab8188393bd83c892ef2af25e6
    Creates a pagination_type based on the paginated_type function
    :param qs:
    :param page_size:
    :param page:
    :param paginated_type:
    :param kwargs: Additional kwargs to pass paginated_type function, usually unneeded
    :return:
    """
    p = Paginator(qs.order_by('id'), page_size)
    try:
        page_obj = p.page(page)
    except PageNotAnInteger:
        page_obj = p.page(1)
    except EmptyPage:
        page_obj = p.page(p.num_pages)
    return paginated_type(
        page=page_obj.number,
        pages=p.num_pages,
        page_size=page_size,
        has_next=page_obj.has_next(),
        has_prev=page_obj.has_previous(),
        objects=page_obj.object_list,
        **kwargs
    )


def create_paginated_type_mixin(model_object_type, model_object_type_fields):
    """
        Constructs a PaginatedTypeMixin class and the fields object (for use in allowed filtering).
        The pagination is for the given model_object_type
    :param model_object_type: E.g. LocationType
    :param model_object_type_fields: The fields of the model_object_type, e.g. location_fields
    :return: An object containing {type: The class, fields: The field}
    """

    """
        Mixin for adding pagination to any Graphene Type
    """
    paginated_type_mixin = type(
        f'PaginatedTypeMixinFor{model_object_type.__name__}',
        (ObjectType,),
        dict(
            page_size=Int(),
            page=Int(),
            pages=Int(),
            has_next=Boolean(),
            has_prev=Boolean(),
            objects=List(model_object_type),
        )
    )

    paginated_fields = dict(
        page_size=dict(type=Int, graphene_type=Int, create=DENY, update=DENY),
        page=dict(type=Int, graphene_type=Int, create=DENY, update=DENY),
        pages=dict(type=Int, graphene_type=Int, create=DENY, update=DENY),
        has_next=dict(type=Boolean, graphene_type=Boolean, create=DENY, update=DENY),
        has_prev=dict(type=Boolean, graphene_type=Boolean, create=DENY, update=DENY),
        objects=dict(
            type=model_object_type,
            graphene_type=model_object_type,
            fields=model_object_type_fields,
            type_modifier=lambda *type_and_args: List(*type_and_args)
        )
    )

    return dict(type=paginated_type_mixin, fields=paginated_fields)


def resolve_paginated_for_type(paginated_type, type_resolver, **kwargs):
    """
        Resolver for paginated types
    :param paginated_type: The paginated Type, e.g. LocationPaginationType
    :param type_resolver: The resolver for the non-paginated type, e.g. location_resolver
    :param kwargs: The kwargs Array of prop sets for the non-paginated objects in 'objects'.
    Normally it's just a 1-item array.
    Other required kwargs are for pagination are page_size and page
    :return: The paginated query
    """

    def reduce_or(q_expressions):
        return R.reduce(
            lambda qs, q: qs | q if qs else q,
            None,
            q_expressions
        )

    objects = R.prop_or({}, 'objects', kwargs)

    instances = reduce_or(R.map(
        lambda obj: type_resolver('filter', **obj),
        objects
    ))

    return get_paginator(
        instances,
        R.prop('page_size', kwargs),
        R.prop('page', kwargs),
        paginated_type
    )
