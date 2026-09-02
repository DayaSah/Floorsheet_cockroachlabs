// State Management for Multi-Day Analytics
const state = {
  preset: '5D',
  startDate: '',
  endDate: '',
  viewMode: 'brokers', // 'brokers' or 'scrips'
  searchQuery: '',
  brokerSortBy: 'gross_activity',
  brokerSortOrder: 'desc',
  scripSortBy: 'turnover',
  scripSortOrder: 'desc',
  drawerSortBy: 'buy_amount',
  drawerSortOrder: 'desc',
  brokers: [],
  scrips: [],
  period: null,
  selectedDrawerType: null, // 'broker' or 'scrip'
  selectedDrawerId: null,
  currentDrawerData: null,
  chartInstance: null
};

// DOM Selectors
const customStartGroup = document.getElementById('customStartGroup');
const customEndGroup = document.getElementById('customEndGroup');
const filterStartDate = document.getElementById('filterStartDate');
const filterEndDate = document.getElementById('filterEndDate');
const searchInput = document.getElementById('searchInput');
const applyFilterBtn = document.getElementById('applyFilterBtn');
const resetFilterBtn = document.getElementById('resetFilterBtn');
const exportCsvBtn = document.getElementById('exportCsvBtn');
const windowMetaText = document.getElementById('windowMetaText');

const kpiTurnover = document.getElementById('kpiTurnover');
const kpiQuantity = document.getElementById('kpiQuantity');
const kpiTrades = document.getElementById('kpiTrades');
const kpiActiveScrips = document.getElementById('kpiActiveScrips');
const kpiActiveBrokers = document.getElementById('kpiActiveBrokers');

const viewBrokersBtn = document.getElementById('viewBrokersBtn');
const viewScripsBtn = document.getElementById('viewScripsBtn');
const brokerSection = document.getElementById('brokerSection');
const scripSection = document.getElementById('scripSection');

const brokerMultiBody = document.getElementById('brokerMultiBody');
const scripMultiBody = document.getElementById('scripMultiBody');
const brokerMultiInfo = document.getElementById('brokerMultiInfo');
const scripMultiInfo = document.getElementById('scripMultiInfo');
const loadingOverlay = document.getElementById('loadingOverlay');

// Drawer Elements
const drawerBackdrop = document.getElementById('drawerBackdrop');
const drawerLoadingOverlay = document.getElementById('drawerLoadingOverlay');
const drawerLoadingText = document.getElementById('drawerLoadingText');
const drawerTitle = document.getElementById('drawerTitle');
const drawerPeriodBadge = document.getElementById('drawerPeriodBadge');
const closeDrawerBtn = document.getElementById('closeDrawerBtn');

const dKpiTitle1 = document.getElementById('dKpiTitle1');
const dKpiVal1 = document.getElementById('dKpiVal1');
const dKpiTitle2 = document.getElementById('dKpiTitle2');
const dKpiVal2 = document.getElementById('dKpiVal2');
const dKpiTitle3 = document.getElementById('dKpiTitle3');
const dKpiVal3 = document.getElementById('dKpiVal3');
const dKpiTitle4 = document.getElementById('dKpiTitle4');
const dKpiVal4 = document.getElementById('dKpiVal4');

const chartTitleText = document.getElementById('chartTitleText');
const drawerTableTitle = document.getElementById('drawerTableTitle');
const drawerFilterInput = document.getElementById('drawerFilterInput');
const drawerTableHead = document.getElementById('drawerTableHead');
const drawerTableBody = document.getElementById('drawerTableBody');

// Currency & Formatting Helpers
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
  bindEventListeners();
  fetchMultiDayOverview();
});

