from django.contrib import admin
from django.utils.html import format_html

from .models import Contacto, Empresa, GrupoEmpresas


@admin.register(GrupoEmpresas)
class GrupoEmpresasAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activo', 'propietario', 'creado_por', 'created_at']
    search_fields = ['nombre', 'descripcion']
    list_filter = ['activo']
    readonly_fields = ['created_at']
    fields = ['nombre', 'descripcion', 'activo', 'propietario', 'creado_por', 'created_at']


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'razon_social', 'tipo_inmueble', 'grupo', 'propietario', 'created_at']
    search_fields = ['nombre', 'razon_social']
    readonly_fields = ['created_at', 'logo_preview']
    fields = ['nombre', 'razon_social', 'tipo_inmueble', 'grupo', 'propietario', 'logo', 'logo_preview', 'created_at']

    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" width="80" />', obj.logo.url)
        return format_html('<span>-</span>')
    logo_preview.short_description = 'Vista previa del logo'


@admin.register(Contacto)
class ContactoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cargo', 'empresa', 'telefono_principal')
    list_filter = ('empresa',)
    search_fields = ('nombre', 'cargo', 'correo_principal', 'telefono_principal')
    autocomplete_fields = ('empresa',)
