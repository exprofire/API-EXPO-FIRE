"""Lectura, validación y persistencia de cargas masivas de extintores."""

import unicodedata
from datetime import date, datetime
from io import BytesIO

from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from openpyxl import load_workbook

from empresas.models import Empresa
from extintores.models import Extintor
from extintores.serializers import CargaMasivaFilaSerializer


MAX_FILAS = 200
MAX_TAMANO = 5 * 1024 * 1024

COLUMNAS = {
    'codigo': 'Código',
    'ubicacion': 'Ubicación',
    'tipo': 'Agente',
    'modalidad': 'Modalidad',
    'capacidad': 'Capacidad',
    'fecha_fabricacion': 'Fecha de fabricación',
    'ultima_revision': 'Fecha de mantenimiento',
    'fecha_vencimiento': 'Fecha de vencimiento',
    'proxima_revision': 'Próxima revisión',
}

COLUMNAS_OBLIGATORIAS = {
    'codigo',
    'ubicacion',
    'tipo',
    'modalidad',
    'capacidad',
    'ultima_revision',
    'fecha_vencimiento',
    'proxima_revision',
}


def normalizar_encabezado(valor):
    """Compara encabezados ignorando acentos, mayúsculas y espacios."""
    texto = '' if valor is None else str(valor)
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return ' '.join(texto.casefold().strip().split())


def _texto(valor):
    return '' if valor is None else str(valor).strip()


def _es_fila_vacia(valores):
    return all(_texto(valor) == '' for valor in valores)


def _fecha(valor, campo):
    """Convierte fechas de Excel o texto ISO a texto ISO para el serializer."""
    if valor in (None, ''):
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = _texto(valor)
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date().isoformat()
    except ValueError:
        raise ValueError(f'El campo {campo} debe tener formato AAAA-MM-DD o ser una fecha de Excel.')


def _normalizar_modalidad(valor):
    texto = unicodedata.normalize('NFKD', _texto(valor))
    texto = ''.join(caracter for caracter in texto if not unicodedata.combining(caracter))
    equivalencias = {
        'portatil': 'portatil',
        'móvil': 'movil',
        'movil': 'movil',
    }
    clave = texto.strip().lower()
    return equivalencias.get(clave, _texto(valor))


def _normalizar_tipo(valor):
    """Normaliza el agente antes de validarlo contra las choices del modelo."""
    import re

    return re.sub(r'[\s-]+', '_', _texto(valor).upper())


def _normalizar_fila(valores, indices):
    """Mapea una fila de Excel a los nombres internos del modelo."""
    def obtener(campo):
        indice = indices.get(campo)
        return valores[indice] if indice is not None and indice < len(valores) else None

    fila = {
        'codigo': _texto(obtener('codigo')),
        'ubicacion': _texto(obtener('ubicacion')),
        'tipo': _normalizar_tipo(obtener('tipo')),
        'modalidad': _normalizar_modalidad(obtener('modalidad')),
        'capacidad': _texto(obtener('capacidad')),
        'fecha_fabricacion': None,
        'ultima_revision': None,
        'fecha_vencimiento': None,
        'proxima_revision': None,
    }

    for campo in ('fecha_fabricacion', 'ultima_revision', 'fecha_vencimiento', 'proxima_revision'):
        valor = obtener(campo)
        if valor not in (None, ''):
            try:
                fila[campo] = _fecha(valor, COLUMNAS[campo])
            except ValueError:
                # Conserva el texto para producir un único error de formato.
                fila[campo] = _texto(valor)

    return fila


def _error(campo, mensaje):
    return {'campo': campo, 'mensaje': mensaje}


def _agregar_error_unico(errores, campo, mensaje):
    """Agrega un error sin repetir el mismo campo y mensaje."""
    if not any(error['campo'] == campo and error['mensaje'] == mensaje for error in errores):
        errores.append(_error(campo, mensaje))


