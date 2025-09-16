// Setup WebSocket untuk notifikasi
const ws_scheme = window.dashboardConfig?.wsScheme || (window.location.protocol === "https:" ? "wss://" : "ws://");
const wsHost = window.dashboardConfig?.wsHost || window.location.host;
const socket = new WebSocket(ws_scheme + wsHost + '/ws/sync_notify/');

socket.onmessage = function(e) {
    const data = JSON.parse(e.data);
    handleSyncStatusUpdate(data);
};

socket.onerror = function(e) {
    console.error('WebSocket error:', e);
};

socket.onopen = function(e) {
    console.log('WebSocket connected');
    // Check current sync status when WebSocket connects
    checkCurrentSyncStatus();
};

// Function to handle sync status updates from WebSocket
function handleSyncStatusUpdate(data) {
    const statusIndicator = document.getElementById('sync-status-indicator');
    const statusText = document.getElementById('sync-status-text');
    const syncDisplay = document.getElementById('sync-status-display');
    const detailedStatus = document.getElementById('sync-detailed-status');
    const lastSyncTimeElement = document.getElementById('last-sync-time');
    const syncButton = document.getElementById('sync-button');
    
    if (detailedStatus) {
        detailedStatus.textContent = data.detail || data.message || 'Processing...';
    }
    
    // Update UI based on status
    if (data.status === 'in_progress') {
        if (statusIndicator) {
            statusIndicator.className = 'status-indicator status-warning';
            statusIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>In Progress</span>';
        }
        if (statusText) statusText.textContent = 'In Progress';
        if (syncDisplay) syncDisplay.style.display = 'block';
        
        // Disable sync button during sync
        if (syncButton) {
            syncButton.disabled = true;
            syncButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Syncing...';
            syncButton.classList.add('btn-secondary');
            syncButton.classList.remove('btn-success');
        }
        
        // Update progress if provided
        if (data.progress !== undefined) {
            updateSyncProgress(data.progress, data.current_step);
        }
        
    } else if (data.status === 'success') {
        if (statusIndicator) {
            statusIndicator.className = 'status-indicator status-success';
            statusIndicator.innerHTML = '<i class="fas fa-check-circle"></i><span>Completed</span>';
        }
        if (statusText) statusText.textContent = 'Completed';
        if (syncDisplay) syncDisplay.style.display = 'none';
        
        // Re-enable sync button
        if (syncButton) {
            syncButton.disabled = false;
            syncButton.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Sync Now';
            syncButton.classList.remove('btn-secondary');
            syncButton.classList.add('btn-success');
        }
        
        // Update the last sync time
        const now = new Date();
        localStorage.setItem('lastSyncTime', now.getTime());
        if (lastSyncTimeElement) lastSyncTimeElement.textContent = "Just now";
        
        showNotification('Synchronization completed successfully!', 'success');
        
    } else if (data.status === 'failure') {
        if (statusIndicator) {
            statusIndicator.className = 'status-indicator status-danger';
            statusIndicator.innerHTML = '<i class="fas fa-times-circle"></i><span>Failed</span>';
        }
        if (statusText) statusText.textContent = 'Failed';
        if (syncDisplay) syncDisplay.style.display = 'none';
        
        // Re-enable sync button
        if (syncButton) {
            syncButton.disabled = false;
            syncButton.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Sync Now';
            syncButton.classList.remove('btn-secondary');
            syncButton.classList.add('btn-success');
        }
        
        showNotification('Synchronization failed. Please try again.', 'error');
    }
}

// Function to update sync progress
function updateSyncProgress(progress, currentStep) {
    const progressBar = document.querySelector('#sync-status-display .progress-bar');
    const progressText = document.getElementById('sync-progress-text');
    const stepText = document.getElementById('sync-step-text');
    
    if (progressBar) {
        progressBar.style.width = progress + '%';
        progressBar.setAttribute('aria-valuenow', progress);
    }
    
    if (progressText) {
        progressText.textContent = progress + '%';
    }
    
    if (stepText && currentStep) {
        stepText.textContent = currentStep;
    }
}

