// State Management for Scrip Analytics
const state = {
  date: '2026-08-31',
  startTime: '00:00:00',
  endTime: '23:59:59',
  searchSymbol: '',
  minTurnover: 0,
  sortBy: 'turnover',
  sortOrder: 'desc',
  drawerSortBy: 'buy_value',
  drawerSortOrder: 'desc',
  scrips: [],
  selectedSymbol: null,
  currentScripData: null,
  activeBucket: '15m',
  chartInstance: null,
  whaleFilter: 'all'
};

// DOM Element Selectors
const filterDate = document.getElementById('filterDate');
const filterStartTime = document.getElementById('filterStartTime');
const filterEndTime = document.getElementById('filterEndTime');
const searchSymbol = document.getElementById('searchSymbol');
const minTurnover = document.getElementById('minTurnover');
const applyFilterBtn = document.getElementById('applyFilterBtn');
const resetFilterBtn = document.getElementById('resetFilterBtn');
const exportCsvBtn = document.getElementById('exportCsvBtn');

const kpiTurnover = document.getElementById('kpiTurnover');
const kpiQuantity = document.getElementById('kpiQuantity');
const kpiTrades = document.getElementById('kpiTrades');
const kpiActiveScrips = document.getElementById('kpiActiveScrips');
const kpiTopTurnoverScrip = document.getElementById('kpiTopTurnoverScrip');

const scripTableBody = document.getElementById('scripTableBody');
const leaderboardInfo = document.getElementById('leaderboardInfo');
const loadingOverlay = document.getElementById('loadingOverlay');

// Drawer Elements
const drawerBackdrop = document.getElementById('drawerBackdrop');
const drawerLoadingOverlay = document.getElementById('drawerLoadingOverlay');
const drawerLoadingText = document.getElementById('drawerLoadingText');
const drawerTitle = document.getElementById('drawerTitle');
const drawerDateBadge = document.getElementById('drawerDateBadge');
const closeDrawerBtn = document.getElementById('closeDrawerBtn');

const sKpiTurnover = document.getElementById('sKpiTurnover');
const sKpiVolTrades = document.getElementById('sKpiVolTrades');
const sKpiLtpVwap = document.getElementById('sKpiLtpVwap');
const sKpiRange = document.getElementById('sKpiRange');
const sKpiConcentration = document.getElementById('sKpiConcentration');
const sKpiPeak = document.getElementById('sKpiPeak');

const brokerFilterInput = document.getElementById('brokerFilterInput');
const scripBrokersBody = document.getElementById('scripBrokersBody');
const cpRouteBody = document.getElementById('cpRouteBody');
const whaleFilterSelect = document.getElementById('whaleFilterSelect');
const whaleDealsBody = document.getElementById('whaleDealsBody');

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
  fetchScripsOverview();
});

// Load distinct trading dates
async function loadAvailableDates() {
  try {
    const res = await fetch('/api/script/dates');
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

// Bind Event Listeners
function bindEventListeners() {
  // Apply & Reset Filters
  applyFilterBtn.addEventListener('click', handleApplyFilters);
  resetFilterBtn.addEventListener('click', handleResetFilters);
  exportCsvBtn.addEventListener('click', exportScripsToCSV);

  // Time Preset Chips
  document.querySelectorAll('.time-chips .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.time-chips .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.startTime = chip.dataset.start;
      state.endTime = chip.dataset.end;
      filterStartTime.value = state.startTime.slice(0, 5);
      filterEndTime.value = state.endTime.slice(0, 5);
      fetchScripsOverview();
    });
  });

  // Live Symbol Search Filter
  searchSymbol.addEventListener('input', () => {
    state.searchSymbol = searchSymbol.value.trim().toUpperCase();
    renderScripLeaderboard();
  });

  // Table Sorting
  document.querySelectorAll('#scripTable th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.sortBy === field) {
        state.sortOrder = state.sortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        state.sortBy = field;
        state.sortOrder = 'desc';
      }
      updateSortUI(th);
      renderScripLeaderboard();
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
      if (state.selectedSymbol) {
        fetchScripDeepDive(state.selectedSymbol);
      }
    });
  });

  // Broker Filter in Drawer
  brokerFilterInput.addEventListener('input', () => {
    if (state.currentScripData && state.currentScripData.brokers) {
      const q = brokerFilterInput.value.trim();
      const filtered = q ? state.currentScripData.brokers.filter(b => String(b.broker_id).includes(q)) : state.currentScripData.brokers;
      renderDrawerBrokers(filtered);
    }
  });

  // Whale Deals Filter Selector
  whaleFilterSelect.addEventListener('change', () => {
    state.whaleFilter = whaleFilterSelect.value;
    if (state.currentScripData && state.currentScripData.whales) {
      renderDrawerWhales(filterWhalesList(state.currentScripData.whales));
  // Drawer Scrip Brokers Table Sorting
  document.querySelectorAll('#scripBrokersTable th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.drawerSortBy === field) {
        state.drawerSortOrder = state.drawerSortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        state.drawerSortBy = field;
        state.drawerSortOrder = 'desc';
      }
      updateDrawerSortUI(th);
      if (state.currentScripData && state.currentScripData.brokers) {
        const q = brokerFilterInput.value.trim();
        const filtered = q ? state.currentScripData.brokers.filter(b => String(b.broker_id).includes(q)) : state.currentScripData.brokers;
        renderDrawerBrokers(filtered);
      }
    });
  });
}

