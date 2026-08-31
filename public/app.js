// State Management
const state = {
  date: new Date().toISOString().split('T')[0],
  symbol: '',
  buyer: '',
  seller: '',
  sortBy: 'trade_time',
  order: 'desc',
  page: 1,
  limit: 50,
  totalPages: 1,
  currentRecords: []
};

// DOM Elements
const filterDate = document.getElementById('filterDate');
const filterSymbol = document.getElementById('filterSymbol');
const filterBuyer = document.getElementById('filterBuyer');
const filterSeller = document.getElementById('filterSeller');
const symbolList = document.getElementById('symbolList');

const applyFilterBtn = document.getElementById('applyFilterBtn');
const resetFilterBtn = document.getElementById('resetFilterBtn');
const exportBtn = document.getElementById('exportBtn');

const tableBody = document.getElementById('tableBody');
const loadingOverlay = document.getElementById('loadingOverlay');

const kpiTurnover = document.getElementById('kpiTurnover');
const kpiQuantity = document.getElementById('kpiQuantity');
const kpiTrades = document.getElementById('kpiTrades');
const kpiAvgRate = document.getElementById('kpiAvgRate');

const paginationInfo = document.getElementById('paginationInfo');
const pageTracker = document.getElementById('pageTracker');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');
const pageSizeSelect = document.getElementById('pageSize');

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
  filterDate.value = state.date;
  fetchSymbols();
  fetchData();

  // Event Listeners
  applyFilterBtn.addEventListener('click', handleFilterApply);
  resetFilterBtn.addEventListener('click', handleFilterReset);
  exportBtn.addEventListener('click', exportToCSV);

  prevPageBtn.addEventListener('click', () => changePage(-1));
  nextPageBtn.addEventListener('click', () => changePage(1));
  pageSizeSelect.addEventListener('change', (e) => {
    state.limit = parseInt(e.target.value);
    state.page = 1;
    fetchData();
  });

  // Table Column Header Sorting
  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.sortBy === field) {
        state.order = state.order === 'asc' ? 'desc' : 'asc';
      } else {
        state.sortBy = field;
        state.order = 'desc';
      }
      updateSortUI(th);
      fetchData();
    });
  });
});

// Fetch distinct symbols for autocomplete datalist
async function fetchSymbols() {
  try {
    const res = await fetch(`/api/symbols?date=${filterDate.value}`);
    if (!res.ok) return;
    const symbols = await res.json();
    symbolList.innerHTML = symbols.map(s => `<option value="${s}">`).join('');
  } catch (err) {
    console.error('Failed to load symbol list:', err);
  }
}

// Fetch Paginated Floorsheet Data
async function fetchData() {
  showLoading(true);

  const params = new URLSearchParams({
    date: state.date,
    sort_by: state.sortBy,
    order: state.order,
    page: state.page,
    limit: state.limit
  });

  if (state.symbol) params.append('symbol', state.symbol);
  if (state.buyer) params.append('buyer', state.buyer);
  if (state.seller) params.append('seller', state.seller);

  try {
    const res = await fetch(`/api/floorsheet?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
    
    const result = await res.json();
    state.currentRecords = result.data;
    state.totalPages = result.pagination.total_pages;

    renderKPIs(result.summary);
    renderTable(result.data);
    renderPagination(result.pagination);
  } catch (err) {
    console.error('Fetch Error:', err);
    tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--accent-red); padding: 20px;">Failed to load data from database.</td></tr>`;
  } finally {
    showLoading(false);
  }
}

// Render KPI Summary
function renderKPIs(summary) {
  kpiTurnover.textContent = `NPR ${summary.total_amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  kpiQuantity.textContent = summary.total_quantity.toLocaleString('en-IN');
  kpiTrades.textContent = summary.total_trades.toLocaleString('en-IN');
  kpiAvgRate.textContent = `NPR ${summary.avg_rate.toFixed(2)}`;
}

// Render Table Rows
function renderTable(records) {
  if (!records || records.length === 0) {
    tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 30px; color: var(--text-muted);">No records found matching current criteria.</td></tr>`;
    return;
  }

  tableBody.innerHTML = records.map(r => `
    <tr>
      <td>${r.trade_time_formatted}</td>
      <td style="color: var(--text-muted);">${r.contract_id}</td>
      <td><span class="symbol-tag">${r.symbol}</span></td>
      <td class="text-right">${r.buyer_broker}</td>
      <td class="text-right">${r.seller_broker}</td>
      <td class="text-right">${r.quantity.toLocaleString('en-IN')}</td>
      <td class="text-right">${r.rate.toFixed(1)}</td>
      <td class="text-right font-mono" style="color: var(--text-bright); font-weight:600;">${r.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
    </tr>
  `).join('');
}

// Render Pagination Controls
function renderPagination(p) {
  const start = p.total_records === 0 ? 0 : (p.current_page - 1) * p.limit + 1;
  const end = Math.min(p.current_page * p.limit, p.total_records);
  
  paginationInfo.textContent = `Showing ${start}-${end} of ${p.total_records.toLocaleString('en-IN')} trades`;
  pageTracker.textContent = `Page ${p.current_page} of ${p.total_pages}`;

  prevPageBtn.disabled = p.current_page <= 1;
  nextPageBtn.disabled = p.current_page >= p.total_pages;
}

function changePage(delta) {
  state.page += delta;
  fetchData();
}

function handleFilterApply() {
  state.date = filterDate.value;
  state.symbol = filterSymbol.value.trim().toUpperCase();
  state.buyer = filterBuyer.value.trim();
  state.seller = filterSeller.value.trim();
  state.page = 1;
  fetchSymbols();
  fetchData();
}

function handleFilterReset() {
  state.date = new Date().toISOString().split('T')[0];
  state.symbol = '';
  state.buyer = '';
  state.seller = '';
  state.page = 1;
  
  filterDate.value = state.date;
  filterSymbol.value = '';
  filterBuyer.value = '';
  filterSeller.value = '';
  
  fetchSymbols();
  fetchData();
}

function updateSortUI(activeTh) {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    th.querySelector('.sort-icon').textContent = '';
  });
  activeTh.classList.add(`sorted-${state.order}`);
  activeTh.querySelector('.sort-icon').textContent = state.order === 'asc' ? '▲' : '▼';
}

function showLoading(isLoading) {
  loadingOverlay.classList.toggle('hidden', !isLoading);
}

// Export Visible Page Dataset to CSV
function exportToCSV() {
  if (!state.currentRecords || state.currentRecords.length === 0) {
    alert("No data available to export.");
    return;
  }

  const headers = ["Contract ID", "Time", "Symbol", "Buyer Broker", "Seller Broker", "Quantity", "Rate", "Amount"];
  const rows = state.currentRecords.map(r => [
    r.contract_id,
    r.trade_time_formatted,
    r.symbol,
    r.buyer_broker,
    r.seller_broker,
    r.quantity,
    r.rate,
    r.amount
  ]);

  let csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `floorsheet_${state.date}_${state.symbol || 'ALL'}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