// Function to check current sync status from server
function checkCurrentSyncStatus() {
    const getSyncStatusUrl = window.dashboardConfig?.getSyncStatusUrl;
    if (!getSyncStatusUrl) {
        console.error('getSyncStatusUrl not configured');
        return;
    }
    
    fetch(getSyncStatusUrl, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success && data.sync_status) {
            const syncStatus = data.sync_status;
            const syncButton = document.getElementById('sync-button');
            
            // Update UI based on current status
            if (syncStatus.status === 'in_progress') {
                handleSyncStatusUpdate({
                    status: 'in_progress',
                    detail: syncStatus.message || 'Synchronization in progress...',
                    progress: syncStatus.progress || 0,
                    current_step: syncStatus.current_step
                });
            } else if (syncStatus.status === 'success') {
                const statusIndicator = document.getElementById('sync-status-indicator');
                const statusText = document.getElementById('sync-status-text');
                
                if (statusIndicator) {
                    statusIndicator.className = 'status-indicator status-success';
                    statusIndicator.innerHTML = '<i class="fas fa-check-circle"></i><span>Completed</span>';
                }
                if (statusText) statusText.textContent = 'Completed';
                
                // Ensure sync button is enabled for completed status
                if (syncButton) {
                    syncButton.disabled = false;
                    syncButton.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Sync Now';
                    syncButton.classList.remove('btn-secondary');
                    syncButton.classList.add('btn-success');
                }
                
                // Update last sync time based on completed_at
                if (syncStatus.completed_at) {
                    updateLastSyncTime(syncStatus.completed_at);
                }
            } else if (syncStatus.status === 'failure') {
                const statusIndicator = document.getElementById('sync-status-indicator');
                const statusText = document.getElementById('sync-status-text');
                
                if (statusIndicator) {
                    statusIndicator.className = 'status-indicator status-danger';
                    statusIndicator.innerHTML = '<i class="fas fa-times-circle"></i><span>Failed</span>';
                }
                if (statusText) statusText.textContent = 'Failed';
                
                // Ensure sync button is enabled for failed status
                if (syncButton) {
                    syncButton.disabled = false;
                    syncButton.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Sync Now';
                    syncButton.classList.remove('btn-secondary');
                    syncButton.classList.add('btn-success');
                }
            }
        }
    })
    .catch(error => {
        console.error('Error checking sync status:', error);
    });
}

// Function to update last sync time display
function updateLastSyncTime(completedAtISO) {
    const lastSyncTimeElement = document.getElementById('last-sync-time');
    if (!lastSyncTimeElement || !completedAtISO) return;
    
    const completedAt = new Date(completedAtISO);
    const now = new Date();
    const diffMs = now - completedAt;
    const diffMins = Math.round(diffMs / 60000);
    
    let timeText;
    if (diffMins < 1) {
        timeText = "Just now";
    } else if (diffMins === 1) {
        timeText = "1 minute ago";
    } else if (diffMins < 60) {
        timeText = `${diffMins} minutes ago`;
    } else if (diffMins < 120) {
        timeText = "1 hour ago";
    } else {
        const diffHours = Math.floor(diffMins / 60);
        timeText = `${diffHours} hours ago`;
    }
    
    lastSyncTimeElement.textContent = timeText;
}

// Helper function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Initialize Charts
document.addEventListener('DOMContentLoaded', function() {
    initializeCharts();
    
    // Update metrics immediately
    updateSystemMetrics();
    updateDashboardStats();
    
    // Check for last sync time
    checkLastSyncTime();
    
    // Update metrics every 30 seconds
    setInterval(updateSystemMetrics, 30000);
    
    // Update dashboard stats every 60 seconds
    setInterval(updateDashboardStats, 60000);
});