function updateDrawerSortUI(activeTh) {
  document.querySelectorAll('#scripBrokersTable th.sortable').forEach(th => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '';
  });
  activeTh.classList.add(`sorted-${state.drawerSortOrder}`);
  const icon = activeTh.querySelector('.sort-icon');
  if (icon) icon.textContent = state.drawerSortOrder === 'asc' ? '▲' : '▼';
}

function updateSortUI(activeTh) {
  document.querySelectorAll('#scripTable th.sortable').forEach(th => {
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
  state.minTurnover = parseFloat(minTurnover.value) || 0;
  state.searchSymbol = searchSymbol.value.trim().toUpperCase();
  fetchScripsOverview();
}

function handleResetFilters() {
  filterStartTime.value = '11:00';
  filterEndTime.value = '15:00';
  minTurnover.value = '0';
  searchSymbol.value = '';
  
  state.startTime = '00:00:00';
  state.endTime = '23:59:59';
  state.minTurnover = 0;
  state.searchSymbol = '';

  document.querySelectorAll('.time-chips .chip').forEach(c => c.classList.remove('active'));
  document.querySelector('.time-chips .chip[data-start="00:00:00"]').classList.add('active');

  fetchScripsOverview();
}

// Fetch Market Scrip Overview
async function fetchScripsOverview() {
  showLoading(true);
  try {
    const params = new URLSearchParams({
      date: state.date,
      start_time: state.startTime,
      end_time: state.endTime,
      min_turnover: state.minTurnover
    });

    const res = await fetch(`/api/script/overview?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch scrips overview`);

    const data = await res.json();
    state.scrips = data.scrips || [];

    renderMarketKPIs(data.market_summary, state.scrips);
    renderScripLeaderboard();
  } catch (err) {
    console.error('Error loading scrips overview:', err);
    scripTableBody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding: 30px; color: var(--accent-red);">Failed to load scrip intelligence from database.</td></tr>`;
  } finally {
    showLoading(false);
  }
}

// Render Macro KPIs
function renderMarketKPIs(summary, scrips) {
  kpiTurnover.textContent = formatNPR(summary.total_market_turnover);
  kpiQuantity.textContent = formatQty(summary.total_market_shares);
  kpiTrades.textContent = formatQty(summary.total_market_trades);
  kpiActiveScrips.textContent = formatQty(summary.active_scrips_count);

  if (scrips && scrips.length > 0) {
    const topScrip = scrips[0];
    kpiTopTurnoverScrip.textContent = `${topScrip.symbol} (${formatCompact(topScrip.turnover)})`;
  } else {
    kpiTopTurnoverScrip.textContent = '--';
  }
}

// Render Scrip Leaderboard Table
function renderScripLeaderboard() {
  let list = [...state.scrips];

  if (state.searchSymbol) {
    list = list.filter(s => s.symbol.includes(state.searchSymbol));
  }

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

  leaderboardInfo.textContent = `Showing ${list.length} active stocks on ${state.date}`;

  if (list.length === 0) {
    scripTableBody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding: 40px; color: var(--text-muted);">No scrips found matching the selected criteria.</td></tr>`;
    return;
  }

  scripTableBody.innerHTML = list.map(s => {
    const buyerDisplay = s.top_net_buyer 
      ? `<span class="badge-accum">#${s.top_net_buyer.broker_id} (+${formatQty(s.top_net_buyer.net_qty)})</span>` 
      : '<span style="color: var(--text-muted); font-size:11px;">-</span>';
    
    const sellerDisplay = s.top_net_seller 
      ? `<span class="badge-dist">#${s.top_net_seller.broker_id} (${formatQty(s.top_net_seller.net_qty)})</span>` 
      : '<span style="color: var(--text-muted); font-size:11px;">-</span>';

    return `
      <tr style="cursor: pointer;" onclick="openScripDeepDive('${s.symbol}')">
        <td>
          <span class="symbol-tag" style="font-size: 12px; font-weight: 700;">${s.symbol}</span>
        </td>
        <td class="text-right font-mono" style="font-weight: 700; color: var(--text-bright);">
          ${formatNPR(s.turnover)}
          <div style="font-size: 10px; color: var(--text-muted); font-weight: 400;">${s.market_share_pct.toFixed(2)}% of market</div>
        </td>
        <td class="text-right font-mono">${formatQty(s.quantity)}</td>
        <td class="text-right font-mono">${formatQty(s.trades_count)}</td>
        <td class="text-right font-mono" style="font-weight: 700; color: var(--accent-blue);">${s.ltp.toFixed(1)}</td>
        <td class="text-right font-mono" style="color: var(--text-bright);">${s.vwap.toFixed(1)}</td>
        <td class="text-right font-mono" style="font-size: 11px; color: var(--text-muted);">
          ${s.low_price.toFixed(1)} - ${s.high_price.toFixed(1)}
        </td>
        <td>${buyerDisplay}</td>
        <td>${sellerDisplay}</td>
        <td class="text-right font-mono" style="font-weight: 600; color: ${s.top3_concentration_pct >= 50 ? 'var(--accent-green)' : 'var(--text-bright)'};">
          ${s.top3_concentration_pct.toFixed(1)}%
        </td>
        <td class="text-right">
          <button class="btn-broker-action" onclick="event.stopPropagation(); openScripDeepDive('${s.symbol}')">🔍 Deep Dive</button>
        </td>
      </tr>
    `;
  }).join('');
}

// Deep Scrip Drilldown Drawer Implementation
async function openScripDeepDive(symbol) {
  state.selectedSymbol = symbol;
  drawerTitle.textContent = `📊 ${symbol} Deep Scrip Intelligence`;
  drawerDateBadge.textContent = state.date;
  drawerBackdrop.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  if (drawerLoadingOverlay) {
    drawerLoadingOverlay.classList.remove('hidden');
    drawerLoadingText.textContent = `Analyzing ${symbol} Deep Intelligence...`;
  }

  await fetchScripDeepDive(symbol);
}

function closeDrawer() {
  drawerBackdrop.classList.add('hidden');
  document.body.style.overflow = '';
  state.selectedSymbol = null;
}

async function fetchScripDeepDive(symbol) {
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

    const res = await fetch(`/api/script/${symbol}?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch scrip details`);

    const data = await res.json();
    state.currentScripData = data;

    renderDrawerKPIs(data.summary);
    renderDrawerChart(data.timeline);
    renderDrawerBrokers(data.brokers);
    renderDrawerCounterparties(data.counterparties);
    renderDrawerWhales(filterWhalesList(data.whales));

    if (drawerLoadingOverlay) {
      drawerLoadingOverlay.classList.add('hidden');
    }
  } catch (err) {
    console.error('Failed to fetch scrip deep dive:', err);
    if (drawerLoadingText) {
      drawerLoadingText.innerHTML = `<span style="color: var(--accent-red);">Failed to load scrip intelligence.<br/><small>${err.message}</small></span>`;
    }
  }
}

function renderDrawerKPIs(s) {
  sKpiTurnover.textContent = formatNPR(s.turnover);
  sKpiVolTrades.textContent = `Vol: ${formatCompact(s.quantity)} | Tr: ${formatQty(s.trades_count)}`;
  sKpiLtpVwap.textContent = `LTP: ${s.ltp.toFixed(1)} | VWAP: ${s.vwap.toFixed(1)}`;
  sKpiRange.textContent = `${s.low_price.toFixed(1)} - ${s.high_price.toFixed(1)} (Δ ${s.price_spread.toFixed(1)})`;
  sKpiConcentration.textContent = `${s.top3_concentration_pct.toFixed(1)}%`;
  sKpiPeak.textContent = s.peak_trading_window || '--:--';
}

function renderDrawerChart(timeline) {
  const ctx = document.getElementById('timelineChart').getContext('2d');

  if (state.chartInstance) {
    state.chartInstance.destroy();
  }

  const labels = timeline.map(t => t.time_label);
  const vwapData = timeline.map(t => t.vwap);
  const highData = timeline.map(t => t.high_price);
  const lowData = timeline.map(t => t.low_price);
  const volData = timeline.map(t => t.volume);

  state.chartInstance = new Chart(ctx, {
    data: {
      labels: labels,
      datasets: [
        {
          type: 'line',
          label: 'VWAP (NPR)',
          data: vwapData,
          borderColor: '#2962ff',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          tension: 0.2,
          yAxisID: 'yPrice'
        },
        {
          type: 'line',
          label: 'High Price',
          data: highData,
          borderColor: 'rgba(38, 166, 154, 0.4)',
          borderDash: [4, 4],
          borderWidth: 1,
          pointRadius: 0,
          yAxisID: 'yPrice'
        },
        {
          type: 'line',
          label: 'Low Price',
          data: lowData,
          borderColor: 'rgba(239, 83, 80, 0.4)',
          borderDash: [4, 4],
          borderWidth: 1,
          pointRadius: 0,
          yAxisID: 'yPrice'
        },
        {
          type: 'bar',
          label: 'Volume Traded',
          data: volData,
          backgroundColor: 'rgba(38, 166, 154, 0.5)',
          borderColor: '#26a69a',
          borderWidth: 1,
          borderRadius: 2,
          yAxisID: 'yVolume'
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
          padding: 10
        }
      },
      scales: {
        x: {
          grid: { color: '#262b37' },
          ticks: { color: '#787b86', font: { family: 'JetBrains Mono', size: 10 } }
        },
        yPrice: {
          type: 'linear',
          position: 'left',
          grid: { color: '#262b37' },
          ticks: {
            color: '#2962ff',
            font: { family: 'JetBrains Mono', size: 10 }
          }
        },
        yVolume: {
          type: 'linear',
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: {
            color: '#26a69a',
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

function renderDrawerBrokers(brokers) {
  if (!brokers || brokers.length === 0) {
    scripBrokersBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 20px; color: var(--text-muted);">No broker activity in this window.</td></tr>`;
    return;
  }

  let list = [...brokers];
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

  scripBrokersBody.innerHTML = list.map(b => {
    const isNetBuy = b.flow_status === 'NET BUYING';
    const badge = isNetBuy 
      ? `<span class="badge-accum">🟢 NET BUYING</span>` 
      : `<span class="badge-dist">🔴 NET SELLING</span>`;
    const netClass = isNetBuy ? 'text-green' : 'text-red';
    const netSign = b.net_flow_value >= 0 ? '+' : '';

    return `
      <tr>
        <td style="font-weight: 700; color: var(--accent-blue);">Broker #${b.broker_id}</td>
        <td class="text-right font-mono">${formatQty(b.buy_qty)}</td>
        <td class="text-right font-mono">${formatQty(b.sell_qty)}</td>
        <td class="text-right font-mono ${netClass}" style="font-weight: 700;">${netSign}${formatQty(b.net_flow_qty)}</td>
        <td class="text-right font-mono">${formatNPR(b.buy_value)}</td>
        <td class="text-right font-mono">${formatNPR(b.sell_value)}</td>
        <td class="text-right font-mono ${netClass}" style="font-weight: 700;">${netSign}${formatNPR(b.net_flow_value)}</td>
        <td class="text-right font-mono">${b.buy_vwap.toFixed(1)}</td>
        <td class="text-right font-mono">${b.sell_vwap.toFixed(1)}</td>
        <td class="text-right">${badge}</td>
      </tr>
    `;
  }).join('');
}

function renderDrawerCounterparties(cp) {
  if (!cp || cp.length === 0) {
    cpRouteBody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 14px; color: var(--text-muted);">No counterparty deals found.</td></tr>`;
    return;
  }

  cpRouteBody.innerHTML = cp.map(c => `
    <tr>
      <td>
        <span style="font-weight: 700; color: var(--accent-green);">#${c.buyer_broker}</span>
        <span style="color: var(--text-muted); margin: 0 4px;">➔</span>
        <span style="font-weight: 700; color: var(--accent-red);">#${c.seller_broker}</span>
      </td>
      <td class="text-right font-mono">${formatNPR(c.value)}</td>
      <td class="text-right font-mono">${formatQty(c.quantity)}</td>
      <td class="text-right font-mono">${c.route_vwap.toFixed(1)}</td>
      <td class="text-right font-mono text-green" style="font-weight: 700;">${c.share_pct.toFixed(1)}%</td>
    </tr>
  `).join('');
}

function filterWhalesList(whales) {
  if (!whales) return [];
  if (state.whaleFilter === 'qty1k') return whales.filter(w => w.quantity >= 1000);
  if (state.whaleFilter === 'qty5k') return whales.filter(w => w.quantity >= 5000);
  if (state.whaleFilter === 'val5l') return whales.filter(w => w.amount >= 500000);
  if (state.whaleFilter === 'val10l') return whales.filter(w => w.amount >= 1000000);
  return whales;
}

function renderDrawerWhales(whales) {
  if (!whales || whales.length === 0) {
    whaleDealsBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 14px; color: var(--text-muted);">No whale contracts matching filter.</td></tr>`;
    return;
  }

  whaleDealsBody.innerHTML = whales.map(w => `
    <tr>
      <td class="font-mono" style="font-size: 11px; color: var(--text-muted);">${w.trade_time}</td>
      <td class="font-mono" style="font-size: 10px; color: var(--text-muted);">#${w.contract_id}</td>
      <td>
        <span style="font-weight: 700; color: var(--accent-green);">#${w.buyer_broker}</span>
        <span style="color: var(--text-muted); margin: 0 2px;">➔</span>
        <span style="font-weight: 700; color: var(--accent-red);">#${w.seller_broker}</span>
      </td>
      <td class="text-right font-mono" style="font-weight: 700;">${formatQty(w.quantity)}</td>
      <td class="text-right font-mono">${w.rate.toFixed(1)}</td>
      <td class="text-right font-mono text-green" style="font-weight: 700;">${formatNPR(w.amount)}</td>
    </tr>
  `).join('');
}

function showLoading(isLoading) {
  loadingOverlay.classList.toggle('hidden', !isLoading);
}

// Export Leaderboard to CSV
function exportScripsToCSV() {
  if (!state.scrips || state.scrips.length === 0) {
    alert("No scrip matrix data to export.");
    return;
  }

  const headers = [
    "Symbol",
    "Turnover (NPR)",
    "Volume (Shares)",
    "Trades Count",
    "LTP (NPR)",
    "VWAP (NPR)",
    "High Price",
    "Low Price",
    "Price Spread",
    "Market Share %",
    "Top 3 Buyer Share %",
    "Top Net Buyer Broker",
    "Top Net Buyer Net Qty",
    "Top Net Buyer Net Value",
    "Top Net Seller Broker",
    "Top Net Seller Net Qty",
    "Top Net Seller Net Value"
  ];

  const rows = state.scrips.map(s => [
    s.symbol,
    s.turnover,
    s.quantity,
    s.trades_count,
    s.ltp,
    s.vwap,
    s.high_price,
    s.low_price,
    s.price_spread,
    s.market_share_pct,
    s.top3_concentration_pct,
    s.top_net_buyer ? s.top_net_buyer.broker_id : '',
    s.top_net_buyer ? s.top_net_buyer.net_qty : '',
    s.top_net_buyer ? s.top_net_buyer.net_value : '',
    s.top_net_seller ? s.top_net_seller.broker_id : '',
    s.top_net_seller ? s.top_net_seller.net_qty : '',
    s.top_net_seller ? s.top_net_seller.net_value : ''
  ]);

  let csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `nepse_scrips_matrix_${state.date}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
