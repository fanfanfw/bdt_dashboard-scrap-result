from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.utils import timezone
from dashboard.models import UserProfile

class Command(BaseCommand):
    help = 'Create a Super Admin user'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Username for the super admin', required=True)
        parser.add_argument('--email', type=str, help='Email for the super admin', required=True)
        parser.add_argument('--password', type=str, help='Password for the super admin', required=True)
        parser.add_argument('--first_name', type=str, help='First name for the super admin', default='')
        parser.add_argument('--last_name', type=str, help='Last name for the super admin', default='')

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        first_name = options['first_name']
        last_name = options['last_name']

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.ERROR(f'User "{username}" already exists'))
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.ERROR(f'Email "{email}" already exists'))
            return

        try:
            # Create Super Admin group if it doesn't exist
            super_admin_group, created = Group.objects.get_or_create(name='Super Admin')
            if created:
                self.stdout.write(self.style.SUCCESS('Super Admin group created'))

            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_staff=True,
                is_superuser=True,
                is_active=True
            )

            # Add to Super Admin group
            user.groups.add(super_admin_group)

            # Create user profile
            profile = UserProfile.objects.create(
                user=user,
                is_approved=True,
                created_by_admin=True,
                approval_date=timezone.now()
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Super Admin user "{username}" created successfully!'
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Email: {email}'
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Role: Super Admin'
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating super admin: {str(e)}')
            )
