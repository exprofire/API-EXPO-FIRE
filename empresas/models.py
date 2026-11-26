"""

Modelos del dominio empresarial.

"""

from django.db import models
from django.conf import settings



class GrupoEmpresas(models.Model):
    """Agrupa empresas relacionadas sin alterar su operación actual."""

    nombre = models.CharField(max_length=150, unique=True, verbose_name='Nombre')
    descripcion = models.TextField(blank=True, default='', verbose_name='Descripción')
    activo = models.BooleanField(default=True, verbose_name='Activo')
    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grupos_propios',
        verbose_name='Propietario',
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grupos_creados',
        verbose_name='Creado por',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')

    class Meta:
        verbose_name = 'Grupo de empresas'
        verbose_name_plural = 'Grupos de empresas'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Empresa(models.Model):
    # --- Campos existentes ---
    id = models.AutoField(primary_key=True, verbose_name='ID')
    nombre = models.CharField(max_length=150, unique=True, verbose_name='Nombre')
    razon_social = models.CharField(max_length=200, blank=True, verbose_name='Razón Social')
    logo = models.ImageField(upload_to='logos/', blank=True, null=True, verbose_name='Logo')
    tipo_inmueble = models.CharField(max_length=150, blank=True, verbose_name='Tipo de inmueble')
    estatus = models.CharField(
        max_length=20,
        choices=[
            ('VIGENTE', 'Vigente'),
            ('BORRADA', 'Borrada'),
        ],
        default='VIGENTE',
        verbose_name='Estatus',
        help_text='Control visual para ocultar la empresa en el frontend sin eliminarla.',
    )
    activa = models.BooleanField(default=True, verbose_name='Activa')

    grupo = models.ForeignKey(
        'GrupoEmpresas',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='empresas',
        verbose_name='Grupo de empresas',
    )

    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='empresas_propias',
        verbose_name='Propietario',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')

    # --- Relación con el usuario que registra (técnico) ---
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='empresas_creadas',
        verbose_name='Creado por',
        help_text='Usuario (técnico) que registró la empresa'
    )

    # --- Punto 1 y 2 del cuestionario: Metrajes ---
    metros_cuadrados_totales = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Metros cuadrados totales',
        help_text='Metros cuadrados de todo el establecimiento'
    )
    
    perimetro = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Perímetro',
        help_text='Perímetro del establecimiento en metros'
    )

    # --- Punto 4: Estacionamiento ---
    metros_cuadrados_estacionamiento = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Metros cuadrados estacionamiento'
    )
    
    cajones_estacionamiento = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Cajones de estacionamiento'
    )

    # --- Punto 4 del cuestionario: Ubicación física ---
    en_establecimiento = models.BooleanField(
        default=True,
        verbose_name='¿Se encuentra en el establecimiento?',
        help_text='Indica si el técnico está físicamente en el establecimiento'
    )
    
    datos_quien_refiere = models.TextField(
        blank=True,
        verbose_name='Datos de quien refiere al cliente',
        help_text='Completar solo si no se encuentra en el establecimiento'
    )

    # --- Fecha de evaluación ---
    fecha_evaluacion_riesgo = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fecha de evaluación de riesgo'
    )

    # --- Punto 5: Materiales combustibles (campo abierto) ---
    materiales_combustibles = models.TextField(
        blank=True,
        verbose_name='Materiales combustibles',
        help_text='Describir los materiales combustibles presentes: sólidos (kg/ton), líquidos (litros), gases (capacidad), etc.'
    )

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Contacto(models.Model):
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name='contactos',
        verbose_name='Empresa'
    )
    nombre = models.CharField(max_length=180, verbose_name='Nombre del contacto')
    cargo = models.CharField(max_length=150, verbose_name='Cargo')
    correo_principal = models.EmailField(verbose_name='Correo principal')
    correo_secundario = models.EmailField(blank=True, null=True, verbose_name='Correo secundario')
    telefono_principal = models.CharField(max_length=30, verbose_name='Teléfono principal')
    telefono_secundario = models.CharField(max_length=30, blank=True, null=True, verbose_name='Teléfono secundario')
    domicilio = models.CharField(max_length=250, verbose_name='Domicilio')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Fecha de actualización')

    class Meta:
        verbose_name = 'Contacto'
        verbose_name_plural = 'Contactos'
        ordering = ['empresa__nombre', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.cargo})"
