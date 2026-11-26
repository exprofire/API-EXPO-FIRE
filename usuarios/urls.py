from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import EquipoEmpresaView, MisEmpresasView, PerfilViewSet

router = DefaultRouter()
router.register(r'', PerfilViewSet, basename='perfil')

urlpatterns = [
    path('mis-empresas/', MisEmpresasView.as_view(), name='mis-empresas'),
    path('empresa/<int:empresa_id>/equipo/', EquipoEmpresaView.as_view(), name='empresa-equipo'),
    path('', include(router.urls)),
]
