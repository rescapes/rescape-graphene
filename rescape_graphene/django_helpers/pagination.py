from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from graphene import Int, Boolean, ObjectType, List
from rescape_graphene import DENY


def get_paginator(qs, page_size, page, paginated_type, **kwargs):
    """
    Adapted from https://gist.github.com/mbrochh/f92594ab8188393bd83c892ef2af25e6
    First we create a little helper function, becase we will potentially have many PaginatedTypes
    and we will potentially want to turn many querysets into paginated results:
    :param qs:
    :param page_size:
    :param page:
    :param paginated_type:
    :param kwargs:
    :return:
    """
    p = Paginator(qs, page_size)
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
    class PaginatedTypeMixin(ObjectType):
        """
            Mixin for adding pagination to any Graphene Type
        """
        page_size = Int()
        page = Int()
        pages = Int()
        has_next = Boolean()
        has_prev = Boolean()
        objects = List(model_object_type)

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

    return dict(type=PaginatedTypeMixin, fields=paginated_fields)
