document.addEventListener('DOMContentLoaded', function() {
  let logSocket = null;
  let currentLogId = null;
  let autoScroll = true;
  let wordWrap = true;
  const logContent = document.getElementById('logContent');
  const logViewerCard = document.getElementById('logViewerCard');
  const logViewerTitle = document.getElementById('logViewerTitle');
  const connectionStatus = document.getElementById('connectionStatus');
  const autoScrollToggle = document.getElementById('autoScrollToggle');
  const clearLogsBtn = document.getElementById('clearLogs');
  const downloadLogsBtn = document.getElementById('downloadLogs');
  const closeLogViewerBtn = document.getElementById('closeLogViewer');
  const refreshLogsBtn = document.getElementById('refreshLogs');
  const refreshProcessesBtn = document.getElementById('refreshProcesses');
  const toggleWrapBtn = document.getElementById('toggleWrap');
  
  // Setup event listeners
  document.querySelectorAll('.view-log').forEach(button => {
    button.addEventListener('click', function() {
      const logId = this.getAttribute('data-log-id');
      openLogViewer(logId);
    });
  });
  
  closeLogViewerBtn.addEventListener('click', function() {
    closeLogViewer();
  });
  
  autoScrollToggle.addEventListener('click', function() {
    autoScroll = !autoScroll;
    this.innerHTML = autoScroll ? 
      '<i class="fas fa-scroll"></i> Auto-scroll: ON' : 
      '<i class="fas fa-scroll"></i> Auto-scroll: OFF';
  });
  
  toggleWrapBtn.addEventListener('click', function() {
    wordWrap = !wordWrap;
    logContent.style.whiteSpace = wordWrap ? 'pre-wrap' : 'pre';
    this.innerHTML = wordWrap ? 
      '<i class="fas fa-exchange-alt"></i> Toggle Word Wrap' : 
      '<i class="fas fa-exchange-alt"></i> Word Wrap: OFF';
  });
  
  clearLogsBtn.addEventListener('click', function() {
    logContent.textContent = '';
  });
  
  downloadLogsBtn.addEventListener('click', function() {
    const logName = logViewerTitle.textContent.replace('Log File: ', '');
    const blob = new Blob([logContent.textContent], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${logName}_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });
  
  refreshLogsBtn.addEventListener('click', function() {
    window.location.reload();
  });
  
  refreshProcessesBtn?.addEventListener('click', function() {
    window.location.reload();
  });
  
  function openLogViewer(logId) {
    // Close existing connection if any
    if (logSocket) {
      logSocket.close();
    }
    
    currentLogId = logId;
    
    // Find the log file card element by data-log-id
    const logCard = document.querySelector(`.view-log[data-log-id="${logId}"]`).closest('.card');
    const logName = logCard.querySelector('.card-title').innerText.trim();
    
    // Update UI
    logViewerTitle.textContent = `Log File: ${logName}`;
    logContent.textContent = 'Connecting to log stream...';
    logViewerCard.style.display = 'block';
    connectionStatus.innerHTML = '<i class="fas fa-circle me-1"></i> Connecting...';
    connectionStatus.className = 'badge bg-warning';
    
    // Scroll to log viewer
    logViewerCard.scrollIntoView({ behavior: 'smooth' });
    
    // Connect to WebSocket
    const socketProtocol = window.logsConfig?.wsScheme || (window.location.protocol === 'https:' ? 'wss:' : 'ws:');
    const socketHost = window.logsConfig?.wsHost || window.location.host;
    const socketUrl = `${socketProtocol}//${socketHost}/ws/cronlogs/${logId}/`;
    
    logSocket = new WebSocket(socketUrl);
    
    logSocket.onopen = function(e) {
      connectionStatus.innerHTML = '<i class="fas fa-circle me-1"></i> Connected (Live)';
      connectionStatus.className = 'badge bg-success';
      
      // Add connection info to log
      logContent.textContent += '\n[INFO] Real-time log streaming started using tail -f';
    };
    
    logSocket.onmessage = function(e) {
      const data = JSON.parse(e.data);
      
      if (data.error) {
        logContent.textContent += `\n[ERROR] ${data.error}`;
        connectionStatus.innerHTML = '<i class="fas fa-circle me-1"></i> Error';
        connectionStatus.className = 'badge bg-danger';
      } 
      else if (data.message) {
        logContent.textContent += `\n[INFO] ${data.message}`;
      }
      else if (data.log) {
        // For initial log or clear and replace
        if (data.type === 'initial') {
          logContent.textContent = data.log;
        } 
        // For updates - replace entire content with latest 500 lines
        else {
          logContent.textContent = data.log;
          
          // Highlight new content if available
          if (data.new_content) {
            // Add a separator for new content (visual indicator)
            const lines = logContent.textContent.split('\n');
            const newLines = data.new_content.split('\n').filter(line => line.trim());
            
            // Flash the log container briefly to indicate new content
            const container = logContent.parentElement;
            container.style.boxShadow = '0 0 10px rgba(0, 255, 0, 0.5)';
            setTimeout(() => {
              container.style.boxShadow = '';
            }, 300);
          }
        }
        
        // Auto-scroll to bottom if enabled
        if (autoScroll) {
          const container = logContent.parentElement;
          container.scrollTop = container.scrollHeight;
        }
      }
    };
    
    logSocket.onclose = function(e) {
      connectionStatus.innerHTML = '<i class="fas fa-circle me-1"></i> Disconnected';
      connectionStatus.className = 'badge bg-secondary';
      
      if (e.wasClean) {
        logContent.textContent += `\n[INFO] Log stream closed cleanly (code=${e.code})`;
      } else {
        logContent.textContent += '\n[INFO] Log stream connection lost';
      }
    };
    
    logSocket.onerror = function(e) {
      connectionStatus.innerHTML = '<i class="fas fa-circle me-1"></i> Error';
      connectionStatus.className = 'badge bg-danger';
      logContent.textContent += '\n[ERROR] WebSocket error occurred';
    };
  }
  
  function closeLogViewer() {
    if (logSocket) {
      logSocket.close();
      logSocket = null;
    }
    logViewerCard.style.display = 'none';
    currentLogId = null;
  }
});