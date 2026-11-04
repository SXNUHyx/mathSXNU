import uuid
from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from . import test_course_features as fixtures
from .models import Response, ResponseEvent, TeacherReply


class FeedbackOrderTests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp

    def question(self, status='yellow', user=None, text='问题'):
        response = Response.objects.create(lesson=self.lesson, participant=uuid.uuid4(), user=user,
                                           status=status, note=text)
        event = ResponseEvent.objects.create(lesson=self.lesson, participant=response.participant,
                                             user=user, status=status, note=text)
        return response, event

    def reply(self, response, event):
        return TeacherReply.objects.create(response=response, question_event=event, teacher=self.teacher,
                                            question_text=event.note if event else response.note, message='教师解释')

    def data(self, **params):
        return self.teacher_client.get(reverse('lesson_stats', args=[self.lesson.code]), params).json()

    def ids(self, data, status):
        return [n['id'] for n in next(g for g in data['question_groups'] if g['status']==status)['notes']]

    def test_each_group_puts_unanswered_first_and_newly_answered_last(self):
        for status in ['yellow', 'red']:
            first, e1 = self.question(status)
            second, e2 = self.question(status)
            third, e3 = self.question(status)
            self.assertEqual(self.ids(self.data(), status), [third.pk, second.pk, first.pk])
            self.reply(third, e3)
            self.assertEqual(self.ids(self.data(), status), [second.pk, first.pk, third.pk])
            self.reply(second, e2)
            self.assertEqual(self.ids(self.data(), status), [first.pk, third.pk, second.pk])
            self.reply(third, e3)
            self.assertEqual(self.ids(self.data(), status), [first.pk, second.pk, third.pk])
        page = self.teacher_client.get(reverse('dashboard', args=[self.lesson.code]))
        self.assertEqual([n['id'] for n in page.context['summary']['notes']], [n['id'] for n in self.data()['notes']])

    def test_reply_route_reorders_and_new_question_returns_to_front(self):
        waiting, _ = self.question(user=self.peer)
        response, old_event = self.question(user=self.student, text='第一问')
        result = self.teacher_client.post(reverse('reply_create', args=[self.lesson.code, response.pk]),
                                          {'event_id': old_event.pk, 'message': '这是一条教师回复'})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.ids(self.data(), 'yellow'), [waiting.pk, response.pk])
        # A new event must be treated as pending even if its text repeats.
        ResponseEvent.objects.create(lesson=self.lesson, participant=response.participant, user=self.student,
                                     status='yellow', note='第一问')
        response.save()  # refresh the updated_at timestamp
        self.assertEqual(self.ids(self.data(), 'yellow'), [response.pk, waiting.pk])
        self.reply(response, old_event)  # late reply to history cannot answer the latest event
        self.assertEqual(self.ids(self.data(), 'yellow'), [response.pk, waiting.pk])

    def test_unanswered_priority_applies_before_pagination(self):
        waiting, _ = self.question(status='red')
        for _ in range(51):
            response, event = self.question(status='red')
            self.reply(response, event)
        first = self.data()
        second = self.data(feedback_page=2)
        self.assertEqual(first['notes'][0]['id'], waiting.pk)
        self.assertEqual((len(first['notes']),len(second['notes']),first['pages']), (50,2,2))
        self.assertEqual(first['total'], 52)

    def test_legacy_reply_counts_only_for_matching_current_feedback(self):
        waiting, _ = self.question()
        response = Response.objects.create(lesson=self.lesson, participant=uuid.uuid4(), status='yellow', note='原问题')
        self.reply(response, None)
        self.assertEqual(self.ids(self.data(), 'yellow'), [waiting.pk,response.pk])
        Response.objects.filter(pk=response.pk).update(note='新问题', updated_at=timezone.now()+timedelta(seconds=1))
        self.assertEqual(self.ids(self.data(), 'yellow'), [response.pk,waiting.pk])
