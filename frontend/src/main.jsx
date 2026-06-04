import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  Bell,
  Bitcoin,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Clock,
  Database,
  ExternalLink,
  Radio,
  RefreshCw,
  Star,
  Trophy,
  Wifi,
  WifiOff,
  Power,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './styles.css';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';
const WS_URL = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/market`;
const PAGE_SIZE = 16;
const DEFAULT_FILTERS = {
  sports: true,
  esports: true,
  crypto: true,
  general: true,
  minProbability: 80,
  maxProbability: 100,
  maxHours: 48,
  minLiquidity: 1000,
};
const LANES = [
  { id: 'scalp', label: '短线高频', hint: 'Crypto 15m 起，隐藏 5m' },
  { id: 'sports', label: '体育临场', hint: '赛前 15m 至开赛后 3.5h' },
  { id: 'esports', label: '电竞临场', hint: '赛前 15m 至开赛后 3.5h' },
  { id: 'regular', label: '常规事件', hint: '2 天内，概率 80%+' },
];

function App() {
  const [markets, setMarkets] = useState([]);
  const [stagedMarkets, setStagedMarkets] = useState([]);
  const [hasPendingUpdate, setHasPendingUpdate] = useState(false);
  const [events, setEvents] = useState([]);
  const [priceHistory, setPriceHistory] = useState({});
  const [selectedId, setSelectedId] = useState(null);
  const [connection, setConnection] = useState({ frontend: 'connecting', gamma: 'unknown', clob: 'unknown' });
  const [lastRefresh, setLastRefresh] = useState(null);
  const [lastScanCompletedAt, setLastScanCompletedAt] = useState(null);
  const [manualRefreshState, setManualRefreshState] = useState('idle');
  const [scannerEnabled, setScannerEnabled] = useState(true);
  const [scannerToggleState, setScannerToggleState] = useState('idle');
  const [page, setPage] = useState(1);
  const [activeLane, setActiveLane] = useState('sports');
  const activeLaneRef = React.useRef(activeLane);
  const [detailTab, setDetailTab] = useState('summary');
  const [draftFilters, setDraftFilters] = useState(DEFAULT_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(DEFAULT_FILTERS);

  async function refreshMarkets() {
    setManualRefreshState('loading');
    if (hasPendingUpdate && stagedMarkets.length > 0) {
      setMarkets(stagedMarkets);
      setSelectedId((current) => current || stagedMarkets[0]?.market_id || null);
      setLastRefresh(new Date());
      setHasPendingUpdate(false);
      setManualRefreshState('done');
      window.setTimeout(() => setManualRefreshState('idle'), 1800);
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/markets`);
      const data = await response.json();
      setMarkets(data);
      setStagedMarkets(data);
      setHasPendingUpdate(false);
      setSelectedId((current) => current || data[0]?.market_id || null);
      setLastRefresh(new Date());
      setManualRefreshState('done');
      window.setTimeout(() => setManualRefreshState('idle'), 1800);
    } catch {
      setConnection((current) => ({ ...current, gamma: 'error' }));
      setManualRefreshState('error');
    }
  }

  async function toggleScanner() {
    const nextEnabled = !scannerEnabled;
    setScannerToggleState('loading');
    try {
      const response = await fetch(`${API_BASE}/api/scanner`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      const status = await response.json();
      setScannerEnabled(Boolean(status.scanning_enabled));
      if (status.connection) {
        setConnection((current) => mergeConnectionStatus(current, status.connection, status.scanning_enabled !== false, true));
      }
      setScannerToggleState('idle');
    } catch {
      setScannerToggleState('error');
      window.setTimeout(() => setScannerToggleState('idle'), 1800);
    }
  }

  useEffect(() => {
    activeLaneRef.current = activeLane;
  }, [activeLane]);

  useEffect(() => {
    let alive = true;
    let ws;
    let reconnectTimer;
    let statusTimer;

    async function loadInitial() {
      try {
        const [marketsResponse, statusResponse] = await Promise.all([
          fetch(`${API_BASE}/api/markets`),
          fetch(`${API_BASE}/api/status`),
        ]);
        const data = await marketsResponse.json();
        const status = await statusResponse.json();
        if (!alive) return;
        setMarkets(data);
        setStagedMarkets(data);
        setSelectedId((current) => current || data[0]?.market_id || null);
        const completed = status.last_scan_completed_at ? new Date(status.last_scan_completed_at) : new Date();
        setLastRefresh(completed);
        setLastScanCompletedAt(completed);
        setScannerEnabled(status.scanning_enabled !== false);
        if (status.connection) {
          setConnection((current) => mergeConnectionStatus(current, status.connection, status.scanning_enabled !== false, true));
        }
      } catch {
        setConnection((current) => ({ ...current, gamma: 'error' }));
      }
    }

    async function refreshStatus() {
      try {
        const response = await fetch(`${API_BASE}/api/status`);
        const status = await response.json();
        if (!alive) return;
        setScannerEnabled(status.scanning_enabled !== false);
        if (status.last_scan_completed_at) {
          setLastScanCompletedAt(new Date(status.last_scan_completed_at));
        }
        if (status.connection) {
          setConnection((current) => mergeConnectionStatus(current, status.connection, status.scanning_enabled !== false, true));
        }
      } catch {
        setConnection((current) => ({ ...current, gamma: 'error' }));
      }
    }

    function connect() {
      ws = new WebSocket(WS_URL);
      window.polyMonitorSocket = ws;
      ws.onopen = () => {
        setConnection((current) => ({ ...current, frontend: 'connected' }));
        ws.send(JSON.stringify({
          type: 'focus_markets',
          market_ids: focusedMarketIds(visibleMarkets, selected, opportunities),
        }));
      };
      ws.onclose = () => {
        if (!alive) return;
        setConnection((current) => ({ ...current, frontend: 'reconnecting' }));
        reconnectTimer = window.setTimeout(connect, 1600);
      };
      ws.onerror = () => setConnection((current) => ({ ...current, frontend: 'error' }));
      ws.onmessage = (message) => {
        const payload = JSON.parse(message.data);
        if (payload.type === 'markets_snapshot') {
          if (shouldAutoApplyLane(activeLaneRef.current)) {
            setMarkets(payload.data);
            setStagedMarkets(payload.data);
            setHasPendingUpdate(false);
            setLastRefresh(new Date());
          } else {
            setStagedMarkets(payload.data);
            setHasPendingUpdate(true);
          }
          setLastScanCompletedAt(new Date());
        }
        if (payload.type === 'events_snapshot') setEvents(payload.data);
        if (payload.type === 'connection_status') {
          setConnection((current) => mergeConnectionStatus(current, payload.data, scannerEnabled, false));
        }
        if (payload.type === 'market_update') {
          if (shouldAutoApplyLane(activeLaneRef.current)) {
            setMarkets((current) => upsertMarket(current, payload.data));
            setStagedMarkets((current) => upsertMarket(current, payload.data));
            setHasPendingUpdate(false);
            setLastRefresh(new Date());
          } else {
            setStagedMarkets((current) => upsertMarket(current, payload.data));
            setHasPendingUpdate(true);
          }
        }
        if (payload.type === 'price_update') {
          setPriceHistory((current) => appendPricePoint(current, payload.data.market_id, payload.data.price));
        }
        if (payload.type === 'push_event') {
          setEvents((current) => [payload.data, ...current].slice(0, 14));
        }
      };
    }

    loadInitial();
    statusTimer = window.setInterval(refreshStatus, 10000);
    connect();
    return () => {
      alive = false;
      window.clearTimeout(reconnectTimer);
      window.clearInterval(statusTimer);
      ws?.close();
      if (window.polyMonitorSocket === ws) window.polyMonitorSocket = null;
    };
  }, []);

  const selected = useMemo(
    () => laneMarkets(filteredMarkets(markets, appliedFilters), activeLane).find((market) => market.market_id === selectedId) || laneMarkets(filteredMarkets(markets, appliedFilters), activeLane)[0],
    [markets, selectedId, appliedFilters, activeLane],
  );

  const filtered = useMemo(() => filteredMarkets(markets, appliedFilters), [markets, appliedFilters]);
  const laneCounts = useMemo(() => laneSummary(filtered), [filtered]);
  const opportunities = useMemo(() => laneMarkets(filtered, activeLane), [filtered, activeLane]);

  const stats = useMemo(() => {
    const high = opportunities.filter((market) => winRate(market) >= 90).length;
    const ending = opportunities.filter((market) => remainingHours(market) <= 1).length;
    const resolved = opportunities.filter((market) => market.status === 'resolved').length;
    const liquid = opportunities.filter((market) => (market.liquidity || 0) >= 10_000).length;
    return { total: opportunities.length, high, ending, resolved, liquid, raw: markets.length };
  }, [markets, opportunities, appliedFilters]);

  const pageCount = Math.max(1, Math.ceil(opportunities.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const visibleMarkets = useMemo(
    () => opportunities.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [opportunities, safePage],
  );
  const chartData = priceHistory[selected?.market_id] || [];
  const dataMode = markets.some((market) => market.market_id?.startsWith('mock-')) ? '仿真数据' : '真实 Gamma 数据';

  useEffect(() => {
    setPage(1);
    setSelectedId((current) => (opportunities.some((market) => market.market_id === current) ? current : opportunities[0]?.market_id || null));
  }, [activeLane, appliedFilters, markets.length]);

  useEffect(() => {
    if (window.polyMonitorSocket?.readyState !== WebSocket.OPEN) return;
    window.polyMonitorSocket.send(JSON.stringify({
      type: 'focus_markets',
      market_ids: focusedMarketIds(visibleMarkets, selected, opportunities),
    }));
  }, [visibleMarkets, selected, opportunities]);

  return (
    <main className="app-shell">
      <nav className="topbar">
        <div className="brand">
          <span className="brand-mark"><Radio size={18} /></span>
          <strong>EdgeRadar</strong>
          <em className={dataMode === '真实 Gamma 数据' ? 'source-live' : 'source-mock'}>{dataMode}</em>
        </div>
        <div className="nav-pills single-nav"><span><Activity size={16} />机会雷达</span></div>
        <div className="top-status">
          <Bell size={16} />
          <Clock size={16} />
          <span>{new Date().toLocaleTimeString('en-GB', { timeZoneName: 'short' })}</span>
        </div>
      </nav>

      <section className="workspace">
        <aside className="filters">
          <PanelTitle
            title="筛选条件"
            action="重置"
            onAction={() => {
              setDraftFilters(DEFAULT_FILTERS);
              setAppliedFilters(DEFAULT_FILTERS);
              setPage(1);
            }}
          />
          <FilterCheckbox
            checked={draftFilters.sports}
            label="体育比赛"
            onChange={(checked) => setDraftFilters((current) => ({ ...current, sports: checked }))}
          />
          <FilterCheckbox
            checked={draftFilters.esports}
            label="电子竞技"
            onChange={(checked) => setDraftFilters((current) => ({ ...current, esports: checked }))}
          />
          <FilterCheckbox
            checked={draftFilters.crypto}
            label="加密货币"
            onChange={(checked) => setDraftFilters((current) => ({ ...current, crypto: checked }))}
          />
          <FilterCheckbox
            checked={draftFilters.general}
            label="政治 / 天气 / 金融 / 其他"
            onChange={(checked) => setDraftFilters((current) => ({ ...current, general: checked }))}
          />
          <div className="filter-group">
            <span className="filter-label">资金占用时间</span>
            <SegmentedControl
              value={draftFilters.maxHours}
              options={[
                [1, '1h'],
                [3, '3h'],
                [24, '24h'],
                [48, '2d'],
                [Infinity, '全部'],
              ]}
              onChange={(value) => setDraftFilters((current) => ({ ...current, maxHours: value }))}
            />
          </div>
          <div className="filter-group">
            <span className="filter-label">候选概率</span>
            <div className="range-row">
              <input
                type="range"
                min="80"
                max="99"
                value={draftFilters.minProbability}
                onChange={(event) => setDraftFilters((current) => ({ ...current, minProbability: Number(event.target.value) }))}
              />
              <b>{draftFilters.minProbability}%</b>
            </div>
          </div>
          <FilterCheckbox
            checked={draftFilters.maxProbability < 100}
            label="隐藏接近 100% 的低收益市场"
            onChange={(checked) => setDraftFilters((current) => ({ ...current, maxProbability: checked ? 99.5 : 100 }))}
          />
          <div className="filter-group">
            <span className="filter-label">最低流动性</span>
            <SegmentedControl
              value={draftFilters.minLiquidity}
              options={[
                [0, '不限'],
                [250, '$250'],
                [1000, '$1k'],
                [10000, '$10k'],
              ]}
              onChange={(value) => setDraftFilters((current) => ({ ...current, minLiquidity: value }))}
            />
          </div>
          <button
            className="primary-button"
            onClick={() => {
              setAppliedFilters(draftFilters);
              setPage(1);
            }}
          >
            应用筛选
          </button>
          <p className="filter-hint">默认显示 2 天内、候选概率 ≥80%、有流动性的市场；强信号和推送仍按 CLOB ≥90% 严格判断。</p>
        </aside>

        <section className="market-panel">
          <div className="section-head">
            <div className="section-main">
              <div className="section-title-block">
                <h1>{laneTitle(activeLane)}</h1>
                <p>显示 {stats.total} / {stats.raw} 个机会 · 当前第 {safePage}/{pageCount} 页 · 当前结果 {formatTime(lastRefresh)}{hasPendingUpdate ? ' · 后台有新结果待查看' : autoApplyHint(activeLane)}</p>
              </div>
              <div className="market-kpis">
                <span><b>{stats.ending}</b><em>1h 内</em></span>
                <span><b>{stats.liquid}</b><em>$10k+</em></span>
                <span><b>{scannerEnabled ? 'running' : 'paused'}</b><em>扫描</em></span>
                <span><b>{connection.clob}</b><em>CLOB</em></span>
              </div>
            </div>
            <div className="refresh-actions">
              <div className="auto-refresh">
                <RefreshCw size={15} />
                <span>{scannerEnabled ? `${autoApplyLabel(activeLane)} · Gamma 3min / CLOB 30s` : '后台扫描已暂停，不消耗 Gamma/CLOB 扫描流量'}</span>
                <i className={scannerEnabled ? '' : 'off'} />
              </div>
              <button className={scannerEnabled ? 'scanner-toggle active' : 'scanner-toggle'} onClick={toggleScanner} disabled={scannerToggleState === 'loading'}>
                <Power size={14} />
                {scannerEnabled ? '暂停扫描' : '开始扫描'}
              </button>
              <button className="manual-refresh" onClick={refreshMarkets} disabled={manualRefreshState === 'loading'}>
                <RefreshCw size={14} />
                {manualRefreshLabel(manualRefreshState, hasPendingUpdate)}
              </button>
            </div>
          </div>

          <LaneTabs active={activeLane} counts={laneCounts} onChange={setActiveLane} />

          <MarketTable markets={visibleMarkets} selectedId={selected?.market_id} onSelect={setSelectedId} />
          <Pagination
            page={safePage}
            pageCount={pageCount}
            total={opportunities.length}
            onPrev={() => setPage((current) => Math.max(1, current - 1))}
            onNext={() => setPage((current) => Math.min(pageCount, current + 1))}
          />
        </section>
      </section>

      <section className="detail-grid">
        {selected ? (
          <div className="detail-main">
            <SelectedSummary market={selected} />
            <DetailTabs active={detailTab} onChange={setDetailTab} />
            <DetailContent market={selected} active={detailTab} chartData={chartData} />
          </div>
        ) : (
          <div className="detail-main detail-empty">
            <h2>等待高胜率市场出现</h2>
            <p>真实模式不会用仿真订单簿填充页面。等 Gamma API 扫描到高胜率市场后，这里会显示价格走势、买卖价和推送历史。</p>
          </div>
        )}

        <aside className="orderbook">
          <PanelTitle title="最佳买卖价" action={`更新时间 ${formatTime(lastRefresh)}`} />
          {selected ? (
            <>
              <div className="bidask">
                <div className="bid">
                  <span>买入 (Yes)</span>
                  <strong>{formatPrice(selected?.best_bid || selected?.last_price)}</strong>
                </div>
                <div className="ask">
                  <span>卖出 (Yes)</span>
                  <strong>{formatPrice(selected?.best_ask)}</strong>
                </div>
              </div>
              <p className="orderbook-note">当前展示 CLOB 实时最佳买卖价。完整深度需保存 book 事件后再展示，避免用假深度误导判断。</p>
            </>
          ) : (
            <div className="orderbook-empty">
              <Database size={22} />
              <span>暂无真实订单簿数据</span>
            </div>
          )}
        </aside>
      </section>

      <section className="bottom-grid">
        <StatusCard title="监控状态" rows={[
          ['监控中市场数', stats.total],
          ['高胜率市场 (≥90%)', stats.high],
          ['接近结束 (≤1小时)', stats.ending],
          ['已结束市场', stats.resolved],
        ]} />
        <StatusCard title="推送状态" rows={[
          ['Telegram', '已连接'],
          ['Discord', '已连接'],
          ['Webhook', '已连接'],
        ]} success />
        <StatusCard title="连接状态" rows={[
          ['Gamma API', displayConnectionStatus(connection.gamma, scannerEnabled)],
          ['WebSocket', connection.frontend],
          ['CLOB Stream', displayConnectionStatus(connection.clob, scannerEnabled)],
        ]} success />
        <SignalPanel markets={opportunities} />
      </section>
    </main>
  );
}

function MarketTable({ markets, selectedId, onSelect }) {
  return (
    <div className="market-table">
      <div className="table-row table-head">
        <span>市场</span><span>方向/选项</span><span>类型</span><span>Gamma%</span><span>CLOB%</span><span>偏差</span><span>30s</span><span>3m</span><span>spread</span><span>last trade</span><span>流动性</span><span>开赛/结束</span><span>评分</span>
      </div>
      {markets.length === 0 && (
        <div className="empty-market-state">
          <h3>当前筛选下没有资金效率机会</h3>
          <p>可以把资金占用时间放宽到 30 天，或降低最低流动性。系统会继续按 Gamma 3 分钟、CLOB 30 秒更新真实数据。</p>
        </div>
      )}
      {markets.map((market) => (
        <div
          key={market.market_id}
          className={`table-row market-row ${selectedId === market.market_id ? 'selected' : ''} ${market.status}`}
          onClick={() => onSelect(market.market_id)}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') onSelect(market.market_id);
          }}
        >
          <span className="market-name">
            <MarketIcon kind={market.kind} image={market.image} />
            <span className="market-copy">
              {market.market_url ? (
                <a
                  className="question-link"
                  href={market.market_url}
                  target="_blank"
                  rel="noreferrer"
                  title={marketLinkTitle(market)}
                  onClick={(event) => event.stopPropagation()}
                >
                  {market.question}
                  <ExternalLink size={13} />
                </a>
              ) : (
                <span className="question-link muted-link" title={marketLinkTitle(market)}>{market.question}</span>
              )}
              <span className="outcome-line">{outcomeLine(market)}</span>
            </span>
          </span>
          <strong className="outcome-cell">{outcomeValue(market)}</strong>
          <span><Tag>{marketLabel(market)}</Tag></span>
          <strong className={gammaRate(market) >= 90 ? 'green' : ''}>{formatPercent(gammaRate(market))}</strong>
          <strong className={clobRate(market) >= 90 ? 'green' : 'muted-cell'}>{formatPercent(clobRate(market))}</strong>
          <span className={Math.abs(diffRate(market)) >= 5 ? 'orange' : 'muted-cell'}>{formatSignedPercent(diffRate(market))}</span>
          <span className={Math.abs((market.price_change_30s || 0) * 100) >= 1.5 ? 'orange' : ''}>{formatSignedPercent((market.price_change_30s || 0) * 100)}</span>
          <span>{formatSignedPercent((market.price_change_3m || 0) * 100)}</span>
          <span>{spreadLabel(market)}</span>
          <span>{lastTradeLabel(market)}</span>
          <span>{formatMoney(market.liquidity)}</span>
          <span className={market.status === 'ending' ? 'orange' : ''} title={targetTimeLabel(market)}>{remainingLabel(market)}</span>
          <span className={market.tradable === false ? 'score-pill blocked' : 'score-pill'}>
            {market.tradable === false ? '不可交易' : Math.round(signalScore(market))}
          </span>
        </div>
      ))}
    </div>
  );
}