def _fecha_segura(valor):
    """Convierte un valor normalizado a fecha para validaciones cruzadas."""
    if isinstance(valor, date):
        return valor
    if not valor:
        return None
    try:
        return datetime.strptime(str(valor), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _agregar_errores_obligatorios(datos, errores):
    """Agrega mensajes claros para campos requeridos, aun con otros errores."""
    obligatorios = {
        'codigo': 'Falta el código.',
        'ubicacion': 'Falta la ubicación.',
        'tipo': 'Falta el agente.',
        'modalidad': 'Falta la modalidad.',
        'capacidad': 'Falta la capacidad.',
        'ultima_revision': 'Falta la fecha de mantenimiento.',
        'fecha_vencimiento': 'Falta la fecha de vencimiento.',
        'proxima_revision': 'Falta la próxima revisión.',
    }
    for campo, mensaje in obligatorios.items():
        if datos.get(campo) in (None, ''):
            _agregar_error_unico(errores, campo, mensaje)


def _agregar_errores_coherencia(datos, errores):
    """Reporta coherencia aunque otro campo de la fila tenga errores."""
    mantenimiento = _fecha_segura(datos.get('ultima_revision'))
    vencimiento = _fecha_segura(datos.get('fecha_vencimiento'))
    proxima = _fecha_segura(datos.get('proxima_revision'))
    fabricacion = _fecha_segura(datos.get('fecha_fabricacion'))

    if mantenimiento and vencimiento and vencimiento <= mantenimiento:
        _agregar_error_unico(errores, 'fecha_vencimiento', 'Debe ser posterior a la fecha de mantenimiento.')
    if mantenimiento and proxima and proxima < mantenimiento:
        _agregar_error_unico(errores, 'proxima_revision', 'No puede ser anterior a la fecha de mantenimiento.')
    if fabricacion and fabricacion > date.today():
        _agregar_error_unico(errores, 'fecha_fabricacion', 'No puede ser una fecha futura.')


def _validar_filas_legacy(filas, empresa):
    """Valida filas normalizadas y consulta códigos existentes una sola vez."""
    if len(filas) > MAX_FILAS:
        raise ValueError(f'El archivo no puede contener más de {MAX_FILAS} filas de datos.')

    codigos = [str(fila.get('codigo', '')).strip() for fila in filas if isinstance(fila, dict)]
    existentes = set(
        Extintor.objects.filter(empresa=empresa, codigo__in=codigos)
        .values_list('codigo', flat=True)
    )
    vistos = set()
    validas = []
    con_error = []

    for numero, fila in enumerate(filas, start=1):
        numero_fila = fila.get('_fila_excel', numero) if isinstance(fila, dict) else numero
        datos = dict(fila) if isinstance(fila, dict) else {}
        datos.pop('_errores_preliminares', None)
        datos.pop('_fila_excel', None)
        datos.pop('clase_fuego', None)
        if 'modalidad' in datos:
            datos['modalidad'] = _normalizar_modalidad(datos['modalidad'])
        if 'tipo' in datos:
            datos['tipo'] = _normalizar_tipo(datos['tipo'])
        errores = list(fila.get('_errores_preliminares', [])) if isinstance(fila, dict) else []
        serializer = CargaMasivaFilaSerializer(data=datos)
        if serializer.is_valid():
            datos_validados = dict(serializer.validated_data)
            codigo = datos_validados['codigo']
            codigo_clave = codigo.casefold()
            if codigo_clave in vistos:
                errores.append(_error('codigo', 'El código está repetido dentro del archivo.'))
            elif codigo in existentes:
                errores.append(_error('codigo', 'Ya existe un extintor con este código en la empresa seleccionada.'))
            vistos.add(codigo_clave)
            datos = datos_validados
        else:
            for campo, mensajes in serializer.errors.items():
                for mensaje in mensajes:
                    errores.append(_error(campo, str(mensaje)))

        if errores:
            con_error.append({'fila': numero_fila, 'datos': datos, 'errores': errores})
        else:
            validas.append({'fila': numero_fila, 'datos': datos})

    return validas, con_error


def validar_filas(filas, empresa):
    """Valida todas las reglas de una carga sin detenerse en el primer error."""
    if len(filas) > MAX_FILAS:
        raise ValueError(f'El archivo no puede contener más de {MAX_FILAS} filas de datos.')

    codigos = [str(fila.get('codigo', '')).strip() for fila in filas if isinstance(fila, dict)]
    existentes = set(
        Extintor.objects.filter(empresa=empresa, codigo__in=codigos)
        .values_list('codigo', flat=True)
    )
    vistos = set()
    validas = []
    con_error = []

    for numero, fila in enumerate(filas, start=1):
        numero_fila = fila.get('_fila_excel', numero) if isinstance(fila, dict) else numero
        datos = dict(fila) if isinstance(fila, dict) else {}
        datos.pop('_errores_preliminares', None)
        datos.pop('_fila_excel', None)
        if 'modalidad' in datos:
            datos['modalidad'] = _normalizar_modalidad(datos['modalidad'])
        if 'tipo' in datos:
            datos['tipo'] = _normalizar_tipo(datos['tipo'])

        errores = []
        serializer = CargaMasivaFilaSerializer(data=datos)
        serializer.is_valid()
        datos_salida = dict(datos)
        datos_salida.pop('clase_fuego', None)
        datos_salida.update(serializer.validated_data)

        for campo, mensajes in serializer.errors.items():
            for mensaje in mensajes:
                errores.append(_error(campo, str(mensaje)))

        # Se ejecutan aun cuando otro campo de la misma fila sea inválido.
        _agregar_errores_obligatorios(datos_salida, errores)
        _agregar_errores_coherencia(datos_salida, errores)

        codigo = str(datos_salida.get('codigo') or '').strip()
        if codigo:
            codigo_clave = codigo.casefold()
            if codigo_clave in vistos:
                _agregar_error_unico(errores, 'codigo', 'El código está repetido dentro del archivo.')
            elif codigo in existentes:
                _agregar_error_unico(errores, 'codigo', 'Ya existe un extintor con este código en la empresa seleccionada.')
            vistos.add(codigo_clave)

        if errores:
            con_error.append({'fila': numero_fila, 'datos': datos_salida, 'errores': errores})
        else:
            validas.append({'fila': numero_fila, 'datos': datos_salida})

    return validas, con_error


def leer_y_validar_excel(archivo, empresa):
    """Lee el Excel, localiza encabezados y devuelve filas validadas."""
    nombre = str(getattr(archivo, 'name', '')).casefold()
    if not nombre.endswith('.xlsx'):
        raise ValueError('El archivo debe tener extensión .xlsx.')
    if getattr(archivo, 'size', 0) > MAX_TAMANO:
        raise ValueError('El archivo no puede superar 5 MB.')

    contenido = archivo.read()
    if len(contenido) > MAX_TAMANO:
        raise ValueError('El archivo no puede superar 5 MB.')

    libro = load_workbook(filename=BytesIO(contenido), read_only=True, data_only=True)
    try:
        hoja = libro.active
        encabezados = None
        fila_encabezado = None
        for numero, valores in enumerate(hoja.iter_rows(values_only=True), start=1):
            mapa = {normalizar_encabezado(valor): indice for indice, valor in enumerate(valores)}
            if normalizar_encabezado('Código') in mapa:
                encabezados = mapa
                fila_encabezado = numero
                break

        if encabezados is None:
            raise ValueError('No se encontró una fila de encabezados que contenga la columna Código.')

        indices = {}
        faltantes = []
        for campo, etiqueta in COLUMNAS.items():
            clave = normalizar_encabezado(etiqueta)
            if clave in encabezados:
                indices[campo] = encabezados[clave]
            elif campo in COLUMNAS_OBLIGATORIAS:
                faltantes.append(etiqueta)

        if faltantes:
            raise ValueError(f'Faltan columnas obligatorias: {", ".join(faltantes)}.')

        filas = []
        for numero_fila, valores in enumerate(
            hoja.iter_rows(min_row=fila_encabezado + 1, values_only=True),
            start=fila_encabezado + 1,
        ):
            if _es_fila_vacia(valores):
                continue
            codigo = _texto(valores[indices['codigo']] if indices['codigo'] < len(valores) else '')
            ubicacion = _texto(valores[indices['ubicacion']] if indices['ubicacion'] < len(valores) else '')
            if codigo.casefold() == 'ext-001' and ubicacion.casefold() == 'pasillo principal, planta baja':
                continue
            if codigo.casefold().startswith('código único') or codigo.casefold().startswith('codigo unico'):
                continue
            fila = _normalizar_fila(valores, indices)
            fila['_fila_excel'] = numero_fila
            filas.append(fila)

        if len(filas) > MAX_FILAS:
            raise ValueError(f'El archivo no puede contener más de {MAX_FILAS} filas de datos.')
        return validar_filas(filas, empresa)
    finally:
        libro.close()


def guardar_filas(validas, empresa, usuario):
    """Guarda cada extintor con save() y limpia QR si falla la operación."""
    creados = []
    nombres_qr = set()
    try:
        with transaction.atomic():
            for elemento in validas:
                datos = dict(elemento.get('datos', elemento))
                extintor = Extintor(
                    empresa=empresa,
                    creado_por=usuario,
                    **datos,
                )
                try:
                    extintor.save()
                except Exception:
                    if extintor.qr_code and extintor.qr_code.name:
                        nombres_qr.add(extintor.qr_code.name)
                    raise
                if extintor.qr_code and extintor.qr_code.name:
                    nombres_qr.add(extintor.qr_code.name)
                creados.append(extintor)
    except Exception:
        for nombre in nombres_qr:
            try:
                default_storage.delete(nombre)
            except Exception:
                pass
        raise

    return creados