// Bind Event Listeners
function bindEventListeners() {
  // Preset Chips
  document.querySelectorAll('.time-chips .chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.time-chips .chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.preset = chip.dataset.preset;

      if (state.preset === 'CUSTOM') {
        customStartGroup.classList.remove('hidden');
        customEndGroup.classList.remove('hidden');
      } else {
        customStartGroup.classList.add('hidden');
        customEndGroup.classList.add('hidden');
        fetchMultiDayOverview();
      }
    });
  });

  // Apply & Reset Filters
  applyFilterBtn.addEventListener('click', () => {
    if (state.preset === 'CUSTOM') {
      state.startDate = filterStartDate.value;
      state.endDate = filterEndDate.value;
      if (!state.startDate || !state.endDate) {
        alert('Please select both From Date and To Date for Custom Range.');
        return;
      }
    }
    fetchMultiDayOverview();
  });

  resetFilterBtn.addEventListener('click', () => {
    state.preset = '5D';
    state.startDate = '';
    state.endDate = '';
    state.searchQuery = '';
    searchInput.value = '';
    customStartGroup.classList.add('hidden');
    customEndGroup.classList.add('hidden');
    document.querySelectorAll('.time-chips .chip').forEach(c => c.classList.remove('active'));
    document.querySelector('.time-chips .chip[data-preset="5D"]').classList.add('active');
    fetchMultiDayOverview();
  });

  exportCsvBtn.addEventListener('click', exportMultiDayToCSV);

  // View Mode Switcher
  viewBrokersBtn.addEventListener('click', () => {
    state.viewMode = 'brokers';
    viewBrokersBtn.className = 'btn btn-primary';
    viewScripsBtn.className = 'btn btn-secondary';
    brokerSection.classList.remove('hidden');
    scripSection.classList.add('hidden');
  });

  viewScripsBtn.addEventListener('click', () => {
    state.viewMode = 'scrips';
    viewScripsBtn.className = 'btn btn-primary';
    viewBrokersBtn.className = 'btn btn-secondary';
    scripSection.classList.remove('hidden');
    brokerSection.classList.add('hidden');
  });

  // Live Search Filter
  searchInput.addEventListener('input', () => {
    state.searchQuery = searchInput.value.trim().toUpperCase();
    if (state.viewMode === 'brokers') {
      renderBrokerLeaderboard();
    } else {
      renderScripLeaderboard();
    }
  });

  // Broker Table Column Sorting
  document.querySelectorAll('#brokerMultiTable th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.brokerSortBy === field) {
        state.brokerSortOrder = state.brokerSortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        state.brokerSortBy = field;
        state.brokerSortOrder = 'desc';
      }
      updateSortUI('#brokerMultiTable', th, state.brokerSortOrder);
      renderBrokerLeaderboard();
    });
  });

  // Scrip Table Column Sorting
  document.querySelectorAll('#scripMultiTable th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (state.scripSortBy === field) {
        state.scripSortOrder = state.scripSortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        state.scripSortBy = field;
        state.scripSortOrder = 'desc';
      }
      updateSortUI('#scripMultiTable', th, state.scripSortOrder);
      renderScripLeaderboard();
    });
  });

  // Drawer Controls
  closeDrawerBtn.addEventListener('click', closeDrawer);
  drawerBackdrop.addEventListener('click', (e) => {
    if (e.target === drawerBackdrop) closeDrawer();
  });

  // Drawer Filter
  drawerFilterInput.addEventListener('input', () => {
    if (state.currentDrawerData) {
      const q = drawerFilterInput.value.trim().toUpperCase();
      if (state.selectedDrawerType === 'broker') {
        const filtered = state.currentDrawerData.scrips.filter(s => s.symbol.includes(q));
        renderDrawerBrokerScrips(filtered);
      } else {
        const filtered = state.currentDrawerData.brokers.filter(b => String(b.broker_id).includes(q));
        renderDrawerScripBrokers(filtered);
      }
    }
  });
}

function updateSortUI(tableSelector, activeTh, order) {
  document.querySelectorAll(`${tableSelector} th.sortable`).forEach(th => {
    th.classList.remove('sorted-asc', 'sorted-desc');
    const icon = th.querySelector('.sort-icon');
    if (icon) icon.textContent = '';
  });
  activeTh.classList.add(`sorted-${order}`);
  const icon = activeTh.querySelector('.sort-icon');
  if (icon) icon.textContent = order === 'asc' ? '▲' : '▼';
}

