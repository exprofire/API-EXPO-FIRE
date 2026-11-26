"""
Vistas enfocadas en usuarios.
"""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from empresas.services.asignacion import transferir_cartera
from usuarios.visibilidad import empresas_visibles, puede_ver_empresa

from .models import Perfil
from .serializers import (
    CambiarMiPasswordSerializer,
    ConfirmarOlvidePasswordSerializer,
    PerfilSerializer,
    PerfilCreateSerializer,
    SolicitarOlvidePasswordSerializer,
    SolicitarResetPasswordSerializer,
    CambiarRolSerializer,
)
from empresas.models import Empresa, GrupoEmpresas
from empresas.serializers import EmpresaSerializer, TransferenciaCarteraSerializer
from core.brevo import send_brevo_transactional_email
User = get_user_model()
logger = logging.getLogger(__name__)


def _build_password_reset_link(user, base_url=None):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base_url = (base_url or getattr(settings, 'PASSWORD_RESET_FRONTEND_URL', '')).strip()

    if not base_url:
        base_url = 'https://www.exprofire.com//olvide-password'

    separator = '&' if '?' in base_url else '?'
    query = urlencode({'uid': uid, 'token': token})
    return f"{base_url}{separator}{query}"


def _send_welcome_email(user):
    reset_link = _build_password_reset_link(
        user,
        getattr(
            settings,
            'NEW_USER_PASSWORD_FRONTEND_URL',
            'https://www.exprofire.com/crear-password',
        ),
    )
    result = send_brevo_transactional_email(
        to_email=user.email,
        subject='Bienvenido a Expro Fire',
        text_content=(
            f'Hola {user.get_full_name() or user.username},\n\n'
            'Tu acceso a Expro Fire fue creado correctamente.\n\n'
            f'Usuario: {user.username}\n\n'
            'Para establecer tu contraseña, abre este enlace:\n'
            f'{reset_link}\n\n'
            'Por seguridad, el enlace es personal y temporal.'
        ),
        html_content=(
            f'<p>Hola {user.get_full_name() or user.username},</p>'
            '<p>Tu acceso a Expro Fire fue creado correctamente.</p>'
            f'<p><strong>Usuario:</strong> {user.username}</p>'
            f'<p><a href="{reset_link}">Establecer mi contraseña</a></p>'
            '<p>Por seguridad, el enlace es personal y temporal.</p>'
        ),
    )
    status_data = {
        'enviado': result['ok'],
        'destinatario': user.email,
    }
    if not result['ok']:
        status_data['error'] = result['error']
        logger.error(
            'Error enviando bienvenida a nuevo usuario %s: %s',
            user.username,
            result['error'],
        )
    return status_data


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        perfil = getattr(self.user, 'perfil', None)
        empresa = perfil.empresa if perfil and perfil.empresa else None
        empresa_data = None
        if empresa:
            empresa_data = EmpresaSerializer(
                empresa,
                context=self.context,
            ).data

        data['requiere_cambio_password'] = bool(
            perfil and perfil.requiere_cambio_password
        )
        data['usuario'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'rol': perfil.rol if perfil else None,
            'empresa_id': perfil.empresa_id if perfil else None,
            'empresa': empresa_data,
            'grupo_id': perfil.grupo_id if perfil else None,
            'puede_reportes': bool(perfil and perfil.puede_reportes),
            'puede_documentar': bool(perfil and perfil.puede_documentar),
            'logo_empresa_url': empresa_data['logo_url'] if empresa_data else None,
        }
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class PerfilDetailView(APIView):
    """Devuelve la información del perfil autenticado."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        perfil, _ = Perfil.objects.get_or_create(
            user=request.user,
            defaults={
                'empresa': None,
                'foto_perfil': None,
            }
        )
        serializer = PerfilSerializer(perfil, context={'request': request})
        return Response(serializer.data)


class SolicitarOlvidePasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SolicitarOlvidePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user:
            reset_link = _build_password_reset_link(user)
            result = send_brevo_transactional_email(
                to_email=user.email,
                subject='Restablece tu contrasena',
                text_content=(
                    'Hemos recibido una solicitud para restablecer tu contrasena.\n\n'
                    f'Abre este enlace para continuar:\n{reset_link}\n\n'
                    'Si no solicitaste este cambio, puedes ignorar este correo.'
                ),
            )
            if not result['ok']:
                logger.exception(
                    'Error enviando correo de restablecimiento: %s',
                    result['error'],
                )
                return Response(
                    {
                        'detail': (
                            'Encontramos el usuario, pero no fue posible enviar el correo. '
                            'Revisa la configuracion de Brevo.'
                        )
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        return Response({
            'detail': 'Si el correo existe, te enviaremos un enlace para restablecer la contrasena.'
        })


class ConfirmarOlvidePasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ConfirmarOlvidePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uid = serializer.validated_data['uid']
        token = serializer.validated_data['token']

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {'detail': 'El enlace de restablecimiento no es válido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {'detail': 'El enlace de restablecimiento no es válido o ya expiró.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data['password'])
        user.save(update_fields=['password'])

        perfil, _ = Perfil.objects.get_or_create(user=user)
        perfil.requiere_cambio_password = False
        perfil.reset_password_solicitado_at = None
        perfil.reset_password_solicitado_por = None
        perfil.save(update_fields=[
            'requiere_cambio_password',
            'reset_password_solicitado_at',
            'reset_password_solicitado_por',
            'updated_at',
        ])

        return Response({'detail': 'Contraseña actualizada correctamente.'})


class EquipoEmpresaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, empresa_id):
        if not self._puede_ver_empresa(request.user, empresa_id):
            return Response(
                {'detail': 'No tienes permiso para ver el equipo de esta empresa.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        perfiles = Perfil.objects.select_related('user', 'empresa').filter(
            empresa_id=empresa_id,
            rol__in=[Perfil.ROLE_SUPERVISOR, Perfil.ROLE_ANALISTA],
        )
        supervisores = perfiles.filter(rol=Perfil.ROLE_SUPERVISOR)
        analistas = perfiles.filter(rol=Perfil.ROLE_ANALISTA)

        return Response({
            'empresa_id': empresa_id,
            'conteos': {
                'supervisores': supervisores.count(),
                'analistas': analistas.count(),
                'total': perfiles.count(),
            },
            'supervisores': PerfilSerializer(
                supervisores,
                many=True,
                context={'request': request},
            ).data,
            'analistas': PerfilSerializer(
                analistas,
                many=True,
                context={'request': request},
            ).data,
        })

    def _puede_ver_empresa(self, user, empresa_id):
        perfil = getattr(user, 'perfil', None)
        if not perfil:
            return False
        if perfil.rol == Perfil.ROLE_SUPERADMIN:
            return True
        if perfil.rol in [Perfil.ROLE_ADMIN_EXPROFIRE, Perfil.ROLE_ADMIN_GRUPO]:
            return puede_ver_empresa(user, empresa_id)
        if perfil.rol in [Perfil.ROLE_ADMIN_EMPRESA, Perfil.ROLE_SUPERVISOR]:
            return str(perfil.empresa_id) == str(empresa_id)
        return False


class MisEmpresasView(APIView):
    """Lista las empresas visibles para el usuario autenticado."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresas = empresas_visibles(request.user).select_related(
            'grupo', 'propietario'
        ).only(
            'id', 'nombre', 'logo', 'grupo_id', 'grupo__nombre',
            'propietario_id', 'propietario__username',
            'propietario__first_name', 'propietario__last_name',
        )
        return Response({
            'resultados': [
                {
                    'id': empresa.id,
                    'nombre': empresa.nombre,
                    'logo': empresa.logo.url if empresa.logo else None,
                    'grupo_id': empresa.grupo_id,
                    'grupo_nombre': empresa.grupo.nombre if empresa.grupo else None,
                    'propietario_id': empresa.propietario_id,
                    'propietario_nombre': (
                        empresa.propietario.get_full_name()
                        or empresa.propietario.username
                        if empresa.propietario else None
                    ),
                }
                for empresa in empresas
            ]
        })


