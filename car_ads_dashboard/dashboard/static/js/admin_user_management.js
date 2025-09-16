// Show create user modal
function showCreateUserModal() {
  new bootstrap.Modal(document.getElementById('createUserModal')).show();
}

// Create user form handler
document.getElementById('createUserForm').addEventListener('submit', function(e) {
  e.preventDefault();
  
  const formData = {
    username: document.getElementById('newUsername').value,
    email: document.getElementById('newEmail').value,
    first_name: document.getElementById('newFirstName').value,
    last_name: document.getElementById('newLastName').value,
    password: document.getElementById('newPassword').value,
    role: document.getElementById('newRole').value
  };
  
  fetch(window.userManagementConfig?.createUserUrl || '/dashboard/admin/users/create/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify(formData)
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showNotification(data.message, 'success');
      bootstrap.Modal.getInstance(document.getElementById('createUserModal')).hide();
      location.reload();
    } else {
      showNotification(data.error, 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showNotification('Network error occurred', 'error');
  });
});

// View user details
function viewUserDetails(username) {
  const getUserDetailsUrl = window.userManagementConfig?.getUserDetailsUrl;
  if (!getUserDetailsUrl) {
    console.error('getUserDetailsUrl not configured');
    return;
  }
  
  fetch(`${getUserDetailsUrl}?target_username=${encodeURIComponent(username)}`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const user = data.user;
        const modalContent = document.getElementById('userDetailsContent');
        modalContent.innerHTML = `
          <div class="row">
            <div class="col-md-4 text-center">
              <div class="user-avatar mx-auto mb-3" style="width: 80px; height: 80px; font-size: 2rem;">
                ${user.first_name ? user.first_name.charAt(0).toUpperCase() : user.username.charAt(0).toUpperCase()}
              </div>
              <h5>${user.username}</h5>
              <p class="text-muted">${user.first_name} ${user.last_name}</p>
            </div>
            <div class="col-md-8">
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Username:</strong></div>
                <div class="col-sm-8">${user.username}</div>
              </div>
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Email:</strong></div>
                <div class="col-sm-8">${user.email}</div>
              </div>
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Full Name:</strong></div>
                <div class="col-sm-8">${user.first_name} ${user.last_name}</div>
              </div>
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Registration:</strong></div>
                <div class="col-sm-8">${user.date_joined}</div>
              </div>
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Last Login:</strong></div>
                <div class="col-sm-8">${user.last_login}</div>
              </div>
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Status:</strong></div>
                <div class="col-sm-8">
                  <span class="status-indicator ${user.is_approved && user.is_active ? 'status-success' : user.is_approved ? 'status-danger' : 'status-warning'}">
                    <i class="fas fa-${user.is_approved && user.is_active ? 'check-circle' : user.is_approved ? 'times-circle' : 'clock'}"></i>
                    ${user.status_display}
                  </span>
                </div>
              </div>
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Approval Date:</strong></div>
                <div class="col-sm-8">${user.approval_date || 'Not approved yet'}</div>
              </div>
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Approved By:</strong></div>
                <div class="col-sm-8">${user.approved_by || 'N/A'}</div>
              </div>
              <div class="row mb-3">
                <div class="col-sm-4"><strong>Groups:</strong></div>
                <div class="col-sm-8">${user.groups.join(', ') || 'None'}</div>
              </div>
            </div>
          </div>
        `;
        
        new bootstrap.Modal(document.getElementById('userDetailsModal')).show();
      } else {
        showNotification(data.error || 'Failed to load user details', 'error');
      }
    })
    .catch(error => {
      console.error('Error:', error);
      showNotification('Network error occurred', 'error');
    });
}

// Approve user
function approveUser(username) {
  if (confirm(`Are you sure you want to approve user "${username}"?`)) {
    const approveUserUrl = window.userManagementConfig?.approveUserUrl;
    if (!approveUserUrl) {
      console.error('approveUserUrl not configured');
      return;
    }
    
    fetch(approveUserUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({ target_username: username })
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        showNotification(data.message, 'success');
        location.reload();
      } else {
        showNotification(data.error || 'Failed to approve user', 'error');
      }
    })
    .catch(error => {
      console.error('Error:', error);
      showNotification('Network error occurred', 'error');
    });
  }
}

