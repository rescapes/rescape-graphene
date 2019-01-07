from django.conf.urls import url
from django.urls import include
from django.views.decorators.csrf import csrf_exempt
from rescape_graphene.graphql_helpers.views import SafeGraphQLView
from rest_framework.routers import DefaultRouter
from django.contrib import admin

router = DefaultRouter()

urlpatterns = [
    # Includes /login/, /logout/, /password..., etc https://docs.djangoproject.com/en/2.0/topics/auth/default/
    url('^', include('django.contrib.auth.urls')),
    url(r'^admin/', admin.site.urls),
    url(r'^admin/', include('loginas.urls')),
    url(r'^graphql', csrf_exempt(SafeGraphQLView.as_view(graphiql=True))),
]
