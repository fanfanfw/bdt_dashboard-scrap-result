// Global chart variables
let performanceChart = null;
let userActivityChart = null;

document.addEventListener('DOMContentLoaded', function() {
    initializeCharts();
    updateDashboardStats();
    updateSystemMetrics();

    // Update metrics every 30 seconds
    setInterval(() => {
        updateSystemMetrics();
        updatePerformanceChart();
    }, 30000);

    // Update dashboard stats every 60 seconds
    setInterval(() => {
        updateDashboardStats();
        updateUserActivityChart();
    }, 60000);
});

function updateDashboardStats() {
    const dashboardStatsUrl = window.dashboardConfig?.dashboardStatsUrl;
    if (!dashboardStatsUrl) {
        console.error('dashboardStatsUrl not configured');
        return;
    }

    fetch(dashboardStatsUrl, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update total listings
            const totalListingsElement = document.getElementById('total-listings');
            if (totalListingsElement) {
                totalListingsElement.textContent = data.stats.total_listings?.toLocaleString() || '0';
            }

            // Update active listings
            const activeListingsElement = document.getElementById('active-listings');
            if (activeListingsElement) {
                activeListingsElement.textContent = data.stats.active_listings?.toLocaleString() || '0';
            }

            // Update sold listings
            const soldListingsElement = document.getElementById('sold-listings');
            if (soldListingsElement) {
                soldListingsElement.textContent = data.stats.sold_listings?.toLocaleString() || '0';
            }

            // Update today's listings
            const todayListingsElement = document.getElementById('today-listings');
            if (todayListingsElement) {
                todayListingsElement.textContent = data.stats.today_listings?.toLocaleString() || '0';
            }

            // Update percentage changes if available
            if (data.stats.changes) {
                updatePercentageChanges(data.stats.changes);
            }

            // Update user counts for charts if available
            if (data.stats.user_counts) {
                window.dashboardConfig.userCounts = data.stats.user_counts;
            }
        }
    })
    .catch(error => {
        console.error('Error fetching dashboard stats:', error);
    });
}

function updatePercentageChanges(changes) {
    // Update total change
    const totalChangeElement = document.getElementById('total-change');
    if (totalChangeElement && changes.total_change !== undefined) {
        const change = changes.total_change;
        totalChangeElement.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`;
        totalChangeElement.className = `change-text ${change >= 0 ? 'positive' : 'negative'}`;
    }

    // Update active change
    const activeChangeElement = document.getElementById('active-change');
    if (activeChangeElement && changes.active_change !== undefined) {
        const change = changes.active_change;
        activeChangeElement.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`;
        activeChangeElement.className = `change-text ${change >= 0 ? 'positive' : 'negative'}`;
    }

    // Update sold change
    const soldChangeElement = document.getElementById('sold-change');
    if (soldChangeElement && changes.sold_change !== undefined) {
        const change = changes.sold_change;
        soldChangeElement.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`;
        soldChangeElement.className = `change-text ${change >= 0 ? 'positive' : 'negative'}`;
    }

    // Update today change
    const todayChangeElement = document.getElementById('today-change');
    if (todayChangeElement && changes.today_change !== undefined) {
        const change = changes.today_change;
        todayChangeElement.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(1)}%`;
        todayChangeElement.className = `change-text ${change >= 0 ? 'positive' : 'negative'}`;
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
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateServerStatus(data.data);
        } else {
            console.error('Server metrics API error:', data.error);
        }
    })
    .catch(error => {
        console.error('Error fetching server metrics:', error);
    });
}

function updateServerStatus(metrics) {
    // Update server uptime
    const uptimeElement = document.getElementById('server-uptime');
    if (uptimeElement && metrics.system) {
        uptimeElement.textContent = metrics.system.uptime;
    }

    // Update response time (simulated)
    const responseTimeElement = document.getElementById('server-response-time');
    if (responseTimeElement) {
        responseTimeElement.textContent = `${Math.floor(Math.random() * 50) + 20}ms`;
    }

    // Update CPU usage percentage and progress
    const cpuPercentElement = document.getElementById('cpu-usage-percent');
    const cpuProgressBar = document.getElementById('cpu-progress-bar');
    if (cpuPercentElement && metrics.cpu) {
        cpuPercentElement.textContent = `${metrics.cpu.percent}%`;
        if (cpuProgressBar) {
            cpuProgressBar.style.width = `${metrics.cpu.percent}%`;
        }
    }

    // Update Memory usage percentage and progress
    const memoryPercentElement = document.getElementById('memory-usage-percent');
    const memoryProgressBar = document.getElementById('memory-progress-bar');
    if (memoryPercentElement && metrics.memory) {
        memoryPercentElement.textContent = `${metrics.memory.percent}%`;
        if (memoryProgressBar) {
            memoryProgressBar.style.width = `${metrics.memory.percent}%`;
        }
    }

    // Update Storage usage percentage and progress
    const storagePercentElement = document.getElementById('storage-usage-percent');
    const storageProgressBar = document.getElementById('storage-progress-bar');
    if (storagePercentElement && metrics.storage) {
        storagePercentElement.textContent = `${metrics.storage.percent}%`;
        if (storageProgressBar) {
            storageProgressBar.style.width = `${metrics.storage.percent}%`;
        }
    }

    // Update health status based on metrics
    updateHealthStatus(metrics);
}

