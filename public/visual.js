// State Management for Visual Analytics
const state = {
  date: '2026-08-31',
  startTime: '00:00:00',
  endTime: '23:59:59',
  searchBroker: '',
  minActivity: 0,
  sortBy: 'gross_activity',
  sortOrder: 'desc',
  drawerSortBy: 'buy_value',
  drawerSortOrder: 'desc',
  brokers: [],
  selectedBrokerId: null,
  currentBrokerData: null,
  activeBucket: '15m',
  chartInstance: null
};

// DOM Element Selectors
const filterDate = document.getElementById('filterDate');
const filterStartTime = document.getElementById('filterStartTime');
const filterEndTime = document.getElementById('filterEndTime');
const searchBroker = document.getElementById('searchBroker');
const minTurnover = document.getElementById('minTurnover');
const applyFilterBtn = document.getElementById('applyFilterBtn');
const resetFilterBtn = document.getElementById('resetFilterBtn');
const exportCsvBtn = document.getElementById('exportCsvBtn');

const kpiTurnover = document.getElementById('kpiTurnover');
const kpiQuantity = document.getElementById('kpiQuantity');
const kpiTrades = document.getElementById('kpiTrades');
const kpiTopAccumulator = document.getElementById('kpiTopAccumulator');
const kpiTopDistributor = document.getElementById('kpiTopDistributor');

const brokerTableBody = document.getElementById('brokerTableBody');
const leaderboardInfo = document.getElementById('leaderboardInfo');
const loadingOverlay = document.getElementById('loadingOverlay');

// Drawer Elements
const drawerBackdrop = document.getElementById('drawerBackdrop');
const drawerLoadingOverlay = document.getElementById('drawerLoadingOverlay');
const drawerLoadingText = document.getElementById('drawerLoadingText');
const drawerTitle = document.getElementById('drawerTitle');
const drawerDateBadge = document.getElementById('drawerDateBadge');
const closeDrawerBtn = document.getElementById('closeDrawerBtn');

const bKpiGross = document.getElementById('bKpiGross');
const bKpiBuySell = document.getElementById('bKpiBuySell');
const bKpiNet = document.getElementById('bKpiNet');
const bKpiRatio = document.getElementById('bKpiRatio');
const bKpiPeak = document.getElementById('bKpiPeak');

const scripFilterInput = document.getElementById('scripFilterInput');
const brokerScripsBody = document.getElementById('brokerScripsBody');
const cpBoughtBody = document.getElementById('cpBoughtBody');
const cpSoldBody = document.getElementById('cpSoldBody');