function mergeConnectionStatus(current, update, scannerEnabled, authoritative = false) {
  const next = { ...current, ...update };
  if (scannerEnabled && !authoritative) {
    if (update?.gamma === 'paused') next.gamma = current.gamma === 'paused' ? 'unknown' : current.gamma;
    if (update?.clob === 'paused') next.clob = current.clob === 'paused' ? 'unknown' : current.clob;
  }
  if (scannerEnabled && authoritative) {
    if (next.gamma === 'paused') next.gamma = 'unknown';
    if (next.clob === 'paused') next.clob = 'unknown';
  }
  return next;
}

function displayConnectionStatus(value, scannerEnabled) {
  if (scannerEnabled && value === 'paused') return 'unknown';
  return value || 'unknown';
}

function LaneTabs({ active, counts, onChange }) {
  return (
    <div className="lane-tabs">
      {LANES.map((lane) => (
        <button
          key={lane.id}
          className={active === lane.id ? 'active' : ''}
          onClick={() => onChange(lane.id)}
          type="button"
        >
          <strong>{lane.label}</strong>
          <span>{lane.hint}</span>
          <b>{counts[lane.id] || 0}</b>
        </button>
      ))}
    </div>
  );
}

function SelectedSummary({ market }) {
  if (!market) return null;
  return (
    <div className="selected-summary">
      <div className="summary-title">
        <MarketIcon kind={market.kind} image={market.image} />
        <div>
          <h2>{market.question}</h2>
          <p>{marketLabel(market)} · {outcomeLine(market)} · ID: {market.market_id}</p>
        </div>
      </div>
      <Metric label="领先概率" value={`${winRate(market).toFixed(1)}%`} accent="green" />
      <Metric label="领先方向" value={market.leading_outcome || '-'} />
      <Metric label="剩余时间" value={remainingLabel(market)} accent="orange" />
      <StatusBadge status={market.status} />
      {market.market_url && (
        <a className="detail-link" href={market.market_url} target="_blank" rel="noreferrer">
          <ExternalLink size={15} />
          打开市场
        </a>
      )}
    </div>
  );
}