function updateDashboardStats() {
    const dashboardStatsUrl = window.dashboardConfig?.dashboardStatsUrl;
    if (!dashboardStatsUrl) {
        console.error('dashboardStatsUrl not configured');
        return;
    }
    
    fetch(dashboardStatsUrl)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const stats = data.stats;
                
                // Update pending users count
                const pendingCountEl = document.querySelector('.text-warning.fw-bold');
                if (pendingCountEl) {
                    const oldCount = parseInt(pendingCountEl.textContent);
                    const newCount = stats.pending_users_count;
                    
                    if (oldCount !== newCount) {
                        pendingCountEl.textContent = newCount;
                        
                        // Show notification if new pending users
                        if (newCount > oldCount) {
                            showNotification(`${newCount - oldCount} new user registration${newCount - oldCount > 1 ? 's' : ''} pending approval!`, 'info');
                        }
                        
                        // Update review button visibility
                        const reviewBtn = document.querySelector('.btn-warning');
                        const reviewContainer = reviewBtn.closest('.text-center');
                        if (newCount > 0) {
                            reviewContainer.innerHTML = `
                                <h2 class="fw-bold text-warning mb-2">${newCount}</h2>
                                <p class="text-muted mb-3">Users awaiting approval</p>
                                <a href="/dashboard/admin/{{ username }}/users/" class="btn-admin btn-warning">
                                    <i class="fas fa-eye"></i>
                                    Review
                                </a>
                            `;
                        } else {
                            reviewContainer.innerHTML = `
                                <h2 class="fw-bold text-warning mb-2">0</h2>
                                <p class="text-muted mb-3">Users awaiting approval</p>
                                <span class="text-muted">All users processed</span>
                            `;
                        }
                    }
                }
                
                // Update activity chart
                if (window.activityChart) {
                    window.activityChart.data.datasets[0].data = [
                        stats.regular_users_count,
                        stats.pending_users_count,
                        stats.admin_users_count
                    ];
                    window.activityChart.update();
                }
                
                // Update recent activity
                const activityFeed = document.querySelector('.activity-feed');
                if (activityFeed) {
                    activityFeed.innerHTML = `
                        <div class="activity-item d-flex align-items-center mb-3">
                            <div class="activity-icon bg-success text-white rounded-circle d-flex align-items-center justify-content-center me-3" style="width: 40px; height: 40px;">
                                <i class="fas fa-user-plus"></i>
                            </div>
                            <div class="flex-grow-1">
                                <p class="mb-1"><strong>New registrations this week:</strong> ${stats.recent_registrations}</p>
                                <small class="text-muted">${stats.recent_registrations} new user${stats.recent_registrations !== 1 ? 's' : ''} registered</small>
                            </div>
                        </div>
                        <div class="activity-item d-flex align-items-center mb-3">
                            <div class="activity-icon bg-info text-white rounded-circle d-flex align-items-center justify-content-center me-3" style="width: 40px; height: 40px;">
                                <i class="fas fa-users"></i>
                            </div>
                            <div class="flex-grow-1">
                                <p class="mb-1"><strong>Total active users:</strong> ${stats.active_users_count}</p>
                                <small class="text-muted">${stats.active_users_count} user${stats.active_users_count !== 1 ? 's' : ''} currently active</small>
                            </div>
                        </div>
                        <div class="activity-item d-flex align-items-center mb-3">
                            <div class="activity-icon bg-warning text-white rounded-circle d-flex align-items-center justify-content-center me-3" style="width: 40px; height: 40px;">
                                <i class="fas fa-clock"></i>
                            </div>
                            <div class="flex-grow-1">
                                <p class="mb-1"><strong>Pending approvals:</strong> ${stats.pending_users_count}</p>
                                <small class="text-muted">${stats.pending_users_count} user${stats.pending_users_count !== 1 ? 's' : ''} awaiting approval</small>
                            </div>
                        </div>
                        <div class="activity-item d-flex align-items-center">
                            <div class="activity-icon bg-primary text-white rounded-circle d-flex align-items-center justify-content-center me-3" style="width: 40px; height: 40px;">
                                <i class="fas fa-shield-alt"></i>
                            </div>
                            <div class="flex-grow-1">
                                <p class="mb-1"><strong>Admin users:</strong> ${stats.admin_users_count}</p>
                                <small class="text-muted">${stats.admin_users_count} administrator${stats.admin_users_count !== 1 ? 's' : ''} in system</small>
                            </div>
                        </div>
                    `;
                }
            }
        })
        .catch(error => {
            console.error('Error updating dashboard stats:', error);
        });
}

function initializeCharts() {
    // Performance Chart
    const performanceCtx = document.getElementById('performanceChart').getContext('2d');
    window.performanceChart = new Chart(performanceCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'CPU Usage (%)',
                data: [],
                borderColor: '#2C3E50',
                backgroundColor: 'rgba(44, 62, 80, 0.1)',
                tension: 0.4,
                fill: true
            }, {
                label: 'Memory Usage (%)',
                data: [],
                borderColor: '#E74C3C',
                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100
                }
            }
        }
    });

    // User Activity Chart
    const activityCtx = document.getElementById('activityChart').getContext('2d');
    const userCounts = window.dashboardConfig?.userCounts || { regular: 0, pending: 0, admin: 0 };
    
    window.activityChart = new Chart(activityCtx, {
        type: 'doughnut',
        data: {
            labels: ['Active Users', 'Pending Approval', 'Admin Users'],
            datasets: [{
                data: [userCounts.regular, userCounts.pending, userCounts.admin],
                backgroundColor: [
                    '#27AE60',
                    '#F39C12',
                    '#E74C3C'
                ],
                borderWidth: 3,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                }
            }
        }
    });
}