// Currency & Number Formatting Helpers
function formatNPR(val, decimals = 2) {
  if (val === null || val === undefined || isNaN(val)) return 'NPR 0.00';
  return 'NPR ' + Number(val).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function formatQty(val) {
  if (val === null || val === undefined || isNaN(val)) return '0';
  return Number(val).toLocaleString('en-IN');
}

function formatCompact(val) {
  if (!val) return '0';
  const num = Math.abs(val);
  if (num >= 10000000) return (val / 10000000).toFixed(2) + ' Cr';
  if (num >= 100000) return (val / 100000).toFixed(2) + ' L';
  if (num >= 1000) return (val / 1000).toFixed(1) + ' K';
  return Number(val).toFixed(0);
}

// App Initialization
document.addEventListener('DOMContentLoaded', async () => {
  await loadAvailableDates();
  bindEventListeners();
  fetchOverviewData();
});

// Load distinct trading dates
async function loadAvailableDates() {
  try {
    const res = await fetch('/api/visual/dates');
    if (res.ok) {
      const dates = await res.json();
      if (dates && dates.length > 0) {
        state.date = dates[0].date;
      }
    }
  } catch (err) {
    console.warn('Could not load dates from API, using default:', err);
  }
  filterDate.value = state.date;
}

// Bind User Actions & Event Listeners
function bindEventListeners() {
  // Apply & Reset Filters
  applyFilterBtn.addEventListener('click', handleApplyFilters);
  resetFilterBtn.addEventListener('click', handleResetFilters);
  exportCsvBtn.addEventListener('click', exportMatrixToCSV);

  // Time Preset Chips
  document.querySelectorAll('.time-chips .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.time-chips .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.startTime = chip.dataset.start;
      state.endTime = chip.dataset.end;
      filterStartTime.value = state.startTime.slice(0, 5);
      filterEndTime.value = state.endTime.slice(0, 5);
      fetchOverviewData();
    });
  });

  // Broker Search live filter
  searchBroker.addEventListener('input', () => {
    state.searchBroker = searchBroker.value.trim();
    renderLeaderboardTable();
  });

  // Table Column Header Sorting
  document.querySelectorAll('#brokerTable th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.sortBy === field) {
        state.sortOrder = state.sortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        state.sortBy = field;
        state.sortOrder = 'desc';
      }
      updateSortUI(th);
      renderLeaderboardTable();
    });
  });

  // Drawer Controls
  closeDrawerBtn.addEventListener('click', closeDrawer);
  drawerBackdrop.addEventListener('click', (e) => {
    if (e.target === drawerBackdrop) closeDrawer();
  });

  // Bucket Switcher
  document.querySelectorAll('.bucket-controls .btn-bucket').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.bucket-controls .btn-bucket').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeBucket = btn.dataset.bucket;
      if (state.selectedBrokerId) {
        fetchBrokerDeepDive(state.selectedBrokerId);
      }
    });
  });

  // Scrips Filter in Drawer
  scripFilterInput.addEventListener('input', () => {
    if (state.currentBrokerData && state.currentBrokerData.scrips) {
      const q = scripFilterInput.value.trim().toUpperCase();
      const filtered = state.currentBrokerData.scrips.filter(s => s.symbol.includes(q));
  // Drawer Scrips Table Sorting
  document.querySelectorAll('#brokerScripsTable th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.drawerSortBy === field) {
        state.drawerSortOrder = state.drawerSortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        state.drawerSortBy = field;
        state.drawerSortOrder = 'desc';
      }
      updateDrawerSortUI(th);
      if (state.currentBrokerData && state.currentBrokerData.scrips) {
        const q = scripFilterInput.value.trim().toUpperCase();
        const filtered = q ? state.currentBrokerData.scrips.filter(s => s.symbol.includes(q)) : state.currentBrokerData.scrips;
        renderDrawerScrips(filtered);
      }
    });
  });
}

function updateDrawerSortUI(activeTh) {
  document.querySelectorAll('#brokerScripsTable th.sortable').forEach(th => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '';
  });
  activeTh.classList.add(`sorted-${state.drawerSortOrder}`);
  const icon = activeTh.querySelector('.sort-icon');
  if (icon) icon.textContent = state.drawerSortOrder === 'asc' ? '▲' : '▼';
}

function updateSortUI(activeTh) {
  document.querySelectorAll('#brokerTable th.sortable').forEach(th => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '';
  });
  activeTh.classList.add(`sorted-${state.sortOrder}`);
  const icon = activeTh.querySelector('.sort-icon');
  if (icon) icon.textContent = state.sortOrder === 'asc' ? '▲' : '▼';
}

function handleApplyFilters() {
  state.date = filterDate.value;
  state.startTime = filterStartTime.value ? filterStartTime.value + ':00' : '00:00:00';
  state.endTime = filterEndTime.value ? filterEndTime.value + ':59' : '23:59:59';
  state.minActivity = parseFloat(minTurnover.value) || 0;
  state.searchBroker = searchBroker.value.trim();
  fetchOverviewData();
}

function handleResetFilters() {
  filterStartTime.value = '11:00';
  filterEndTime.value = '15:00';
  minTurnover.value = '0';
  searchBroker.value = '';
  
  state.startTime = '00:00:00';
  state.endTime = '23:59:59';
  state.minActivity = 0;
  state.searchBroker = '';

  document.querySelectorAll('.time-chips .chip').forEach(c => c.classList.remove('active'));
  document.querySelector('.time-chips .chip[data-start="00:00:00"]').classList.add('active');

  fetchOverviewData();
}

