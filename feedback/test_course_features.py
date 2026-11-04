import csv
import io
from pathlib import Path
import tarfile
import tempfile
import zipfile
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image
from .models import AccountProfile, Lesson, Response, ResponseEvent, KnowledgeBlock, CourseMaterial, TeacherReply


def picture():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(output, format="PNG")
    return SimpleUploadedFile("知识点.png", output.getvalue(), content_type="image/png")


class CourseFeatureTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        setting = override_settings(MEDIA_ROOT=Path(self.temp.name) / "media")
        setting.enable()
        self.addCleanup(setting.disable)
        self.teacher = get_user_model().objects.create_user("任老师")
        self.other = get_user_model().objects.create_user("其他老师")
        self.student = get_user_model().objects.create_user("张小明")
        self.peer = get_user_model().objects.create_user("其他学生")
        for user, role in [(self.teacher, "teacher"), (self.other, "teacher"), (self.student, "student"), (self.peer, "student")]:
            AccountProfile.objects.create(user=user, role=role)
        self.lesson = Lesson.objects.create(teacher=self.teacher, course="统计学", title="均值与方差")
        self.other_lesson = Lesson.objects.create(teacher=self.other, title="另一课堂")
        self.teacher_client, self.student_client, self.peer_client, self.other_client = Client(), Client(), Client(), Client()
        for client, user in [(self.teacher_client,self.teacher), (self.student_client,self.student), (self.peer_client,self.peer), (self.other_client,self.other)]:
            client.force_login(user)
        self.class_url = reverse("student", args=[self.lesson.code])

    def feedback(self, **fields):
        return self.student_client.post(self.class_url, {"status": "red", "note": "方差的公式不明白", "real_name": "张小明", "student_number": "00123", **fields})

    def upload(self, file=None, **extra):
        return self.teacher_client.post(reverse("material_upload", args=[self.lesson.code]), {"title": "测试资料", "file": file or picture(), **extra})

    def reply(self, text="可以先计算偏差。", client=None, **extra):
        response = Response.objects.get(lesson=self.lesson, user=self.student)
        return (client or self.teacher_client).post(reverse("reply_create", args=[self.lesson.code,response.pk]), {"message":text, **extra})

    def test_chinese_username_registration_and_login(self):
        password = "Learning!Name-2846"
        result = self.client.post(reverse("register_student"), {"username": "王𠮷同学", "password1":password, "password2":password})
        self.assertRedirects(result, reverse("student_home"))
        self.client.logout()
        self.assertRedirects(self.client.post(reverse("login"), {"username":"王𠮷同学","password":password}), reverse("student_home"))
        self.assertContains(self.client.get(reverse("home")), "课程学习")
        self.assertNotContains(self.client.get(reverse("home")), "高等数学")

    def test_identity_is_required_saved_and_visible_only_to_teacher(self):
        self.assertEqual(self.feedback(real_name="").status_code,400)
        self.assertFalse(Response.objects.exists())
        self.feedback()
        response=Response.objects.get()
        self.assertEqual((response.real_name,response.student_number),("张小明","00123"))
        self.assertEqual(ResponseEvent.objects.get().student_number,"00123")
        profile=AccountProfile.objects.get(user=self.student)
        self.assertEqual(profile.real_name,"张小明")
        data=self.teacher_client.get(reverse("lesson_stats",args=[self.lesson.code])).json()
        self.assertEqual(data["notes"][0]["student_number"],"00123")
        self.peer_client.get(self.class_url)
        self.assertNotContains(self.peer_client.get(self.class_url),"00123")

    def test_identity_snapshot_in_history_and_csv_is_safe(self):
        self.feedback(real_name="=SUM(1)")
        self.feedback(real_name="张小明",student_number="00999")
        self.assertEqual(ResponseEvent.objects.order_by("pk").first().student_number,"00123")
        data=self.teacher_client.get(reverse("export_csv",args=[self.lesson.code])+"?history=1").content.decode("utf-8-sig")
        rows=list(csv.reader(io.StringIO(data)))
        self.assertEqual(rows[1][-2],"'=SUM(1)")
        self.assertEqual(rows[2][-1],"00999")

    def test_modules_all_types_and_latex_are_persisted_and_escaped(self):
        for kind in ["knowledge","key","difficult"]:
            result=self.teacher_client.post(reverse("block_create",args=[self.lesson.code]), {"kind":kind,"title":"模块"+kind,"body":r"\(\frac{a}{b}\) <script>x</script>","position":0})
            self.assertEqual(result.status_code,302)
        self.assertEqual(self.lesson.blocks.count(),3)
        self.student_client.get(self.class_url)
        page=self.student_client.get(self.class_url)
        self.assertContains(page,r"\(\frac{a}{b}\)",count=3)
        self.assertNotContains(page,"<script>x</script>")
        self.assertContains(page,"vendor/katex/katex.min.js")

    def test_other_roles_cannot_change_course_content(self):
        for client in [self.student_client,self.other_client]:
            expected=403 if client==self.student_client else 404
            self.assertEqual(client.post(reverse("block_create",args=[self.lesson.code]),{}).status_code,expected)
            self.assertEqual(client.post(reverse("material_upload",args=[self.lesson.code]),{}).status_code,expected)
        self.assertEqual(self.other_client.get(self.class_url).status_code,404)

    def test_image_private_download_and_persistence(self):
        self.assertEqual(self.upload().status_code,302)
        material=CourseMaterial.objects.get()
        self.assertTrue(material.is_image)
        self.assertTrue(Path(material.file.path).exists())
        url=reverse("material_file",args=[material.pk])
        self.assertEqual(self.client.get(url).status_code,302)
        self.assertEqual(self.peer_client.get(url).status_code,404)
        self.assertEqual(self.other_client.get(url).status_code,404)
        self.student_client.get(self.class_url)
        result=self.student_client.get(url)
        self.assertEqual(result["Content-Type"],"image/png")
        self.assertTrue(b"".join(result.streaming_content).startswith(b"\x89PNG"))
        result.close()

    def test_pdf_and_pptx_basic_formats(self):
        pdf=SimpleUploadedFile("课件.pdf",b"%PDF-1.7\nfixture",content_type="application/pdf")
        self.assertEqual(self.upload(pdf).status_code,302)
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w") as z:
            z.writestr("[Content_Types].xml","<Types/>")
            z.writestr("ppt/presentation.xml","<presentation/>")
        self.assertEqual(self.upload(SimpleUploadedFile("课件.pptx",buf.getvalue())).status_code,302)
        material=CourseMaterial.objects.get(original_name="课件.pdf")
        result=self.teacher_client.get(reverse("material_file",args=[material.pk]))
        self.assertIn("attachment",result["Content-Disposition"])
        result.close()

    def test_invalid_active_or_oversized_files_are_rejected(self):
        files=[SimpleUploadedFile("x.svg",b"<svg/>",content_type="image/svg+xml"),
               SimpleUploadedFile("x.png",b"<html>not an image</html>"),
               SimpleUploadedFile("x.pdf",b"not a pdf"),
               SimpleUploadedFile("x.ppt",b"not an ole file"),
               SimpleUploadedFile("x.pptx",b"not a zip"),
               SimpleUploadedFile("x.pdf",b"%PDF-"+b"0"*(25*1024*1024))]
        for file in files:
            with self.subTest(name=file.name):
                self.assertEqual(self.upload(file).status_code,200)
                self.assertFalse(CourseMaterial.objects.exists())

    def test_upload_cannot_reference_another_class_module(self):
        block=KnowledgeBlock.objects.create(lesson=self.other_lesson,title="私有模块")
        self.assertEqual(self.upload(block=block.pk).status_code,200)
        self.assertFalse(CourseMaterial.objects.exists())

    def test_deleted_module_retains_material(self):
        block=KnowledgeBlock.objects.create(lesson=self.lesson,title="知识点")
        self.upload(block=block.pk)
        self.teacher_client.post(reverse("block_delete",args=[self.lesson.code,block.pk]))
        material=CourseMaterial.objects.get()
        self.assertIsNone(material.block_id)
        self.assertTrue(Path(material.file.path).exists())

    def test_deleted_material_is_not_downloadable(self):
        self.upload()
        material=CourseMaterial.objects.get()
        self.teacher_client.post(reverse("material_delete",args=[self.lesson.code,material.pk]))
        self.assertEqual(self.teacher_client.get(reverse("material_file",args=[material.pk])).status_code,404)
        self.assertTrue(Path(material.file.path).exists())

    def test_class_delete_restore_preserves_data_and_revokes_access(self):
        self.feedback();self.upload();self.reply()
        url=reverse("lesson_delete",args=[self.lesson.code])
        self.assertEqual(self.teacher_client.get(url).status_code,200)
        self.assertIsNone(Lesson.objects.get(pk=self.lesson.pk).deleted_at)
        self.assertEqual(self.other_client.post(url,{"confirm":"yes"}).status_code,404)
        self.assertEqual(self.student_client.post(url,{"confirm":"yes"}).status_code,403)
        self.teacher_client.post(url,{"confirm":"yes"})
        self.assertEqual(self.student_client.get(self.class_url).status_code,404)
        self.assertEqual(self.teacher_client.get(reverse("dashboard",args=[self.lesson.code])).status_code,404)
        self.assertEqual(self.student_client.get(reverse("student_notifications")).json()["count"],0)
        self.assertNotContains(self.teacher_client.get(reverse("teacher_home")),"均值与方差")
        self.assertEqual((Response.objects.count(),CourseMaterial.objects.count(),TeacherReply.objects.count()),(1,1,1))
        self.teacher_client.post(reverse("lesson_restore",args=[self.lesson.code]))
        self.lesson.refresh_from_db();self.assertIsNone(self.lesson.deleted_at);self.assertFalse(self.lesson.is_open)
        self.assertContains(self.student_client.get(self.class_url),"可以先计算偏差")

    def test_delete_is_csrf_protected(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.teacher)
        self.assertEqual(client.post(reverse("lesson_delete",args=[self.lesson.code]),{"confirm":"yes"}).status_code,403)

    def test_private_replies_notifications_and_read_tracking(self):
        self.feedback();self.reply(text=r"请看 \(E(X)\)")
        url=reverse("student_updates",args=[self.lesson.code])
        data=self.student_client.get(url).json()
        self.assertEqual(data["replies"][0]["message"],r"请看 \(E(X)\)")
        self.assertEqual(self.student_client.get(reverse("student_notifications")).json()["count"],1)
        self.assertEqual(self.peer_client.get(url).status_code,404)
        self.peer_client.get(self.class_url)
        self.assertEqual(self.peer_client.get(url).json()["replies"],[])
        pk=TeacherReply.objects.get().pk
        self.peer_client.post(reverse("replies_read",args=[self.lesson.code]),{"up_to":pk})
        self.assertIsNone(TeacherReply.objects.get().student_read_at)
        self.student_client.post(reverse("replies_read",args=[self.lesson.code]),{"up_to":pk})
        self.assertIsNotNone(TeacherReply.objects.get().student_read_at)
        self.assertEqual(self.student_client.get(reverse("student_notifications")).json()["count"],0)

    def test_reply_permissions_and_question_version(self):
        self.feedback(note="第一个问题")
        event=ResponseEvent.objects.get()
        self.feedback(note="新的问题")
        self.assertEqual(self.reply(event_id=event.pk).status_code,302)
        self.assertEqual(TeacherReply.objects.get().question_text,"第一个问题")
        self.assertEqual(self.reply(client=self.peer_client).status_code,403)
        self.assertEqual(self.reply(client=self.other_client).status_code,404)

    def test_reply_cannot_be_bound_to_someone_elses_question(self):
        self.feedback()
        other_event=ResponseEvent.objects.create(lesson=self.other_lesson,participant=AccountProfile.objects.get(user=self.peer).participant,status="red",note="其他学生的问题")
        self.assertEqual(self.reply(event_id=other_event.pk).status_code,404)
        self.assertFalse(TeacherReply.objects.exists())

    def test_reply_html_is_text_and_new_read_ack_does_not_hide_future_replies(self):
        self.feedback();self.reply(text="<script>alert(1)</script>")
        first=TeacherReply.objects.get()
        self.reply(text="后来的解释")
        self.student_client.post(reverse("replies_read",args=[self.lesson.code]),{"up_to":first.pk})
        self.assertEqual(TeacherReply.objects.filter(student_read_at__isnull=True).count(),1)
        page=self.student_client.get(self.class_url)
        self.assertContains(page,"&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(page,"<script>alert(1)</script>")

    def test_course_material_backup_contains_files_not_secrets(self):
        self.upload();material=CourseMaterial.objects.get()
        target=Path(self.temp.name)/"course-files.tar.gz"
        call_command("backup_course_files",output=str(target),stdout=io.StringIO())
        with tarfile.open(target,"r:gz") as archive:
            names=archive.getnames()
            self.assertEqual(names,["media/"+material.file.name])
            self.assertTrue(archive.extractfile(names[0]).read().startswith(b"\x89PNG"))

    def test_every_question_is_accessible_through_pagination(self):
        import uuid
        Response.objects.bulk_create([Response(lesson=self.lesson,participant=uuid.uuid4(),status="yellow",note=f"反馈{x}") for x in range(51)])
        url=reverse("lesson_stats",args=[self.lesson.code])
        first=self.teacher_client.get(url).json()
        second=self.teacher_client.get(url,{"feedback_page":2}).json()
        self.assertEqual((first["total"],len(first["notes"])),(51,50))
        self.assertEqual((second["page"],second["pages"],len(second["notes"])),(2,2,1))
