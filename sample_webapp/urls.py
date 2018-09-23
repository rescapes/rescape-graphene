from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt
from rescape_graphene.graphql_helpers.views import SafeGraphQLView
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = [
    url(r'^graphql', csrf_exempt(SafeGraphQLView.as_view(graphiql=True))),
]
