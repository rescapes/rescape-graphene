import graphene


class DjangoObjectTypeRevisionedMixin(object):
    id = graphene.Int(source='pk')
    date_created = graphene.DateTime(source='date_created')
    date_updated = graphene.DateTime(source='date_updated')
    version_number = graphene.Int(source='version_number')
    revision_id = graphene.Int(source='revision_id')
