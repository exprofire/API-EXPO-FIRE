# views.py
from rest_framework import viewsets, status
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView
from django.db import transaction
from django.db.models import Count, Q
from django.contrib.auth import get_user_model

from .models import Empresa, Contacto, GrupoEmpresas
from .serializers import (
    EmpresaSerializer, 
    EmpresaCreacionSerializer, 
    EmpresaResumenSerializer,
    ContactoSerializer,
    GrupoEmpresasSerializer,
    AsignacionPropietarioSerializer,
)
from usuarios.models import Perfil
from .services.asignacion import asignar_empresas
from usuarios.visibilidad import empresas_visibles, puede_ver_empresa

User = get_user_model()


class EmpresaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar empresas.
    
    Endpoints:
    - GET /empresas/ - Listar todas las empresas
    - POST /empresas/ - Crear una nueva empresa (requiere autenticación)
    - GET /empresas/{id}/ - Ver detalle de una empresa
    - PUT/PATCH /empresas/{id}/ - Actualizar una empresa
    - DELETE /empresas/{id}/ - Eliminar una empresa
    - GET /empresas/resumen/ - Ver resumen de empresas (total, activas, inactivas)
    - GET /empresas/mis-registros/ - Ver empresas registradas por el técnico actual
    - POST /empresas/{id}/agregar-contacto/ - Agregar contacto adicional a una empresa
    - POST /empresas/{id}/borrar/ - Marcar una empresa como borrada sin eliminarla
    """
    
    queryset = Empresa.objects.select_related('grupo', 'propietario').all()
    serializer_class = EmpresaSerializer
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_queryset(self):
        return empresas_visibles(self.request.user).select_related(
            'grupo', 'propietario'
        )

    def filter_queryset(self, queryset):
        """Aplica grupo después del alcance ya calculado para el usuario."""
        queryset = super().filter_queryset(queryset)
        grupo_id = self.request.query_params.get('grupo')
        if grupo_id:
            queryset = queryset.filter(grupo_id=grupo_id)
        return queryset
    @action(detail=False, methods=['get'], url_path='resumen')
    def resumen(self, request):
        """
        Endpoint: GET /empresas/resumen/
        
        Devuelve un resumen de empresas:
        - Total de empresas
        - Empresas activas
        - Empresas inactivas
        - (Opcional para admins) Registros por técnico
        """
        queryset = self.get_queryset()
        perfil = getattr(request.user, 'perfil', None)

        # Los filtros por querystring solo se permiten dentro del universo
        # que el usuario ya tiene autorizado a ver.
        tecnico_id = request.query_params.get('tecnico_id')
        creado_por_id = request.query_params.get('creado_por_id')

        if tecnico_id:
            queryset = queryset.filter(creado_por_id=tecnico_id)

        if creado_por_id:
            queryset = queryset.filter(creado_por_id=creado_por_id)
        
        # Conteos básicos
        total = queryset.count()
        activas = queryset.filter(activa=True).count()
        inactivas = queryset.filter(activa=False).count()
        
        data = {
            'total': total,
            'activas': activas,
            'inactivas': inactivas,
        }
        
        # Solo el superadmin ve el desglose global por técnico.
        if perfil and perfil.rol == Perfil.ROLE_SUPERADMIN:
            registros_por_tecnico = []

            for user in User.objects.filter(empresas_creadas__isnull=False).distinct():
                count = user.empresas_creadas.count()
                perfil_user = getattr(user, 'perfil', None)

                registros_por_tecnico.append({
                    'tecnico_id': user.id,
                    'nombre': perfil_user.nombre_completo if perfil_user else user.username,
                    'email': user.email,
                    'total_registros': count,
                    'activas': user.empresas_creadas.filter(activa=True).count(),
                    'inactivas': user.empresas_creadas.filter(activa=False).count(),
                })

            data['registros_por_tecnico'] = registros_por_tecnico
        
        serializer = EmpresaResumenSerializer(data)
        return Response(serializer.data)
    
    
    def get_serializer_class(self):
        """Retorna diferentes serializers según la acción"""
        if self.action == 'create':
            return EmpresaCreacionSerializer
        return EmpresaSerializer
    
    def get_permissions(self):
        """Define permisos según la acción"""
        permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def perform_create(self, serializer):
        """
        Fija el técnico autenticado como creador de la empresa.
        """
        perfil = getattr(self.request.user, 'perfil', None)
        propietario = self.request.user if perfil and perfil.rol == Perfil.ROLE_ADMIN_EXPROFIRE else None
        serializer.save(creado_por=self.request.user, propietario=propietario)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        empresa = serializer.instance
        response_serializer = EmpresaSerializer(
            empresa,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
   
    @action(detail=False, methods=['get'], url_path='mis-registros')
    def mis_registros(self, request):
        """
        Endpoint: GET /empresas/mis-registros/
        
        Devuelve las empresas registradas por el técnico actualmente autenticado.
        Requiere autenticación.
        """
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Se requiere autenticación'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        empresas = self.get_queryset().filter(creado_por=request.user)
        serializer = self.get_serializer(empresas, many=True)
        
        return Response({
            'total': empresas.count(),
            'resultados': serializer.data
        })
    
    @action(detail=True, methods=['post'], url_path='agregar-contacto')
    def agregar_contacto(self, request, pk=None):
        """
        Endpoint: POST /empresas/{id}/agregar-contacto/
        
        Agrega un contacto adicional a una empresa existente.
        """
        empresa = self.get_object()
        serializer = ContactoSerializer(data=request.data)
        
        if serializer.is_valid():
            serializer.save(empresa=empresa)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='borrar')
    def borrar(self, request, pk=None):
        """
        Endpoint: POST /empresas/{id}/borrar/

        Marca la empresa como BORRADA para ocultarla del frontend sin
        eliminar el registro de la base de datos.
        """
        empresa = self.get_object()

        perfil = getattr(request.user, 'perfil', None)
        if not (
            request.user.is_superuser
            or (perfil and perfil.rol == Perfil.ROLE_SUPERADMIN)
            or (
                perfil
                and perfil.rol in [
                    Perfil.ROLE_ADMIN_EMPRESA,
                    Perfil.ROLE_ADMIN_EXPROFIRE,
                    Perfil.ROLE_ADMIN_GRUPO,
                ]
                and puede_ver_empresa(request.user, empresa.id)
            )
        ):
            raise PermissionDenied('No tienes permiso para borrar esta empresa.')

        if empresa.estatus == 'BORRADA':
            return Response({
                'detail': 'La empresa ya estaba marcada como borrada.',
                'empresa_id': str(empresa.id),
                'estatus': empresa.estatus,
            })

        empresa.estatus = 'BORRADA'
        empresa.save(update_fields=['estatus'])

        return Response({
            'detail': 'Empresa marcada como borrada correctamente.',
            'empresa_id': str(empresa.id),
            'estatus': empresa.estatus,
        }, status=status.HTTP_200_OK)


class ContactoViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar contactos de empresas.
    
    Endpoints:
    - GET /contactos/ - Listar todos los contactos
    - GET /contactos/?empresa_id=1 - Filtrar contactos por empresa
    - POST /contactos/ - Crear un nuevo contacto
    - GET /contactos/{id}/ - Ver detalle de un contacto
    - PUT/PATCH /contactos/{id}/ - Actualizar un contacto
    - DELETE /contactos/{id}/ - Eliminar un contacto
    """
    
    queryset = Contacto.objects.select_related('empresa').all()
    serializer_class = ContactoSerializer

    def perform_create(self, serializer):
        empresa_id = self.kwargs.get('empresa_pk') or self.request.data.get('empresa_id')
        user = self.request.user
        perfil = getattr(user, 'perfil', None)

        if user.is_superuser or (perfil and perfil.rol == Perfil.ROLE_SUPERADMIN):
            if not empresa_id:
                raise PermissionDenied('Debes indicar la empresa para crear el contacto.')

            empresa = Empresa.objects.get(id=empresa_id)
            serializer.save(empresa=empresa)
            return

        empresa_permitida_id = getattr(perfil, 'empresa_id', None)
        if not empresa_permitida_id and not empresas_visibles(user).exists():
            raise PermissionDenied('Tu usuario no tiene una empresa asociada.')

        empresa_id_resuelto = empresa_id or empresa_permitida_id
        if not puede_ver_empresa(user, empresa_id_resuelto):
            raise PermissionDenied('No puedes crear contactos para otra empresa.')

        empresa = Empresa.objects.get(id=empresa_id_resuelto)
        serializer.save(empresa=empresa)
    
    def get_permissions(self):
        permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """Filtra contactos por empresa si se proporciona el parámetro"""
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()

        if not (user.is_superuser or (getattr(getattr(user, 'perfil', None), 'rol', None) == Perfil.ROLE_SUPERADMIN)):
            queryset = queryset.filter(empresa_id__in=empresas_visibles(user).values('id'))

        empresa_id = (
            self.kwargs.get('empresa_pk')
            or self.request.query_params.get('empresa_id')
        )
        
        if empresa_id:
            queryset = queryset.filter(empresa_id=empresa_id)
        
        return queryset