// Fetch Multi-Day Overview Data
async function fetchMultiDayOverview() {
  showLoading(true);
  try {
    const params = new URLSearchParams({
      preset: state.preset
    });
    if (state.preset === 'CUSTOM' && state.startDate && state.endDate) {
      params.append('start_date', state.startDate);
      params.append('end_date', state.endDate);
    }

    const res = await fetch(`/api/multiday/overview?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch multi-day overview`);

    const data = await res.json();
    state.period = data.period;
    state.brokers = data.brokers || [];
    state.scrips = data.scrips || [];

    renderMacroKPIs(data.market_summary);
    renderPeriodMetadata(data.period);
    renderBrokerLeaderboard();
    renderScripLeaderboard();
  } catch (err) {
    console.error('Failed to load multi-day overview:', err);
    brokerMultiBody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:30px; color:var(--accent-red);">Failed to load multi-day matrix: ${err.message}</td></tr>`;
  } finally {
    showLoading(false);
  }
}

function renderMacroKPIs(s) {
  kpiTurnover.textContent = formatNPR(s.total_market_turnover);
  kpiQuantity.textContent = formatQty(s.total_market_shares);
  kpiTrades.textContent = formatQty(s.total_market_trades);
  kpiActiveScrips.textContent = formatQty(s.active_scrips_count);
  kpiActiveBrokers.textContent = formatQty(s.active_brokers_count);
}

function renderPeriodMetadata(p) {
  windowMetaText.innerHTML = `📅 Active Period: <b>${p.trading_sessions_count} Trading Sessions</b> (${p.start_date} to ${p.end_date}) · Preset: <b>${p.preset}</b>`;
}

// Render Broker Leaderboard
function renderBrokerLeaderboard() {
  let list = [...state.brokers];

  if (state.searchQuery) {
    list = list.filter(b => String(b.broker_id).includes(state.searchQuery));
  }

  list.sort((a, b) => {
    let valA = a[state.brokerSortBy];
    let valB = b[state.brokerSortBy];
    if (valA === null || valA === undefined) valA = -Infinity;
    if (valB === null || valB === undefined) valB = -Infinity;
    return state.brokerSortOrder === 'asc' ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
  });

  brokerMultiInfo.textContent = `Showing ${list.length} active brokers over ${state.period ? state.period.trading_sessions_count : 5} sessions`;

  if (list.length === 0) {
    brokerMultiBody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:30px; color:var(--text-muted);">No brokers found matching criteria.</td></tr>`;
    return;
  }

  brokerMultiBody.innerHTML = list.map(b => {
    const isNetBuy = b.flow_status === 'NET BUYING';
    const badge = isNetBuy 
      ? `<span class="badge-accum">🟢 NET BUYING</span>` 
      : `<span class="badge-dist">🔴 NET SELLING</span>`;
    const netClass = isNetBuy ? 'text-green' : 'text-red';
    const netSign = b.net_flow_value >= 0 ? '+' : '';

    return `
      <tr style="cursor:pointer;" onclick="openBrokerMultiDrilldown(${b.broker_id})">
        <td style="font-weight:700; color:var(--accent-blue);">Broker #${b.broker_id}</td>
        <td class="text-right font-mono" style="font-weight:700; color:var(--text-bright);">${formatNPR(b.gross_activity)}</td>
        <td class="text-right font-mono">${formatNPR(b.buy_amount)}</td>
        <td class="text-right font-mono">${formatNPR(b.sell_amount)}</td>
        <td class="text-right font-mono ${netClass}" style="font-weight:700;">${netSign}${formatNPR(b.net_flow_value)}</td>
        <td class="text-right font-mono">${b.buy_vwap.toFixed(1)}</td>
        <td class="text-right font-mono">${b.sell_vwap.toFixed(1)}</td>
        <td class="text-right font-mono">${b.positive_days}/${state.period ? state.period.trading_sessions_count : '-'}</td>
        <td class="text-right font-mono" style="font-weight:700; color:${b.buy_persistence_pct >= 60 ? 'var(--accent-green)' : 'var(--text-bright)'};">
          ${b.buy_persistence_pct.toFixed(1)}%
        </td>
        <td class="text-right font-mono">${b.market_share_pct.toFixed(2)}%</td>
        <td class="text-right">
          <button class="btn-broker-action" onclick="event.stopPropagation(); openBrokerMultiDrilldown(${b.broker_id})">🔍 Deep Dive</button>
        </td>
      </tr>
    `;
  }).join('');
}

