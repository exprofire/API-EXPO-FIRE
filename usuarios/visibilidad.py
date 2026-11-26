"""Reglas centrales de visibilidad de empresas por usuario."""


def rol_de(user):
    """Devuelve el rol del perfil o ``None`` para anónimos y usuarios sin perfil."""
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    perfil = getattr(user, 'perfil', None)
    return getattr(perfil, 'rol', None)


def es_superadmin(user):
    """Indica si el usuario es superusuario Django o tiene rol SUPERADMIN."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    from usuarios.models import Perfil

    return bool(
        getattr(user, 'is_superuser', False)
        or rol_de(user) == Perfil.ROLE_SUPERADMIN
    )


def empresas_visibles(user):
    """Devuelve las empresas visibles según rol, grupo o empresa asignada."""
    from empresas.models import Empresa
    from usuarios.models import Perfil

    if not user or not getattr(user, 'is_authenticated', False):
        return Empresa.objects.none()

    if es_superadmin(user):
        return Empresa.objects.all()

    perfil = getattr(user, 'perfil', None)
    rol = rol_de(user)

    if rol == Perfil.ROLE_ADMIN_EXPROFIRE:
        return Empresa.objects.filter(propietario=user)

    if rol == Perfil.ROLE_ADMIN_GRUPO:
        if not perfil or not perfil.grupo_id:
            return Empresa.objects.none()
        return Empresa.objects.filter(grupo_id=perfil.grupo_id)

    if rol in (
        Perfil.ROLE_ADMIN_EMPRESA,
        Perfil.ROLE_SUPERVISOR,
        Perfil.ROLE_ANALISTA,
    ):
        if not perfil or not perfil.empresa_id:
            return Empresa.objects.none()
        return Empresa.objects.filter(id=perfil.empresa_id)

    return Empresa.objects.none()


def ids_empresas_visibles(user):
    """Devuelve como conjunto los IDs de empresas visibles para el usuario."""
    return set(empresas_visibles(user).values_list('id', flat=True))


def puede_ver_empresa(user, empresa_id):
    """Indica si el usuario puede ver la empresa indicada por su ID."""
    if empresa_id in (None, ''):
        return False
    try:
        empresa_id = int(empresa_id)
    except (TypeError, ValueError):
        return False
    return empresa_id in ids_empresas_visibles(user)


def empresa_unica_de(user):
    """Devuelve la empresa única de roles operativos o ``None`` en los demás casos."""
    from usuarios.models import Perfil

    if rol_de(user) not in (
        Perfil.ROLE_ADMIN_EMPRESA,
        Perfil.ROLE_SUPERVISOR,
        Perfil.ROLE_ANALISTA,
    ):
        return None
    perfil = getattr(user, 'perfil', None)
    return getattr(perfil, 'empresa_id', None)
