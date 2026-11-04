import uuid
from django.urls import reverse
from django.test import TestCase
from . import test_feedback_order as ordering
from . import test_course_features as fixtures
from .models import Response, ResponseEvent


class QuestionStatisticsTests(TestCase):
    setUp = fixtures.CourseFeatureTests.setUp
    question = ordering.FeedbackOrderTests.question
    reply = ordering.FeedbackOrderTests.reply
    data = ordering.FeedbackOrderTests.data
    def stats(self, status, **params):
        return next(g['statistics'] for g in self.data(**params)['question_groups'] if g['status']==status)

    def test_followups_count_once_each_and_replies_do_not_inflate_resolved(self):
        for status in ['yellow', 'red']:
            response, event = self.question(status, text='第一次问题')
            self.assertEqual(self.stats(status), {'people':1, 'total':1, 'resolved':0, 'pending':1})
            self.reply(response, event)
            self.reply(response, event)
            self.assertEqual(self.stats(status), {'people':1, 'total':1, 'resolved':1, 'pending':0})
            followup = ResponseEvent.objects.create(lesson=self.lesson, participant=response.participant,
                                                     status=status, note='再次追问')
            self.assertEqual(self.stats(status), {'people':1, 'total':2, 'resolved':1, 'pending':1})
            self.reply(response, event)  # history reply cannot solve the follow-up
            self.assertEqual(self.stats(status)['resolved'], 1)
            self.reply(response, followup)
            self.assertEqual(self.stats(status), {'people':1, 'total':2, 'resolved':2, 'pending':0})

    def test_same_text_followup_after_reply_counts_once_but_retry_does_not(self):
        for status in ['yellow', 'red']:
            fields={'status':status, 'note':'同一句追问', 'real_name':'学生', 'student_number':'001'}
            self.student_client.post(self.class_url, fields)
            self.student_client.post(self.class_url, fields)
            response=Response.objects.get(lesson=self.lesson, user=self.student)
            event=self.lesson.events.latest('pk')
            self.assertEqual(self.stats(status)['total'], 1)
            self.reply(response, event)
            self.student_client.post(self.class_url, fields)
            self.student_client.post(self.class_url, fields)
            self.assertEqual(self.stats(status), {'people':1,'total':2,'resolved':1,'pending':1})

    def test_counts_cover_all_pages_and_keep_old_status_history(self):
        response, event=self.question('yellow')
        self.reply(response,event)
        ResponseEvent.objects.create(lesson=self.lesson,participant=response.participant,status='red',note='转为求助')
        response.status='red';response.save()
        self.assertEqual(self.stats('yellow'), {'people':1,'total':1,'resolved':1,'pending':0})
        for _ in range(51):
            self.question('red')
        self.assertEqual(self.stats('red'), self.stats('red',feedback_page=2))
        self.assertEqual(self.stats('red')['total'],52)
        self.assertEqual(self.stats('red')['people'],52)

    def test_legacy_no_event_snapshot_and_unlinked_reply_are_counted(self):
        response=Response.objects.create(lesson=self.lesson,participant=uuid.uuid4(),status='yellow',note='旧问题')
        self.reply(response,None)
        self.assertEqual(self.stats('yellow'), {'people':1,'total':1,'resolved':1,'pending':0})
        later,event=self.question('red',text='原问题')
        self.reply(later,None)
        ResponseEvent.objects.create(lesson=self.lesson,participant=later.participant,status='red',note='原问题')
        self.assertEqual(self.stats('red'), {'people':1,'total':2,'resolved':1,'pending':1})
