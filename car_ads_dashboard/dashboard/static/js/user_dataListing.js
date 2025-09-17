$(document).ready(function() {
  // Get config from Django template
  const config = window.dataListingConfig;

  // Show loading skeleton on initial load
  showLoadingSkeleton();
  
  // Toggle sidebar
  $('#btnToggleSidebar').click(function() {
    $('#sidebarWrapper').toggleClass('sidebar-hidden');
    if ($('#sidebarWrapper').hasClass('sidebar-hidden')) {
      $('#btnToggleSidebar').find('i').removeClass('fa-chevron-left').addClass('fa-chevron-right');
    } else {
      $('#btnToggleSidebar').find('i').removeClass('fa-chevron-right').addClass('fa-chevron-left');
    }
    $('#listingTable').DataTable().columns.adjust();
  });
  
  // Mobile responsive sidebar handler
  function handleResponsiveSidebar() {
    const isMobile = window.innerWidth <= 768;
    
    if (isMobile) {
      // On mobile, default is hidden
      $('#sidebarWrapper').addClass('sidebar-hidden');
      $('#btnToggleSidebar').find('i').removeClass('fa-chevron-left').addClass('fa-chevron-right');
    } else {
      // On desktop, default is shown (or keep current state)
      if ($('#sidebarWrapper').hasClass('sidebar-hidden') && !localStorage.getItem('sidebarHidden')) {
        $('#sidebarWrapper').removeClass('sidebar-hidden');
        $('#btnToggleSidebar').find('i').removeClass('fa-chevron-right').addClass('fa-chevron-left');
      }
    }
  }
  
  // Run on page load
  handleResponsiveSidebar();
  
  // Run on window resize
  $(window).resize(function() {
    handleResponsiveSidebar();
  });
  
  // Save sidebar state to localStorage
  $('#btnToggleSidebar').click(function() {
    if ($('#sidebarWrapper').hasClass('sidebar-hidden')) {
      localStorage.setItem('sidebarHidden', 'true');
    } else {
      localStorage.removeItem('sidebarHidden');
    }
  });
  
  // Apply saved state on load
  if (localStorage.getItem('sidebarHidden') === 'true') {
    $('#sidebarWrapper').addClass('sidebar-hidden');
    $('#btnToggleSidebar').find('i').removeClass('fa-chevron-left').addClass('fa-chevron-right');
  }
  
  // Show loading skeleton function
  function showLoadingSkeleton() {
    const skeletonRows = Array.from({length: 5}, () =>
      `<tr class="loading-skeleton">
        <td><div class="loading-skeleton" style="height: 60px; width: 80px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
        <td><div class="loading-skeleton" style="height: 20px;"></div></td>
      </tr>`
    ).join('');
    $('#listingTable tbody').html(skeletonRows);
  }

  // Initialize DataTables
  var table = $('#listingTable').DataTable({
    processing: true,
    serverSide: true,
    responsive: true,
    ajax: {
      url: config.getListingDataUrl,
      type: "GET",
      dataType: "json",
      data: function(d) {
        d.brand = $('#brandSelect').val();
        d.model = $('#modelSelect').val();
        d.variant = $('#variantSelect').val();
        d.year = $('#yearSelect').val();
      },
      error: function(xhr, error, thrown) {
        console.error('DataTables error:', error);
        alert('Error loading data. Please try again.');
      }
    },
    columns: [
      { 
        data: 'img', 
        orderable: false, 
        searchable: false,
        render: function(data) {
          return data ? `<img src="${data}" alt="Car Image" style="width:70px; height:50px; object-fit:cover; border-radius:6px;">` : '-';
        }
      },
      { data: 'year' },
      { data: 'brand' },
      { data: 'model' },
      { data: 'variant' },
      { data: 'mileage' },
      {
        data: 'starting',
        render: function(data) {
          if (data === '-' || data === null) return '-';
          // Format angka dengan koma dan prefix RM
          return 'RM ' + data.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        }
      },
      {
        data: 'latest',
        render: function(data) {
          if (data === '-' || data === null) return '-';
          return 'RM ' + data.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
        }
      },
      { data: 'created_at' },
      { 
        data: 'status',
        render: function(data) {
          if (!data) return '-';
          if (data.toLowerCase() === 'sold') {
            return '<span class="badge bg-danger">Sold</span>';
          } else if (data.toLowerCase() === 'active') {
            return '<span class="badge bg-success">Active</span>';
          } else {
            return data;
          }
        }
      },
      { data: 'sold_duration' }
    ],
    pageLength: 25,
    lengthMenu: [[10, 25, 50, 100], [10, 25, 50, 100]],
    order: [[1, "desc"]],
    language: {
      processing: '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>',
      search: "Pencarian:",
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
    drawCallback: function(settings) {
      $('.paginate_button').addClass('btn btn-sm');
      renderGridView(settings.json.data);
    }
  });

  // Reload tabel saat filter berubah
  function reloadTable() {
    // Add loading state
    $('#listingTable').addClass('table-loading');
    $('#gridViewContainer').html('<div class="loading-skeleton" style="height: 200px; margin: 2rem;"></div>');
    
    table.ajax.reload(function() {
      // Remove loading state
      $('#listingTable').removeClass('table-loading');
    }, false);
  }

  // Render grid view cards
  function renderGridView(data) {
      var container = $('#gridViewContainer');
      container.empty();

      if (!data || data.length === 0) {
          container.append('<div class="col">No data available</div>');
          return;
      }

      function formatPrice(price) {
          if (
              price === null ||
              price === undefined ||
              price === '' ||
              (typeof price === 'string' && price.trim() === '-')
          ) {
              return '-';
          }
          let priceStr = price.toString();
          if (!priceStr.toUpperCase().startsWith('RM')) {
              priceStr = 'RM ' + priceStr.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
          }
          return priceStr;
      }

      data.forEach(function(item, index) {
          let statusBadgeClass = 'badge bg-secondary';
          let statusText = item.status.charAt(0).toUpperCase() + item.status.slice(1);
          if (item.status.toLowerCase() === 'sold') {
              statusBadgeClass = 'badge bg-danger';
          } else if (item.status.toLowerCase() === 'active') {
              statusBadgeClass = 'badge bg-success';
          }

          // Gunakan starting dan latest seperti di list view
          let startingPrice = formatPrice(item.starting);
          let latestPrice = formatPrice(item.latest);

          var card = `
        <div class="grid-col" style="animation-delay: ${index * 0.1}s;">
            <div class="card h-100 shadow-sm">
                <div class="position-relative">
                    <img src="${item.img || 'https://via.placeholder.com/400x250?text=No+Image&bg=30475E&color=DDDDDD'}" class="card-img-top" alt="Car Image" loading="lazy">
                    <div class="position-absolute top-0 end-0 m-2">
                        <span class="${statusBadgeClass}">${statusText}</span>
                    </div>
                    ${item.status.toLowerCase() === 'sold' ? '<div class="position-absolute top-50 start-50 translate-middle"><span class="badge bg-danger fs-6 px-3 py-2">SOLD</span></div>' : ''}
                </div>
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <h6 class="card-title mb-0">${item.year} ${item.brand}</h6>
                        <small class="text-muted">${item.year}</small>
                    </div>
                    <h6 class="fw-bold text-primary mb-2">${item.model}</h6>
                    <p class="text-muted mb-3 small">${item.variant || 'Standard Variant'}</p>
                    
                    <div class="price-section mb-3">
                        <div class="price-display mb-1">
                            ${latestPrice}
                        </div>
                        ${startingPrice !== latestPrice ? `<small class="text-muted">Starting: ${startingPrice}</small>` : ''}
                    </div>

                    <div class="stats-row">
                        <div class="row text-center g-0">
                            <div class="col">
                                <div class="stat-item">
                                    <i class="fas fa-tachometer-alt text-primary"></i>
                                    <small class="text-muted d-block">Mileage</small>
                                    <span class="fw-semibold">${item.mileage || '-'}</span>
                                </div>
                            </div>
                            <div class="col">
                                <div class="stat-item">
                                    <i class="fas fa-clock text-warning"></i>
                                    <small class="text-muted d-block">Listed</small>
                                    <span class="fw-semibold">${item.sold_duration || '-'}</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="card-footer-info mt-3 pt-3 border-top">
                        <div class="d-flex align-items-center justify-content-between">
                            <span class="text-muted small">
                                <i class="far fa-calendar-alt me-1"></i> ${item.created_at}
                            </span>
                            <span class="badge bg-light text-dark">ID: ${item.id || index + 1}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        `;
        container.append(card);
    });
}

  /// Toggle List/Grid View
  $('#btnGridView').click(function() {
    $('#contentWrapper').hide();          // sembunyikan tabel list view
    $('#gridViewContainer').show();       // tampilkan grid view
    $(this).addClass('active');
    $('#btnListView').removeClass('active');
    
    // Load grid data if not loaded
    if ($('#gridViewContainer').children().length === 0) {
      loadGridData();
    }
  });

  $('#btnListView').click(function() {
    $('#contentWrapper').show();           // tampilkan tabel list view
    $('#gridViewContainer').hide();        // sembunyikan grid view
    $(this).addClass('active');
    $('#btnGridView').removeClass('active');
  });

  // Load grid data function
  function loadGridData() {
    $('#gridViewContainer').html(`
      <div class="col-12 text-center py-5">
        <div class="loading-skeleton mx-auto" style="height: 200px; width: 300px; margin-bottom: 1rem;"></div>
        <div class="loading-skeleton mx-auto" style="height: 20px; width: 200px; margin-bottom: 0.5rem;"></div>
        <div class="loading-skeleton mx-auto" style="height: 20px; width: 150px;"></div>
      </div>
    `);
    
    // Simulate loading for demonstration
    setTimeout(() => {
      // This would normally be triggered by DataTables drawCallback
      const currentData = table.data().toArray();
      renderGridView(currentData);
    }, 500);
  }

  // Load brand stats di sidebar
  function loadBrandStats() {
    const brandsList = $('#brandsList');
    
    // Show loading skeleton
    brandsList.html(`
      <div class="loading-skeleton" style="height: 40px; margin-bottom: 1rem;"></div>
      <div class="loading-skeleton" style="height: 40px; margin-bottom: 1rem;"></div>
      <div class="loading-skeleton" style="height: 40px; margin-bottom: 1rem;"></div>
      <div class="loading-skeleton" style="height: 40px; margin-bottom: 1rem;"></div>
    `);
    
    $.ajax({
      url: config.getBrandStatsUrl,
      type: "GET",
      data: {},
      success: function(response) {
        brandsList.empty();
        if (response.brands && response.brands.length > 0) {
          response.brands.forEach(function(brand, index) {
            const brandSafeId = brand.brand.replace(/\s+/g, '-');
            const brandHtml = `
              <div class="brand-container mb-2" style="animation-delay: ${index * 0.1}s;">
                <div class="list-group-item list-group-item-action d-flex justify-content-between align-items-center brand-item" data-brand="${brand.brand}" style="cursor:pointer;">
                  <span><i class="fas fa-car me-2"></i>${brand.brand}</span>
                  <span class="badge bg-secondary rounded-pill">${brand.total.toLocaleString()}</span>
                </div>
                <div class="models-container mt-1" id="models-${brandSafeId}" style="display:none; padding-left: 15px;"></div>
              </div>
            `;
            brandsList.append(brandHtml);
          });
          
          // Add animation class after append
          $('.brand-container').addClass('fadeInUp');
        } else {
          brandsList.append('<div class="alert alert-info">No brands found</div>');
        }
      },
      error: function() {
        brandsList.html('<div class="alert alert-danger">Error loading brands</div>');
      }
    });
  }
  loadBrandStats();

  // Klik brand di sidebar toggle model list
  $(document).on('click', '.brand-item', function() {
    const brand = $(this).data('brand');
    const brandSafeId = brand.replace(/\s+/g, '-');
    const modelsContainer = $(`#models-${brandSafeId}`);

    $('.brand-item').not(this).removeClass('active');
    $(this).toggleClass('active');
    $('.models-container').not(modelsContainer).slideUp();

    if (modelsContainer.is(':empty')) {
      $.ajax({
        url: config.getModelStatsUrl,
        type: "GET",
        data: { brand: brand },
        success: function(response) {
          if (response.models && response.models.length > 0) {
            response.models.forEach(function(model) {
              const modelHtml = `
                <div class="list-group-item model-item d-flex justify-content-between align-items-center" style="cursor:pointer;">
                  <span>${model.model || '-'}</span>
                  <span class="text-muted">(${model.total})</span>
                </div>
              `;
              modelsContainer.append(modelHtml);
            });
          } else {
            modelsContainer.append('<div class="list-group-item">No models found</div>');
          }
          modelsContainer.slideDown();
        }
      });
    } else {
      modelsContainer.slideToggle();
    }
  });

  // Klik model di sidebar update filter dan reload tabel
  $(document).on('click', '.model-item', function(e) {
    e.preventDefault();
    const brand = $(this).closest('.brand-container').find('.brand-item').data('brand');
    const model = $(this).find('span:first').text().trim();

    $('#brandSelect').val(brand).trigger('change');

    // Tunggu dropdown model update sebelum set nilai dan reload tabel
    const waitForModels = setInterval(function() {
      if ($('#modelSelect option').length > 1) {
        $('#modelSelect').val(model).trigger('change');
        clearInterval(waitForModels);
      }
    }, 100);

    $('#variantSelect').val('');
    $('#yearSelect').val('');
  });

  // Dropdown brand change update model options dengan perbaikan untuk mobile
  $('#brandSelect').on('change', function() {
    const brand = $(this).val();
    
    // Reset dropdowns
    $('#modelSelect').html('<option value="">Pilih Model</option>').prop('disabled', true);
    $('#variantSelect').html('<option value="">Pilih Variant</option>').prop('disabled', true);
    $('#yearSelect').html('<option value="">Pilih Tahun</option>').prop('disabled', true);
    
    // Tambah indikator loading
    const $modelSelect = $('#modelSelect');
    $modelSelect.addClass('loading-select');
    
    if (brand) {
      $.ajax({
        url: config.getModelsUrl,
        type: "GET",
        dataType: "json",
        data: { brand: brand },
        success: function(response) {
          if (response && response.length > 0) {
            response.forEach(function(model) {
              if (model) { // Hanya tambahkan jika model tidak null
                $modelSelect.append(`<option value="${model}">${model}</option>`);
              }
            });
            // Enable model dropdown
            $modelSelect.prop('disabled', false);
            // Memastikan dropdown model terlihat aktif
            setTimeout(() => {
              $modelSelect.focus();
            }, 100);
          }
          reloadTable();
          $modelSelect.removeClass('loading-select');
        },
        error: function() {
          // Handle error
          $modelSelect.removeClass('loading-select');
          console.error("Error loading models");
        }
      });
    } else {
      reloadTable();
      $modelSelect.removeClass('loading-select');
    }
  });

  // Dropdown model change update variant options & reload table dengan perbaikan untuk mobile
  $('#modelSelect').change(function() {
    const brand = $('#brandSelect').val();
    const model = $(this).val();

    // Reset dropdowns yang tergantung pada model
    const $variantSelect = $('#variantSelect');
    $variantSelect.html('<option value="">Pilih Variant</option>').prop('disabled', true);
    $('#yearSelect').html('<option value="">Pilih Tahun</option>').prop('disabled', true);
    
    // Tambah indikator loading
    $variantSelect.addClass('loading-select');

    if (brand && model) {
      $.ajax({
        url: config.getVariantsUrl,
        type: "GET",
        dataType: "json",
        data: { brand: brand, model: model },
        success: function(response) {
          if (response && response.length > 0) {
            response.forEach(function(variant) {
              if (variant) { // Hanya tambahkan jika variant tidak null
                $variantSelect.append(`<option value="${variant}">${variant}</option>`);
              }
            });
            // Enable variant dropdown
            $variantSelect.prop('disabled', false);
            // Memastikan dropdown variant terlihat aktif
            setTimeout(() => {
              $variantSelect.focus();
            }, 100);
          }
          reloadTable();
          $variantSelect.removeClass('loading-select');
        },
        error: function() {
          // Handle error
          $variantSelect.removeClass('loading-select');
          console.error("Error loading variants");
        }
      });
    } else {
      reloadTable();
      $variantSelect.removeClass('loading-select');
    }
  });

  // Variant change update year options
  $('#variantSelect').on('change', function() {
    const brand = $('#brandSelect').val();
    const model = $('#modelSelect').val();
    const variant = $(this).val();
    
    // Reset year dropdown
    const $yearSelect = $('#yearSelect');
    $yearSelect.html('<option value="">Pilih Tahun</option>').prop('disabled', true);
    
    // Tambah indikator loading
    $yearSelect.addClass('loading-select');
    
    if (brand) {
      $.ajax({
        url: config.getYearsUrl,
        type: "GET",
        dataType: "json",
        data: {
          brand: brand,
          model: model || '',
          variant: variant || ''
        },
        success: function(response) {
          if (response && response.length > 0) {
            response.forEach(function(year) {
              if (year) { // Hanya tambahkan jika year tidak null
                $yearSelect.append(`<option value="${year}">${year}</option>`);
              }
            });
            // Enable year dropdown
            $yearSelect.prop('disabled', false);
            // Memastikan dropdown year terlihat aktif
            setTimeout(() => {
              $yearSelect.focus();
            }, 100);
          }
          reloadTable();
          $yearSelect.removeClass('loading-select');
        },
        error: function() {
          // Handle error
          $yearSelect.removeClass('loading-select');
          console.error("Error loading years");
        }
      });
    } else {
      reloadTable();
      $yearSelect.removeClass('loading-select');
    }
  });

  // Year change reload table
  $('#yearSelect').on('change', function() {
    reloadTable();
    
    // Jika year dipilih, focus pada tombol cari
    if ($(this).val() !== '') {
      $('#btnSubmitFilter').focus();
    }
  });

  // Form submit reload table
  $('#filterForm').on('submit', function(e) {
    e.preventDefault();
    reloadTable();
  });

  // Reset form reload table
  $('#filterForm').on('reset', function() {
    setTimeout(function() {
      $('#brandSelect').val('');
      $('#modelSelect').html('<option value="">Pilih Model</option>').prop('disabled', true);
      $('#variantSelect').html('<option value="">Pilih Variant</option>').prop('disabled', true);
      $('#yearSelect').html('<option value="">Pilih Tahun</option>').prop('disabled', true);
      reloadTable();
    }, 1);
  });
  
  // Tambahkan touch event handler untuk perangkat mobile
  if ('ontouchstart' in window || navigator.maxTouchPoints) {
    $('.form-select').on('touchstart', function(e) {
      // Memastikan dropdown terbuka pada touch event
      $(this).focus();
    });
    
    // Hapus fokus dari dropdown setelah pilihan dibuat
    $('.form-select').on('change', function() {
      $(this).blur();
    });
    
    // Pastikan tidak ada konflik dengan event scroll
    $('.form-select').on('touchmove', function(e) {
      e.stopPropagation();
    });
  }
  
  // Ganti animasi DOM dengan waktu yang lebih cepat di mobile
  if (window.innerWidth <= 768) {
    $('.fadeInUp').css('animation-duration', '0.3s');
  }
  
  // Reset fokus setelah form reset
  $('#btnResetFilter').on('click', function() {
    setTimeout(function() {
      $('#brandSelect').focus();
    }, 100);
  });
});