function updateHealthStatus(metrics) {
    const healthElement = document.getElementById('system-health');
    if (!healthElement) return;

    let statusText = 'Good';
    let statusClass = 'text-success';

    // Check various thresholds
    if (metrics.cpu?.percent > 80 || metrics.memory?.percent > 85 || metrics.storage?.percent > 90) {
        statusText = 'Warning';
        statusClass = 'text-warning';
    }

    if (metrics.cpu?.percent > 95 || metrics.memory?.percent > 95 || metrics.storage?.percent > 95) {
        statusText = 'Critical';
        statusClass = 'text-danger';
    }

    healthElement.textContent = statusText;
    healthElement.className = `fw-bold ${statusClass}`;
}


function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 1050; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    // Add to page
    document.body.appendChild(notification);

    // Auto remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 5000);
}

// CSRF token helper
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

// Chart initialization functions
function initializeCharts() {
    initializePerformanceChart();
    initializeUserActivityChart();
}

function initializePerformanceChart() {
    const ctx = document.getElementById('performanceChart');
    if (!ctx) return;

    // Generate sample data for the last 24 hours
    const labels = [];
    const cpuData = [];
    const memoryData = [];

    for (let i = 23; i >= 0; i--) {
        const hour = new Date();
        hour.setHours(hour.getHours() - i);
        labels.push(hour.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }));

        // Generate realistic-looking data
        cpuData.push(Math.floor(Math.random() * 30) + 20); // 20-50%
        memoryData.push(Math.floor(Math.random() * 20) + 50); // 50-70%
    }

    performanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'CPU Usage (%)',
                data: cpuData,
                borderColor: '#3498db',
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }, {
                label: 'Memory Usage (%)',
                data: memoryData,
                borderColor: '#e74c3c',
                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
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
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                },
                x: {
                    ticks: {
                        maxTicksLimit: 8
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
}

function initializeUserActivityChart() {
    const ctx = document.getElementById('activityChart');
    if (!ctx) return;

    // Get user counts from config
    const userCounts = window.dashboardConfig?.userCounts || { regular: 0, pending: 0, admin: 0 };

    userActivityChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Active Users', 'Pending Approval', 'Admin Users'],
            datasets: [{
                data: [userCounts.regular, userCounts.pending, userCounts.admin],
                backgroundColor: [
                    '#27ae60',  // Green for active
                    '#f39c12',  // Orange for pending
                    '#e74c3c'   // Red for admin
                ],
                borderWidth: 2,
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

function updatePerformanceChart() {
    if (!performanceChart) return;

    // Add new data point (simulate real-time data)
    const now = new Date();
    const timeLabel = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

    // Remove oldest data point and add new one
    performanceChart.data.labels.shift();
    performanceChart.data.labels.push(timeLabel);

    // Update CPU data
    performanceChart.data.datasets[0].data.shift();
    performanceChart.data.datasets[0].data.push(Math.floor(Math.random() * 30) + 20);

    // Update Memory data
    performanceChart.data.datasets[1].data.shift();
    performanceChart.data.datasets[1].data.push(Math.floor(Math.random() * 20) + 50);

    performanceChart.update('none'); // Update without animation for smooth real-time feel
}

function updateUserActivityChart() {
    if (!userActivityChart) return;

    // Get updated user counts from latest dashboard stats
    const userCounts = window.dashboardConfig?.userCounts || { regular: 0, pending: 0, admin: 0 };

    userActivityChart.data.datasets[0].data = [userCounts.regular, userCounts.pending, userCounts.admin];
    userActivityChart.update();
}