// Render Scrip Leaderboard
function renderScripLeaderboard() {
  let list = [...state.scrips];

  if (state.searchQuery) {
    list = list.filter(s => s.symbol.includes(state.searchQuery));
  }

  list.sort((a, b) => {
    let valA = a[state.scripSortBy];
    let valB = b[state.scripSortBy];
    if (valA === null || valA === undefined) valA = -Infinity;
    if (valB === null || valB === undefined) valB = -Infinity;
    return state.scripSortOrder === 'asc' ? (valA > valB ? 1 : -1) : (valA < valB ? 1 : -1);
  });

  scripMultiInfo.textContent = `Showing ${list.length} active stocks over ${state.period ? state.period.trading_sessions_count : 5} sessions`;

  if (list.length === 0) {
    scripMultiBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:30px; color:var(--text-muted);">No scrips found matching criteria.</td></tr>`;
    return;
  }

  scripMultiBody.innerHTML = list.map(s => {
    const buyerDisplay = s.top_net_buyer 
      ? `<span class="badge-accum">#${s.top_net_buyer.broker_id} (+${formatQty(s.top_net_buyer.net_qty)})</span>` 
      : '<span style="color:var(--text-muted);">-</span>';
    
    const sellerDisplay = s.top_net_seller 
      ? `<span class="badge-dist">#${s.top_net_seller.broker_id} (${formatQty(s.top_net_seller.net_qty)})</span>` 
      : '<span style="color:var(--text-muted);">-</span>';

    return `
      <tr style="cursor:pointer;" onclick="openScripMultiDrilldown('${s.symbol}')">
        <td><span class="symbol-tag" style="font-weight:700;">${s.symbol}</span></td>
        <td class="text-right font-mono" style="font-weight:700; color:var(--text-bright);">${formatNPR(s.turnover)}</td>
        <td class="text-right font-mono">${formatQty(s.volume)}</td>
        <td class="text-right font-mono">${formatQty(s.trades_count)}</td>
        <td class="text-right font-mono" style="font-weight:700; color:var(--accent-blue);">${s.multi_day_vwap.toFixed(1)}</td>
        <td>${buyerDisplay}</td>
        <td>${sellerDisplay}</td>
        <td class="text-right font-mono" style="font-weight:600; color:${s.top3_concentration_pct >= 50 ? 'var(--accent-green)' : 'var(--text-bright)'};">
          ${s.top3_concentration_pct.toFixed(1)}%
        </td>
        <td class="text-right font-mono">${s.market_share_pct.toFixed(2)}%</td>
        <td class="text-right">
          <button class="btn-broker-action" onclick="event.stopPropagation(); openScripMultiDrilldown('${s.symbol}')">🔍 Deep Dive</button>
        </td>
      </tr>
    `;
  }).join('');
}

