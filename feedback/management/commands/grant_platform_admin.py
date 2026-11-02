from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from feedback.models import AccountProfile
from feedback.user_management import account_state, apply_role, audit


class Command(BaseCommand):
    help='从有服务器终端权限的维护者手中，为已有账号开通开发者管理权限；不创建默认密码。'

    def add_arguments(self,parser):
        parser.add_argument('--username',required=True,help='已有账号的准确用户名（支持中文）')

    def handle(self,*args,**options):
        with transaction.atomic():
            try:
                user=get_user_model().objects.select_for_update().get(username=options['username'])
            except get_user_model().DoesNotExist as exc:
                raise CommandError('找不到该用户名。请先从前端注册，或使用createsuperuser新建管理员。') from exc
            if not user.has_usable_password():
                raise CommandError('该账号没有可用密码，请先用changepassword设置密码。')
            before=account_state(user)
            profile,_=AccountProfile.objects.get_or_create(user=user)
            user.account_profile=profile
            apply_role(user,profile,'admin');user.is_active=True;profile.archived_at=None
            user.save();profile.save()
            audit(None,user,'grant_admin',before,'服务器终端开通并启用开发者管理员',actor_name='服务器终端')
        self.stdout.write(self.style.SUCCESS('已开通开发者管理员权限。请使用该账号登录网站后进入“开发者管理”。密码未改变。'))
