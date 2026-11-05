from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from . import test_course_features as fixtures
from .models import ClassroomMembership, Lesson


class ClassroomOrderTests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp

    def classrooms(self):
        old = self.lesson
        new = Lesson.objects.create(teacher=self.teacher, title='新建课堂')
        Lesson.objects.filter(pk=old.pk).update(created_at=timezone.now()-timedelta(days=2))
        # Join the newer course first and the older course last, deliberately
        # opposing course creation order.
        ClassroomMembership.objects.create(lesson=new,student=self.student)
        ClassroomMembership.objects.create(lesson=old,student=self.student)
        return old, new

    def test_teacher_and_student_show_newest_created_first_regardless_of_join_order(self):
        old,new=self.classrooms()
        teacher=self.teacher_client.get(reverse('teacher_home'))
        student=self.student_client.get(reverse('student_home'))
        self.assertEqual([x.pk for x in teacher.context['lessons']],[new.pk,old.pk])
        self.assertEqual([x['lesson'].pk for x in student.context['classrooms']],[new.pk,old.pk])
        self.assertLess(teacher.content.index(new.title.encode()),teacher.content.index(old.title.encode()))
        self.assertLess(student.content.index(new.title.encode()),student.content.index(old.title.encode()))

    def test_equal_creation_times_use_same_stable_order_in_both_portals(self):
        old,new=self.classrooms()
        Lesson.objects.filter(pk__in=[old.pk,new.pk]).update(created_at=timezone.now())
        for _ in range(2):
            self.assertEqual([x.pk for x in self.teacher_client.get(reverse('teacher_home')).context['lessons']],[new.pk,old.pk])
            self.assertEqual([x['lesson'].pk for x in self.student_client.get(reverse('student_home')).context['classrooms']],[new.pk,old.pk])

    def test_closed_lessons_keep_their_position_and_deleted_lessons_stay_hidden(self):
        old,new=self.classrooms()
        Lesson.objects.filter(pk=new.pk).update(is_open=False)
        self.assertEqual([x['lesson'].pk for x in self.student_client.get(reverse('student_home')).context['classrooms']],[new.pk,old.pk])
        Lesson.objects.filter(pk=new.pk).update(deleted_at=timezone.now())
        self.assertEqual([x.pk for x in self.teacher_client.get(reverse('teacher_home')).context['lessons']],[old.pk])
        self.assertEqual([x['lesson'].pk for x in self.student_client.get(reverse('student_home')).context['classrooms']],[old.pk])
