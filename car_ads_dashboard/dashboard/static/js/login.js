// Theme toggle functionality
function toggleTheme() {
    const body = document.body;
    const themeIcon = document.getElementById('theme-icon');
    const themeText = document.getElementById('theme-text');
    
    body.classList.toggle('dark-mode');
    
    if (body.classList.contains('dark-mode')) {
    themeIcon.className = 'fas fa-sun';
    themeText.textContent = 'Light';
    localStorage.setItem('theme', 'dark');
    } else {
    themeIcon.className = 'fas fa-moon';
    themeText.textContent = 'Dark';
    localStorage.setItem('theme', 'light');
    }
}

// Load saved theme
document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
    document.body.classList.add('dark-mode');
    document.getElementById('theme-icon').className = 'fas fa-sun';
    document.getElementById('theme-text').textContent = 'Light';
    }
});

// Tab switching functionality
function switchTab(tab) {
    const loginTab = document.getElementById('login-tab');
    const registerTab = document.getElementById('register-tab');
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');

    if (tab === 'login') {
    loginTab.classList.add('active');
    registerTab.classList.remove('active');
    loginForm.classList.remove('hidden');
    registerForm.classList.add('hidden');
    } else {
    registerTab.classList.add('active');
    loginTab.classList.remove('active');
    registerForm.classList.remove('hidden');
    loginForm.classList.add('hidden');
    }
}

// Password visibility toggle
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    const eye = document.getElementById(inputId === 'reg_password1' ? 'reg-password1-eye' : 
                                    inputId === 'reg_password2' ? 'reg-password2-eye' : 'password-eye');
    
    if (input.type === 'password') {
    input.type = 'text';
    eye.className = 'fas fa-eye-slash';
    } else {
    input.type = 'password';
    eye.className = 'fas fa-eye';
    }
}

// Form validation
(() => {
    'use strict';
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(form => {
    form.addEventListener('submit', event => {
        if (!form.checkValidity()) {
        event.preventDefault();
        event.stopPropagation();
        }
        form.classList.add('was-validated');
    }, false);
    });
})();

// Login form submission
document.getElementById('loginForm').addEventListener('submit', function(e) {
    const spinner = document.getElementById('login-spinner');
    const text = document.getElementById('login-text');
    const button = e.target.querySelector('.btn-auth');
    
    if (this.checkValidity()) {
    spinner.style.display = 'inline-block';
    text.textContent = 'Signing In...';
    button.disabled = true;
    }
});

// Register form submission
document.getElementById('registerForm').addEventListener('submit', function(e) {
    e.preventDefault();
    
    const spinner = document.getElementById('register-spinner');
    const text = document.getElementById('register-text');
    const button = e.target.querySelector('.btn-auth');
    const successMessage = document.getElementById('register-success');
    
    // Clear previous errors
    document.querySelectorAll('.invalid-feedback').forEach(el => el.style.display = 'none');
    
    // Show loading state
    spinner.style.display = 'inline-block';
    text.textContent = 'Creating Account...';
    button.disabled = true;
    
    // Get form data
    const formData = new FormData(this);
    const data = Object.fromEntries(formData);
    
    // Make AJAX call to registration endpoint
    fetch('/dashboard/register/', {
    method: 'POST',
    body: JSON.stringify(data),
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('#registerForm [name=csrfmiddlewaretoken]').value
    }
    })
    .then(response => response.json())
    .then(data => {
    spinner.style.display = 'none';
    text.textContent = 'Create Account';
    button.disabled = false;
    
    if (data.success) {
        successMessage.style.display = 'block';
        this.reset();
        
        // Switch to login tab after 3 seconds
        setTimeout(() => {
        switchTab('login');
        successMessage.style.display = 'none';
        }, 3000);
    } else {
        // Handle errors
        if (data.errors) {
        Object.keys(data.errors).forEach(field => {
            const errorDiv = document.getElementById(field + '-error');
            if (errorDiv && data.errors[field] && data.errors[field].length > 0) {
            errorDiv.textContent = data.errors[field][0];
            errorDiv.style.display = 'block';
            }
        });
        }
    }
    })
    .catch(error => {
    spinner.style.display = 'none';
    text.textContent = 'Create Account';
    button.disabled = false;
    console.error('Error:', error);
    
    // Show generic error
    const errorDiv = document.getElementById('username-error');
    errorDiv.textContent = 'Registration failed. Please try again.';
    errorDiv.style.display = 'block';
    });
});

// Password strength checker
function checkPasswordStrength(password) {
    const requirements = {
    length: password.length >= 6,
    uppercase: /[A-Z]/.test(password),
    number: /[0-9]/.test(password),
    symbol: /[^A-Za-z0-9]/.test(password)
    };

    const metCount = Object.values(requirements).filter(Boolean).length;
    let strength = 'weak';
    let strengthText = 'Password is too weak';

    if (metCount === 4) {
    strength = 'strong';
    strengthText = 'Strong password';
    } else if (metCount >= 2) {
    strength = 'medium';
    strengthText = 'Medium password';
    }

    return { requirements, strength, strengthText, metCount };
}

// Update password strength indicator
function updatePasswordStrength(password) {
    const { requirements, strength, strengthText } = checkPasswordStrength(password);

    // Update strength bar
    const strengthFill = document.getElementById('strength-fill');
    const strengthTextEl = document.getElementById('strength-text');

    strengthFill.className = `strength-fill ${strength}`;
    strengthTextEl.className = `strength-text ${strength}`;
    strengthTextEl.textContent = strengthText;

    // Update requirements
    Object.keys(requirements).forEach(req => {
    const reqEl = document.getElementById(`req-${req}`);
    const icon = reqEl.querySelector('i');

    if (requirements[req]) {
        reqEl.classList.add('met');
        icon.className = 'fas fa-check';
    } else {
        reqEl.classList.remove('met');
        icon.className = 'fas fa-times';
    }
    });

    return strength === 'strong';
}

