from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.utils import timezone
from dashboard.models import UserProfile


class Command(BaseCommand):
    help = 'Auto-approve existing Admin users and create profiles if needed'

    def handle(self, *args, **kwargs):
        # Get Admin group
        try:
            admin_group = Group.objects.get(name='Admin')
        except Group.DoesNotExist:
            self.stdout.write(self.style.ERROR('Admin group does not exist. Run create_groups first.'))
            return

        # Get all Admin users
        admin_users = User.objects.filter(groups=admin_group)
        superusers = User.objects.filter(is_superuser=True)

        # Combine admin users and superusers
        all_admin_users = admin_users.union(superusers)

        updated_count = 0
        created_count = 0

        for user in all_admin_users:
            # Get or create UserProfile
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'is_approved': True,
                    'approval_date': timezone.now(),
                    'created_by_admin': True
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created profile for Admin user: {user.username}')
                )
            elif not profile.is_approved:
                # Update existing profile to be approved
                profile.is_approved = True
                profile.approval_date = timezone.now()
                profile.save()
                updated_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Auto-approved Admin user: {user.username}')
                )
            else:
                self.stdout.write(f'Admin user {user.username} already approved')

        self.stdout.write(
            self.style.SUCCESS(
                f'Completed! Created {created_count} profiles, updated {updated_count} profiles'
            )
        )