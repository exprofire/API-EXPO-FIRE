from rest_framework import serializers

from .models import Empresa, Contacto, GrupoEmpresas
from usuarios.models import Perfil


class ContactoSerializer(serializers.ModelSerializer):
    """Serializer para los contactos de la empresa"""

    class Meta:
        model = Contacto
        fields = [
            'id',
            'empresa_id',
            'nombre',
            'cargo',
            'correo_principal',
            'correo_secundario',
            'telefono_principal',
            'telefono_secundario',
            'domicilio',
            'created_at',
        ]
        read_only_fields = ['id', 'empresa_id', 'created_at']


class ContactoCreacionSerializer(serializers.ModelSerializer):
    """Serializer auxiliar para crear contactos desde empresas."""

    class Meta:
        model = Contacto
        fields = [
            'nombre',
            'cargo',
            'correo_principal',
            'correo_secundario',
            'telefono_principal',
            'telefono_secundario',
            'domicilio',
        ]


class EmpresaSerializer(serializers.ModelSerializer):
    """Serializer principal para empresas."""

    creado_por_nombre = serializers.SerializerMethodField()
    creado_por_email = serializers.EmailField(source='creado_por.email', read_only=True)
    creado_por_rol = serializers.SerializerMethodField()
    grupo_id = serializers.IntegerField(read_only=True)
    grupo_nombre = serializers.SerializerMethodField()
    propietario_id = serializers.IntegerField(read_only=True)
    propietario_nombre = serializers.SerializerMethodField()
    contactos = ContactoSerializer(many=True, read_only=True)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        fields = [
            'id',
            'nombre',
            'razon_social',
            'logo',
            'logo_url',
            'tipo_inmueble',
            'estatus',
            'activa',
            'created_at',
            'creado_por',
            'creado_por_nombre',
            'creado_por_email',
            'creado_por_rol',
            'grupo_id',
            'grupo_nombre',
            'propietario_id',
            'propietario_nombre',
            'metros_cuadrados_totales',
            'perimetro',
            'metros_cuadrados_estacionamiento',
            'cajones_estacionamiento',
            'en_establecimiento',
            'datos_quien_refiere',
            'fecha_evaluacion_riesgo',
            'materiales_combustibles',
            'contactos',
        ]
        read_only_fields = ['id', 'created_at', 'creado_por']

    def get_creado_por_nombre(self, obj):
        if obj.creado_por:
            perfil = getattr(obj.creado_por, 'perfil', None)
            if perfil and perfil.nombre_completo:
                return perfil.nombre_completo
            return obj.creado_por.get_full_name() or obj.creado_por.username
        return None

    def get_creado_por_rol(self, obj):
        if obj.creado_por:
            perfil = getattr(obj.creado_por, 'perfil', None)
            if perfil:
                return {
                    'codigo': perfil.rol,
                    'nombre': perfil.get_rol_display(),
                }
        return None

    def get_grupo_nombre(self, obj):
        """Devuelve el nombre del grupo, o ``None`` si no está agrupada."""
        return obj.grupo.nombre if obj.grupo else None

    def get_propietario_nombre(self, obj):
        """Devuelve el nombre completo o username del propietario."""
        if not obj.propietario:
            return None
        return obj.propietario.get_full_name() or obj.propietario.username

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.logo.url)
        return obj.logo.url


class EmpresaCreacionSerializer(serializers.ModelSerializer):
    """Serializer especial para crear empresa con contactos iniciales"""

    logo_empresa = serializers.ImageField(source='logo', required=False, allow_null=True, write_only=True)
    contactos = serializers.JSONField(write_only=True, required=False, default=list)

    class Meta:
        model = Empresa
        fields = [
            'nombre',
            'razon_social',
            'logo',
            'logo_empresa',
            'tipo_inmueble',
            'estatus',
            'activa',
            'creado_por',
            'metros_cuadrados_totales',
            'perimetro',
            'metros_cuadrados_estacionamiento',
            'cajones_estacionamiento',
            'en_establecimiento',
            'datos_quien_refiere',
            'fecha_evaluacion_riesgo',
            'materiales_combustibles',
            'contactos',
        ]
        read_only_fields = ['creado_por']

    def create(self, validated_data):
        contactos_data = validated_data.pop('contactos', [])

        if isinstance(contactos_data, str):
            try:
                import json
                contactos_data = json.loads(contactos_data) or []
            except Exception:
                raise serializers.ValidationError({
                    'contactos': 'Debe enviarse como una lista JSON valida.'
                })

        if contactos_data in (None, ''):
            contactos_data = []

        if not isinstance(contactos_data, list):
            raise serializers.ValidationError({
                'contactos': 'Debe ser una lista de contactos.'
            })

        empresa = Empresa.objects.create(**validated_data)

        for contacto_data in contactos_data:
            contacto_serializer = ContactoCreacionSerializer(data=contacto_data)
            contacto_serializer.is_valid(raise_exception=True)
            Contacto.objects.create(
                empresa=empresa,
                **contacto_serializer.validated_data,
            )

        return empresa


class EmpresaResumenSerializer(serializers.Serializer):
    """Serializer para el resumen de empresas"""

    total = serializers.IntegerField()
    activas = serializers.IntegerField()
    inactivas = serializers.IntegerField()
    registros_por_tecnico = serializers.ListField(
        child=serializers.DictField(),
        required=False,
    )


class GrupoEmpresasSerializer(serializers.ModelSerializer):
    """Serializer de lectura y escritura para grupos de empresas."""

    class Meta:
        model = GrupoEmpresas
        fields = [
            'id',
            'nombre',
            'descripcion',
            'activo',
            'propietario',
            'creado_por',
            'created_at',
        ]
        read_only_fields = ['id', 'propietario', 'creado_por', 'created_at']


class AsignacionPropietarioSerializer(serializers.Serializer):
    """Valida las solicitudes nuevas de asignación de propietarios."""

    propietario_id = serializers.IntegerField()
    criterios = serializers.DictField()
    modo = serializers.ChoiceField(choices=['simular', 'aplicar'], default='simular')
    sobrescribir = serializers.BooleanField(default=False)


class TransferenciaCarteraSerializer(serializers.Serializer):
    """Valida la transferencia de empresas y grupos entre propietarios."""

    nuevo_propietario_id = serializers.IntegerField()
    incluir_grupos = serializers.BooleanField(default=False)
    desactivar_usuario = serializers.BooleanField(default=False)
    modo = serializers.ChoiceField(choices=['simular', 'aplicar'], default='simular')