// Reject user
function rejectUser(username) {
  document.getElementById('rejectUsername').value = username;
  new bootstrap.Modal(document.getElementById('rejectUserModal')).show();
}

// Reject user form handler
document.getElementById('rejectUserForm').addEventListener('submit', function(e) {
  e.preventDefault();
  
  const username = document.getElementById('rejectUsername').value;
  const reason = document.getElementById('rejectReason').value;
  
  const rejectUserUrl = window.userManagementConfig?.rejectUserUrl;
  if (!rejectUserUrl) {
    console.error('rejectUserUrl not configured');
    return;
  }
  
  fetch(rejectUserUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify({ 
      target_username: username,
      reason: reason
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showNotification(data.message, 'success');
      bootstrap.Modal.getInstance(document.getElementById('rejectUserModal')).hide();
      location.reload();
    } else {
      showNotification(data.error || 'Failed to reject user', 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showNotification('Network error occurred', 'error');
  });
});

// Toggle user status
function toggleUserStatus(username, newStatus) {
  const action = newStatus ? 'activate' : 'deactivate';
  if (confirm(`Are you sure you want to ${action} user "${username}"?`)) {
    const toggleStatusUrl = window.userManagementConfig?.toggleStatusUrl;
    if (!toggleStatusUrl) {
      console.error('toggleStatusUrl not configured');
      return;
    }
    
    fetch(toggleStatusUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({ target_username: username })
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        showNotification(data.message, 'success');
        location.reload();
      } else {
        showNotification(data.error || 'Failed to change user status', 'error');
      }
    })
    .catch(error => {
      console.error('Error:', error);
      showNotification('Network error occurred', 'error');
    });
  }
}

// Show edit user modal
function showEditUserModal(username) {
  // Fetch user details first
  const getUserDetailsUrl = window.userManagementConfig?.getUserDetailsUrl;
  if (!getUserDetailsUrl) {
    console.error('getUserDetailsUrl not configured');
    return;
  }
  
  fetch(`${getUserDetailsUrl}?target_username=${encodeURIComponent(username)}`)
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        const user = data.user;
        document.getElementById('editUsername').value = user.username;
        document.getElementById('editEmail').value = user.email;
        document.getElementById('editFirstName').value = user.first_name;
        document.getElementById('editLastName').value = user.last_name;
        
        new bootstrap.Modal(document.getElementById('editUserModal')).show();
      } else {
        showNotification(data.error || 'Failed to load user details', 'error');
      }
    })
    .catch(error => {
      console.error('Error:', error);
      showNotification('Network error occurred', 'error');
    });
}

// Edit user form handler
document.getElementById('editUserForm').addEventListener('submit', function(e) {
  e.preventDefault();
  
  const formData = {
    target_username: document.getElementById('editUsername').value,
    email: document.getElementById('editEmail').value,
    first_name: document.getElementById('editFirstName').value,
    last_name: document.getElementById('editLastName').value
  };
  
  const updateUserUrl = window.userManagementConfig?.updateUserUrl;
  if (!updateUserUrl) {
    console.error('updateUserUrl not configured');
    return;
  }
  
  fetch(updateUserUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify(formData)
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showNotification(data.message, 'success');
      bootstrap.Modal.getInstance(document.getElementById('editUserModal')).hide();
      location.reload();
    } else {
      showNotification(data.error, 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showNotification('Network error occurred', 'error');
  });
});

// Show reset password modal
function showResetPasswordModal(username) {
  document.getElementById('resetUsername').value = username;
  new bootstrap.Modal(document.getElementById('resetPasswordModal')).show();
}

