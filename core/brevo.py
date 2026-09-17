import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


BREVO_TRANSAC_EMAIL_URL = 'https://api.brevo.com/v3/smtp/email'


def send_brevo_transactional_email(
    *,
    to_email=None,
    to_emails=None,
    subject,
    text_content,
    sender_email=None,
    sender_name=None,
    html_content=None,
    reply_to=None,
    tags=None,
    params=None,
    attachments=None,
    timeout=10,
):
    """
    Sends a transactional email through Brevo's HTTPS API.

    Returns a dict with:
        - ok: bool
        - status_code: int | None
        - data: dict | None
        - error: str | None
    """
    api_key = getattr(settings, 'BREVO_API_KEY', '').strip()
    if not api_key:
        return {
            'ok': False,
            'status_code': None,
            'data': None,
            'error': 'BREVO_API_KEY no está configurada.',
        }

    sender_email = (sender_email or getattr(settings, 'BREVO_SENDER_EMAIL', '')).strip()
    sender_name = (sender_name or getattr(settings, 'BREVO_SENDER_NAME', '')).strip()
    if not sender_email:
        return {
            'ok': False,
            'status_code': None,
            'data': None,
            'error': 'BREVO_SENDER_EMAIL no está configurada.',
        }

    recipients = []
    if to_emails:
        recipients = [
            {'email': email}
            for email in to_emails
            if email
        ]
    elif to_email:
        recipients = [{'email': to_email}]

    if not recipients:
        return {
            'ok': False,
            'status_code': None,
            'data': None,
            'error': 'No se proporcionó ningún destinatario.',
        }

    payload = {
        'sender': {
            'email': sender_email,
        },
        'to': recipients,
        'subject': subject,
        'textContent': text_content,
    }

    if sender_name:
        payload['sender']['name'] = sender_name
    if html_content:
        payload['htmlContent'] = html_content
    if reply_to:
        payload['replyTo'] = {'email': reply_to}
    if tags:
        payload['tags'] = list(tags)
    if params:
        payload['params'] = params
    if attachments:
        payload['attachment'] = [
            {
                'name': attachment['name'],
                'content': base64.b64encode(attachment['content']).decode('ascii'),
            }
            for attachment in attachments
        ]

    request = Request(
        BREVO_TRANSAC_EMAIL_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'accept': 'application/json',
            'api-key': api_key,
            'content-type': 'application/json',
        },
        method='POST',
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
            data = json.loads(raw) if raw else {}
            return {
                'ok': True,
                'status_code': response.status,
                'data': data,
                'error': None,
            }
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore') if exc.fp else ''
        return {
            'ok': False,
            'status_code': exc.code,
            'data': _safe_json_loads(body),
            'error': body or str(exc),
        }
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            'ok': False,
            'status_code': None,
            'data': None,
            'error': str(exc),
        }


def _safe_json_loads(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {'raw': value}