class SoloSuperadminPermission(BasePermission):
    """Permiso exclusivo para SUPERADMIN o superusuario Django."""

    message = 'Solo SUPERADMIN o superusuario pueden gestionar grupos y propietarios.'

    def has_permission(self, request, view):
        perfil = getattr(request.user, 'perfil', None)
        return bool(
            request.user.is_authenticated
            and (
                request.user.is_superuser
                or (perfil and perfil.rol == Perfil.ROLE_SUPERADMIN)
            )
        )


class GrupoEmpresasViewSet(viewsets.ModelViewSet):
    """CRUD y asociación de empresas para grupos."""

    queryset = GrupoEmpresas.objects.select_related('propietario', 'creado_por').all()
    serializer_class = GrupoEmpresasSerializer
    permission_classes = [IsAuthenticated, SoloSuperadminPermission]

    def perform_create(self, serializer):
        serializer.save(creado_por=self.request.user, propietario=None)

    def destroy(self, request, *args, **kwargs):
        grupo = self.get_object()
        if grupo.empresas.exists():
            return Response(
                {'detail': 'No puedes borrar un grupo que tiene empresas asignadas.'},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

    def _ids(self, request):
        ids = request.data.get('empresa_ids')
        if not isinstance(ids, list) or any(not isinstance(item, int) for item in ids):
            return None
        return ids

    @action(detail=True, methods=['post'], url_path='agregar-empresas')
    def agregar_empresas(self, request, pk=None):
        grupo = self.get_object()
        ids = self._ids(request)
        if ids is None:
            return Response({'detail': 'empresa_ids debe ser una lista.'}, status=400)
        empresas = Empresa.objects.filter(id__in=ids)
        existentes = set(empresas.values_list('id', flat=True))
        with transaction.atomic():
            empresas.update(grupo=grupo)
        return Response({
            'asignadas': sorted(existentes),
            'no_existen': sorted(set(ids) - existentes),
        })

    @action(detail=True, methods=['post'], url_path='quitar-empresas')
    def quitar_empresas(self, request, pk=None):
        grupo = self.get_object()
        ids = self._ids(request)
        if ids is None:
            return Response({'detail': 'empresa_ids debe ser una lista.'}, status=400)
        empresas = Empresa.objects.filter(id__in=ids, grupo=grupo)
        quitadas = list(empresas.values_list('id', flat=True))
        with transaction.atomic():
            empresas.update(grupo=None)
        return Response({'quitadas': sorted(quitadas)})


class AsignarPropietarioView(APIView):
    """Simula o aplica asignaciones de propietario."""

    permission_classes = [IsAuthenticated, SoloSuperadminPermission]

    def post(self, request):
        serializer = AsignacionPropietarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resultado = asignar_empresas(
                usuario=request.user,
                **serializer.validated_data,
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)
