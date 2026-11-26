"""
Configuración de URLs para el proyecto Core

El `urlpatterns` incluye:
- Django Admin
- API de extintores
- Rutas de autenticación JWT
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from usuarios.views import (
    ConfirmarOlvidePasswordView,
    CustomTokenObtainPairView,
    PerfilDetailView,
    MisEmpresasView,
    SolicitarOlvidePasswordView,
)

urlpatterns = [
    # Django Admin
    path('admin/', admin.site.urls),
    # Recuperación de contraseña
    path('olvide-password/', SolicitarOlvidePasswordView.as_view(), name='olvide-password'),
    path('reestablecer-password/', ConfirmarOlvidePasswordView.as_view(), name='reestablecer-password'),
    # Perfil del usuario autenticado
    path('api/perfil/', PerfilDetailView.as_view(), name='perfil-detail'),
    path('mis-empresas/', MisEmpresasView.as_view(), name='mis-empresas-global'),

    # Usuarios (list, detail)
    path('usuarios/', include('usuarios.urls')),

    # API de extintores
    path('', include('extintores.urls')),
    
    # Autenticación JWT
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/', include('leads.urls')),
    path('empresas/', include('empresas.urls')),
    path('grupos/', include('empresas.grupos_urls')),
    path('forms/', include('forms.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('reportes/', include('reportes.urls')),
]

# Servir archivos media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