// Reset password form handler
document.getElementById('resetPasswordForm').addEventListener('submit', function(e) {
  e.preventDefault();
  
  const newPassword = document.getElementById('newPasswordReset').value;
  const confirmPassword = document.getElementById('confirmPasswordReset').value;
  
  if (newPassword !== confirmPassword) {
    showNotification('Passwords do not match', 'error');
    return;
  }
  
  const username = document.getElementById('resetUsername').value;
  
  const resetPasswordUrl = window.userManagementConfig?.resetPasswordUrl;
  if (!resetPasswordUrl) {
    console.error('resetPasswordUrl not configured');
    return;
  }
  
  fetch(resetPasswordUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify({
      target_username: username,
      new_password: newPassword
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showNotification(data.message, 'success');
      bootstrap.Modal.getInstance(document.getElementById('resetPasswordModal')).hide();
    } else {
      showNotification(data.error || 'Failed to reset password', 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showNotification('Network error occurred', 'error');
  });
});

// Show change role modal
function showChangeRoleModal(username) {
  document.getElementById('roleUsername').value = username;
  new bootstrap.Modal(document.getElementById('changeRoleModal')).show();
}

// Change role form handler
document.getElementById('changeRoleForm').addEventListener('submit', function(e) {
  e.preventDefault();
  
  const username = document.getElementById('roleUsername').value;
  const role = document.getElementById('userRole').value;
  
  const updateRoleUrl = window.userManagementConfig?.updateRoleUrl;
  if (!updateRoleUrl) {
    console.error('updateRoleUrl not configured');
    return;
  }
  
  fetch(updateRoleUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken()
    },
    body: JSON.stringify({
      target_username: username,
      role: role
    })
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      showNotification(data.message, 'success');
      bootstrap.Modal.getInstance(document.getElementById('changeRoleModal')).hide();
      location.reload();
    } else {
      showNotification(data.error || 'Failed to change role', 'error');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showNotification('Network error occurred', 'error');
  });
});

// Show delete user modal
function showDeleteUserModal(username) {
  document.getElementById('deleteUsername').value = username;
  new bootstrap.Modal(document.getElementById('deleteUserModal')).show();
}

// Delete user form handler
document.getElementById('deleteUserForm').addEventListener('submit', function(e) {
  e.preventDefault();
  
  const username = document.getElementById('deleteUsername').value;
  const permanent = document.getElementById('permanentDelete').checked;
  
  const confirmMessage = permanent 
    ? `Are you sure you want to PERMANENTLY delete user "${username}"? This cannot be undone.`
    : `Are you sure you want to deactivate user "${username}"? They can be restored later.`;
  
  if (confirm(confirmMessage)) {
    const deleteUserUrl = window.userManagementConfig?.deleteUserUrl;
    if (!deleteUserUrl) {
      console.error('deleteUserUrl not configured');
      return;
    }
    
    fetch(deleteUserUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        target_username: username,
        permanent: permanent
      })
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        showNotification(data.message, 'success');
        bootstrap.Modal.getInstance(document.getElementById('deleteUserModal')).hide();
        location.reload();
      } else {
        showNotification(data.error || 'Failed to delete user', 'error');
      }
    })
    .catch(error => {
      console.error('Error:', error);
      showNotification('Network error occurred', 'error');
    });
  }
});

// Helper functions
function getCsrfToken() {
  return document.querySelector('[name=csrfmiddlewaretoken]')?.value || window.userManagementConfig?.csrfToken || '';
}

function showNotification(message, type) {
  const notification = document.createElement('div');
  notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show position-fixed`;
  notification.style.cssText = 'top: 90px; right: 20px; z-index: 9999; min-width: 300px;';
  notification.innerHTML = `
    <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-triangle'} me-2"></i>
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  `;
  
  document.body.appendChild(notification);
  
  setTimeout(() => {
    if (notification.parentElement) {
      notification.remove();
    }
  }, 5000);
}

// Add CSRF token to page
document.addEventListener('DOMContentLoaded', function() {
  if (!document.querySelector('[name=csrfmiddlewaretoken]')) {
    const csrfToken = window.userManagementConfig?.csrfToken;
    if (csrfToken) {
      const csrfInput = document.createElement('input');
      csrfInput.type = 'hidden';
      csrfInput.name = 'csrfmiddlewaretoken';
      csrfInput.value = csrfToken;
      document.body.appendChild(csrfInput);
    }
  }
});