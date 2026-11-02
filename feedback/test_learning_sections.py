from django.test import TestCase, override_settings
from django.urls import reverse
from .models import KnowledgeBlock, CourseMaterial
from . import test_course_features as fixtures


# Reuse fixtures without duplicating the earlier feature suite.
class LearningSectionTests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp
    upload = fixtures.CourseFeatureTests.upload

    def dashboard(self):
        return self.teacher_client.get(reverse('dashboard', args=[self.lesson.code]))

    def test_three_independent_sections_and_section_uploads_without_modules(self):
        for kind, label in KnowledgeBlock.Kind.choices:
            self.assertEqual(self.upload(section=kind, title=label+'专属资料').status_code, 302)
        self.assertEqual(set(CourseMaterial.objects.values_list('section', flat=True)), set(KnowledgeBlock.Kind.values))
        for client, url in [(self.teacher_client, reverse('dashboard', args=[self.lesson.code])),
                            (self.student_client, self.class_url)]:
            page = client.get(url)
            sections = page.context['content_sections']
            self.assertEqual(len(sections), 3)
            for section in sections:
                self.assertEqual([m.title for m in section['materials']], [section['label']+'专属资料'])
                self.assertContains(page, 'id="section-'+section['kind']+'"', count=1)

    def test_upload_prefills_section_and_module_and_rejects_wrong_section(self):
        block = KnowledgeBlock.objects.create(lesson=self.lesson, kind='difficult', title='难点模块')
        url = reverse('material_upload', args=[self.lesson.code])
        page = self.teacher_client.get(url+f'?section=difficult&block={block.pk}')
        self.assertEqual(page.context['form']['block'].value(), block.pk)
        self.assertEqual(page.context['form']['section'].value(), 'difficult')
        self.assertEqual(self.upload(section='key', block=block.pk).status_code, 200)
        self.assertFalse(CourseMaterial.objects.exists())
        self.assertEqual(self.upload(section='difficult', block=block.pk).status_code, 302)
        self.assertEqual(CourseMaterial.objects.get().block_id, block.pk)
        self.assertEqual(self.teacher_client.get(url+f'?section=key&block={block.pk}').status_code, 404)
        self.assertEqual(self.teacher_client.get(url+'?section=unknown').status_code, 400)
        self.assertEqual(self.teacher_client.get(url+'?section=key&block=oops').status_code, 400)
        self.assertEqual(self.upload(section='unknown').status_code, 400)
        self.assertEqual(self.teacher_client.post(url+'?section=key', {'section':'difficult'}).status_code, 200)

    def test_editing_module_type_moves_attachments_and_delete_retains_section(self):
        block = KnowledgeBlock.objects.create(lesson=self.lesson, kind='key', title='重点')
        self.upload(section='key', block=block.pk)
        self.teacher_client.post(reverse('block_edit', args=[self.lesson.code,block.pk]),
                                 {'kind':'difficult','title':'难点','body':'内容','position':0})
        material = CourseMaterial.objects.get()
        self.assertEqual(material.section, 'difficult')
        sections = self.dashboard().context['content_sections']
        self.assertEqual(sections[2]['blocks'][0]['materials'][0].pk, material.pk)
        self.assertEqual(sections[1]['blocks'], [])
        self.teacher_client.post(reverse('block_delete',args=[self.lesson.code,block.pk]))
        material.refresh_from_db()
        self.assertIsNone(material.block_id)
        self.assertEqual(material.section, 'difficult')
        self.assertEqual(self.dashboard().context['content_sections'][2]['materials'][0].pk, material.pk)

    def test_new_module_prefills_kind_and_local_editor_is_available(self):
        url = reverse('block_create', args=[self.lesson.code])
        page = self.teacher_client.get(url+'?kind=key')
        self.assertEqual(page.context['form']['kind'].value(), 'key')
        self.assertContains(page, 'vendor/mathlive/mathlive.min.js')
        self.assertContains(page, 'formula-editor.js')
        self.assertContains(page, 'data-mathtype-uri=""')
        self.assertNotContains(page, 'wiris.net')
        self.assertContains(self.student_client.get(self.class_url), 'mathlive.min.js')

    @override_settings(MATHTYPE_SERVICE_URI='https://licensed.example.org/plugin/app/', MATHTYPE_SERVICE_SERVER='java')
    def test_optional_mathtype_configuration_uses_public_service_address(self):
        page = self.teacher_client.get(reverse('block_create', args=[self.lesson.code]))
        self.assertContains(page, 'data-mathtype-uri="https://licensed.example.org/plugin/app/"')
        self.assertContains(page, 'data-mathtype-server="java"')
        self.assertContains(page, 'data-mathtype-script="/static/vendor/mathtype/wirisplugin-generic.js"')
