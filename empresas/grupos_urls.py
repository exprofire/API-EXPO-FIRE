"""Rutas del CRUD de grupos de empresas."""

from rest_framework.routers import DefaultRouter

from .views import GrupoEmpresasViewSet


router = DefaultRouter()
router.register(r'', GrupoEmpresasViewSet, basename='grupo-empresa')

urlpatterns = router.urls