// Real-time password strength checking
document.getElementById('reg_password1').addEventListener('input', function() {
    const password = this.value;
    const isStrong = updatePasswordStrength(password);
    const registerButton = document.querySelector('#registerForm .btn-auth');

    // Enable/disable register button based on password strength
    if (password.length === 0) {
    registerButton.disabled = false; // Allow empty for form validation to handle
    } else if (!isStrong) {
    registerButton.disabled = true;
    registerButton.style.opacity = '0.5';
    registerButton.title = 'Password must meet all requirements';
    } else {
    registerButton.disabled = false;
    registerButton.style.opacity = '1';
    registerButton.title = '';
    }
});

// Real-time password validation
document.getElementById('reg_password2').addEventListener('input', function() {
    const password1 = document.getElementById('reg_password1').value;
    const password2 = this.value;
    const errorDiv = document.getElementById('password2-error');

    if (password2 && password1 !== password2) {
    this.setCustomValidity('Passwords do not match');
    errorDiv.textContent = 'Passwords do not match';
    errorDiv.style.display = 'block';
    } else {
    this.setCustomValidity('');
    errorDiv.style.display = 'none';
    }
});

// Username availability check
let usernameTimeout;
document.getElementById('reg_username').addEventListener('input', function() {
    const username = this.value;
    const errorDiv = document.getElementById('username-error');
    
    clearTimeout(usernameTimeout);
    
    if (username.length >= 3) {
    usernameTimeout = setTimeout(() => {
        fetch(`/dashboard/check-username/?username=${encodeURIComponent(username)}`)
        .then(response => response.json())
        .then(data => {
            if (!data.available) {
            this.setCustomValidity(data.message);
            errorDiv.textContent = data.message;
            errorDiv.style.display = 'block';
            } else {
            this.setCustomValidity('');
            errorDiv.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Error checking username:', error);
        });
    }, 500);
    } else {
    this.setCustomValidity('');
    errorDiv.style.display = 'none';
    }
});

// Add smooth transitions and animations
document.addEventListener('DOMContentLoaded', function() {
    // Add intersection observer for animations
    const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        }
    });
    }, observerOptions);

    // Observe elements for animation
    document.querySelectorAll('.form-group').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'all 0.3s ease';
    observer.observe(el);
    });

    // Progressive enhancement for form inputs
    document.querySelectorAll('.form-control').forEach(input => {
    input.addEventListener('focus', function() {
        this.parentElement.parentElement.classList.add('focused');
    });
    
    input.addEventListener('blur', function() {
        if (!this.value) {
        this.parentElement.parentElement.classList.remove('focused');
        }
    });
    
    // Check if input has value on load
    if (input.value) {
        input.parentElement.parentElement.classList.add('focused');
    }
    });
});

// Keyboard navigation improvements
document.addEventListener('keydown', function(e) {
    // Switch tabs with Ctrl+Tab
    if (e.ctrlKey && e.key === 'Tab') {
    e.preventDefault();
    const currentTab = document.querySelector('.tab-button.active').textContent.trim();
    switchTab(currentTab === 'Login' ? 'register' : 'login');
    }
    
    // Submit form with Ctrl+Enter
    if (e.ctrlKey && e.key === 'Enter') {
    const activeForm = document.querySelector('.form-content:not(.hidden) form');
    if (activeForm) {
        activeForm.dispatchEvent(new Event('submit', { bubbles: true }));
    }
    }
});

// Add ripple effect to buttons
document.querySelectorAll('.btn-auth, .tab-button').forEach(button => {
    button.addEventListener('click', function(e) {
    let ripple = document.createElement('span');
    ripple.classList.add('ripple');
    this.appendChild(ripple);

    let x = e.clientX - e.target.offsetLeft;
    let y = e.clientY - e.target.offsetTop;

    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;

    setTimeout(() => {
        ripple.remove();
    }, 300);
    });
});

// Add smooth transitions and animations
document.addEventListener('DOMContentLoaded', function() {
    // Add intersection observer for animations
    const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        }
    });
    }, observerOptions);

    // Observe elements for animation
    document.querySelectorAll('.form-group').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'all 0.3s ease';
    observer.observe(el);
    });

    // Progressive enhancement for form inputs
    document.querySelectorAll('.form-control').forEach(input => {
    input.addEventListener('focus', function() {
        this.parentElement.parentElement.classList.add('focused');
    });

    input.addEventListener('blur', function() {
        if (!this.value) {
        this.parentElement.parentElement.classList.remove('focused');
        }
    });

    // Check if input has value on load
    if (input.value) {
        input.parentElement.parentElement.classList.add('focused');
    }
    });
});

// Keyboard navigation improvements
document.addEventListener('keydown', function(e) {
    // Switch tabs with Ctrl+Tab
    if (e.ctrlKey && e.key === 'Tab') {
    e.preventDefault();
    const currentTab = document.querySelector('.tab-button.active').textContent.trim();
    switchTab(currentTab === 'Login' ? 'register' : 'login');
    }

    // Submit form with Ctrl+Enter
    if (e.ctrlKey && e.key === 'Enter') {
    const activeForm = document.querySelector('.form-content:not(.hidden) form');
    if (activeForm) {
        activeForm.dispatchEvent(new Event('submit', { bubbles: true }));
    }
    }
});