// Drilldown Drawer Implementations
async function openBrokerMultiDrilldown(brokerId) {
  state.selectedDrawerType = 'broker';
  state.selectedDrawerId = brokerId;
  drawerTitle.textContent = `🏢 Broker #${brokerId} Multi-Day Intelligence`;
  drawerPeriodBadge.textContent = `${state.period ? state.period.trading_sessions_count : 5} Sessions`;
  chartTitleText.textContent = `📈 Day-by-Day Buy vs Sell Flow (Broker #${brokerId})`;
  drawerTableTitle.textContent = `📑 Complete Traded Scrips Portfolio (${state.period ? state.period.trading_sessions_count : 5} Sessions)`;

  dKpiTitle1.textContent = "GROSS ACTIVITY";
  dKpiTitle2.textContent = "NET FLOW VALUE";
  dKpiTitle3.textContent = "BUY / SELL VWAP";
  dKpiTitle4.textContent = "ACTIVE SCOPE";

  drawerBackdrop.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  if (drawerLoadingOverlay) drawerLoadingOverlay.classList.remove('hidden');

  try {
    const params = new URLSearchParams({ preset: state.preset });
    if (state.preset === 'CUSTOM' && state.startDate && state.endDate) {
      params.append('start_date', state.startDate);
      params.append('end_date', state.endDate);
    }

    const res = await fetch(`/api/multiday/broker/${brokerId}?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    state.currentDrawerData = data;

    // Render KPIs
    dKpiVal1.textContent = formatNPR(data.summary.gross_activity);
    dKpiVal2.textContent = formatNPR(data.summary.net_flow_value);
    dKpiVal2.className = `kpi-value ${data.summary.net_flow_value >= 0 ? 'text-green' : 'text-red'}`;
    dKpiVal3.textContent = `${data.summary.buy_vwap.toFixed(1)} / ${data.summary.sell_vwap.toFixed(1)}`;
    dKpiVal4.textContent = `${data.summary.active_scrips_count} Stocks`;

    renderMultiTimelineChart(data.timeline, 'broker');
    renderDrawerBrokerScrips(data.scrips);
  } catch (err) {
    console.error('Failed to load broker drilldown:', err);
  } finally {
    if (drawerLoadingOverlay) drawerLoadingOverlay.classList.add('hidden');
  }
}

async function openScripMultiDrilldown(symbol) {
  state.selectedDrawerType = 'scrip';
  state.selectedDrawerId = symbol;
  drawerTitle.textContent = `📊 ${symbol} Multi-Day Intelligence`;
  drawerPeriodBadge.textContent = `${state.period ? state.period.trading_sessions_count : 5} Sessions`;
  chartTitleText.textContent = `📈 Day-by-Day Turnover & Volume (${symbol})`;
  drawerTableTitle.textContent = `🏢 Multi-Day Broker Participation Matrix (${symbol})`;

  dKpiTitle1.textContent = "TOTAL TURNOVER";
  dKpiTitle2.textContent = "TOTAL VOLUME";
  dKpiTitle3.textContent = "MULTI-DAY VWAP";
  dKpiTitle4.textContent = "ACTIVE BROKERS";

  drawerBackdrop.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  if (drawerLoadingOverlay) drawerLoadingOverlay.classList.remove('hidden');

  try {
    const params = new URLSearchParams({ preset: state.preset });
    if (state.preset === 'CUSTOM' && state.startDate && state.endDate) {
      params.append('start_date', state.startDate);
      params.append('end_date', state.endDate);
    }

    const res = await fetch(`/api/multiday/scrip/${symbol}?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    state.currentDrawerData = data;

    // Render KPIs
    dKpiVal1.textContent = formatNPR(data.summary.turnover);
    dKpiVal2.textContent = `${formatQty(data.summary.volume)} Shares`;
    dKpiVal2.className = 'kpi-value text-green';
    dKpiVal3.textContent = `Rs ${data.summary.multi_day_vwap.toFixed(2)}`;
    dKpiVal4.textContent = `${data.summary.active_brokers_count} Brokers`;

    renderMultiTimelineChart(data.timeline, 'scrip');
    renderDrawerScripBrokers(data.brokers);
  } catch (err) {
    console.error('Failed to load scrip drilldown:', err);
  } finally {
    if (drawerLoadingOverlay) drawerLoadingOverlay.classList.add('hidden');
  }
}

function closeDrawer() {
  drawerBackdrop.classList.add('hidden');
  document.body.style.overflow = '';
  state.selectedDrawerType = null;
  state.selectedDrawerId = null;
}

// Chart.js Timeline Renderer
function renderMultiTimelineChart(timeline, type) {
  const ctx = document.getElementById('multiTimelineChart').getContext('2d');
  if (state.chartInstance) state.chartInstance.destroy();

  const labels = timeline.map(t => t.date);

  let datasets = [];
  if (type === 'broker') {
    datasets = [
      {
        type: 'bar',
        label: 'Buy Turnover (NPR)',
        data: timeline.map(t => t.buy_amount),
        backgroundColor: 'rgba(38, 166, 154, 0.6)',
        borderColor: '#26a69a',
        borderWidth: 1
      },
      {
        type: 'bar',
        label: 'Sell Turnover (NPR)',
        data: timeline.map(t => t.sell_amount),
        backgroundColor: 'rgba(239, 83, 80, 0.6)',
        borderColor: '#ef5350',
        borderWidth: 1
      },
      {
        type: 'line',
        label: 'Net Flow (NPR)',
        data: timeline.map(t => t.net_amount),
        borderColor: '#2962ff',
        borderWidth: 2,
        pointRadius: 4,
        tension: 0.2
      }
    ];
  } else {
    datasets = [
      {
        type: 'bar',
        label: 'Daily Turnover (NPR)',
        data: timeline.map(t => t.turnover),
        backgroundColor: 'rgba(41, 98, 255, 0.5)',
        borderColor: '#2962ff',
        borderWidth: 1,
        yAxisID: 'y'
      },
      {
        type: 'line',
        label: 'Daily VWAP (NPR)',
        data: timeline.map(t => t.vwap),
        borderColor: '#ff9800',
        borderWidth: 2,
        pointRadius: 4,
        yAxisID: 'yVwap'
      }
    ];
  }

  state.chartInstance = new Chart(ctx, {
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#d1d4dc', font: { family: 'Inter', size: 11, weight: '600' } } }
      },
      scales: {
        x: { grid: { color: '#262b37' }, ticks: { color: '#787b86', font: { family: 'JetBrains Mono', size: 10 } } },
        y: {
          grid: { color: '#262b37' },
          ticks: { color: '#787b86', font: { family: 'JetBrains Mono', size: 10 }, callback: v => formatCompact(v) }
        },
        ...(type === 'scrip' ? {
          yVwap: {
            type: 'linear',
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { color: '#ff9800', font: { family: 'JetBrains Mono', size: 10 } }
          }
        } : {})
      }
    }
  });
}