// Fetch Market Overview & Broker Matrix
async function fetchOverviewData() {
  showLoading(true);
  try {
    const params = new URLSearchParams({
      date: state.date,
      start_time: state.startTime,
      end_time: state.endTime,
      min_activity: state.minActivity
    });

    const res = await fetch(`/api/visual/overview?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch market overview`);

    const data = await res.json();
    state.brokers = data.brokers || [];

    renderMarketKPIs(data.market_summary, state.brokers);
    renderLeaderboardTable();
  } catch (err) {
    console.error('Error loading overview:', err);
    brokerTableBody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding: 30px; color: var(--accent-red);">Failed to load broker matrix from database.</td></tr>`;
  } finally {
    showLoading(false);
  }
}

// Render Macro KPIs
function renderMarketKPIs(summary, brokers) {
  kpiTurnover.textContent = formatNPR(summary.total_market_turnover);
  kpiQuantity.textContent = formatQty(summary.total_market_shares);
  kpiTrades.textContent = formatQty(summary.total_market_trades);

  if (brokers && brokers.length > 0) {
    const topAccum = [...brokers].sort((a, b) => b.net_flow_value - a.net_flow_value)[0];
    const topDist = [...brokers].sort((a, b) => a.net_flow_value - b.net_flow_value)[0];

    if (topAccum && topAccum.net_flow_value > 0) {
      kpiTopAccumulator.textContent = `Broker #${topAccum.broker_id} (+${formatCompact(topAccum.net_flow_value)})`;
    } else {
      kpiTopAccumulator.textContent = 'None';
    }

    if (topDist && topDist.net_flow_value < 0) {
      kpiTopDistributor.textContent = `Broker #${topDist.broker_id} (${formatCompact(topDist.net_flow_value)})`;
    } else {
      kpiTopDistributor.textContent = 'None';
    }
  } else {
    kpiTopAccumulator.textContent = 'Broker --';
    kpiTopDistributor.textContent = 'Broker --';
  }
}

// Render Broker Leaderboard Table
function renderLeaderboardTable() {
  let list = [...state.brokers];

  // Filter by search broker number
  if (state.searchBroker) {
    list = list.filter(b => String(b.broker_id).includes(state.searchBroker));
  }

  // Sort list
  list.sort((a, b) => {
    let valA = a[state.sortBy];
    let valB = b[state.sortBy];
    if (valA === null || valA === undefined) valA = -Infinity;
    if (valB === null || valB === undefined) valB = -Infinity;
    if (state.sortOrder === 'asc') {
      return valA > valB ? 1 : -1;
    } else {
      return valA < valB ? 1 : -1;
    }
  });

  leaderboardInfo.textContent = `Showing ${list.length} active brokers on ${state.date}`;

  if (list.length === 0) {
    brokerTableBody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding: 40px; color: var(--text-muted);">No broker activity found for the selected criteria.</td></tr>`;
    return;
  }

  brokerTableBody.innerHTML = list.map(b => {
    const isNetPositive = b.net_flow_value >= 0;
    const netClass = isNetPositive ? 'text-green' : 'text-red';
    const netSign = isNetPositive ? '+' : '';
    const ratioDisplay = b.buy_sell_ratio !== null ? b.buy_sell_ratio.toFixed(2) : '∞';

    return `
      <tr style="cursor: pointer;" onclick="openBrokerDeepDive(${b.broker_id})">
        <td>
          <span style="font-weight: 700; color: var(--accent-blue); font-size: 13px;">#${b.broker_id}</span>
        </td>
        <td class="text-right font-mono" style="font-weight: 700; color: var(--text-bright);">
          ${formatNPR(b.gross_activity)}
          <div style="font-size: 10px; color: var(--text-muted); font-weight: 400;">${b.market_share_pct.toFixed(2)}% mkt share</div>
        </td>
        <td class="text-right font-mono">${formatNPR(b.buy_value)}</td>
        <td class="text-right font-mono">${formatNPR(b.sell_value)}</td>
        <td class="text-right font-mono ${netClass}" style="font-weight: 700;">
          ${netSign}${formatNPR(b.net_flow_value)}
        </td>
        <td class="text-right font-mono ${netClass}">
          ${netSign}${b.net_flow_pct.toFixed(1)}%
        </td>
        <td class="text-right font-mono" style="color: var(--text-bright);">
          ${ratioDisplay}
        </td>
        <td>${renderScripPill(b.top_bought, 'buy')}</td>
        <td>${renderScripPill(b.top_sold, 'sell')}</td>
        <td>${renderScripPill(b.top_accumulation, 'accum')}</td>
        <td>${renderScripPill(b.top_distribution, 'dist')}</td>
        <td class="text-right">
          <button class="btn-broker-action" onclick="event.stopPropagation(); openBrokerDeepDive(${b.broker_id})">🔍 Deep Dive</button>
        </td>
      </tr>
    `;
  }).join('');
}

