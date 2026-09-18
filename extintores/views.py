# views.py
"""
Vistas de la API REST para extintores.

Este módulo define los ViewSets que manejan las peticiones HTTP
para la gestión de extintores.
"""
import logging

from rest_framework import viewsets, filters, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings
from django.http import Http404, HttpResponse
from django.db.models import Q
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image
from core.brevo import send_brevo_transactional_email
from .models import Extintor
from empresas.models import Empresa
from usuarios.models import Perfil
from .serializers import (
    ExtintorSerializer,
    ExtintorListSerializer,
    ExtintorPublicSerializer,
    ExtintorCreateSerializer,
    RevisionExtintorSerializer,
)


logger = logging.getLogger(__name__)


class ExtintorViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar extintores.
    
    Endpoints:
        - GET /extintores/ - Lista todos los extintores
        - POST /extintores/ - Crea un nuevo extintor
        - GET /extintores/{id}/ - Detalle de un extintor
        - PUT /extintores/{id}/ - Actualiza un extintor
        - PATCH /extintores/{id}/ - Actualización parcial
        - DELETE /extintores/{id}/ - Elimina un extintor
        - GET /extintores/por_codigo/{codigo}/ - Busca por código
    """
    
    queryset = Extintor.objects.all()
    serializer_class = ExtintorSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['codigo', 'ubicacion', 'tipo']
    ordering_fields = ['codigo', 'ubicacion', 'fecha_vencimiento', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """
        Retorna el serializador apropiado según la acción.
        """
        if self.action == 'list':
            return ExtintorListSerializer
        elif self.action == 'create':
            return ExtintorCreateSerializer
        elif self.action == 'informacion_publica':
            return ExtintorPublicSerializer
        return ExtintorSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action not in ['por_codigo', 'informacion_publica']:
            if self.action == 'revisiones' and self.request.method == 'POST':
                return queryset
            queryset = self._filter_queryset_by_user_company(queryset)

        empresa = self.request.query_params.get('empresa')
        if empresa:
            empresa_filter = Q(empresa__nombre__iexact=empresa)
            if str(empresa).isdigit():
                empresa_filter |= Q(empresa__id=empresa)
            queryset = queryset.filter(empresa_filter)
        
        # --- NUEVO: Filtrar por creador ---
        creado_por = self.request.query_params.get('creado_por')
        if creado_por:
            queryset = queryset.filter(creado_por_id=creado_por)

        queryset = queryset.filter(
            Q(empresa__isnull=True) | ~Q(empresa__estatus='BORRADA')
        )
        
        return queryset

    def _filter_queryset_by_user_company(self, queryset):
        user = self.request.user
        perfil = getattr(user, 'perfil', None)

        if user.is_superuser:
            return queryset

        if perfil and perfil.rol == Perfil.ROLE_SUPERADMIN:
            return queryset

        if perfil and perfil.rol in [
            Perfil.ROLE_ADMIN_EMPRESA,
            Perfil.ROLE_SUPERVISOR,
            Perfil.ROLE_ANALISTA,
        ]:
            if perfil.empresa_id:
                return queryset.filter(empresa_id=perfil.empresa_id)
            return queryset.none()

        return queryset.none()

    def get_permissions(self):
        """
        Define permisos según la acción.
        
        - por_codigo: Público (para QR scanner)
        - Resto: Requiere autenticación
        """
        if self.action in ['por_codigo', 'informacion_publica']:
            permission_classes = [AllowAny]
        elif self.action == 'revisiones' and self.request.method == 'POST':
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    def _describe_png_buffer(self, buffer):
        buffer.seek(0)
        with Image.open(buffer) as image:
            return {
                'width': image.width,
                'height': image.height,
                'dpi': image.info.get('dpi'),
                'mode': image.mode,
            }
    
    # --- NUEVO: Perform create para asignar creado_por ---
    def perform_create(self, serializer):
        """
        Asigna automáticamente el usuario autenticado como creador del extintor.
        """
        perfil = getattr(self.request.user, 'perfil', None)
        if (
            not self.request.user.is_superuser
            and perfil
            and perfil.rol in [
                Perfil.ROLE_ADMIN_EMPRESA,
                Perfil.ROLE_SUPERVISOR,
                Perfil.ROLE_ANALISTA,
            ]
        ):
            serializer.save(creado_por=self.request.user, empresa=perfil.empresa)
            return

        empresa = None
        empresa_id = self.request.data.get('empresa_id')
        if empresa_id not in (None, ''):
            empresa = Empresa.objects.filter(id=empresa_id).first()
            if not empresa:
                raise serializers.ValidationError({
                    'empresa_id': 'Empresa no encontrada.'
                })

        serializer.save(creado_por=self.request.user, empresa=empresa)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        extintor = serializer.instance
        response_serializer = ExtintorSerializer(
            extintor,
            context=self.get_serializer_context(),
        )
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(detail=False, methods=['get'], url_path='por-codigo/(?P<codigo>[^/.]+)')
    def por_codigo(self, request, codigo=None):
        """
        Obtiene un extintor por su código.
        
        Este endpoint es público y se usa cuando se escanea un QR.
        
        Args:
            codigo: Código del extintor
            
        Returns:
            JSON con la información del extintor
        """
        empresa_id = request.query_params.get('empresa_id')
        queryset = Extintor.objects.filter(codigo=codigo).filter(
            Q(empresa__isnull=True) | ~Q(empresa__estatus='BORRADA')
        )

        if empresa_id:
            queryset = queryset.filter(empresa_id=empresa_id)

        count = queryset.count()
        if count == 0:
            raise Http404

        if count > 1 and not empresa_id:
            return Response(
                {
                    'detail': (
                        'El código existe en más de una empresa. '
                        'Debes enviar empresa_id para identificar el extintor.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        extintor = queryset.first()
        serializer = self.get_serializer(extintor)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='informacion')
    def informacion_publica(self, request, pk=None):
        """
        Endpoint público para la página /informacion/{id}.
        
        Devuelve solo datos seguros del extintor para consulta externa.
        """
        extintor = self.get_object()
        serializer = self.get_serializer(extintor)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get', 'post'], url_path='revisiones')
    def revisiones(self, request, pk=None):
        """
        GET /extintores/{id}/revisiones/ -> lista el historial de revisiones.
        POST /extintores/{id}/revisiones/ -> crea una nueva revisión.
        """
        extintor = Extintor.objects.filter(pk=pk).select_related('empresa', 'creado_por').first()
        if not extintor:
            raise Http404

        if request.method == 'GET':
            revisiones = extintor.revisiones.select_related('tecnico', 'empresa').all()
            serializer = RevisionExtintorSerializer(revisiones, many=True)
            return Response(serializer.data)

        serializer = RevisionExtintorSerializer(
            data=request.data,
            context={
                'request': request,
                'extintor': extintor,
            },
        )
        serializer.is_valid(raise_exception=True)
        revision = serializer.save()
        extintor.registrar_revision(revision.creado_en.date(), meses_siguiente=1)
        read_serializer = RevisionExtintorSerializer(revision)

        email_status = {'enviado': False, 'destinatarios': []}
        destinatarios = getattr(settings, 'UIPC_PDF_RECIPIENTS', [])
        if revision.pdf_uipc and destinatarios:
            try:
                with revision.pdf_uipc.open('rb') as pdf_file:
                    attachment_bytes = pdf_file.read()
                email_result = send_brevo_transactional_email(
                    subject=f'UIPC generada - {extintor.codigo}',
                    text_content=(
                        f'Se generó una nueva UIPC para el extintor {extintor.codigo}.\n'
                        f'Folio: {revision.id.hex[:8].upper()}\n'
                        f'Fecha: {revision.creado_en.strftime("%d/%m/%Y %H:%M") if revision.creado_en else ""}'
                    ),
                    to_emails=destinatarios,
                    sender_email=getattr(settings, 'BREVO_SENDER_EMAIL', ''),
                    sender_name=getattr(settings, 'BREVO_SENDER_NAME', ''),
                    attachments=[
                        {
                            'name': Path(revision.pdf_uipc.name).name,
                            'content': attachment_bytes,
                        }
                    ],
                    timeout=getattr(settings, 'EMAIL_TIMEOUT', 10),
                )
                email_status = {
                    'enviado': email_result['ok'],
                    'destinatarios': destinatarios,
                }
                logger.info(
                    'Resultado envío UIPC por Brevo: enviado=%s status_code=%s destinatarios=%s',
                    email_result['ok'],
                    email_result['status_code'],
                    destinatarios,
                )
                if not email_result['ok']:
                    email_status['error'] = email_result['error']
                    logger.error('Error Brevo enviando UIPC: %s', email_result['error'])
            except Exception as exc:
                email_status = {'enviado': False, 'error': str(exc), 'destinatarios': destinatarios}
                logger.exception('Excepción enviando UIPC por Brevo: %s', exc)

        response_data = read_serializer.data
        response_data['correo_pdf'] = email_status
        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='kpis')
    def kpis(self, request):
        """
        KPI demo: totales y porcentajes clave por estado y empresa.
        """
        extintores = self.get_queryset()
        total = extintores.count()
        estados = {'verde': 0, 'amarillo': 0, 'rojo': 0}
        empresas = {}
        
        for ext in extintores:
            estados[ext.estado] += 1
            if ext.empresa:
                empresas.setdefault(ext.empresa.nombre, 0)
                empresas[ext.empresa.nombre] += 1

        def pct(value):
            return round((value / total) * 100, 1) if total else 0

        data = {
            'total_extintores': total,
            'por_estado': {
                estado: {
                    'cantidad': count,
                    'porcentaje': pct(count),
                }
                for estado, count in estados.items()
            },
            'empresas_activas': empresas,
        }
        return Response(data)
    
    @action(detail=False, methods=['get'], url_path='estadisticas')
    def estadisticas(self, request):
        """
        Obtiene estadísticas generales de los extintores.
        
        Returns:
            JSON con estadísticas (total, por estado, por tipo)
        """
        extintores = self.get_queryset()
        
        # Contar por estado
        estados = {'verde': 0, 'amarillo': 0, 'rojo': 0}
        for extintor in extintores:
            estados[extintor.estado] += 1
        
        # Contar por tipo
        tipos = {}
        for extintor in extintores:
            tipo = extintor.get_tipo_display()
            tipos[tipo] = tipos.get(tipo, 0) + 1
        
        data = {
            'total': extintores.count(),
            'empresas_activas': Empresa.objects.filter(activa=True).count(),
            'por_estado': estados,
            'por_tipo': tipos,
        }
        
        return Response(data)

    @action(detail=False, methods=['post'], url_path='impresionmasiva')
    def impresionmasiva(self, request):
        """Genera un ZIP con las etiquetas PNG de múltiples extintores."""
        ids = request.data.get('ids')
        if not isinstance(ids, list) or not ids:
            return Response(
                {'detail': 'Debe enviar una lista de IDs en el cuerpo JSON bajo la llave "ids".'},
                status=400,
            )

        queryset = self.get_queryset().filter(id__in=ids)
        encontrados = {str(ext.id) for ext in queryset}
        faltantes = [ext_id for ext_id in ids if ext_id not in encontrados]

        if faltantes:
            return Response(
                {'detail': 'No se encontraron todos los extintores solicitados.', 'faltantes': faltantes},
                status=404,
            )

        archivo_zip = BytesIO()
        with ZipFile(archivo_zip, 'w', ZIP_DEFLATED) as zipfile:
            for extintor in queryset:
                if not extintor.qr_code:
                    extintor.save()

                with extintor.qr_code.open('rb') as qr_file:
                    nombre_archivo = f"{extintor.codigo}.png"
                    zipfile.writestr(nombre_archivo, qr_file.read())
        archivo_zip.seek(0)

        response = HttpResponse(archivo_zip.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="etiquetas_extintores.zip"'
        return response

    @action(detail=True, methods=['get'], url_path='etiqueta')
    def etiqueta(self, request, pk=None):
        """
        Devuelve la URL firmada de la etiqueta QR almacenada en S3.
        """
        extintor = self.get_object()
        if not extintor.qr_code:
            extintor.save()

        return Response({
            'etiqueta_url': extintor.qr_code.url,
        })

    @action(detail=True, methods=['post'], url_path='regenerar-qr')
    def regenerar_qr(self, request, pk=None):
        """
        Regenera el QR del extintor usando la URL actual configurada.
        """
        extintor = self.get_object()
        diagnostico = str(request.query_params.get('diagnostico', '')).lower() in {'1', 'true', 'yes', 'si', 'sí'}
        preview_buffer = extintor.obtener_etiqueta_png() if diagnostico else None
        extintor.regenerar_qr()
        serializer = self.get_serializer(extintor)
        response_data = {
            'detail': 'QR regenerado correctamente.',
            'extintor': serializer.data,
        }

        if diagnostico:
            saved_buffer = BytesIO()
            with extintor.qr_code.open('rb') as qr_file:
                saved_buffer.write(qr_file.read())
            saved_buffer.seek(0)
            response_data['diagnostico_qr'] = {
                'preview': self._describe_png_buffer(preview_buffer),
                'guardado': self._describe_png_buffer(saved_buffer),
                'storage_backend': extintor.qr_code.storage.__class__.__name__,
                'nombre_archivo': extintor.qr_code.name,
                'url': extintor.qr_code.url,
            }

        return Response(response_data)

    @action(detail=True, methods=['get'], url_path='qr-descargar')
    def qr_descargar(self, request, pk=None):
        """
        Descarga directa del PNG del QR/etiqueta del extintor.
        Útil para evitar problemas de CORS con el bucket privado de S3.
        """
        extintor = self.get_object()
        if not extintor.qr_code:
            extintor.save()

        with extintor.qr_code.open('rb') as qr_file:
            response = HttpResponse(qr_file.read(), content_type='image/png')
            response['Content-Disposition'] = f'attachment; filename="qr_{extintor.codigo}.png"'
            return response
    
    # --- NUEVO: Endpoint para ver mis extintores registrados ---
    @action(detail=False, methods=['get'], url_path='mis-registros')
    def mis_registros(self, request):
        """
        Endpoint: GET /extintores/mis-registros/
        
        Devuelve los extintores registrados por el usuario actualmente autenticado.
        Requiere autenticación.
        """
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Se requiere autenticación'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        extintores = self.get_queryset().filter(creado_por=request.user)
        serializer = self.get_serializer(extintores, many=True)
        
        return Response({
            'total': extintores.count(),
            'resultados': serializer.data
        })
