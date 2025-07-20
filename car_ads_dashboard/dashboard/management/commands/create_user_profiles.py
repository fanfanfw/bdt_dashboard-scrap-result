"""
Management command to create UserProfile for existing users
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from dashboard.models import UserProfile

class Command(BaseCommand):
    help = 'Create UserProfile for existing users'

    def handle(self, *args, **options):
        users_without_profile = User.objects.filter(profile__isnull=True)
        
        for user in users_without_profile:
            # Create profile for existing users
            # Assume existing users are approved (since they were created before the system)
            profile = UserProfile.objects.create(
                user=user,
                is_approved=True,  # Existing users are considered approved
                created_by_admin=True,  # Consider them as admin-created for compatibility
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'Created profile for user: {user.username}')
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created profiles for {users_without_profile.count()} users')
        )
