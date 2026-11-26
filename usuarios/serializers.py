"""
Serializadores para el dominio de usuarios.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Perfil
from empresas.models import Empresa, GrupoEmpresas
from empresas.serializers import EmpresaSerializer
from usuarios.visibilidad import puede_ver_empresa

User = get_user_model()


class PerfilSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    foto_perfil = serializers.ImageField(required=False, allow_null=True)
    nombre_completo = serializers.CharField(read_only=True)

    rol = serializers.ChoiceField(
        choices=Perfil.ROLE_CHOICES,
        default=Perfil.ROLE_ANALISTA,
        required=False,
        help_text='Rol del usuario dentro del sistema'
    )

    empresa = EmpresaSerializer(read_only=True)
    grupo_id = serializers.IntegerField(required=False, allow_null=True)
    grupo = serializers.SerializerMethodField()
    puede_reportes = serializers.BooleanField(required=False)
    puede_documentar = serializers.BooleanField(required=False)
    # Estos campos solo se aceptan en escritura cuando la vista autoriza al
    # usuario gestor; la vista impide que el propio usuario los cambie.
    empresa_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    is_superuser = serializers.BooleanField(required=False, write_only=True)
    is_staff = serializers.BooleanField(required=False, write_only=True)

    class UserSerializer(serializers.ModelSerializer):
        class Meta:
            model = User
            fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active']
            read_only_fields = fields

    class Meta:
        model = Perfil
        fields = [
            'id',
            'user',
            'username',
            'email',
            'nombre_completo',
            'empresa',
            'empresa_id',
            'grupo_id',
            'grupo',
            'foto_perfil',
            'rol',
            'is_superuser',
            'is_staff',
            'puede_reportes',
            'puede_documentar',
            'telefono',
            'domicilio',
            'requiere_cambio_password',
            'reset_password_solicitado_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'username',
            'email',
            'requiere_cambio_password',
            'reset_password_solicitado_at',
            'created_at',
            'updated_at',
            'empresa',
        ]

    def get_user(self, obj):
        serializer = self.UserSerializer(obj.user, context=self.context)
        return serializer.data

    def get_grupo(self, obj):
        if not obj.grupo_id:
            return None
        return {'id': obj.grupo_id, 'nombre': obj.grupo.nombre}

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.foto_perfil:
            request = self.context.get('request')
            data['foto_perfil'] = (
                request.build_absolute_uri(instance.foto_perfil.url)
                if request
                else instance.foto_perfil.url
            )
        else:
            data['foto_perfil'] = None
        return data

    def validate_empresa_id(self, value):
        if value is None:
            return None
        if not Empresa.objects.filter(id=value).exists():
            raise serializers.ValidationError('Empresa no encontrada.')
        return value

    def update(self, instance, validated_data):
        """Actualiza el perfil y, si la vista lo permite, los campos sensibles."""
        empresa_id = validated_data.pop('empresa_id', serializers.empty)
        grupo_id = validated_data.pop('grupo_id', serializers.empty)
        is_superuser = validated_data.pop('is_superuser', serializers.empty)
        is_staff = validated_data.pop('is_staff', serializers.empty)

        perfil = super().update(instance, validated_data)
        campos_usuario = []
        if empresa_id is not serializers.empty:
            perfil.empresa_id = empresa_id
            perfil.save(update_fields=['empresa'])
        if grupo_id is not serializers.empty:
            perfil.grupo_id = grupo_id
            perfil.save(update_fields=['grupo'])
        if is_superuser is not serializers.empty:
            perfil.user.is_superuser = is_superuser
            campos_usuario.append('is_superuser')
        if is_staff is not serializers.empty:
            perfil.user.is_staff = is_staff
            campos_usuario.append('is_staff')
        if campos_usuario:
            perfil.user.save(update_fields=campos_usuario)
        return perfil


class PerfilCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    rol = serializers.ChoiceField(
        choices=Perfil.ROLE_CHOICES,
        default=Perfil.ROLE_ANALISTA,
    )
    empresa_id = serializers.IntegerField(required=False)
    grupo_id = serializers.IntegerField(required=False, allow_null=True)
    foto_perfil = serializers.ImageField(required=False, allow_null=True)
    telefono = serializers.CharField(required=False, allow_blank=True, max_length=30)
    domicilio = serializers.CharField(required=False, allow_blank=True, max_length=250)

    def validate(self, attrs):
        request = self.context.get('request')
        perfil_solicitante = getattr(request.user, 'perfil', None) if request else None

        es_privilegiado = bool(
            request and request.user.is_superuser
        ) or bool(
            perfil_solicitante and perfil_solicitante.rol == Perfil.ROLE_SUPERADMIN
        )
        roles_gestores = [
            Perfil.ROLE_ADMIN_EMPRESA,
            Perfil.ROLE_ADMIN_EXPROFIRE,
            Perfil.ROLE_ADMIN_GRUPO,
        ]
        if not es_privilegiado and not (
            perfil_solicitante and perfil_solicitante.rol in roles_gestores
        ):
            raise serializers.ValidationError('No tienes permiso para crear usuarios.')

        if not es_privilegiado and perfil_solicitante.rol in roles_gestores:
            if attrs['rol'] not in [Perfil.ROLE_SUPERVISOR, Perfil.ROLE_ANALISTA]:
                raise serializers.ValidationError({
                    'rol': 'Este administrador solo puede crear supervisores y analistas.'
                })
        if attrs['rol'] in [
            Perfil.ROLE_ADMIN_EMPRESA,
            Perfil.ROLE_SUPERVISOR,
            Perfil.ROLE_ANALISTA,
        ] and not attrs.get('empresa_id'):
            raise serializers.ValidationError({
                'empresa_id': 'Este rol requiere una empresa asignada.'
            })
        if attrs['rol'] == Perfil.ROLE_ADMIN_GRUPO and not attrs.get('grupo_id'):
            raise serializers.ValidationError({
                'grupo_id': 'ADMIN_GRUPO requiere un grupo asignado.'
            })

        if not es_privilegiado and perfil_solicitante.rol == Perfil.ROLE_ADMIN_EMPRESA:
            if not perfil_solicitante.empresa_id:
                raise serializers.ValidationError({
                    'empresa_id': 'El administrador no tiene una empresa asignada.'
                })
            if attrs.get('empresa_id') and attrs['empresa_id'] != perfil_solicitante.empresa_id:
                raise serializers.ValidationError({
                    'empresa_id': 'Solo puedes crear usuarios para tu propia empresa.'
                })
            attrs['empresa_id'] = perfil_solicitante.empresa_id
        elif not es_privilegiado and attrs.get('empresa_id') and not puede_ver_empresa(
            request.user, attrs['empresa_id']
        ):
            raise serializers.ValidationError({
                'empresa_id': 'Solo puedes crear usuarios en empresas visibles.'
            })

        return attrs

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Ya existe un usuario con este username.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo electrónico.")
        return value

    def validate_empresa_id(self, value):
        empresa = Empresa.objects.filter(id=value).first()
        if not empresa:
            raise serializers.ValidationError("Empresa no encontrada.")
        return value

    def validate_grupo_id(self, value):
        if value is None:
            return value
        if not GrupoEmpresas.objects.filter(id=value).exists():
            raise serializers.ValidationError('Grupo no encontrado.')
        return value

    def create(self, validated_data):
        empresa_id = validated_data.pop('empresa_id', None)
        grupo_id = validated_data.pop('grupo_id', None)
        foto = validated_data.pop('foto_perfil', None)
        telefono = validated_data.pop('telefono', '')
        domicilio = validated_data.pop('domicilio', '')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        empresa = None
        if empresa_id:
            empresa = Empresa.objects.get(id=empresa_id)
        perfil = Perfil.objects.create(
            user=user,
            rol=validated_data['rol'],
            empresa=empresa,
            grupo_id=grupo_id,
            foto_perfil=foto,
            telefono=telefono,
            domicilio=domicilio,
        )
        return perfil


class SolicitarResetPasswordSerializer(serializers.Serializer):
    motivo = serializers.CharField(required=False, allow_blank=True)


class CambiarMiPasswordSerializer(serializers.Serializer):
    password_actual = serializers.CharField(write_only=True)
    password_nueva = serializers.CharField(write_only=True, min_length=8)

    def validate_password_actual(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return value

    def validate_password_nueva(self, value):
        validate_password(value, self.context['request'].user)
        return value


class SolicitarOlvidePasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ConfirmarOlvidePasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirmacion = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirmacion']:
            raise serializers.ValidationError({
                'password_confirmacion': 'Las contraseñas no coinciden.'
            })

        validate_password(attrs['password'])
        return attrs


class CambiarRolSerializer(serializers.Serializer):
    """Valida el cambio explícito de rol y su alcance empresarial."""

    rol = serializers.ChoiceField(choices=Perfil.ROLE_CHOICES)
    empresa_id = serializers.IntegerField(required=False, allow_null=True)
    grupo_id = serializers.IntegerField(required=False, allow_null=True)
