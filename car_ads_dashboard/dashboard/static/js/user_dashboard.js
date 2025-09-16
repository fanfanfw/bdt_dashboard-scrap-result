// Charts script
document.addEventListener('DOMContentLoaded', function() {
  // Initialize tooltips
  var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });

  // Get config from Django template
  const config = window.dashboardConfig;

  const chartColors = [
    'rgba(48, 71, 94, 0.8)',
    'rgba(240, 84, 84, 0.8)',
    'rgba(54, 162, 235, 0.8)',
    'rgba(255, 206, 86, 0.8)',
    'rgba(75, 192, 192, 0.8)',
    'rgba(153, 102, 255, 0.8)',
    'rgba(255, 159, 64, 0.8)',
    'rgba(199, 199, 199, 0.8)',
    'rgba(83, 102, 255, 0.8)',
    'rgba(255, 99, 132, 0.8)'
  ];
  
  // Top 10 Brands Chart
  const top10BrandsCtx = document.getElementById('top10BrandsChart').getContext('2d');
  const top10BrandsChart = new Chart(top10BrandsCtx, {
    type: 'bar',
    data: {
      labels: config.top_10_brands_labels,
      datasets: [{
        label: 'Jumlah Listing',
        data: config.top_10_brands_data,
        backgroundColor: chartColors,
        borderColor: chartColors.map(color => color.replace('0.8', '1')),
        borderWidth: 2,
        borderRadius: 8,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(34, 40, 49, 0.9)',
          titleColor: '#DDDDDD',
          bodyColor: '#DDDDDD',
          borderColor: '#30475E',
          borderWidth: 1,
          cornerRadius: 8,
          displayColors: false
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(48, 71, 94, 0.1)'
          },
          ticks: {
            color: '#30475E'
          }
        },
        x: {
          grid: {
            display: false
          },
          ticks: {
            color: '#30475E'
          }
        }
      }
    }
  });

  // Brand Chart
  const brandCtx = document.getElementById('brandChart').getContext('2d');
  const brandChart = new Chart(brandCtx, {
    type: 'bar',
    data: {
      labels: config.brand_labels,
      datasets: [{
        label: 'Aktif',
        data: config.brand_active_data,
        backgroundColor: 'rgba(48, 71, 94, 0.8)',
        borderColor: 'rgba(48, 71, 94, 1)',
        borderWidth: 2,
        borderRadius: 6
      }, {
        label: 'Terjual',
        data: config.brand_sold_data,
        backgroundColor: 'rgba(240, 84, 84, 0.8)',
        borderColor: 'rgba(240, 84, 84, 1)',
        borderWidth: 2,
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: '#30475E',
            usePointStyle: true,
            padding: 20
          }
        },
        tooltip: {
          backgroundColor: 'rgba(34, 40, 49, 0.9)',
          titleColor: '#DDDDDD',
          bodyColor: '#DDDDDD',
          borderColor: '#30475E',
          borderWidth: 1,
          cornerRadius: 8
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(48, 71, 94, 0.1)'
          },
          ticks: {
            color: '#30475E'
          }
        },
        x: {
          grid: {
            display: false
          },
          ticks: {
            color: '#30475E'
          }
        }
      }
    }
  });

  // Year Chart
  const yearCtx = document.getElementById('yearChart').getContext('2d');
  const yearChart = new Chart(yearCtx, {
    type: 'line',
    data: {
      labels: config.year_labels,
      datasets: [{
        label: 'Jumlah Listing',
        data: config.year_data,
        borderColor: 'rgba(240, 84, 84, 1)',
        backgroundColor: 'rgba(240, 84, 84, 0.1)',
        tension: 0.4,
        borderWidth: 3,
        pointBackgroundColor: 'rgba(240, 84, 84, 1)',
        pointBorderColor: '#ffffff',
        pointBorderWidth: 2,
        pointRadius: 6,
        pointHoverRadius: 8,
        fill: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(34, 40, 49, 0.9)',
          titleColor: '#DDDDDD',
          bodyColor: '#DDDDDD',
          borderColor: '#30475E',
          borderWidth: 1,
          cornerRadius: 8
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(48, 71, 94, 0.1)'
          },
          ticks: {
            color: '#30475E'
          }
        },
        x: {
          grid: {
            display: false
          },
          ticks: {
            color: '#30475E'
          }
        }
      }
    }
  });

  // Price Chart
  const priceCtx = document.getElementById('priceChart').getContext('2d');
  const priceChart = new Chart(priceCtx, {
    type: 'bar',
    data: {
      labels: config.price_labels,
      datasets: [{
        label: 'Harga Rata-rata (RM)',
        data: config.price_data,
        backgroundColor: chartColors,
        borderColor: chartColors.map(color => color.replace('0.8', '1')),
        borderWidth: 2,
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(34, 40, 49, 0.9)',
          titleColor: '#DDDDDD',
          bodyColor: '#DDDDDD',
          borderColor: '#30475E',
          borderWidth: 1,
          cornerRadius: 8,
          callbacks: {
            label: function(context) {
              return context.dataset.label + ': RM ' + context.parsed.y.toLocaleString();
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: {
            color: 'rgba(48, 71, 94, 0.1)'
          },
          ticks: {
            color: '#30475E',
            callback: function(value) {
              return 'RM ' + value.toLocaleString();
            }
          }
        },
        x: {
          grid: {
            display: false
          },
          ticks: {
            color: '#30475E'
          }
        }
      }
    }
  });




  // Scatter Chart
  const scatterCtx = document.getElementById('scatterChart').getContext('2d');
  let scatterChart = new Chart(scatterCtx, {
    type: 'scatter',
    data: {
      datasets: [{
        label: 'Harga vs Mileage',
        data: [],
        backgroundColor: 'rgba(240, 84, 84, 0.6)',
        borderColor: 'rgba(240, 84, 84, 1)',
        pointRadius: 4,
        pointHoverRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(34, 40, 49, 0.9)',
          titleColor: '#DDDDDD',
          bodyColor: '#DDDDDD',
          borderColor: '#30475E',
          borderWidth: 1,
          cornerRadius: 8,
          callbacks: {
            label: function(context) {
              return `Harga: RM ${context.parsed.y.toLocaleString()}, Mileage: ${context.parsed.x.toLocaleString()} km`;
            }
          }
        }
      },
      scales: {
        x: {
          type: 'linear',
          position: 'bottom',
          title: {
            display: true,
            text: 'Mileage (km)',
            color: '#30475E'
          },
          grid: {
            color: 'rgba(48, 71, 94, 0.1)'
          },
          ticks: {
            color: '#30475E'
          }
        },
        y: {
          title: {
            display: true,
            text: 'Harga (RM)',
            color: '#30475E'
          },
          grid: {
            color: 'rgba(48, 71, 94, 0.1)'
          },
          ticks: {
            color: '#30475E',
            callback: function(value) {
              return 'RM ' + value.toLocaleString();
            }
          }
        }
      }
    }
  });

  // Average Mileage Chart
  const avgMileageCtx = document.getElementById('avgMileageChart').getContext('2d');
  let avgMileageChart = new Chart(avgMileageCtx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Average Mileage (km)',
        data: [],
        borderColor: 'rgba(48, 71, 94, 1)',
        backgroundColor: 'rgba(48, 71, 94, 0.1)',
        tension: 0.4,
        borderWidth: 3,
        pointBackgroundColor: 'rgba(48, 71, 94, 1)',
        pointBorderColor: '#ffffff',
        pointBorderWidth: 2,
        pointRadius: 6,
        pointHoverRadius: 8,
        fill: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(34, 40, 49, 0.9)',
          titleColor: '#DDDDDD',
          bodyColor: '#DDDDDD',
          borderColor: '#30475E',
          borderWidth: 1,
          cornerRadius: 8,
          callbacks: {
            label: function(context) {
              return `Average Mileage: ${context.parsed.y.toLocaleString()} km`;
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          title: {
            display: true,
            text: 'Mileage (km)',
            color: '#30475E'
          },
          grid: {
            color: 'rgba(48, 71, 94, 0.1)'
          },
          ticks: {
            color: '#30475E',
            callback: function(value) {
              return value.toLocaleString() + ' km';
            }
          }
        },
        x: {
          title: {
            display: true,
            text: 'Year',
            color: '#30475E'
          },
          grid: {
            display: false
          },
          ticks: {
            color: '#30475E'
          }
        }
      }
    }
  });

  // Function to fetch scatter data and statistics
  function fetchScatterData(brand = '', model = '', variant = '', year = '') {
    const params = new URLSearchParams();
    params.append('source', config.source);
    if (brand) params.append('brand', brand);
    if (model) params.append('model', model);
    if (variant) params.append('variant', variant);
    if (year) params.append('year', year);

    // Fetch scatter plot data
    fetch(`/dashboard/user/${config.username}/scatter-data/?${params.toString()}`)
      .then(response => response.json())
      .then(data => {
        scatterChart.data.datasets[0].data = data;
        scatterChart.update();
      })
      .catch(error => console.error('Error fetching scatter data:', error));
    
    // Fetch scatter plot statistics
    fetchScatterStatistics(brand, model, variant, year);
  }
  
  // Function to fetch scatter plot statistics
  function fetchScatterStatistics(brand = '', model = '', variant = '', year = '') {
    const params = new URLSearchParams();
    params.append('source', config.source);
    if (brand) params.append('brand', brand);
    if (model) params.append('model', model);
    if (variant) params.append('variant', variant);
    if (year) params.append('year', year);

    fetch(`/dashboard/user/${config.username}/scatter-stats/?${params.toString()}`)
      .then(response => response.json())
      .then(stats => {
        updateScatterStatistics(stats);
      })
      .catch(error => {
        console.error('Error fetching scatter statistics:', error);
        // Reset stats on error
        updateScatterStatistics({});
      });
  }
  
  // Function to update scatter plot statistics display
  function updateScatterStatistics(stats) {
    // Format price values with RM prefix
    const formatPrice = (value) => {
      if (value === null || value === undefined || value === 0) return '-';
      return 'RM ' + Math.round(value).toLocaleString();
    };
    
    // Format mileage values with km suffix
    const formatMileage = (value) => {
      if (value === null || value === undefined || value === 0) return '-';
      return Math.round(value).toLocaleString() + ' km';
    };
    
    // Format count values
    const formatCount = (value) => {
      if (value === null || value === undefined || value === 0) return '0';
      return value.toLocaleString();
    };
    
    // Update each statistic element
    document.getElementById('avgPrice').textContent = formatPrice(stats.avg_price);
    document.getElementById('avgMileage').textContent = formatMileage(stats.avg_mileage);
    document.getElementById('maxPrice').textContent = formatPrice(stats.max_price);
    document.getElementById('minPrice').textContent = formatPrice(stats.min_price);
    document.getElementById('totalDataPoints').textContent = formatCount(stats.total_points);
    document.getElementById('maxMileage').textContent = formatMileage(stats.max_mileage);
  }

  // Function to load average mileage per year
  function loadAvgMileagePerYear(brand = '', model = '', variant = '', year = '') {
    const params = new URLSearchParams();
    params.append('source', config.source);
    if (brand) params.append('brand', brand);
    if (model) params.append('model', model);
    if (variant) params.append('variant', variant);
    if (year) params.append('year', year);

    fetch(`/dashboard/user/${config.username}/avg-mileage-year/?${params.toString()}`)
      .then(response => response.json())
      .then(data => {
        avgMileageChart.data.labels = data.labels;
        avgMileageChart.data.datasets[0].data = data.data;
        avgMileageChart.update();
      })
      .catch(error => console.error('Error:', error));
  }

  // Load initial scatter data
  fetchScatterData();
  loadAvgMileagePerYear();
  
  // Load today's data
  loadTodaysData();

  // Function to load today's data
  function loadTodaysData() {
    const tableBody = $('#todayDataTableBody');
    
    $.ajax({
      url: `/dashboard/user/${config.username}/todays-data/`,
      method: 'GET',
      data: {
        source: '{{ source }}'
      },
      success: function(response) {
        tableBody.empty();
        
        if (response.data && response.data.length > 0) {
          response.data.forEach(function(item, index) {
            let statusBadge = '';
            if (item.status && item.status.toLowerCase() === 'sold') {
              statusBadge = '<span class="badge bg-danger">Sold</span>';
            } else if (item.status && item.status.toLowerCase() === 'active') {
              statusBadge = '<span class="badge bg-success">Active</span>';
            } else {
              statusBadge = '<span class="badge bg-secondary">' + (item.status || '-') + '</span>';
            }

            let priceFormatted = 'RM -';
            if (item.latest_price && item.latest_price !== null && item.latest_price !== '-') {
              priceFormatted = 'RM ' + parseInt(item.latest_price).toLocaleString();
            }

            let mileageFormatted = '-';
            if (item.mileage && item.mileage !== null && item.mileage !== '-') {
              mileageFormatted = parseInt(item.mileage).toLocaleString() + ' km';
            }

            const row = `
              <tr class="fadeInUp" style="animation-delay: ${index * 0.1}s;">
                <td>
                  ${item.img_url ? 
                    `<img src="${item.img_url}" alt="Car Image" style="width:60px; height:45px; object-fit:cover; border-radius:6px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">` 
                    : '<div class="bg-light d-flex align-items-center justify-content-center" style="width:60px; height:45px; border-radius:6px;"><i class="fas fa-car text-muted"></i></div>'
                  }
                </td>
                <td><span class="fw-semibold">${item.brand || '-'}</span></td>
                <td>${item.model || '-'}</td>
                <td class="text-muted">${item.variant || '-'}</td>
                <td><span class="badge bg-info">${item.year || '-'}</span></td>
                <td><span class="text-primary fw-semibold">${mileageFormatted}</span></td>
                <td><span class="text-success fw-bold">${priceFormatted}</span></td>
                <td>${statusBadge}</td>
                <td class="text-muted small">${new Date(item.created_at).toLocaleDateString('id-ID', {
                  day: '2-digit',
                  month: 'short',
                  hour: '2-digit',
                  minute: '2-digit'
                })}</td>
              </tr>
            `;
            tableBody.append(row);
          });
          
          // Destroy existing DataTable if it exists
          if ($.fn.DataTable.isDataTable('#todayDataTable')) {
            $('#todayDataTable').DataTable().destroy();
          }
          
          // Initialize fresh DataTable
          $('#todayDataTable').DataTable({
            pageLength: 10,
            lengthMenu: [[10, 25, 50, 100], [10, 25, 50, 100]],
            order: [[8, "desc"]], // Order by created_at descending
            language: {
              search: "Cari:",
              lengthMenu: "Tampilkan _MENU_ data",
              info: "Menampilkan _START_ sampai _END_ dari _TOTAL_ data",
              infoEmpty: "Menampilkan 0 sampai 0 dari 0 data",
              infoFiltered: "(disaring dari _MAX_ total data)",
              zeroRecords: "Tidak ada data yang cocok",
              emptyTable: "Tidak ada data tersedia",
              paginate: {
                first: '<i class="fas fa-angle-double-left"></i>',
                previous: '<i class="fas fa-angle-left"></i>',
                next: '<i class="fas fa-angle-right"></i>',
                last: '<i class="fas fa-angle-double-right"></i>'
              }
            },
            responsive: true,
            dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>rtip',
            drawCallback: function(settings) {
              // Apply custom styling after each draw
              $('.today-data-content .dataTables_wrapper .dataTables_paginate .paginate_button').each(function() {
                $(this).addClass('btn-custom-pagination');
              });
            }
          });
        } else {
          tableBody.html(`
            <tr>
              <td colspan="9" class="text-center py-4">
                <div class="text-muted">
                  <i class="fas fa-info-circle mb-2" style="font-size: 2rem;"></i>
                  <p class="mb-0">Belum ada data scraping hari ini</p>
                  <small>Data akan muncul setelah proses scraping berjalan</small>
                </div>
              </td>
            </tr>
          `);
          
          // Still initialize DataTable for empty table
          if ($.fn.DataTable.isDataTable('#todayDataTable')) {
            $('#todayDataTable').DataTable().destroy();
          }
          
          $('#todayDataTable').DataTable({
            pageLength: 10,
            lengthMenu: [[10, 25, 50, 100], [10, 25, 50, 100]],
            language: {
              search: "Cari:",
              lengthMenu: "Tampilkan _MENU_ data",
              info: "Menampilkan _START_ sampai _END_ dari _TOTAL_ data",
              infoEmpty: "Tidak ada data untuk ditampilkan",
              infoFiltered: "(disaring dari _MAX_ total data)",
              zeroRecords: "Belum ada data scraping hari ini",
              emptyTable: "Belum ada data scraping hari ini",
              paginate: {
                first: '<i class="fas fa-angle-double-left"></i>',
                previous: '<i class="fas fa-angle-left"></i>',
                next: '<i class="fas fa-angle-right"></i>',
                last: '<i class="fas fa-angle-double-right"></i>'
              }
            },
            responsive: true,
            dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>rtip'
          });
        }
      },
      error: function(xhr, error, thrown) {
        console.error('Error loading today\'s data:', error);
        tableBody.html(`
          <tr>
            <td colspan="9" class="text-center py-4">
              <div class="text-danger">
                <i class="fas fa-exclamation-triangle mb-2" style="font-size: 2rem;"></i>
                <p class="mb-0">Gagal memuat data hari ini</p>
                <small>Silakan refresh halaman atau coba lagi nanti</small>
              </div>
            </td>
          </tr>
        `);
      }
    });
  }

  // Brand change handler
  $('#scatterBrand').change(function() {
    const brand = $(this).val();
    
    // Clear and load models
    $('#scatterModel').html('<option value="">Semua Model</option>');
    $('#scatterVariant').html('<option value="">Semua Variant</option>');
    $('#scatterYear').html('<option value="">Semua Tahun</option>');
    
    if (brand) {
      fetch(`/dashboard/get-models/?brand=${brand}&source=${config.source}`)
        .then(response => response.json())
        .then(data => {
          data.forEach(model => {
            $('#scatterModel').append(`<option value="${model}">${model}</option>`);
          });
        });
    }
    
    fetchScatterData(brand);
    loadAvgMileagePerYear(brand);
  });

  // Model change handler
  $('#scatterModel').change(function() {
    const brand = $('#scatterBrand').val();
    const model = $(this).val();
    
    // Clear and load variants
    $('#scatterVariant').html('<option value="">Semua Variant</option>');
    $('#scatterYear').html('<option value="">Semua Tahun</option>');
    
    if (model) {
      fetch(`/dashboard/get-variants/?brand=${brand}&model=${model}&source=${config.source}`)
        .then(response => response.json())
        .then(data => {
          data.forEach(variant => {
            $('#scatterVariant').append(`<option value="${variant}">${variant}</option>`);
          });
        });

      fetch(`/dashboard/get-years/?brand=${brand}&model=${model}&source=${config.source}`)
        .then(response => response.json())
        .then(data => {
          data.forEach(year => {
            $('#scatterYear').append(`<option value="${year}">${year}</option>`);
          });
        });
    }
    
    fetchScatterData(brand, model);
    loadAvgMileagePerYear(brand, model);
  });

  // Variant change handler
  $('#scatterVariant').change(function() {
    const brand = $('#scatterBrand').val();
    const model = $('#scatterModel').val();
    const variant = $(this).val();
    const year = $('#scatterYear').val();
    fetchScatterData(brand, model, variant, year);
    loadAvgMileagePerYear(brand, model, variant, year);
  });

  // Year change handler
  $('#scatterYear').change(function() {
    const brand = $('#scatterBrand').val();
    const model = $('#scatterModel').val();
    const variant = $('#scatterVariant').val();
    const year = $(this).val();
    fetchScatterData(brand, model, variant, year);
    loadAvgMileagePerYear(brand, model, variant, year);
  });

  // Add click handlers to trend items
  $(document).on('click', '.trend-item', function() {
    const brand = $(this).find('.trend-brand').text();
    const model = $(this).find('.trend-model').text();
    const variant = $(this).find('.trend-variant').text() || '';
    const condition = $(this).find('.trend-condition').text();
    const year = $(this).find('.trend-year').text() || '';
    const mileage = $(this).find('.trend-mileage').text().replace(' km', '').replace(/,/g, '') || '';
    
    showPriceHistory(brand, model, variant, condition, year, mileage);
  });

  // Function to show price history modal
  function showPriceHistory(brand, model, variant, condition, year, mileage) {
    $('#priceHistoryModal').modal('show');
    $('#priceHistoryContent').html(`
      <div class="text-center py-4">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
        <p class="mt-2">Memuat data perubahan harga...</p>
      </div>
    `);
    
    // Fetch price history data
    $.ajax({
      url: config.priceHistoryUrl,
      method: 'GET',
      data: {
        source: config.source,
        brand: brand,
        model: model,
        variant: variant,
        condition: condition,
        year: year,
        mileage: mileage
      },
      success: function(response) {
        displayPriceHistory(response, brand, model, variant, condition, year, mileage);
      },
      error: function() {
        $('#priceHistoryContent').html(`
          <div class="text-center py-4">
            <i class="fas fa-exclamation-triangle text-warning" style="font-size: 2rem;"></i>
            <p class="mt-2">Gagal memuat data perubahan harga</p>
          </div>
        `);
      }
    });
  }

  // Function to display price history
  function displayPriceHistory(data, brand, model, variant, condition, year, mileage) {
    let html = `
      <div class="car-info-modal">
        <div class="car-info-title">${brand} ${model} ${variant ? variant : ''}</div>
        <div class="car-info-details">
          <div class="car-info-item">
            <div class="car-info-label">Brand</div>
            <div class="car-info-value">${brand}</div>
          </div>
          <div class="car-info-item">
            <div class="car-info-label">Model</div>
            <div class="car-info-value">${model}</div>
          </div>
          ${variant ? `
          <div class="car-info-item">
            <div class="car-info-label">Variant</div>
            <div class="car-info-value">${variant}</div>
          </div>
          ` : ''}
          ${year ? `
          <div class="car-info-item">
            <div class="car-info-label">Year</div>
            <div class="car-info-value">${year}</div>
          </div>
          ` : ''}
          ${mileage ? `
          <div class="car-info-item">
            <div class="car-info-label">Mileage</div>
            <div class="car-info-value">${parseInt(mileage).toLocaleString()} km</div>
          </div>
          ` : ''}
          <div class="car-info-item">
            <div class="car-info-label">Condition</div>
            <div class="car-info-value">${condition}</div>
          </div>
        </div>
      </div>
    `;

    if (data.summary) {
      html += `
        <div class="price-summary">
          <div class="price-summary-item">
            <div class="price-summary-value">${data.summary.total_cars}</div>
            <div class="price-summary-label">Total Listing</div>
          </div>
          <div class="price-summary-item">
            <div class="price-summary-value">${data.summary.total_with_changes}</div>
            <div class="price-summary-label">Dengan Perubahan</div>
          </div>
          <div class="price-summary-item">
            <div class="price-summary-value">RM ${data.summary.avg_change.toLocaleString()}</div>
            <div class="price-summary-label">Rata-rata Perubahan</div>
          </div>
          <div class="price-summary-item">
            <div class="price-summary-value">${data.summary.avg_change_percent.toFixed(1)}%</div>
            <div class="price-summary-label">Persentase Rata-rata</div>
          </div>
        </div>
      `;
    }

    if (data.listings && data.listings.length > 0) {
      html += '<div class="listings-container">';
      html += '<h4 class="listings-title">Semua Listing Individual</h4>';
      html += '<div class="listings-list">';        data.listings.forEach(function(listing) {
        const hasChange = listing.price_change !== null;
        let priceDisplay = `<span class="current-price">RM ${listing.current_price.toLocaleString()}</span>`;
        let changeIndicator = '';
        let listingClasses = '';
        
        if (hasChange) {
          const change = listing.price_change;
          const changeClass = change.change_amount >= 0 ? 'price-increase' : 'price-decrease';
          const changeIcon = change.change_amount >= 0 ? 'fas fa-arrow-up' : 'fas fa-arrow-down';
          
          // Add specific class for price increase vs decrease
          listingClasses = change.change_amount >= 0 ? 'has-change price-up' : 'has-change price-down';
          
          priceDisplay = `
            <div class="price-with-change">
              <span class="old-price-crossed">RM ${change.old_price.toLocaleString()}</span>
              <span class="current-price">RM ${listing.current_price.toLocaleString()}</span>
            </div>
          `;
          
          changeIndicator = `
            <div class="change-indicator ${changeClass}">
              <i class="${changeIcon}"></i>
              ${change.change_amount >= 0 ? '+' : ''}RM ${change.change_amount.toLocaleString()} (${change.change_percent.toFixed(1)}%)
            </div>
          `;
        }
        
        html += `
          <div class="listing-item ${listingClasses}">
            <div class="listing-main-info">
              <div class="listing-header">
                <div class="listing-title">${listing.brand} ${listing.model} ${listing.variant || ''}</div>
                <div class="listing-specs">
                  <span class="spec-item">${listing.year || 'N/A'}</span>
                  <span class="spec-item">${listing.mileage ? parseInt(listing.mileage).toLocaleString() + ' km' : 'N/A'}</span>
                  <span class="spec-item">${listing.condition || 'N/A'}</span>
                </div>
              </div>
              <div class="listing-details">
                <div class="detail-row">
                  <span class="detail-label">Lokasi:</span>
                  <span class="detail-value">${listing.location || 'N/A'}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Terakhir Update:</span>
                  <span class="detail-value">${new Date(listing.last_status_check).toLocaleDateString('id-ID', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                  })}</span>
                </div>
              </div>
            </div>
            <div class="listing-price-info">
              ${priceDisplay}
              ${changeIndicator}
            </div>
          </div>
        `;
      });
      
      html += '</div>';
      html += '</div>';
    } else {
      html += `
        <div class="text-center py-4">
          <i class="fas fa-info-circle text-info" style="font-size: 2rem;"></i>
          <p class="mt-2">Tidak ada listing untuk model/variant ini</p>
        </div>
      `;
    }

    $('#priceHistoryContent').html(html);
  }
});