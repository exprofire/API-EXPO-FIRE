from datetime import date, timedelta
from unittest.mock import patch

from django.test import override_settings
from django.test import TestCase
from rest_framework.test import APIClient

from empresas.models import Empresa
from extintores.models import Extintor, RevisionExtintor


class RevisionExtintorTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.empresa = Empresa.objects.create(nombre='Empresa Prueba')
        hoy = date.today()
        self.extintor = Extintor.objects.create(
            codigo='EXT-001',
            ubicacion='Almacén',
            tipo='CO2',
            capacidad='5 kg',
            fecha_vencimiento=hoy + timedelta(days=365),
            proxima_revision=hoy + timedelta(days=180),
            empresa=self.empresa,
        )

    @override_settings(UIPC_PDF_RECIPIENTS=[])
    def test_crea_revision_desde_payload(self):
        payload = {
            'tipo_servicio': 'uipc',
            'scope_type': 'extintor',
            'scope_id': str(self.extintor.id),
            'estado': 'completado',
            'respuestas_json': {
                'fecha_proxima': True,
                'accesible': True,
                'lugar_asignado': True,
                'señalizacion': True,
                'manometro': True,
                'pasador': True,
                'cuerpo': True,
                'precinto': True,
                'etiqueta': True,
                'manguera': True,
                'observaciones': '',
            },
            'observaciones_por_item': {},
        }

        response = self.client.post(
            f'/extintores/{self.extintor.id}/revisiones/',
            payload,
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(RevisionExtintor.objects.count(), 1)

        revision = RevisionExtintor.objects.first()
        self.assertEqual(revision.extintor_id, self.extintor.id)
        self.assertEqual(revision.empresa_id, self.empresa.id)
        self.assertIsNone(revision.tecnico)
        self.assertEqual(revision.payload_json['tipo_servicio'], 'uipc')
        self.assertEqual(revision.payload_json['scope_id'], str(self.extintor.id))
        self.assertTrue(revision.pdf_uipc)
        self.assertTrue(revision.pdf_uipc.name.endswith('.pdf'))

        self.extintor.refresh_from_db()
        expected_next = self.extintor._sumar_meses(date.today(), 1)
        self.assertEqual(self.extintor.ultima_revision, date.today())
        self.assertEqual(self.extintor.proxima_revision, expected_next)

    @override_settings(
        UIPC_PDF_RECIPIENTS=['destino@example.com'],
        BREVO_SENDER_EMAIL='exprofirextintores@gmail.com',
        BREVO_SENDER_NAME='Expro Fire',
    )
    @patch('extintores.views.send_brevo_transactional_email')
    def test_envia_revision_por_brevo_con_pdf(self, send_email):
        send_email.return_value = {
            'ok': True,
            'status_code': 201,
            'data': {'messageId': '<test-message>'},
            'error': None,
        }
        response = self.client.post(
            f'/extintores/{self.extintor.id}/revisiones/',
            {
                'tipo_servicio': 'uipc',
                'estado': 'completado',
                'respuestas_json': {},
                'observaciones_por_item': {},
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['correo_pdf']['enviado'])
        send_email.assert_called_once()
        call = send_email.call_args.kwargs
        self.assertEqual(call['to_emails'], ['destino@example.com'])
        self.assertEqual(call['attachments'][0]['name'].endswith('.pdf'), True)
        self.assertTrue(call['attachments'][0]['content'])
