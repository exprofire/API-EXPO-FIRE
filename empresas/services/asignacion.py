"""Servicios para asignar empresas a propietarios."""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from empresas.models import Empresa, GrupoEmpresas
from usuarios.models import Perfil


logger = logging.getLogger(__name__)
User = get_user_model()


CRITERIOS_VALIDOS = {
    'ids',
    'nombre_contiene',
    'grupo_id',
    'sin_propietario',
    'propietario_actual_id',
    'creado_por_id',
    'tipo_inmueble',
    'estatus',
    'activa',
    'todas',
}


def validar_propietario(propietario_id):
    """Devuelve un ADMIN_EXPROFIRE activo o lanza ValueError."""
    propietario = User.objects.filter(
        pk=propietario_id,
        is_active=True,
        perfil__rol=Perfil.ROLE_ADMIN_EXPROFIRE,
    ).first()
    if not propietario:
        raise ValueError('El propietario debe ser un usuario activo ADMIN_EXPROFIRE.')
    return propietario


def _construir_queryset(criterios):
    if not isinstance(criterios, dict):
        raise ValueError('criterios debe ser un objeto.')

    desconocidos = set(criterios) - CRITERIOS_VALIDOS
    if desconocidos:
        raise ValueError('Criterios no soportados: ' + ', '.join(sorted(desconocidos)))

    todas = criterios.get('todas') is True
    filtros = {clave: valor for clave, valor in criterios.items() if clave != 'todas'}
    filtros_reales = {
        clave: valor for clave, valor in filtros.items()
        if valor not in (None, '', [], {})
    }
    if not todas and not filtros_reales:
        raise ValueError('Debe indicar al menos un criterio o todas=true.')

    queryset = Empresa.objects.all()
    if todas:
        return queryset
    if 'ids' in filtros_reales:
        if not isinstance(filtros_reales['ids'], list):
            raise ValueError('ids debe ser una lista.')
        queryset = queryset.filter(id__in=filtros_reales['ids'])
    if 'nombre_contiene' in filtros_reales:
        queryset = queryset.filter(nombre__icontains=filtros_reales['nombre_contiene'])
    if 'grupo_id' in filtros_reales:
        queryset = queryset.filter(grupo_id=filtros_reales['grupo_id'])
    if 'sin_propietario' in filtros_reales:
        queryset = queryset.filter(
            propietario__isnull=(filtros_reales['sin_propietario'] is True)
        )
    if 'propietario_actual_id' in filtros_reales:
        queryset = queryset.filter(propietario_id=filtros_reales['propietario_actual_id'])
    if 'creado_por_id' in filtros_reales:
        queryset = queryset.filter(creado_por_id=filtros_reales['creado_por_id'])
    if 'tipo_inmueble' in filtros_reales:
        queryset = queryset.filter(tipo_inmueble=filtros_reales['tipo_inmueble'])
    if 'estatus' in filtros_reales:
        queryset = queryset.filter(estatus=filtros_reales['estatus'])
    if 'activa' in filtros_reales:
        queryset = queryset.filter(activa=filtros_reales['activa'])
    return queryset


def asignar_empresas(propietario_id, criterios, modo='simular', sobrescribir=False, usuario=None):
    """Simula o aplica una asignación de empresas en una sola operación."""
    if modo not in ('simular', 'aplicar'):
        raise ValueError('modo debe ser simular o aplicar.')

    propietario = validar_propietario(propietario_id)
    queryset = _construir_queryset(criterios).order_by('id')
    empresas = list(queryset)
    asignables = []
    omitidas = []

    for empresa in empresas:
        if (
            not sobrescribir
            and empresa.propietario_id
            and empresa.propietario_id != propietario.id
        ):
            omitidas.append({
                'id': empresa.id,
                'nombre': empresa.nombre,
                'motivo': 'La empresa ya tiene otro propietario.',
            })
            continue
        asignables.append(empresa)

    resultado = {
        'modo': modo,
        'total_coinciden': len(empresas),
        'asignadas': len(asignables),
        'omitidas': omitidas,
        'empresas': [
            {
                'id': empresa.id,
                'nombre': empresa.nombre,
                'propietario_anterior_id': empresa.propietario_id,
            }
            for empresa in asignables
        ],
    }

    if modo == 'aplicar':
        with transaction.atomic():
            for empresa in asignables:
                empresa.propietario = propietario
                empresa.save(update_fields=['propietario'])

    logger.info(
        'Asignación de propietarios: usuario=%s propietario=%s criterios=%s '
        'modo=%s sobrescribir=%s cantidad=%s ids=%s',
        getattr(usuario, 'id', None), propietario.id, criterios, modo,
        sobrescribir, len(asignables), [empresa.id for empresa in asignables],
    )
    return resultado


def transferir_cartera(
    propietario_actual_id,
    nuevo_propietario_id,
    incluir_grupos=False,
    desactivar_usuario=False,
    modo='simular',
    usuario=None,
):
    """Transfiere empresas y, opcionalmente, grupos de un administrador."""
    actual = User.objects.filter(
        pk=propietario_actual_id,
        perfil__rol=Perfil.ROLE_ADMIN_EXPROFIRE,
    ).first()
    if not actual:
        raise ValueError('El propietario actual debe ser ADMIN_EXPROFIRE.')
    nuevo = validar_propietario(nuevo_propietario_id)
    if actual.id == nuevo.id:
        raise ValueError('El propietario nuevo debe ser distinto al actual.')

    criterios = {'propietario_actual_id': actual.id}
    if modo == 'aplicar':
        with transaction.atomic():
            resultado_empresas = asignar_empresas(
                propietario_id=nuevo.id,
                criterios=criterios,
                modo='aplicar',
                sobrescribir=True,
                usuario=usuario,
            )
            grupos = list(GrupoEmpresas.objects.filter(propietario=actual).order_by('id'))
            grupos_resultado = [
                {
                    'id': grupo.id,
                    'nombre': grupo.nombre,
                    'propietario_anterior_id': grupo.propietario_id,
                }
                for grupo in grupos
            ]
            if incluir_grupos:
                GrupoEmpresas.objects.filter(propietario=actual).update(propietario=nuevo)
            if desactivar_usuario:
                actual.is_active = False
                actual.save(update_fields=['is_active'])
    else:
        resultado_empresas = asignar_empresas(
            propietario_id=nuevo.id,
            criterios=criterios,
            modo='simular',
            sobrescribir=True,
            usuario=usuario,
        )
        grupos = list(GrupoEmpresas.objects.filter(propietario=actual).order_by('id'))
        grupos_resultado = [
            {
                'id': grupo.id,
                'nombre': grupo.nombre,
                'propietario_anterior_id': grupo.propietario_id,
            }
            for grupo in grupos
        ]

    resultado_empresas['grupos'] = grupos_resultado if incluir_grupos else []
    resultado_empresas['grupos_asignados'] = len(grupos) if incluir_grupos else 0
    resultado_empresas['usuario_desactivado'] = bool(desactivar_usuario and modo == 'aplicar')
    return resultado_empresas