function DetailTabs({ active, onChange }) {
  const tabs = [
    ['summary', '决策摘要'],
    ['price', '实时价格'],
    ['info', '市场信息'],
  ];
  return (
    <div className="tabs">
      {tabs.map(([value, label]) => (
        <button key={value} className={active === value ? 'active' : ''} onClick={() => onChange(value)}>
          {label}
        </button>
      ))}
    </div>
  );
}

function DetailContent({ market, active, chartData }) {
  if (active === 'price') {
    if (chartData.length < 2) {
      return (
        <div className="decision-panel empty-detail">
          <h3>等待真实价格历史</h3>
          <p>CLOB 已连接后，价格变动会写入这里。没有真实历史时不展示模拟曲线。</p>
        </div>
      );
    }
    return (
      <div className="chart-box">
        <ResponsiveContainer width="100%" height={230}>
          <AreaChart data={chartData} margin={{ left: 0, right: 12, top: 16, bottom: 0 }}>
            <defs>
              <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#78e36d" stopOpacity={0.38} />
                <stop offset="95%" stopColor="#78e36d" stopOpacity={0.03} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#e5e9f0" strokeDasharray="3 3" />
            <XAxis dataKey="time" tick={{ fill: '#7b8492', fontSize: 12 }} />
            <YAxis domain={[0.8, 1]} tick={{ fill: '#7b8492', fontSize: 12 }} />
            <Tooltip contentStyle={{ background: '#fff', border: '1px solid #e1e6ee', borderRadius: 12 }} />
            <Area type="monotone" dataKey="price" stroke="#3157ff" fill="url(#priceFill)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (active === 'info') {
    return (
      <div className="decision-panel info-grid">
        <InfoItem label="市场类型" value={marketLabel(market)} />
        <InfoItem label="市场 ID" value={market.market_id} />
        <InfoItem label="Token 数" value={String(market.clob_token_ids?.length || 0)} />
        <InfoItem label="标签" value={(market.tags || []).slice(0, 4).join(' / ') || '-'} />
      </div>
    );
  }

  return (
    <div className="decision-panel decision-grid">
      <InfoItem label="机会评分" value={String(Math.round(signalScore(market)))} tone="strong" />
      <InfoItem label="领先概率" value={`${winRate(market).toFixed(1)}%`} tone="green" />
      <InfoItem label="流动性" value={formatMoney(market.liquidity)} />
      <InfoItem label="资金占用" value={remainingLabel(market)} tone="orange" />
      <InfoItem label="本地时间" value={targetTimeLabel(market)} />
      <InfoItem label="买卖价差" value={spreadLabel(market)} />
      <InfoItem label="盘口状态" value={tradableLabel(market)} tone={market.tradable === false ? 'orange' : 'green'} />
      <InfoItem label="当前判断" value={decisionLabel(market)} tone="strong" />
      <InfoItem label="时间口径" value={timeBasisLabel(market)} />
      <InfoItem label="原始 endDate" value={rawEndDateLabel(market)} />
    </div>
  );
}

function InfoItem({ label, value, tone }) {
  return (
    <div className={`info-item ${tone || ''}`}>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function Pagination({ page, pageCount, total, onPrev, onNext }) {
  const start = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const end = Math.min(total, page * PAGE_SIZE);
  return (
    <div className="pagination">
      <span>显示 {start}-{end} / {total}</span>
      <div className="page-buttons">
        <button onClick={onPrev} disabled={page <= 1} title="上一页"><ChevronLeft size={16} /></button>
        <strong>{page}</strong>
        <button onClick={onNext} disabled={page >= pageCount} title="下一页"><ChevronRight size={16} /></button>
      </div>
    </div>
  );
}

function SignalPanel({ markets }) {
  const signals = markets
    .map((market) => ({ market, score: signalScore(market) }))
    .filter((item) => item.score >= 70)
    .sort((a, b) => b.score - a.score)
    .slice(0, 8);
  return (
    <div className="push-panel">
      <PanelTitle title="强信号池" action="模型预留" />
      <div className="event-list">
        {signals.length === 0 && <p className="empty">当前没有达到强信号阈值的机会</p>}
        {signals.map(({ market, score }) => (
          <div className="event-item signal-item" key={market.market_id}>
            <MarketIcon kind={market.kind} image={market.image} />
            <div>
              {market.market_url ? (
                <a href={market.market_url} target="_blank" rel="noreferrer">{shortQuestion(market.question)}</a>
              ) : (
                <b>{shortQuestion(market.question)}</b>
              )}
              <span>{winRate(market).toFixed(1)}% · {formatMoney(market.liquidity)} · {remainingLabel(market)}</span>
            </div>
            <time>{Math.round(score)}</time>
          </div>
        ))}
      </div>
    </div>
  );
}

function focusedMarketIds(visibleMarkets, selected, opportunities) {
  const strongSignals = opportunities
    .map((market) => ({ market, score: signalScore(market) }))
    .filter((item) => item.score >= 70)
    .sort((a, b) => b.score - a.score)
    .slice(0, 12)
    .map((item) => item.market.market_id);
  return [...new Set([
    selected?.market_id,
    ...visibleMarkets.map((market) => market.market_id),
    ...strongSignals,
  ].filter(Boolean))];
}

function shouldAutoApplyLane(lane) {
  return ['scalp', 'sports', 'esports'].includes(lane);
}

function autoApplyHint(lane) {
  return shouldAutoApplyLane(lane) ? ' · 自动更新中' : '';
}

function autoApplyLabel(lane) {
  return shouldAutoApplyLane(lane) ? '当前频道自动更新' : '常规事件手动查看';
}

function signalScore(market) {
  if (market.score !== undefined && market.score !== null) return Number(market.score) || 0;
  const probability = clobRate(market);
  const hours = remainingHours(market);
  const liquidity = market.liquidity || 0;
  if (market.tradable === false) return 0;
  if (market.category === 'Weather') return 0;
  if (probability < 90 || liquidity < 1000 || hours > 24) return 0;
  if (probability >= 99.0) {
    if (hours > 3 || liquidity < 10_000) return 0;
    const timeScore = Math.max(0, 22 - hours * 4);
    const liquidityScore = Math.min(18, Math.log10(Math.max(1, liquidity / 10_000)) * 10);
    return Math.max(8, Math.min(45, timeScore + liquidityScore));
  }
  const timeScore = Math.max(0, 35 - hours * 1.8);
  const probScore = Math.min(35, (probability - 90) * 4.2);
  const liquidityScore = Math.min(25, Math.log10(Math.max(1, liquidity / 1000)) * 12);
  const typeBonus = market.kind === 'sports' || market.kind === 'crypto' ? 5 : market.kind === 'esports' ? 2 : 0;
  return timeScore + probScore + liquidityScore + typeBonus;
}

function StatusCard({ title, rows, success }) {
  return (
    <div className="status-card">
      <h3>{title}</h3>
      {rows.map(([label, value]) => (
        <div className="status-row" key={label}>
          <span>{label}</span>
          <b className={success ? 'green' : ''}>{String(value)}</b>
        </div>
      ))}
      {success && <button className="secondary-button">测试推送</button>}
    </div>
  );
}

function MarketIcon({ kind, image }) {
  if (image) return <span className="asset-icon image-icon"><img src={image} alt="" /></span>;
  if (kind === 'crypto') return <span className="asset-icon crypto"><Bitcoin size={18} /></span>;
  if (kind === 'sports') return <span className="asset-icon sports"><Trophy size={18} /></span>;
  if (kind === 'esports') return <span className="asset-icon esports"><Activity size={18} /></span>;
  return <span className="asset-icon general"><Activity size={18} /></span>;
}

function PanelTitle({ title, action, onAction }) {
  return <div className="panel-title"><h3>{title}</h3><button onClick={onAction}>{action}</button></div>;
}

function FilterCheckbox({ checked, label, onChange }) {
  return (
    <label className="check-row">
      <input type="checkbox" checked={checked} onChange={(event) => onChange?.(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

function SegmentedControl({ value, options, onChange }) {
  return (
    <div className="segmented-control">
      {options.map(([optionValue, label]) => (
        <button
          key={label}
          className={Object.is(value, optionValue) ? 'active' : ''}
          type="button"
          onClick={() => onChange(optionValue)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Tag({ children }) {
  return <span className="tag">{children}</span>;
}

function StatusBadge({ status }) {
  const labels = { active: '未结束', ending: '接近结束', resolved: '已结束' };
  return <span className={`status-badge ${status}`}>{labels[status] || status}</span>;
}

function Metric({ label, value, accent }) {
  return <div className="metric"><span>{label}</span><strong className={accent}>{value}</strong></div>;
}

function upsertMarket(markets, next) {
  const exists = markets.some((market) => market.market_id === next.market_id);
  if (!exists) return [next, ...markets];
  return markets.map((market) => (market.market_id === next.market_id ? next : market));
}

function appendPricePoint(history, marketId, price) {
  const point = { time: new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }), price: Number(price.toFixed(3)) };
  return { ...history, [marketId]: [...(history[marketId] || []), point].slice(-40) };
}

function winRate(market) {
  return clobRate(market);
}

function displayRate(market) {
  return clobRate(market) || gammaRate(market);
}

function filterRate(market) {
  return Math.max(gammaRate(market), clobRate(market));
}

function upperBoundRate(market) {
  return clobRate(market) || gammaRate(market);
}

function gammaRate(market) {
  const value = market?.gamma_probability ?? maxPrice(market);
  return Number.isFinite(value) ? value * 100 : 0;
}

function clobRate(market) {
  const value = Math.max(market?.clob_probability || 0, market?.last_trade_price || 0);
  if (value === undefined || value === null) return 0;
  return value * 100;
}

function diffRate(market) {
  if (market?.gamma_clob_diff === undefined || market?.gamma_clob_diff === null) return 0;
  return market.gamma_clob_diff * 100;
}

function filteredMarkets(markets, filters) {
  return markets
    .filter((market) => {
      if (market.kind === 'sports' && !filters.sports) return false;
      if (market.kind === 'esports' && !filters.esports) return false;
      if (market.kind === 'crypto' && !filters.crypto) return false;
      if (market.kind === 'general' && !filters.general) return false;
      if (market.kind === 'crypto' && cryptoWindowMinutes(market) <= 5) return false;
      if (upperBoundRate(market) >= 99.9) return false;
      if (filterRate(market) < filters.minProbability) return false;
      if (upperBoundRate(market) >= filters.maxProbability) return false;
      if ((market.liquidity || 0) < filters.minLiquidity) return false;
      if (Number.isFinite(filters.maxHours) && remainingHours(market) > filters.maxHours) return false;
      return market.status !== 'resolved';
    })
    .sort(opportunitySort);
}

function laneMarkets(markets, lane) {
  if (lane === 'scalp') {
    return markets.filter((market) => market.kind === 'crypto' && cryptoWindowMinutes(market) >= 15);
  }
  if (lane === 'sports') {
    return markets.filter((market) => market.kind === 'sports' && isSportsLiveCandidate(market));
  }
  if (lane === 'esports') {
    return markets.filter((market) => market.kind === 'esports' && isSportsLiveCandidate(market));
  }
  return markets.filter((market) => market.kind === 'general');
}

function laneSummary(markets) {
  return {
    scalp: laneMarkets(markets, 'scalp').length,
    sports: laneMarkets(markets, 'sports').length,
    esports: laneMarkets(markets, 'esports').length,
    regular: laneMarkets(markets, 'regular').length,
  };
}

function laneTitle(lane) {
  if (lane === 'scalp') return '短线高频';
  if (lane === 'sports') return '体育临场';
  if (lane === 'esports') return '电竞临场';
  return '常规事件';
}

function opportunitySort(a, b) {
  const displayDiff = displayRank(a) - displayRank(b);
  if (displayDiff !== 0) return displayDiff;
  const riskDiff = riskRank(a) - riskRank(b);
  if (riskDiff !== 0) return riskDiff;
  const urgencyDiff = urgencyRank(a) - urgencyRank(b);
  if (urgencyDiff !== 0) return urgencyDiff;
  const aHours = remainingHours(a);
  const bHours = remainingHours(b);
  if (aHours !== bHours) return aHours - bHours;
  if ((b.score || 0) !== (a.score || 0)) return (b.score || 0) - (a.score || 0);
  const freshnessDiff = freshnessRank(a) - freshnessRank(b);
  if (freshnessDiff !== 0) return freshnessDiff;
  const aLiquidity = a.liquidity || 0;
  const bLiquidity = b.liquidity || 0;
  if (aLiquidity !== bLiquidity) return bLiquidity - aLiquidity;
  return winRate(b) - winRate(a);
}

function displayRank(market) {
  const tags = market.status_tags || [];
  if (['sports', 'esports'].includes(market.kind)) {
    if (!market.game_start_time) return 8;
    const start = new Date(market.game_start_time).getTime();
    if (start > Date.now()) return 6;
    if (tags.includes('ClosedRisk')) return 7;
    if (tags.includes('StaleBook')) return 5;
    if (!clobRate(market)) return 4;
    if (market.clob_spread === undefined || market.clob_spread === null || signalScore(market) <= 0) return 4;
    return 0;
  }
  if (tags.includes('ClosedRisk')) return 7;
  if (tags.includes('StaleBook')) return 5;
  if (!clobRate(market)) return 4;
  if (market.kind === 'crypto') return 1;
  return 2;
}

function isSportsLiveCandidate(market) {
  if (!market.game_start_time) return false;
  if (displayRate(market) >= 99.9) return false;
  const minutesToStart = (new Date(market.game_start_time).getTime() - Date.now()) / 60000;
  if (minutesToStart <= 15 && minutesToStart >= -210) return true;
  return displayRate(market) >= 80 && (market.liquidity || 0) >= 250 && market.status !== 'resolved';
}

function cryptoWindowMinutes(market) {
  if (market?.kind !== 'crypto') return Infinity;
  const text = market.question || '';
  const match = text.match(/(\d{1,2}):(\d{2})\s*(AM|PM)?\s*-\s*(\d{1,2}):(\d{2})\s*(AM|PM)?/i);
  if (!match) return Infinity;
  const [, startHourRaw, startMinuteRaw, startPeriodRaw, endHourRaw, endMinuteRaw, endPeriodRaw] = match;
  const endPeriod = (endPeriodRaw || startPeriodRaw || '').toUpperCase();
  const startPeriod = (startPeriodRaw || endPeriod || '').toUpperCase();
  const start = clockMinutes(Number(startHourRaw), Number(startMinuteRaw), startPeriod);
  let end = clockMinutes(Number(endHourRaw), Number(endMinuteRaw), endPeriod);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return Infinity;
  if (end <= start) end += 24 * 60;
  return end - start;
}

function clockMinutes(hour, minute, period) {
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return Infinity;
  let normalizedHour = hour;
  if (period === 'AM' && normalizedHour === 12) normalizedHour = 0;
  if (period === 'PM' && normalizedHour !== 12) normalizedHour += 12;
  return normalizedHour * 60 + minute;
}

function riskRank(market) {
  const tags = market.status_tags || [];
  if (tags.includes('ClosedRisk')) return 3;
  if (tags.includes('StaleBook')) return 2;
  return 0;
}

function urgencyRank(market) {
  const hours = remainingHours(market);
  if (!Number.isFinite(hours)) return 9;
  if (hours <= 0.5) return 0;
  if (hours <= 3) return 1;
  if (hours <= 6) return 2;
  if (hours <= 24) return 3;
  if (hours <= 48) return 4;
  return 5;
}

function freshnessRank(market) {
  if (!market.orderbook_updated_at) return 3;
  const ageSeconds = (Date.now() - new Date(market.orderbook_updated_at).getTime()) / 1000;
  if (ageSeconds <= 20) return 0;
  if (ageSeconds <= 45) return 1;
  if (ageSeconds <= 75) return 2;
  return 3;
}

function remainingHours(market) {
  if (!market || market.status === 'resolved') return Infinity;
  const target = effectiveDeadline(market);
  if (!target) return Infinity;
  return Math.max(0, (new Date(target).getTime() - Date.now()) / 3600000);
}

function maxPrice(market) {
  return Math.max(...(market?.outcomePrices || [market?.last_price || 0]));
}

function formatPrice(price) {
  if (price === undefined || price === null || Number.isNaN(price)) return '-';
  return Number(price).toFixed(3);
}

function formatPercent(value) {
  if (!value) return '-';
  return `${Number(value).toFixed(1)}%`;
}

function formatSignedPercent(value) {
  if (value === undefined || value === null || Number.isNaN(value)) return '-';
  if (Math.abs(value) < 0.05) return '0.0%';
  return `${value > 0 ? '+' : ''}${Number(value).toFixed(1)}%`;
}

function spreadLabel(market) {
  const spread = market?.clob_spread ?? (market?.best_bid && market?.best_ask ? market.best_ask - market.best_bid : null);
  if (spread === null || spread === undefined) return '-';
  return `${Math.max(0, spread * 100).toFixed(1)}¢`;
}

function lastTradeLabel(market) {
  if (market?.last_trade_price === undefined || market?.last_trade_price === null) return '-';
  return formatPrice(market.last_trade_price);
}

function decisionLabel(market) {
  if (market.tradable === false) return '盘口不可交易';
  const score = signalScore(market);
  if (score >= 82) return '重点检查';
  if (score >= 70) return '候选观察';
  return '暂不优先';
}

function tradableLabel(market) {
  if (market.tradable === true) return 'CLOB 可交易';
  if (market.tradable === false) return 'CLOB 不可交易';
  return '等待盘口校验';
}

function formatMoney(value) {
  if (!value) return '-';
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${Math.round(value)}`;
}

function remainingLabel(market) {
  if (!market) return '-';
  if (market.status === 'resolved') return '已结束';
  const target = effectiveDeadline(market);
  if (!target) return '-';
  const seconds = Math.floor((new Date(target).getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  const hours = Math.floor(abs / 3600);
  const minutes = Math.floor((abs % 3600) / 60);
  const prefix = deadlinePrefix(market);
  if ((market.kind === 'sports' || market.kind === 'esports') && seconds < 0) return `已开赛 ${hours}h ${minutes}m`;
  return `${prefix} ${hours}h ${minutes}m`;
}

function targetTimeLabel(market) {
  const target = effectiveDeadline(market);
  if (!target) return '-';
  return new Date(target).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function timeBasisLabel(market) {
  const labels = {
    sports_start_time: '按开赛时间',
    crypto_endDate: 'Crypto endDate',
    weather_local_day: '天气城市本地日终',
    weather_close_time: '天气交易截止',
    by_date_et_rules: 'By 日期按美东自然日解释',
    inclusive_period_et_rules: '统计周期按美东自然日解释',
    explicit_datetime_et_rules: '规则明确美东时间',
    event_date_et_rules: '事件日期按美东自然日解释',
    election_date_et_rules: '选举日按美东自然日解释',
    endDate: 'Gamma endDate',
  };
  return labels[market.time_basis] || 'Gamma endDate';
}

function effectiveDeadline(market) {
  if (!market) return null;
  if (market.kind === 'sports' || market.kind === 'esports') return market.game_start_time || market.endDate;
  if (['by_date_et_rules', 'inclusive_period_et_rules', 'explicit_datetime_et_rules', 'event_date_et_rules', 'election_date_et_rules'].includes(market.time_basis)) return market.real_deadline || market.endDate;
  if (market.kind === 'general' && market.category !== 'Weather') return market.endDate || market.real_deadline;
  return market.real_deadline || market.endDate;
}

function deadlinePrefix(market) {
  if (market.kind === 'sports' || market.kind === 'esports') return '开赛';
  if (market.kind === 'general' && market.category !== 'Weather') return '交易截止';
  if (['by_date_et_rules', 'inclusive_period_et_rules', 'explicit_datetime_et_rules', 'event_date_et_rules', 'election_date_et_rules'].includes(market.time_basis)) return '规则截止';
  if (market.category === 'Weather') return '交易截止';
  return '截止';
}

function rawEndDateLabel(market) {
  if (!market?.endDate) return '-';
  return new Date(market.endDate).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function firstSportTag(tags = []) {
  return tags.find((tag) => ['NBA', 'NFL', 'NHL', 'MLB'].includes(tag.toUpperCase())) || 'Sports';
}

function marketLabel(market) {
  if (market.kind === 'crypto') return '加密货币';
  if (market.kind === 'sports') return `体育-${firstSportTag(market.tags)}`;
  if (market.kind === 'esports') return '电子竞技';
  return market.category || market.tags?.[0] || '全市场';
}

function outcomeLine(market) {
  const outcome = outcomeValue(market);
  const prefix = ['Yes', 'No'].includes(outcome) ? '方向' : '选项';
  const price = clobRate(market) || gammaRate(market);
  const priceText = price ? ` · ${formatPercent(price)}` : '';
  return `${prefix}: ${outcome}${priceText}`;
}

function outcomeValue(market) {
  return market?.leading_outcome || inferredOutcome(market) || '-';
}

function inferredOutcome(market) {
  const prices = market?.outcomePrices || [];
  const outcomes = market?.outcomes || [];
  if (!prices.length || !outcomes.length) return '';
  const index = prices.reduce((best, value, current) => (value > prices[best] ? current : best), 0);
  return outcomes[index] || '';
}

function marketLinkTitle(market) {
  return `打开 Polymarket 事件页；当前展示合约：${outcomeLine(market)}`;
}

function shortQuestion(question = '') {
  return question.length > 30 ? `${question.slice(0, 30)}...` : question;
}

function formatTime(value) {
  if (!value) return '--:--:--';
  return new Date(value).toLocaleTimeString('en-GB');
}

function manualRefreshLabel(state, hasPendingUpdate = false) {
  if (state === 'loading') return '刷新中';
  if (state === 'done') return '已显示最新结果';
  if (state === 'error') return '刷新失败';
  if (hasPendingUpdate) return '查看后台新结果';
  return '手动刷新';
}

createRoot(document.getElementById('root')).render(<App />);