// Render Drawer Tables
function renderDrawerBrokerScrips(scrips) {
  drawerTableHead.innerHTML = `
    <tr>
      <th>Symbol</th>
      <th class="text-right">Buy Turnover</th>
      <th class="text-right">Sell Turnover</th>
      <th class="text-right">Net Flow (NPR)</th>
      <th class="text-right">Buy VWAP</th>
      <th class="text-right">Sell VWAP</th>
      <th class="text-right">Buy Days</th>
      <th class="text-right">Persistence %</th>
      <th class="text-right">Status</th>
    </tr>
  `;

  if (!scrips || scrips.length === 0) {
    drawerTableBody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px; color:var(--text-muted);">No scrips traded in this window.</td></tr>`;
    return;
  }

  drawerTableBody.innerHTML = scrips.map(s => {
    const isAccum = s.flow_status === '🟢 ACCUMULATING';
    const badge = isAccum ? `<span class="badge-accum">🟢 ACCUMULATING</span>` : `<span class="badge-dist">🔴 DISTRIBUTING</span>`;
    const netClass = isAccum ? 'text-green' : 'text-red';
    const netSign = s.net_amount >= 0 ? '+' : '';

    return `
      <tr>
        <td><span class="symbol-tag">${s.symbol}</span></td>
        <td class="text-right font-mono">${formatNPR(s.buy_amount)}</td>
        <td class="text-right font-mono">${formatNPR(s.sell_amount)}</td>
        <td class="text-right font-mono ${netClass}" style="font-weight:700;">${netSign}${formatNPR(s.net_amount)}</td>
        <td class="text-right font-mono">${s.buy_vwap.toFixed(1)}</td>
        <td class="text-right font-mono">${s.sell_vwap.toFixed(1)}</td>
        <td class="text-right font-mono">${s.buy_days}/${s.active_days}</td>
        <td class="text-right font-mono" style="font-weight:700; color:${s.persistence_pct >= 60 ? 'var(--accent-green)' : 'var(--text-bright)'};">
          ${s.persistence_pct.toFixed(1)}%
        </td>
        <td class="text-right">${badge}</td>
      </tr>
    `;
  }).join('');
}

