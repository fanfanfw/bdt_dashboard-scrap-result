from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordChangeForm, AuthenticationForm
from django.core.exceptions import ValidationError
from .models import CarsStandardMaintenanceJob, UserProfile
from .services.cars_standard_maintenance import ALLOWED_TARGET_TABLES, validate_ambiguous_resolver_limit, validate_fill_batch_size, validate_null_inspector_limit, validate_sources


CARS_STANDARD_EDIT_FIELDS = [
    'brand_norm',
    'brand_raw',
    'brand_raw2',
    'model_group_norm',
    'model_group_raw',
    'model_norm',
    'model_raw',
    'model_raw2',
    'variant_norm',
    'variant_raw',
    'variant_raw2',
    'variant_raw3',
    'variant_raw4',
]


class CarsStandardFieldsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        required_fields = {'brand_norm', 'model_group_norm', 'model_norm', 'variant_norm'}
        for field_name in CARS_STANDARD_EDIT_FIELDS:
            self.fields[field_name] = forms.CharField(
                required=field_name in required_fields,
                max_length=100,
                initial='NO MODEL GROUP' if field_name == 'model_group_norm' else None,
                widget=forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            )

    def clean(self):
        cleaned_data = super().clean()
        normalized_fields = {'brand_norm', 'model_group_norm', 'model_norm', 'variant_norm'}
        for field_name in CARS_STANDARD_EDIT_FIELDS:
            value = cleaned_data.get(field_name)
            if isinstance(value, str):
                value = value.strip()
                cleaned_data[field_name] = value.upper() if field_name in normalized_fields and value else value or None
        return cleaned_data


class CarsStandardCreateForm(CarsStandardFieldsForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['model_group_norm'].required = False


class CarsStandardUpdateForm(CarsStandardFieldsForm):
    cars_standard_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


class CarsStandardDeleteForm(forms.Form):
    cars_standard_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirm_set_null = forms.BooleanField(required=True)


class CarsStandardMergePreviewForm(forms.Form):
    source_id = forms.IntegerField(min_value=1)
    target_id = forms.IntegerField(min_value=1)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('source_id') == cleaned_data.get('target_id'):
            raise ValidationError('Source and target rows must be different.')
        return cleaned_data


class CarsStandardMergeExecuteForm(CarsStandardMergePreviewForm):
    confirm = forms.BooleanField(required=True)
    alias_changes = forms.CharField(required=False, widget=forms.HiddenInput)
    preview_token = forms.CharField(required=True, widget=forms.HiddenInput)


class CarsStandardNullInspectorForm(forms.Form):
    target_table = forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-select'}))
    source = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Source'}),
    )
    preview_limit = forms.IntegerField(
        required=False,
        initial=500,
        min_value=1,
        max_value=10000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '10000'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_table'].choices = [(table, table) for table in ALLOWED_TARGET_TABLES]

    def clean_preview_limit(self):
        return validate_null_inspector_limit(self.cleaned_data.get('preview_limit'))

    def clean(self):
        cleaned_data = super().clean()
        table_name = cleaned_data.get('target_table')
        source = cleaned_data.get('source')
        if table_name and source:
            try:
                cleaned_data['source'] = validate_sources(table_name, [source])[0]
            except ValueError as exc:
                raise ValidationError(str(exc))
        return cleaned_data


class CarsStandardAmbiguousResolverForm(forms.Form):
    target_table = forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-select'}))
    source = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Source'}),
    )
    display_limit = forms.ChoiceField(
        choices=[(10, '10'), (50, '50'), (100, '100')],
        initial=10,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_table'].choices = [(table, table) for table in ALLOWED_TARGET_TABLES]

    def clean_display_limit(self):
        return validate_ambiguous_resolver_limit(self.cleaned_data.get('display_limit'))

    def clean(self):
        cleaned_data = super().clean()
        table_name = cleaned_data.get('target_table')
        source = cleaned_data.get('source')
        if table_name and source:
            try:
                cleaned_data['source'] = validate_sources(table_name, [source])[0]
            except ValueError as exc:
                raise ValidationError(str(exc))
        return cleaned_data


class CarsStandardInsertMissingPreviewForm(forms.Form):
    target_table = forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-select'}))
    sources = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Comma-separated sources'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_table'].choices = [(table, table) for table in ALLOWED_TARGET_TABLES]

    def clean_sources(self):
        value = self.cleaned_data.get('sources') or ''
        return [source.strip() for source in value.split(',') if source.strip()]

    def clean(self):
        cleaned_data = super().clean()
        table_name = cleaned_data.get('target_table')
        sources = cleaned_data.get('sources')
        if table_name and sources:
            try:
                cleaned_data['sources'] = validate_sources(table_name, sources)
            except ValueError as exc:
                raise ValidationError(str(exc))
        return cleaned_data


class CarsStandardInsertMissingExecuteForm(CarsStandardInsertMissingPreviewForm):
    confirm = forms.BooleanField(required=True)
    preview_token = forms.CharField(required=True, widget=forms.HiddenInput)


class CarsStandardFillPreviewForm(forms.Form):
    target_table = forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-select'}))
    sources = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Comma-separated sources'}),
    )
    batch_size = forms.IntegerField(
        initial=500,
        min_value=1,
        max_value=10000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '10000'}),
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_table'].choices = [(table, table) for table in ALLOWED_TARGET_TABLES]

    def clean_sources(self):
        value = self.cleaned_data.get('sources') or ''
        return [source.strip() for source in value.split(',') if source.strip()]

    def clean_batch_size(self):
        return validate_fill_batch_size(self.cleaned_data.get('batch_size'))

    def clean(self):
        cleaned_data = super().clean()
        table_name = cleaned_data.get('target_table')
        sources = cleaned_data.get('sources')
        if table_name and sources:
            try:
                cleaned_data['sources'] = validate_sources(table_name, sources)
            except ValueError as exc:
                raise ValidationError(str(exc))
        return cleaned_data


class CarsStandardFillExecuteForm(CarsStandardFillPreviewForm):
    confirm = forms.BooleanField(required=False)
    preview_token = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('dry_run') and not cleaned_data.get('confirm'):
            raise ValidationError('Non-dry-run fill requires confirmation.')
        return cleaned_data


class CarsStandardMaintenanceJobForm(forms.Form):
    job_type = forms.ChoiceField(
        choices=[
            (CarsStandardMaintenanceJob.JOB_INSERT_MISSING, 'Insert missing cars_standard rows'),
            (CarsStandardMaintenanceJob.JOB_FILL_STANDARD_ID, 'Fill cars_standard_id'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    target_table = forms.ChoiceField(widget=forms.Select(attrs={'class': 'form-select'}))
    sources = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Comma-separated sources, blank for all'}),
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    batch_size = forms.IntegerField(
        initial=500,
        min_value=1,
        max_value=10000,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '10000'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['target_table'].choices = [(table, table) for table in ALLOWED_TARGET_TABLES]

    def clean_sources(self):
        value = self.cleaned_data.get('sources') or ''
        return [source.strip() for source in value.split(',') if source.strip()]

    def clean_batch_size(self):
        return validate_fill_batch_size(self.cleaned_data.get('batch_size'))

    def clean(self):
        cleaned_data = super().clean()
        table_name = cleaned_data.get('target_table')
        sources = cleaned_data.get('sources')
        if not sources:
            raise ValidationError('Sources are required for cars_standard maintenance jobs.')
        if table_name and sources:
            try:
                cleaned_data['sources'] = validate_sources(table_name, sources)
            except ValueError as exc:
                raise ValidationError(str(exc))
        return cleaned_data


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
        fields = ("username", "email")

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
