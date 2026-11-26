# empresas/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from .views import ContactoViewSet, EmpresaViewSet, AsignarPropietarioView

# Router principal para empresas (sin el prefijo 'empresas/' porque ya viene de core.urls)
router = DefaultRouter()
router.register(r'', EmpresaViewSet, basename='empresa')  # ¡Importante! r'' vacío

# Router anidado para contactos
empresa_router = routers.NestedDefaultRouter(
    router, 
    r'',  # Aquí también va vacío porque hereda
    lookup='empresa'
)
empresa_router.register(r'contactos', ContactoViewSet, basename='empresa-contactos')

urlpatterns = [
    path('asignar-propietario/', AsignarPropietarioView.as_view(), name='asignar-propietario'),
    path('', include(router.urls)),
    path('', include(empresa_router.urls)),
]