function renderDrawerScripBrokers(brokers) {
  drawerTableHead.innerHTML = `
    <tr>
      <th>Broker</th>
      <th class="text-right">Buy Turnover</th>
      <th class="text-right">Sell Turnover</th>
      <th class="text-right">Net Flow (NPR)</th>
      <th class="text-right">Buy VWAP</th>
      <th class="text-right">Sell VWAP</th>
      <th class="text-right">Buy Days</th>
      <th class="text-right">Persistence %</th>
      <th class="text-right">Market Share %</th>
      <th class="text-right">Status</th>
    </tr>
  `;

  if (!brokers || brokers.length === 0) {
    drawerTableBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:20px; color:var(--text-muted);">No brokers active in this window.</td></tr>`;
    return;
  }

  drawerTableBody.innerHTML = brokers.map(b => {
    const isNetBuy = b.flow_status === '🟢 NET BUYING';
    const badge = isNetBuy ? `<span class="badge-accum">🟢 NET BUYING</span>` : `<span class="badge-dist">🔴 NET SELLING</span>`;
    const netClass = isNetBuy ? 'text-green' : 'text-red';
    const netSign = b.net_amount >= 0 ? '+' : '';

    return `
      <tr>
        <td style="font-weight:700; color:var(--accent-blue);">Broker #${b.broker_id}</td>
        <td class="text-right font-mono">${formatNPR(b.buy_amount)}</td>
        <td class="text-right font-mono">${formatNPR(b.sell_amount)}</td>
        <td class="text-right font-mono ${netClass}" style="font-weight:700;">${netSign}${formatNPR(b.net_amount)}</td>
        <td class="text-right font-mono">${b.buy_vwap.toFixed(1)}</td>
        <td class="text-right font-mono">${b.sell_vwap.toFixed(1)}</td>
        <td class="text-right font-mono">${b.buy_days}/${b.active_days}</td>
        <td class="text-right font-mono" style="font-weight:700; color:${b.persistence_pct >= 60 ? 'var(--accent-green)' : 'var(--text-bright)'};">
          ${b.persistence_pct.toFixed(1)}%
        </td>
        <td class="text-right font-mono">${b.market_share_pct.toFixed(2)}%</td>
        <td class="text-right">${badge}</td>
      </tr>
    `;
  }).join('');
}

function showLoading(isLoading) {
  loadingOverlay.classList.toggle('hidden', !isLoading);
}

// CSV Exporter
function exportMultiDayToCSV() {
  if (state.viewMode === 'brokers') {
    if (!state.brokers || state.brokers.length === 0) {
      alert("No broker data to export.");
      return;
    }
    const headers = ["Broker ID", "Gross Activity", "Buy Turnover", "Sell Turnover", "Net Flow Value", "Buy Qty", "Sell Qty", "Net Qty", "Buy VWAP", "Sell VWAP", "Positive Days", "Persistence %", "Market Share %", "Flow Status"];
    const rows = state.brokers.map(b => [b.broker_id, b.gross_activity, b.buy_amount, b.sell_amount, b.net_flow_value, b.buy_quantity, b.sell_quantity, b.net_flow_quantity, b.buy_vwap, b.sell_vwap, b.positive_days, b.buy_persistence_pct, b.market_share_pct, b.flow_status]);
    downloadCSV(headers, rows, `nepse_multiday_brokers_${state.preset}.csv`);
  } else {
    if (!state.scrips || state.scrips.length === 0) {
      alert("No scrip data to export.");
      return;
    }
    const headers = ["Symbol", "Turnover", "Volume", "Trades Count", "Multi-Day VWAP", "Market Share %", "Top 3 Buyer Share %", "Top Net Buyer", "Top Net Seller"];
    const rows = state.scrips.map(s => [s.symbol, s.turnover, s.volume, s.trades_count, s.multi_day_vwap, s.market_share_pct, s.top3_concentration_pct, s.top_net_buyer ? s.top_net_buyer.broker_id : '', s.top_net_seller ? s.top_net_seller.broker_id : '']);
    downloadCSV(headers, rows, `nepse_multiday_scrips_${state.preset}.csv`);
  }
}

function downloadCSV(headers, rows, filename) {
  let csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