function renderScripPill(item, type) {
  if (!item || !item.symbol) return '<span style="color: var(--text-muted); font-size:11px;">-</span>';
  
  let valDisplay = '';
  if (type === 'accum') {
    valDisplay = `<span class="badge-accum">+${formatQty(item.net_qty)} (${formatCompact(item.net_value)})</span>`;
  } else if (type === 'dist') {
    valDisplay = `<span class="badge-dist">${formatQty(item.net_qty)} (${formatCompact(item.net_value)})</span>`;
  } else {
    valDisplay = `<span class="scrip-sub">${formatQty(item.quantity)} · ${formatCompact(item.value)}</span>`;
  }

  return `
    <div class="scrip-cell">
      <span class="scrip-sym">${item.symbol}</span>
      ${valDisplay}
    </div>
  `;
}

// Deep Dive Drawer Implementation
async function openBrokerDeepDive(brokerId) {
  state.selectedBrokerId = brokerId;
  drawerTitle.textContent = `🏢 Broker #${brokerId} Deep Intelligence`;
  drawerDateBadge.textContent = state.date;
  drawerBackdrop.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  if (drawerLoadingOverlay) {
    drawerLoadingOverlay.classList.remove('hidden');
    drawerLoadingText.textContent = `Analyzing Broker #${brokerId} Intelligence...`;
  }

  await fetchBrokerDeepDive(brokerId);
}

function closeDrawer() {
  drawerBackdrop.classList.add('hidden');
  document.body.style.overflow = '';
  state.selectedBrokerId = null;
}

async function fetchBrokerDeepDive(brokerId) {
  if (drawerLoadingOverlay) {
    drawerLoadingOverlay.classList.remove('hidden');
  }

  try {
    const params = new URLSearchParams({
      date: state.date,
      start_time: state.startTime,
      end_time: state.endTime,
      bucket: state.activeBucket
    });

    const res = await fetch(`/api/visual/broker/${brokerId}?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch broker details`);

    const data = await res.json();
    state.currentBrokerData = data;

    renderDrawerKPIs(data.summary);
    renderDrawerChart(data.timeline);
    renderDrawerScrips(data.scrips);
    renderDrawerCounterparties(data.counterparties);

    if (drawerLoadingOverlay) {
      drawerLoadingOverlay.classList.add('hidden');
    }
  } catch (err) {
    console.error('Failed to fetch broker deep dive:', err);
    if (drawerLoadingText) {
      drawerLoadingText.innerHTML = `<span style="color: var(--accent-red);">Failed to load broker intelligence.<br/><small>${err.message}</small></span>`;
    }
  }
}