class PerfilViewSet(viewsets.ModelViewSet):
    """
    Listado, detalle y creación de perfiles (usuarios).
    """

    queryset = Perfil.objects.select_related('user', 'empresa').all()

    def get_queryset(self):
        queryset = super().get_queryset()
        rol = self.request.query_params.get('rol')
        empresa_id = self.request.query_params.get('empresa_id')
        is_active = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')

        if rol:
            queryset = queryset.filter(rol=rol)

        if empresa_id:
            queryset = queryset.filter(empresa_id=empresa_id)

        if is_active is not None:
            queryset = queryset.filter(user__is_active=is_active.lower() == 'true')

        if search:
            queryset = queryset.filter(
                Q(user__username__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        return queryset

    def get_serializer_class(self):
        if self.action == 'create':
            return PerfilCreateSerializer
        return PerfilSerializer

    def get_permissions(self):
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        perfil_solicitante = getattr(request.user, 'perfil', None)
        puede_crear = (
            request.user.is_superuser
            or (
                perfil_solicitante
                and perfil_solicitante.rol in [
                    Perfil.ROLE_SUPERADMIN,
                    Perfil.ROLE_ADMIN_EMPRESA,
                    Perfil.ROLE_ADMIN_EXPROFIRE,
                    Perfil.ROLE_ADMIN_GRUPO,
                ]
            )
        )
        if not puede_crear:
            return Response(
                {'detail': 'No tienes permiso para crear usuarios.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        perfil = serializer.save()
        perfil.requiere_cambio_password = True
        perfil.save(update_fields=['requiere_cambio_password', 'updated_at'])

        user = perfil.user
        reset_link = _build_password_reset_link(
            user,
            getattr(
                settings,
                'NEW_USER_PASSWORD_FRONTEND_URL',
                'https://www.exprofire.com/crear-password',
            ),
        )
        email_result = send_brevo_transactional_email(
            to_email=user.email,
            subject='Bienvenido a Expro Fire',
            text_content=(
                f'Hola {user.get_full_name() or user.username},\n\n'
                'Tu acceso a Expro Fire fue creado correctamente.\n\n'
                f'Usuario: {user.username}\n\n'
                'Para establecer tu contraseña, abre este enlace:\n'
                f'{reset_link}\n\n'
                'Por seguridad, el enlace es personal y temporal.'
            ),
            html_content=(
                f'<p>Hola {user.get_full_name() or user.username},</p>'
                '<p>Tu acceso a Expro Fire fue creado correctamente.</p>'
                f'<p><strong>Usuario:</strong> {user.username}</p>'
                f'<p><a href="{reset_link}">Establecer mi contraseña</a></p>'
                '<p>Por seguridad, el enlace es personal y temporal.</p>'
            ),
        )
        correo_bienvenida = {
            'enviado': email_result['ok'],
            'destinatario': user.email,
        }
        if not email_result['ok']:
            correo_bienvenida['error'] = email_result['error']
            logger.error(
                'Error enviando bienvenida a nuevo usuario %s: %s',
                user.username,
                email_result['error'],
            )
        read_serializer = PerfilSerializer(perfil, context=self.get_serializer_context())
        response_data = read_serializer.data
        response_data['correo_bienvenida'] = correo_bienvenida
        headers = self.get_success_headers(read_serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'], url_path='transferir-cartera')
    def transferir_cartera(self, request, pk=None):
        """Transfiere la cartera de un ADMIN_EXPROFIRE a otro."""
        perfil_objetivo = self.get_object()
        solicitante = getattr(request.user, 'perfil', None)
        if not (
            request.user.is_superuser
            or (solicitante and solicitante.rol == Perfil.ROLE_SUPERADMIN)
        ):
            return Response(
                {'detail': 'Solo SUPERADMIN o superusuario pueden transferir carteras.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = TransferenciaCarteraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resultado = transferir_cartera(
                propietario_actual_id=perfil_objetivo.user_id,
                usuario=request.user,
                **serializer.validated_data,
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)

    @action(detail=True, methods=['post'], url_path='cambiar-rol')
    def cambiar_rol(self, request, pk=None):
        """Cambia rol y asignación empresarial bajo control de SUPERADMIN."""
        perfil_objetivo = self.get_object()
        solicitante = getattr(request.user, 'perfil', None)
        if not (
            request.user.is_superuser
            or (solicitante and solicitante.rol == Perfil.ROLE_SUPERADMIN)
        ):
            return Response(
                {'detail': 'Solo SUPERADMIN o superusuario pueden cambiar roles.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if perfil_objetivo.user_id == request.user.id:
            return Response(
                {'detail': 'No puedes cambiar tu propio rol.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CambiarRolSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        nuevo_rol = datos['rol']
        empresa_id = datos.get('empresa_id')
        grupo_id = datos.get('grupo_id')

        if nuevo_rol in [Perfil.ROLE_ADMIN_EMPRESA, Perfil.ROLE_SUPERVISOR, Perfil.ROLE_ANALISTA] and not empresa_id:
            return Response({'detail': 'Este rol requiere empresa_id.'}, status=400)
        if nuevo_rol == Perfil.ROLE_ADMIN_GRUPO and not grupo_id:
            return Response({'detail': 'ADMIN_GRUPO requiere grupo_id.'}, status=400)
        if empresa_id and not Empresa.objects.filter(id=empresa_id).exists():
            return Response({'detail': 'Empresa no encontrada.'}, status=400)
        if grupo_id and not GrupoEmpresas.objects.filter(id=grupo_id).exists():
            return Response({'detail': 'Grupo no encontrado.'}, status=400)
        if perfil_objetivo.rol == Perfil.ROLE_SUPERADMIN and nuevo_rol != Perfil.ROLE_SUPERADMIN:
            queda_otro = Perfil.objects.filter(
                rol=Perfil.ROLE_SUPERADMIN,
                user__is_active=True,
            ).exclude(pk=perfil_objetivo.pk).exists()
            if not queda_otro:
                return Response({'detail': 'Debe permanecer al menos un SUPERADMIN activo.'}, status=400)

        antes = {
            'rol': perfil_objetivo.rol,
            'empresa_id': perfil_objetivo.empresa_id,
            'grupo_id': perfil_objetivo.grupo_id,
            'is_superuser': perfil_objetivo.user.is_superuser,
            'is_staff': perfil_objetivo.user.is_staff,
        }
        with transaction.atomic():
            perfil_objetivo.rol = nuevo_rol
            perfil_objetivo.empresa_id = (
                empresa_id
                if nuevo_rol in [Perfil.ROLE_ADMIN_EMPRESA, Perfil.ROLE_SUPERVISOR, Perfil.ROLE_ANALISTA]
                else None
            )
            perfil_objetivo.grupo_id = grupo_id if nuevo_rol == Perfil.ROLE_ADMIN_GRUPO else None
            perfil_objetivo.save(update_fields=['rol', 'empresa', 'grupo', 'updated_at'])
            if nuevo_rol != Perfil.ROLE_SUPERADMIN:
                perfil_objetivo.user.is_superuser = False
                perfil_objetivo.user.is_staff = False
                perfil_objetivo.user.save(update_fields=['is_superuser', 'is_staff'])
        return Response({
            'antes': antes,
            'despues': {
                'rol': perfil_objetivo.rol,
                'empresa_id': perfil_objetivo.empresa_id,
                'grupo_id': perfil_objetivo.grupo_id,
                'is_superuser': perfil_objetivo.user.is_superuser,
                'is_staff': perfil_objetivo.user.is_staff,
            },
        })

    def update(self, request, *args, **kwargs):
        """Aplica alcance por rol antes de permitir editar un perfil."""
        perfil_objetivo = self.get_object()
        perfil_solicitante = getattr(request.user, 'perfil', None)
        es_privilegiado = (
            request.user.is_superuser
            or (perfil_solicitante and perfil_solicitante.rol == Perfil.ROLE_SUPERADMIN)
        )
        campos_sensibles = {
            'rol', 'empresa_id', 'empresa', 'grupo_id', 'grupo',
            'is_superuser', 'is_staff', 'puede_reportes', 'puede_documentar',
        }
        puede_gestionar = self._puede_gestionar_usuario(request.user, perfil_objetivo)
        es_propio = perfil_objetivo.user_id == request.user.id

        if es_propio and campos_sensibles.intersection(request.data.keys()):
            return Response(
                {'detail': 'No puedes modificar esos campos sobre tu propio usuario.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not es_privilegiado and not puede_gestionar:
            if not self._puede_editar_perfil_basico(request.user, perfil_objetivo):
                return Response(
                    {'detail': 'No tienes permiso para editar este usuario.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if campos_sensibles.intersection(request.data.keys()):
                return Response(
                    {'detail': 'No tienes permiso para modificar rol, empresa o privilegios.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='reenviar-bienvenida')
    def reenviar_bienvenida(self, request, pk=None):
        perfil_objetivo = self.get_object()
        if not self._puede_gestionar_usuario(request.user, perfil_objetivo):
            return Response(
                {'detail': 'No tienes permiso para reenviar esta bienvenida.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        perfil_objetivo.requiere_cambio_password = True
        perfil_objetivo.save(update_fields=['requiere_cambio_password', 'updated_at'])
        correo_bienvenida = _send_welcome_email(perfil_objetivo.user)

        return Response({
            'detail': 'Correo de bienvenida reenviado.',
            'usuario_id': perfil_objetivo.user_id,
            'correo_bienvenida': correo_bienvenida,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='solicitar-reset-password')
    def solicitar_reset_password(self, request, pk=None):
        serializer = SolicitarResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        perfil_objetivo = self.get_object()
        if not self._puede_gestionar_usuario(request.user, perfil_objetivo):
            return Response(
                {'detail': 'No tienes permiso para solicitar este reseteo.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        perfil_objetivo.requiere_cambio_password = True
        perfil_objetivo.reset_password_solicitado_at = timezone.now()
        perfil_objetivo.reset_password_solicitado_por = request.user
        perfil_objetivo.save(update_fields=[
            'requiere_cambio_password',
            'reset_password_solicitado_at',
            'reset_password_solicitado_por',
            'updated_at',
        ])

        return Response({
            'detail': 'Solicitud de cambio de contraseña registrada.',
            'usuario_id': perfil_objetivo.user_id,
            'requiere_cambio_password': perfil_objetivo.requiere_cambio_password,
            'reset_password_solicitado_at': perfil_objetivo.reset_password_solicitado_at,
        })

    @action(detail=False, methods=['post'], url_path='cambiar-mi-password')
    def cambiar_mi_password(self, request):
        serializer = CambiarMiPasswordSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data['password_nueva'])
        request.user.save(update_fields=['password'])

        perfil, _ = Perfil.objects.get_or_create(user=request.user)
        perfil.requiere_cambio_password = False
        perfil.reset_password_solicitado_at = None
        perfil.reset_password_solicitado_por = None
        perfil.save(update_fields=[
            'requiere_cambio_password',
            'reset_password_solicitado_at',
            'reset_password_solicitado_por',
            'updated_at',
        ])

        return Response({'detail': 'Contraseña actualizada correctamente.'})

    @action(detail=True, methods=['post'], url_path='suspender')
    def suspender(self, request, pk=None):
        perfil_objetivo = self.get_object()
        if not self._puede_gestionar_usuario(request.user, perfil_objetivo):
            return Response(
                {'detail': 'No tienes permiso para suspender este usuario.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if perfil_objetivo.user_id == request.user.id:
            return Response(
                {'detail': 'No puedes suspender tu propio usuario.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        perfil_objetivo.user.is_active = False
        perfil_objetivo.user.save(update_fields=['is_active'])
        return Response({
            'detail': 'Usuario suspendido correctamente.',
            'usuario_id': perfil_objetivo.user_id,
            'is_active': perfil_objetivo.user.is_active,
        })

    @action(detail=True, methods=['post'], url_path='reactivar')
    def reactivar(self, request, pk=None):
        perfil_objetivo = self.get_object()
        if not self._puede_gestionar_usuario(request.user, perfil_objetivo):
            return Response(
                {'detail': 'No tienes permiso para reactivar este usuario.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        perfil_objetivo.user.is_active = True
        perfil_objetivo.user.save(update_fields=['is_active'])
        return Response({
            'detail': 'Usuario reactivado correctamente.',
            'usuario_id': perfil_objetivo.user_id,
            'is_active': perfil_objetivo.user.is_active,
        })

    def destroy(self, request, *args, **kwargs):
        perfil_objetivo = self.get_object()
        if not self._puede_gestionar_usuario(request.user, perfil_objetivo):
            return Response(
                {'detail': 'No tienes permiso para eliminar este usuario.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if perfil_objetivo.user_id == request.user.id:
            return Response(
                {'detail': 'No puedes eliminar tu propio usuario.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        usuario = perfil_objetivo.user
        usuario_id = usuario.id
        usuario.delete()
        return Response(
            {'detail': 'Usuario eliminado definitivamente.', 'usuario_id': usuario_id},
            status=status.HTTP_200_OK,
        )

    def _puede_gestionar_usuario(self, user, perfil_objetivo):
        perfil_solicitante = getattr(user, 'perfil', None)
        if not perfil_solicitante:
            return False
        if perfil_solicitante.rol == Perfil.ROLE_SUPERADMIN:
            return True
        if perfil_solicitante.rol in [
            Perfil.ROLE_ADMIN_EMPRESA,
            Perfil.ROLE_ADMIN_EXPROFIRE,
            Perfil.ROLE_ADMIN_GRUPO,
        ]:
            return bool(
                perfil_objetivo.empresa_id
                and puede_ver_empresa(user, perfil_objetivo.empresa_id)
            )
        return False

    def _puede_editar_perfil_basico(self, user, perfil_objetivo):
        """Admin gestiona su empresa; supervisor/analista solo a sí mismos."""
        perfil_solicitante = getattr(user, 'perfil', None)
        if not perfil_solicitante:
            return False
        if perfil_solicitante.rol == Perfil.ROLE_ADMIN_EMPRESA:
            return self._puede_gestionar_usuario(user, perfil_objetivo)
        if perfil_solicitante.rol in [Perfil.ROLE_SUPERVISOR, Perfil.ROLE_ANALISTA]:
            return perfil_objetivo.user_id == user.id
        return False

