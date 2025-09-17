from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm, AuthenticationForm
from django.core.exceptions import ValidationError
from .models import UserProfile


class AdminProfileForm(forms.ModelForm):
    """Form untuk mengubah profile admin"""
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter username'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user_instance = kwargs.pop('user_instance', None)
        super().__init__(*args, **kwargs)
        
        # Make fields required
        self.fields['username'].required = True
        self.fields['email'].required = True
        
        # Set labels
        self.fields['username'].label = 'Username'
        self.fields['first_name'].label = 'First Name'
        self.fields['last_name'].label = 'Last Name'
        self.fields['email'].label = 'Email Address'

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            # Check if username already exists (excluding current user)
            if User.objects.filter(username=username).exclude(id=self.user_instance.id if self.user_instance else None).exists():
                raise ValidationError('Username already exists. Please choose a different one.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if email already exists (excluding current user)
            if User.objects.filter(email=email).exclude(id=self.user_instance.id if self.user_instance else None).exists():
                raise ValidationError('Email already exists. Please choose a different one.')
        return email


class AdminPasswordChangeForm(PasswordChangeForm):
    """Custom password change form dengan styling"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add custom classes and attributes
        self.fields['old_password'].widget.attrs.update({
            'class': 'form-control password-input',
            'placeholder': 'Enter current password'
        })
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control password-input',
            'placeholder': 'Enter new password'
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control password-input',
            'placeholder': 'Confirm new password'
        })
        
        # Set labels
        self.fields['old_password'].label = 'Current Password'
        self.fields['new_password1'].label = 'New Password'
        self.fields['new_password2'].label = 'Confirm New Password'


class CustomAuthenticationForm(AuthenticationForm):
    """
    Custom authentication form with detailed error messages
    """
    
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        
        # Add CSS classes and placeholders
        for visible in self.visible_fields():
            visible.field.widget.attrs['class'] = 'form-control'
            if visible.name == 'username':
                visible.field.widget.attrs['placeholder'] = 'Enter your username'
            elif visible.name == 'password':
                visible.field.widget.attrs['placeholder'] = 'Enter your password'
    
    def confirm_login_allowed(self, user):
        """
        Check if user is allowed to login with detailed error messages
        """
        # Check if user account is active
        if not user.is_active:
            raise forms.ValidationError(
                "Akun Anda telah dinonaktifkan. Silakan hubungi administrator untuk mengaktifkan kembali akun Anda.",
                code='account_disabled',
            )

        # Check if user is Admin - Admin users don't need approval
        if user.groups.filter(name='Admin').exists() or user.is_superuser:
            return  # Admin users can login without approval

        # Check user profile and approval status for non-Admin users
        try:
            profile = UserProfile.objects.get(user=user)
            if not profile.is_approved:
                raise forms.ValidationError(
                    "Akun Anda belum disetujui oleh administrator. Silakan tunggu persetujuan atau hubungi administrator.",
                    code='account_not_approved',
                )
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist and mark as not approved for non-Admin users
            UserProfile.objects.create(user=user, is_approved=False)
            raise forms.ValidationError(
                "Akun Anda belum disetujui oleh administrator. Silakan tunggu persetujuan atau hubungi administrator.",
                code='account_not_approved',
            )
    
    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            # Check if user exists first
            try:
                user = User.objects.get(username=username)
                
                # Check password manually
                if not user.check_password(password):
                    raise forms.ValidationError(
                        "Username atau password yang Anda masukkan salah. Silakan periksa kembali dan coba lagi.",
                        code='invalid_login',
                    )
                
                # If password is correct, run the normal authentication
                self.user_cache = user
                self.confirm_login_allowed(user)
                
            except User.DoesNotExist:
                raise forms.ValidationError(
                    "Username yang Anda masukkan tidak terdaftar. Silakan daftar terlebih dahulu atau periksa kembali username Anda.",
                    code='user_not_found',
                )
        
        return self.cleaned_data


class CustomUserCreationForm(forms.ModelForm):
    """
    Custom user creation form for registration
    """
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        help_text="Password harus minimal 8 karakter."
    )
    password2 = forms.CharField(
        label="Konfirmasi Password",
        widget=forms.PasswordInput,
        help_text="Masukkan password yang sama untuk konfirmasi."
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username sudah digunakan. Silakan pilih username lain.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email sudah terdaftar. Silakan gunakan email lain.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Password tidak cocok. Silakan periksa kembali.")
        return password2

    def clean_password1(self):
        password1 = self.cleaned_data.get("password1")
        if password1 and len(password1) < 8:
            raise forms.ValidationError("Password harus minimal 8 karakter.")
        return password1

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.set_password(self.cleaned_data["password1"])
        user.is_active = True  # Account is active but needs approval
        
        if commit:
            user.save()
            # Create UserProfile for approval tracking
            UserProfile.objects.create(
                user=user,
                is_approved=False  # User needs admin approval
            )
        return user


class UserProfileForm(forms.ModelForm):
    """Form untuk mengubah profile user biasa"""
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter username'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user_instance = kwargs.pop('user_instance', None)
        super().__init__(*args, **kwargs)
        
        # Make fields required
        self.fields['username'].required = True
        self.fields['email'].required = True
        
        # Set labels
        self.fields['username'].label = 'Username'
        self.fields['first_name'].label = 'First Name'
        self.fields['last_name'].label = 'Last Name'
        self.fields['email'].label = 'Email Address'

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username:
            # Check if username already exists (excluding current user)
            if User.objects.filter(username=username).exclude(id=self.user_instance.id if self.user_instance else None).exists():
                raise ValidationError('Username already exists. Please choose a different one.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if email already exists (excluding current user)
            if User.objects.filter(email=email).exclude(id=self.user_instance.id if self.user_instance else None).exists():
                raise ValidationError('Email already exists. Please choose a different one.')
        return email


class UserPasswordChangeForm(PasswordChangeForm):
    """Custom password change form untuk user biasa dengan styling"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add custom classes and attributes
        self.fields['old_password'].widget.attrs.update({
            'class': 'form-control password-input',
            'placeholder': 'Enter current password'
        })
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control password-input',
            'placeholder': 'Enter new password'
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control password-input',
            'placeholder': 'Confirm new password'
        })
        
        # Set labels
        self.fields['old_password'].label = 'Current Password'
        self.fields['new_password1'].label = 'New Password'
        self.fields['new_password2'].label = 'Confirm New Password'
