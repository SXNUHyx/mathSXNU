"""Count distinct question events, not repeated replies or the latest snapshot alone."""
from django.db.models import Count, Exists, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import TeacherReply


def question_statistics(lesson, responses):
    next_event = lesson.events.filter(participant=OuterRef('participant'), pk__gt=OuterRef('pk')).order_by('pk')
    explicit = TeacherReply.objects.filter(question_event_id=OuterRef('pk'), response__lesson=lesson,
                                          response__participant=OuterRef('participant'))
    # Old replies without an event belong only to their matching event's time window.
    legacy = TeacherReply.objects.filter(response__lesson=lesson, response__participant=OuterRef('participant'),
        question_event__isnull=True, question_text=OuterRef('note'), created_at__gte=OuterRef('created_at'),
        created_at__lt=OuterRef('next_event_at'))
    events = lesson.events.filter(status__in=['yellow', 'red']).annotate(
        next_event_at=Coalesce(Subquery(next_event.values('created_at')[:1]), Value(timezone.now())),
    ).annotate(resolved=Exists(explicit) | Exists(legacy))
    stats = {status: {'people': 0, 'total': 0, 'resolved': 0} for status in ['yellow', 'red']}
    for row in events.values('status').annotate(people=Count('participant', distinct=True),
            total=Count('pk'), resolved_count=Count('pk', filter=Q(resolved=True))):
        stats[row['status']] = {'people': row['people'], 'total': row['total'], 'resolved': row['resolved_count']}
    for response in responses:
        if response.status in stats and response.latest_event_id is None:
            item = stats[response.status]
            item['people'] += 1
            item['total'] += 1
            item['resolved'] += int(response.answered_at is not None)
    for item in stats.values():
        item['pending'] = item['total'] - item['resolved']
    return stats
