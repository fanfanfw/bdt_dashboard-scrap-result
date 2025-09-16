let realtimeChart, networkChart, cpuChart, memoryChart, storageChart;
let isRealTimeActive = true;
let realtimeData = {
  labels: [],
  cpu: [],
  memory: [],
  storage: []
};

// Store previous network stats for calculating speed
let previousNetworkStats = null;

document.addEventListener('DOMContentLoaded', function() {
  initializeCharts();
  startRealTimeUpdates();
  // Initial load
  fetchServerMetrics();
});

function initializeCharts() {
  // CPU Doughnut Chart
  const cpuCtx = document.getElementById('cpuChart').getContext('2d');
  cpuChart = new Chart(cpuCtx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [0, 100],
        backgroundColor: ['#3498DB', 'rgba(52, 73, 94, 0.1)'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: {
        legend: { display: false }
      }
    }
  });

  // Memory Doughnut Chart
  const memoryCtx = document.getElementById('memoryChart').getContext('2d');
  memoryChart = new Chart(memoryCtx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [0, 100],
        backgroundColor: ['#F39C12', 'rgba(52, 73, 94, 0.1)'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: {
        legend: { display: false }
      }
    }
  });

  // Storage Doughnut Chart
  const storageCtx = document.getElementById('storageChart').getContext('2d');
  storageChart = new Chart(storageCtx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [0, 100],
        backgroundColor: ['#E74C3C', 'rgba(52, 73, 94, 0.1)'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: false,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: {
        legend: { display: false }
      }
    }
  });

  // Real-time Performance Chart
  const realtimeCtx = document.getElementById('realtimeChart').getContext('2d');
  realtimeChart = new Chart(realtimeCtx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'CPU %',
        data: [],
        borderColor: '#3498DB',
        backgroundColor: 'rgba(52, 152, 219, 0.1)',
        tension: 0.4,
        fill: false
      }, {
        label: 'Memory %',
        data: [],
        borderColor: '#F39C12',
        backgroundColor: 'rgba(243, 156, 18, 0.1)',
        tension: 0.4,
        fill: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          max: 100
        },
        x: {
          display: true
        }
      },
      plugins: {
        legend: {
          position: 'top'
        }
      }
    }
  });

  // Network Activity Chart
  const networkCtx = document.getElementById('networkChart').getContext('2d');
  networkChart = new Chart(networkCtx, {
    type: 'bar',
    data: {
      labels: ['Upload (KB/s)', 'Download (KB/s)'],
      datasets: [{
        label: 'Current Speed',
        data: [0, 0],
        backgroundColor: ['#27AE60', '#E74C3C'],
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top'
        }
      },
      scales: {
        y: {
          beginAtZero: true
        }
      }
    }
  });
}

function startRealTimeUpdates() {
  if (!isRealTimeActive) return;
  
  // Update every 3 seconds
  setInterval(() => {
    if (isRealTimeActive) {
      fetchServerMetrics();
    }
  }, 3000);
}

async function fetchServerMetrics() {
  try {
    const serverMetricsUrl = window.serverMonitorConfig?.serverMetricsUrl;
    if (!serverMetricsUrl) {
      console.error('serverMetricsUrl not configured');
      return;
    }
    
    const response = await fetch(serverMetricsUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
      }
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const result = await response.json();
    
    if (result.success) {
      updateMetricsWithRealData(result.data);
    } else {
      console.error('Server metrics API error:', result.error);
      showNotification('Failed to fetch server metrics: ' + result.error, 'error');
    }
  } catch (error) {
    console.error('Error fetching server metrics:', error);
    showNotification('Error connecting to server metrics API', 'error');
  }
}