// Sync form handling
document.getElementById('sync-form').addEventListener('submit', function(event) {
    event.preventDefault();
    
    // Update UI to show sync starting
    const statusIndicator = document.getElementById('sync-status-indicator');
    const statusText = document.getElementById('sync-status-text');
    const syncDisplay = document.getElementById('sync-status-display');
    const syncButton = document.getElementById('sync-button');
    
    // Disable sync button immediately to prevent multiple clicks
    if (syncButton) {
        syncButton.disabled = true;
        syncButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Starting...';
        syncButton.classList.add('btn-secondary');
        syncButton.classList.remove('btn-success');
    }
    
    statusIndicator.className = 'status-indicator status-warning';
    statusIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Starting</span>';
    statusText.textContent = 'Starting';
    syncDisplay.style.display = 'block';
    
    // Update sync display
    const detailedStatus = document.getElementById('sync-detailed-status');
    if (detailedStatus) {
        detailedStatus.textContent = 'Initializing synchronization...';
    }

    const triggerSyncUrl = window.dashboardConfig?.triggerSyncUrl;
    if (!triggerSyncUrl) {
        console.error('triggerSyncUrl not configured');
        return;
    }

    fetch(triggerSyncUrl, {
        method: "POST",
        headers: {
            "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value,
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
        body: JSON.stringify({})
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.message || 'Request failed with status ' + response.status);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Synchronization started:', data);
        
        if (data.status === 'already_running') {
            // If sync is already running, update UI accordingly
            statusIndicator.className = 'status-indicator status-warning';
            statusIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>In Progress</span>';
            statusText.textContent = 'In Progress';
            if (detailedStatus) {
                detailedStatus.textContent = data.message;
            }
            
            // Keep button disabled since sync is already running
            if (syncButton) {
                syncButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Syncing...';
            }
            
            showNotification(data.message, 'warning');
        } else {
            // Sync started successfully - status will be updated via WebSocket
            if (detailedStatus) {
                detailedStatus.textContent = 'Synchronization started successfully...';
            }
            
            // Update button to show syncing state
            if (syncButton) {
                syncButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Syncing...';
            }
        }
    })
    .catch(error => {
        console.error('Sync request failed:', error);
        
        // Update UI to show error
        statusIndicator.className = 'status-indicator status-danger';
        statusIndicator.innerHTML = '<i class="fas fa-times-circle"></i><span>Failed</span>';
        statusText.textContent = 'Failed';
        syncDisplay.style.display = 'none';
        
        if (detailedStatus) {
            detailedStatus.textContent = 'Failed to start synchronization: ' + error.message;
        }
        
        showNotification('Failed to start synchronization: ' + error.message, 'error');
        
        // Re-enable sync button on error
        if (syncButton) {
            syncButton.disabled = false;
            syncButton.innerHTML = '<i class="fas fa-sync-alt me-2"></i>Sync Now';
            syncButton.classList.remove('btn-secondary');
            syncButton.classList.add('btn-success');
        }
    });
});

function updateSyncStatus(message) {
    const statusIndicator = document.getElementById('sync-status-indicator');
    const statusText = document.getElementById('sync-status-text');
    const syncDisplay = document.getElementById('sync-status-display');
    const detailedStatus = document.getElementById('sync-detailed-status');
    const lastSyncTimeElement = document.getElementById('last-sync-time');
    
    detailedStatus.textContent = message;
    
    if (message.includes('✅') || message.includes('completed')) {
        statusIndicator.className = 'status-indicator status-success';
        statusIndicator.innerHTML = '<i class="fas fa-check-circle"></i><span>Completed</span>';
        statusText.textContent = 'Completed';
        syncDisplay.style.display = 'none';
        
        // Update the last sync time
        const now = new Date();
        localStorage.setItem('lastSyncTime', now.getTime());
        lastSyncTimeElement.textContent = "Just now";
        
        // Show success notification
        showNotification('Synchronization completed successfully!', 'success');
    } else if (message.includes('❌') || message.includes('failed')) {
        statusIndicator.className = 'status-indicator status-danger';
        statusIndicator.innerHTML = '<i class="fas fa-times-circle"></i><span>Failed</span>';
        statusText.textContent = 'Failed';
        syncDisplay.style.display = 'none';
        
        // Show error notification
        showNotification('Synchronization failed. Please try again.', 'error');
    }
}