function renderDrawerKPIs(s) {
  bKpiGross.textContent = formatNPR(s.gross_activity);
  bKpiBuySell.textContent = `Buy: ${formatCompact(s.buy_value)} | Sell: ${formatCompact(s.sell_value)}`;
  
  const isPos = s.net_flow_value >= 0;
  bKpiNet.className = `kpi-value ${isPos ? 'text-green' : 'text-red'}`;
  bKpiNet.textContent = `${isPos ? '+' : ''}${formatNPR(s.net_flow_value)} (${s.net_flow_pct.toFixed(1)}%)`;
  
  bKpiRatio.textContent = s.buy_sell_ratio !== null ? s.buy_sell_ratio.toFixed(2) : '∞';
  bKpiPeak.textContent = s.peak_trading_window || '--:--';
}

function renderDrawerChart(timeline) {
  const ctx = document.getElementById('timelineChart').getContext('2d');

  if (state.chartInstance) {
    state.chartInstance.destroy();
  }

  const labels = timeline.map(t => t.time_label);
  const buyData = timeline.map(t => t.buy_value);
  const sellData = timeline.map(t => t.sell_value);
  const netData = timeline.map(t => t.net_flow_value);

  state.chartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Buy Turnover (NPR)',
          data: buyData,
          backgroundColor: 'rgba(38, 166, 154, 0.7)',
          borderColor: '#26a69a',
          borderWidth: 1,
          borderRadius: 3,
          order: 2
        },
        {
          label: 'Sell Turnover (NPR)',
          data: sellData,
          backgroundColor: 'rgba(239, 83, 80, 0.7)',
          borderColor: '#ef5350',
          borderWidth: 1,
          borderRadius: 3,
          order: 2
        },
        {
          label: 'Net Flow (NPR)',
          data: netData,
          type: 'line',
          borderColor: '#2962ff',
          backgroundColor: 'rgba(41, 98, 255, 0.15)',
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.3,
          fill: true,
          order: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          labels: {
            color: '#d1d4dc',
            font: { family: 'Inter', size: 11, weight: '600' }
          }
        },
        tooltip: {
          backgroundColor: '#1e222d',
          titleColor: '#ffffff',
          bodyColor: '#d1d4dc',
          borderColor: '#363c4e',
          borderWidth: 1,
          padding: 10,
          callbacks: {
            label: function(context) {
              return `${context.dataset.label}: ${formatNPR(context.raw)}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: '#262b37' },
          ticks: { color: '#787b86', font: { family: 'JetBrains Mono', size: 10 } }
        },
        y: {
          grid: { color: '#262b37' },
          ticks: {
            color: '#787b86',
            font: { family: 'JetBrains Mono', size: 10 },
            callback: function(val) {
              return formatCompact(val);
            }
          }
        }
      }
    }
  });
}

function renderDrawerScrips(scrips) {
  if (!scrips || scrips.length === 0) {
    brokerScripsBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 20px; color: var(--text-muted);">No scrips traded in this window.</td></tr>`;
    return;
  }

  let list = [...scrips];
  list.sort((a, b) => {
    let valA = a[state.drawerSortBy];
    let valB = b[state.drawerSortBy];
    if (valA === null || valA === undefined) valA = -Infinity;
    if (valB === null || valB === undefined) valB = -Infinity;
    if (state.drawerSortOrder === 'asc') {
      return valA > valB ? 1 : -1;
    } else {
      return valA < valB ? 1 : -1;
    }
  });

  brokerScripsBody.innerHTML = list.map(s => {
    const isAccum = s.flow_status === 'ACCUMULATING';
    const badge = isAccum 
      ? `<span class="badge-accum">🟢 ACCUMULATING</span>` 
      : `<span class="badge-dist">🔴 DISTRIBUTING</span>`;
    const netClass = isAccum ? 'text-green' : 'text-red';
    const netSign = s.net_flow_value >= 0 ? '+' : '';

    return `
      <tr>
        <td><span class="symbol-tag">${s.symbol}</span></td>
        <td class="text-right font-mono">${formatQty(s.buy_qty)}</td>
        <td class="text-right font-mono">${formatQty(s.sell_qty)}</td>
        <td class="text-right font-mono ${netClass}" style="font-weight: 700;">${netSign}${formatQty(s.net_flow_qty)}</td>
        <td class="text-right font-mono">${formatNPR(s.buy_value)}</td>
        <td class="text-right font-mono">${formatNPR(s.sell_value)}</td>
        <td class="text-right font-mono ${netClass}" style="font-weight: 700;">${netSign}${formatNPR(s.net_flow_value)}</td>
        <td class="text-right font-mono">${s.avg_buy_rate.toFixed(1)}</td>
        <td class="text-right font-mono">${s.avg_sell_rate.toFixed(1)}</td>
        <td class="text-right">${badge}</td>
      </tr>
    `;
  }).join('');
}

function renderDrawerCounterparties(cp) {
  // Bought From
  if (cp.bought_from && cp.bought_from.length > 0) {
    cpBoughtBody.innerHTML = cp.bought_from.map(c => `
      <tr>
        <td style="font-weight: 700; color: var(--accent-blue);">Broker #${c.counter_broker}</td>
        <td class="text-right font-mono">${formatNPR(c.value)}</td>
        <td class="text-right font-mono">${formatQty(c.quantity)}</td>
        <td class="text-right font-mono">${formatQty(c.trades_count)}</td>
        <td class="text-right font-mono text-green" style="font-weight: 700;">${c.buy_value_share_pct.toFixed(1)}%</td>
      </tr>
    `).join('');
  } else {
    cpBoughtBody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 12px; color: var(--text-muted);">No counterparty buys.</td></tr>`;
  }

  // Sold To
  if (cp.sold_to && cp.sold_to.length > 0) {
    cpSoldBody.innerHTML = cp.sold_to.map(c => `
      <tr>
        <td style="font-weight: 700; color: var(--accent-blue);">Broker #${c.counter_broker}</td>
        <td class="text-right font-mono">${formatNPR(c.value)}</td>
        <td class="text-right font-mono">${formatQty(c.quantity)}</td>
        <td class="text-right font-mono">${formatQty(c.trades_count)}</td>
        <td class="text-right font-mono text-red" style="font-weight: 700;">${c.sell_value_share_pct.toFixed(1)}%</td>
      </tr>
    `).join('');
  } else {
    cpSoldBody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 12px; color: var(--text-muted);">No counterparty sells.</td></tr>`;
  }
}

function showLoading(isLoading) {
  loadingOverlay.classList.toggle('hidden', !isLoading);
}

// Export Leaderboard to CSV
function exportMatrixToCSV() {
  if (!state.brokers || state.brokers.length === 0) {
    alert("No broker matrix data to export.");
    return;
  }

  const headers = [
    "Broker ID",
    "Gross Activity (NPR)",
    "Buy Turnover (NPR)",
    "Sell Turnover (NPR)",
    "Net Flow Value (NPR)",
    "Net Flow %",
    "Buy/Sell Ratio",
    "Market Share %",
    "Top Bought Scrip",
    "Top Bought Value",
    "Top Sold Scrip",
    "Top Sold Value",
    "Top Accumulation Scrip",
    "Top Accumulation Net Qty",
    "Top Distribution Scrip",
    "Top Distribution Net Qty"
  ];

  const rows = state.brokers.map(b => [
    b.broker_id,
    b.gross_activity,
    b.buy_value,
    b.sell_value,
    b.net_flow_value,
    b.net_flow_pct,
    b.buy_sell_ratio !== null ? b.buy_sell_ratio : '',
    b.market_share_pct,
    b.top_bought ? b.top_bought.symbol : '',
    b.top_bought ? b.top_bought.value : '',
    b.top_sold ? b.top_sold.symbol : '',
    b.top_sold ? b.top_sold.value : '',
    b.top_accumulation ? b.top_accumulation.symbol : '',
    b.top_accumulation ? b.top_accumulation.net_qty : '',
    b.top_distribution ? b.top_distribution.symbol : '',
    b.top_distribution ? b.top_distribution.net_qty : ''
  ]);

  let csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `nepse_broker_matrix_${state.date}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
