import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Lead
from .serializers import LeadCreateSerializer, LeadSerializer
from core.brevo import send_brevo_transactional_email


TURNSTILE_SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
logger = logging.getLogger(__name__)


class LeadCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LeadCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        captcha_result = self._verify_turnstile(
            serializer.validated_data['captchaToken'],
            self._get_client_ip(request),
        )
        if not captcha_result.get('success'):
            return Response(
                {
                    'detail': 'Captcha inválido.',
                    'captcha_errors': captcha_result.get('error-codes', []),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lead = Lead.objects.create(
            nombre=serializer.validated_data['nombre'],
            empresa=serializer.validated_data['empresa'],
            correo=serializer.validated_data['correo'],
            telefono=serializer.validated_data['telefono'],
            servicio=serializer.validated_data['servicio'],
            mensaje=serializer.validated_data.get('mensaje', ''),
            captcha_success=True,
            captcha_challenge_ts=self._parse_turnstile_datetime(captcha_result.get('challenge_ts')),
            captcha_hostname=captcha_result.get('hostname', ''),
            captcha_action=captcha_result.get('action', ''),
            captcha_cdata=captcha_result.get('cdata', ''),
        )
        self._send_lead_email(lead)

        return Response(
            {
                'detail': 'Lead recibido correctamente.',
                'lead': LeadSerializer(lead).data,
                'email_enviado': lead.email_enviado,
                'email_error': lead.email_error or None,
            },
            status=status.HTTP_201_CREATED,
        )

    def _verify_turnstile(self, token, remote_ip=None):
        secret = getattr(settings, 'TURNSTILE_SECRET_KEY', '')
        logger.warning(
            'Turnstile configurado=%s longitud=%s',
            bool(secret),
            len(secret),
        )
        if not secret:
            return {'success': False, 'error-codes': ['missing-secret-key']}

        payload = {
            'secret': secret,
            'response': token,
        }
        if remote_ip:
            payload['remoteip'] = remote_ip

        data = urlencode(payload).encode('utf-8')
        request = Request(
            TURNSTILE_SITEVERIFY_URL,
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )

        try:
            with urlopen(request, timeout=8) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
            logger.error(
                'Cloudflare rechazó siteverify con HTTP %s: %s',
                exc.code,
                body,
            )
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {'success': False, 'error-codes': ['siteverify-http-error']}
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.exception('Error verificando Turnstile con Cloudflare: %s', exc)
            return {'success': False, 'error-codes': ['siteverify-unavailable']}

    def _get_client_ip(self, request):
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    def _parse_turnstile_datetime(self, value):
        if not value:
            return None
        return parse_datetime(value)
    
    def _send_lead_email(self, lead):
        recipients = getattr(settings, 'LEADS_TO_EMAIL', [])
        if not recipients:
            lead.email_error = 'No se configuró LEADS_TO_EMAIL.'
            lead.save(update_fields=['email_error'])
            return

        if isinstance(recipients, str):
            recipients = [email.strip() for email in recipients.split(',') if email.strip()]

        result = send_brevo_transactional_email(
            to_emails=recipients,
            subject=f'Nuevo lead: {lead.nombre} - {lead.empresa}',
            text_content=(
                f'Nombre: {lead.nombre}; Empresa: {lead.empresa}; Correo: {lead.correo}; '
                f'Telefono: {lead.telefono}; Servicio: {lead.servicio}; Mensaje: {lead.mensaje}'
            ),
        )

        lead.email_enviado = bool(result['ok'])
        lead.email_enviado_at = timezone.now() if lead.email_enviado else None
        lead.email_error = '' if lead.email_enviado else (result['error'] or 'Error enviando correo con Brevo API.')

        lead.save(update_fields=['email_enviado', 'email_enviado_at', 'email_error'])