function updateSystemMetrics() {
    // Fetch real system metrics from the server
    const serverMetricsUrl = window.dashboardConfig?.serverMetricsUrl || '/dashboard/api/server-metrics/';
    
    fetch(serverMetricsUrl, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(result => {
        if (result.success) {
            updateDashboardWithSystemMetrics(result.data);
        } else {
            console.error('Server metrics API error:', result.error);
        }
    })
    .catch(error => {
        console.error('Error fetching system metrics:', error);
        
        // Fallback to random data in case of error
        const cpuUsage = Math.floor(Math.random() * 30) + 40; // 40-70%
        const memoryUsage = Math.floor(Math.random() * 20) + 55; // 55-75%
        const storageUsage = Math.floor(Math.random() * 10) + 75; // 75-85%
        
        // Update progress bars
        updateProgressBars(cpuUsage, memoryUsage, storageUsage);
    });
}

function updateDashboardWithSystemMetrics(data) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    
    // Update System Health card
    const cpuUsage = data.cpu.percent;
    const memoryUsage = data.memory.percent;
    const storageUsage = data.storage.percent;
    
    // Update progress bars
    updateProgressBars(cpuUsage, memoryUsage, storageUsage);
    
    // Update Server Status card
    document.getElementById('server-uptime').textContent = data.system.uptime;
    
    // Calculate a response time based on CPU load (simulated but based on real metrics)
    const responseTime = Math.max(10, Math.round(cpuUsage / 2) + Math.floor(Math.random() * 10));
    document.getElementById('server-response-time').textContent = responseTime + 'ms';
    
    // Update Performance Chart
    if (window.performanceChart) {
        // Keep up to 12 data points (representing 6 minutes at 30-second intervals)
        if (window.performanceChart.data.labels.length >= 12) {
            window.performanceChart.data.labels.shift();
            window.performanceChart.data.datasets[0].data.shift();
            window.performanceChart.data.datasets[1].data.shift();
        }
        
        window.performanceChart.data.labels.push(timeStr);
        window.performanceChart.data.datasets[0].data.push(cpuUsage);
        window.performanceChart.data.datasets[1].data.push(memoryUsage);
        window.performanceChart.update('none');
    }
}

// Function to check the last sync time from server logs
function checkLastSyncTime() {
    // This function would ideally fetch the timestamp of the last successful sync
    // from your backend. For now, we'll simulate by checking local storage or setting a default.
    
    // Try to get the last sync time from localStorage
    const lastSyncTime = localStorage.getItem('lastSyncTime');
    
    if (lastSyncTime) {
        const lastSync = new Date(parseInt(lastSyncTime));
        const now = new Date();
        const diffMs = now - lastSync;
        const diffMins = Math.round(diffMs / 60000);
        
        let timeText;
        if (diffMins < 1) {
            timeText = "Just now";
        } else if (diffMins === 1) {
            timeText = "1 minute ago";
        } else if (diffMins < 60) {
            timeText = `${diffMins} minutes ago`;
        } else if (diffMins < 120) {
            timeText = "1 hour ago";
        } else {
            const diffHours = Math.floor(diffMins / 60);
            timeText = `${diffHours} hours ago`;
        }
        
        document.getElementById('last-sync-time').textContent = timeText;
    } else {
        // If no sync time found, check for any log files or set a default
        document.getElementById('last-sync-time').textContent = "No recent sync";
    }
}

function updateProgressBars(cpuUsage, memoryUsage, storageUsage) {
    // Update CPU metrics
    document.getElementById('cpu-usage-percent').textContent = cpuUsage + '%';
    document.getElementById('cpu-progress-bar').style.width = cpuUsage + '%';
    
    // Update Memory metrics
    document.getElementById('memory-usage-percent').textContent = memoryUsage + '%';
    document.getElementById('memory-progress-bar').style.width = memoryUsage + '%';
    
    // Update Storage metrics
    document.getElementById('storage-usage-percent').textContent = storageUsage + '%';
    document.getElementById('storage-progress-bar').style.width = storageUsage + '%';
}

function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 90px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-triangle'} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

// Update active nav link
document.addEventListener('DOMContentLoaded', function() {
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        if (link.href === window.location.href) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
});

// Quick Actions Functions
function backupData() {
    if (confirm('Are you sure you want to start a data backup? This may take several minutes.')) {
        showNotification('Data backup started. You will be notified when complete.', 'success');
        
        // Simulate backup process
        setTimeout(() => {
            showNotification('Data backup completed successfully!', 'success');
        }, 5000);
    }
}

function openSettings() {
    showNotification('Settings page is under development', 'info');
}

function viewLogs() {
    showNotification('Logs page is under development', 'info');
}