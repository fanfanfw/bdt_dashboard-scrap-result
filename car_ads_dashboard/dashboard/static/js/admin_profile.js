  // Password visibility toggle
  document.querySelectorAll('.password-toggle').forEach(toggle => {
    toggle.addEventListener('click', function() {
      const targetId = this.getAttribute('data-target');
      const passwordInput = document.getElementById(targetId);
      const icon = this.querySelector('i');
      
      if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
      } else {
        passwordInput.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
      }
    });
  });

  // Form validation enhancement
  document.querySelectorAll('form').forEach(form => {
    form.addEventListener('submit', function(e) {
      let isValid = true;
      const requiredFields = this.querySelectorAll('[required]');
      
      requiredFields.forEach(field => {
        if (!field.value.trim()) {
          isValid = false;
          field.classList.add('is-invalid');
        } else {
          field.classList.remove('is-invalid');
        }
      });
      
      if (!isValid) {
        e.preventDefault();
        // Show error message
        const firstInvalid = this.querySelector('.is-invalid');
        if (firstInvalid) {
          firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
          firstInvalid.focus();
        }
      } else {
        // If this is the profile form, prepare for potential redirect
        if (this.id === 'profileForm') {
          const currentUsername = window.profileConfig?.currentUsername;
          const usernameFieldId = window.profileConfig?.usernameFieldId;
          const newUsernameField = document.getElementById(usernameFieldId);
          const newUsername = newUsernameField ? newUsernameField.value : null;
          
          // Store the new username in sessionStorage if it changed
          if (currentUsername && newUsername && currentUsername !== newUsername) {
            sessionStorage.setItem('usernameChanged', 'true');
            sessionStorage.setItem('newUsername', newUsername);
          }
        }
      }
    });
  });

  // Auto-dismiss alerts after 5 seconds
  setTimeout(() => {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
      const bsAlert = new bootstrap.Alert(alert);
      bsAlert.close();
    });
  }, 5000);

  // Check if we need to redirect after username change
  document.addEventListener('DOMContentLoaded', function() {
    // Check for success message indicating profile update
    const successAlerts = document.querySelectorAll('.alert-success');
    const profileSuccessFound = Array.from(successAlerts).some(alert => 
      alert.textContent.includes('Profile updated successfully')
    );
    
    if (profileSuccessFound && sessionStorage.getItem('usernameChanged') === 'true') {
      const newUsername = sessionStorage.getItem('newUsername');
      if (newUsername) {
        // Clear the session storage
        sessionStorage.removeItem('usernameChanged');
        sessionStorage.removeItem('newUsername');
        
        // Show redirect message
        const redirectMessage = document.createElement('div');
        redirectMessage.className = 'alert alert-info alert-dismissible fade show';
        redirectMessage.innerHTML = `
          <i class="fas fa-info-circle"></i>
          Redirecting to your updated profile...
          <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        const container = document.querySelector('.messages-container') || document.querySelector('.page-header');
        if (container) {
          container.appendChild(redirectMessage);
        }
        
        // Redirect after a short delay
        setTimeout(() => {
          window.location.href = `/dashboard/admin/${newUsername}/profile/`;
        }, 2000);
      }
    }
    
    // Add existing error handling for page load
    document.querySelectorAll('.form-control.is-invalid').forEach(input => {
      const wrapper = input.closest('.password-input-wrapper');
      if (wrapper) wrapper.classList.add('has-error');
    });
  });

  // Enhanced form feedback
  document.querySelectorAll('.form-control, .form-select').forEach(input => {
    input.addEventListener('blur', function() {
      const wrapper = this.closest('.password-input-wrapper');
      
      if (this.hasAttribute('required') && !this.value.trim()) {
        this.classList.add('is-invalid');
        if (wrapper) wrapper.classList.add('has-error');
      } else {
        this.classList.remove('is-invalid');
        if (wrapper) wrapper.classList.remove('has-error');
      }
    });
    
    input.addEventListener('input', function() {
      const wrapper = this.closest('.password-input-wrapper');
      
      if (this.classList.contains('is-invalid') && this.value.trim()) {
        this.classList.remove('is-invalid');
        if (wrapper) wrapper.classList.remove('has-error');
      }
    });
  });