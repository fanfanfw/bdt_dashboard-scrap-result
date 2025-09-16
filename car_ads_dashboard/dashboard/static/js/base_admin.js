// Theme Toggle
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;
    
    // Check for saved theme preference or default to light mode
    const currentTheme = localStorage.getItem('adminTheme') || 'light';
    if (currentTheme === 'dark') {
      body.classList.add('dark-mode');
      themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
    }

    themeToggle.addEventListener('click', function() {
      body.classList.toggle('dark-mode');
      const isDark = body.classList.contains('dark-mode');
      
      // Update icon
      themeToggle.innerHTML = isDark ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
      
      // Save preference
      localStorage.setItem('adminTheme', isDark ? 'dark' : 'light');
    });

    // Sidebar Toggle
    const sidebarToggle = document.getElementById('sidebarToggle');
    const adminSidebar = document.getElementById('adminSidebar');
    
    sidebarToggle.addEventListener('click', function() {
      body.classList.toggle('sidebar-collapsed');
      
      // For mobile, use different class
      if (window.innerWidth <= 768) {
        body.classList.toggle('sidebar-open');
      }
    });

    // Close sidebar on mobile when clicking outside
    document.addEventListener('click', function(event) {
      if (window.innerWidth <= 768) {
        const isClickInsideSidebar = adminSidebar.contains(event.target);
        const isClickOnToggle = sidebarToggle.contains(event.target);
        
        if (!isClickInsideSidebar && !isClickOnToggle && body.classList.contains('sidebar-open')) {
          body.classList.remove('sidebar-open');
        }
      }
    });

    // Handle window resize
    window.addEventListener('resize', function() {
      if (window.innerWidth > 768) {
        body.classList.remove('sidebar-open');
      }
    });

    // Set active nav link
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
      link.classList.remove('active');
      if (link.getAttribute('href') === currentPath) {
        link.classList.add('active');
      }
    });

    // Custom dropdown handling for better mobile support
    const userDropdown = document.querySelector('.user-dropdown');
    const dropdownMenu = document.querySelector('.user-menu .dropdown-menu');
    
    if (userDropdown && dropdownMenu) {
      userDropdown.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropdownMenu.classList.toggle('show');
      });

      // Close dropdown when clicking outside
      document.addEventListener('click', function(event) {
        if (!userDropdown.contains(event.target) && !dropdownMenu.contains(event.target)) {
          dropdownMenu.classList.remove('show');
        }
      });

      // Close dropdown on window resize
      window.addEventListener('resize', function() {
        dropdownMenu.classList.remove('show');
      });
    }