function updateMetricsWithRealData(data) {
  const now = new Date();
  const timeStr = now.toLocaleTimeString();
  
  // Update CPU metrics
  const cpuUsage = data.cpu.percent;
  document.getElementById('cpu-percentage').textContent = cpuUsage + '%';
  document.getElementById('cpu-cores').textContent = data.cpu.count_logical;
  document.getElementById('load-avg').textContent = data.cpu.load_avg;
  
  // Update Memory metrics
  const memoryUsage = data.memory.percent;
  document.getElementById('memory-percentage').textContent = memoryUsage + '%';
  document.getElementById('memory-used').textContent = data.memory.used_gb + 'GB';
  document.getElementById('memory-total').textContent = data.memory.total_gb + 'GB';
  
  // Update Storage metrics
  const storageUsage = data.storage.percent;
  document.getElementById('storage-percentage').textContent = storageUsage + '%';
  document.getElementById('storage-used').textContent = data.storage.used_gb + 'GB';
  document.getElementById('storage-total').textContent = data.storage.total_gb + 'GB';
  
  // Update doughnut charts
  cpuChart.data.datasets[0].data = [cpuUsage, 100 - cpuUsage];
  cpuChart.update('none');
  
  memoryChart.data.datasets[0].data = [memoryUsage, 100 - memoryUsage];
  memoryChart.update('none');
  
  storageChart.data.datasets[0].data = [storageUsage, 100 - storageUsage];
  storageChart.update('none');
  
  // Update real-time chart
  realtimeData.labels.push(timeStr);
  realtimeData.cpu.push(cpuUsage);
  realtimeData.memory.push(memoryUsage);
  
  // Keep only last 20 data points
  if (realtimeData.labels.length > 20) {
    realtimeData.labels.shift();
    realtimeData.cpu.shift();
    realtimeData.memory.shift();
  }
  
  realtimeChart.data.labels = realtimeData.labels;
  realtimeChart.data.datasets[0].data = realtimeData.cpu;
  realtimeChart.data.datasets[1].data = realtimeData.memory;
  realtimeChart.update('none');
  
  // Calculate and update network speed
  if (previousNetworkStats) {
    const timeDiff = 3; // 3 seconds interval
    const uploadSpeed = Math.round((data.network.bytes_sent - previousNetworkStats.bytes_sent) / (1024 * timeDiff));
    const downloadSpeed = Math.round((data.network.bytes_recv - previousNetworkStats.bytes_recv) / (1024 * timeDiff));
    
    networkChart.data.datasets[0].data = [Math.max(0, uploadSpeed), Math.max(0, downloadSpeed)];
    networkChart.update('none');
  }
  
  // Store current network stats for next calculation
  previousNetworkStats = {
    bytes_sent: data.network.bytes_sent,
    bytes_recv: data.network.bytes_recv
  };
  
  // Update other system metrics
  document.getElementById('uptime').textContent = data.system.uptime;
  
  // Update process table
  updateProcessTable(data.processes);
  
  // Update response time with a simulated value based on actual performance
  const simulatedResponseTime = Math.max(10, Math.round(cpuUsage / 2 + Math.random() * 20));
  document.getElementById('response-time').textContent = simulatedResponseTime + 'ms';
  
  // Update requests per hour (simulated based on system load)
  const simulatedRequests = Math.round(1000 + (100 - cpuUsage) * 10 + Math.random() * 200);
  document.getElementById('requests').textContent = simulatedRequests.toLocaleString();
}

function updateProcessTable(processes) {
  const tbody = document.getElementById('processes-table');
  tbody.innerHTML = '';
  
  processes.slice(0, 10).forEach(process => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${process.pid}</td>
      <td>
        <div class="d-flex align-items-center">
          <i class="fas fa-cog me-2 text-primary"></i>
          <strong>${process.name}</strong>
        </div>
      </td>
      <td>${process.username}</td>
      <td>
        <div class="d-flex align-items-center">
          <div class="progress me-2" style="width: 60px; height: 6px;">
            <div class="progress-bar bg-success" style="width: ${Math.min(process.cpu_percent * 2, 100)}%"></div>
          </div>
          <span>${process.cpu_percent}%</span>
        </div>
      </td>
      <td>
        <div class="d-flex align-items-center">
          <div class="progress me-2" style="width: 60px; height: 6px;">
            <div class="progress-bar bg-warning" style="width: ${Math.min(process.memory_percent * 2, 100)}%"></div>
          </div>
          <span>${process.memory_percent}%</span>
        </div>
      </td>
      <td>
        <span class="status-indicator ${process.status === 'running' ? 'status-success' : 'status-warning'}">
          <i class="fas fa-${process.status === 'running' ? 'play' : 'pause'}"></i>
          ${process.status}
        </span>
      </td>
      <td>
        <button class="btn-admin btn-danger btn-sm" onclick="killProcess(${process.pid})">
          <i class="fas fa-stop"></i>
        </button>
      </td>
    `;
    tbody.appendChild(row);
  });
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

function toggleRealTime() {
  isRealTimeActive = !isRealTimeActive;
  const icon = document.getElementById('realtime-icon');
  const text = document.getElementById('realtime-text');
  
  if (isRealTimeActive) {
    icon.className = 'fas fa-pause';
    text.textContent = 'Pause';
    startRealTimeUpdates();
  } else {
    icon.className = 'fas fa-play';
    text.textContent = 'Resume';
  }
}

function refreshProcesses() {
  // Fetch fresh data
  fetchServerMetrics();
  showNotification('Process list refreshed', 'success');
  
  // Add animation effect
  const table = document.getElementById('processes-table');
  table.style.opacity = '0.5';
  setTimeout(() => {
    table.style.opacity = '1';
  }, 500);
}

function killProcess(pid) {
  if (confirm(`Are you sure you want to kill process ${pid}?`)) {
    // In a real implementation, you would send a request to kill the process
    // For now, just show a notification
    showNotification(`Process termination requested for PID ${pid}`, 'warning');
    
    // Note: Actual process killing would require additional backend API
    // and proper permissions/security measures
  }
}

function showNotification(message, type) {
  const notification = document.createElement('div');
  notification.className = `alert alert-${type === 'success' ? 'success' : type === 'warning' ? 'warning' : 'danger'} alert-dismissible fade show position-fixed`;
  notification.style.cssText = 'top: 90px; right: 20px; z-index: 9999; min-width: 300px;';
  notification.innerHTML = `
    <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : 'exclamation-triangle'} me-2"></i>
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  `;
  
  document.body.appendChild(notification);
  
  setTimeout(() => {
    if (notification.parentElement) {
      notification.remove();
    }
  }, 3000);
}