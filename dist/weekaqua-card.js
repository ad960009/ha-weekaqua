/**
 * WeekAqua Lovelace Custom Card for Home Assistant
 * Features:
 *  - Premium WPF Dark Glassmorphism UI
 *  - Real-time Channel Sliders (Red, Green, Blue, White, UV, Violet, Fan)
 *  - 100% Total Power Load Gauge
 *  - One-Click Spectrum Presets
 *  - Unlimited Steps Dynamic Schedule Editor with 24-Hour SVG Curve Visualization
 */

const CARD_PRESETS = {
  GreenGrass: { r: 75, g: 95, b: 38, w: 75, uv: 10, v: 5 },
  RedGrass: { r: 95, g: 30, b: 65, w: 75, uv: 15, v: 10 },
  FishMixed: { r: 70, g: 70, b: 70, w: 95, uv: 5, v: 5 },
  Shrimp: { r: 40, g: 90, b: 60, w: 80, uv: 10, v: 5 },
  Fish: { r: 80, g: 50, b: 85, w: 95, uv: 10, v: 10 },
  CoralMarine: { r: 10, g: 20, b: 95, w: 95, uv: 60, v: 40 },
  CoralLps: { r: 15, g: 25, b: 90, w: 70, uv: 50, v: 60 },
  CoralSps: { r: 5, g: 15, b: 100, w: 60, uv: 75, v: 85 },
  CoralAb: { r: 10, g: 20, b: 100, w: 40, uv: 80, v: 90 },
  MarineFot: { r: 50, g: 50, b: 85, w: 90, uv: 25, v: 30 },
  DeepBlue: { r: 0, g: 10, b: 100, w: 20, uv: 80, v: 95 },
  Moonlight: { r: 0, g: 0, b: 25, w: 0, uv: 15, v: 30 },
  AlgaeMax: { r: 70, g: 65, b: 70, w: 55, uv: 20, v: 15 },
  Max: { r: 100, g: 100, b: 100, w: 100, uv: 100, v: 100 },
};

class WeekAquaCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
    this._activeTab = 'live'; // 'live' or 'schedule'
    this._keepMoonlight = true;
    this._moonlightBrightness = 4;
    this._scheduleEnabled = true;
    this._hasLoadedInitialSchedule = false;
    this._scheduleMeta = null;
    this._schedulePoints = [
      { time: '18:00', r: 12, g: 15, b: 6, w: 12, uv: 2, v: 1 },
      { time: '18:26', r: 23, g: 29, b: 12, w: 23, uv: 3, v: 2 },
      { time: '18:51', r: 34, g: 43, b: 17, w: 34, uv: 5, v: 2 },
      { time: '19:17', r: 44, g: 56, b: 22, w: 44, uv: 6, v: 3 },
      { time: '19:43', r: 53, g: 67, b: 27, w: 53, uv: 7, v: 4 },
      { time: '20:09', r: 61, g: 77, b: 31, w: 61, uv: 8, v: 4 },
      { time: '20:34', r: 67, g: 85, b: 34, w: 67, uv: 9, v: 4 },
      { time: '21:00', r: 71, g: 90, b: 36, w: 71, uv: 10, v: 5 },
      { time: '21:26', r: 74, g: 94, b: 38, w: 74, uv: 10, v: 5 },
      { time: '21:51', r: 75, g: 95, b: 38, w: 75, uv: 10, v: 5 },
      { time: '22:17', r: 74, g: 94, b: 38, w: 74, uv: 10, v: 5 },
      { time: '22:43', r: 71, g: 90, b: 36, w: 71, uv: 10, v: 5 },
      { time: '23:09', r: 67, g: 85, b: 34, w: 67, uv: 9, v: 4 },
      { time: '23:34', r: 61, g: 77, b: 31, w: 61, uv: 8, v: 4 },
      { time: '00:00', r: 53, g: 67, b: 27, w: 53, uv: 7, v: 4 },
      { time: '00:24', r: 44, g: 56, b: 22, w: 44, uv: 6, v: 3 },
      { time: '00:48', r: 34, g: 43, b: 17, w: 34, uv: 5, v: 2 },
      { time: '01:12', r: 23, g: 29, b: 12, w: 23, uv: 3, v: 2 },
      { time: '01:36', r: 12, g: 15, b: 6, w: 12, uv: 2, v: 1 },
      { time: '02:00', r: 0, g: 0, b: 4, w: 0, uv: 0, v: 0 },
    ];
    this._isUserInteractingSliders = false;
    this._lastUserSliderInteractionTime = 0;
    this._sliderInteractionTimer = null;
    this._lastLayoutKey = null;
    this._lastLogHash = null;
  }

  setConfig(config) {
    if (!config) {
      throw new Error('Invalid configuration');
    }
    this._config = Object.assign({}, config);
    this._render();
    if (this._hass) {
      this._updateState();
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._updateState();
  }

  _calculatePower(r, g, b, w, uv = 0, v = 0) {
    const attr = this._modelInfo || {};
    const is4ChRgbUv = this._config.is_4ch_rgb_uv !== undefined
      ? Boolean(this._config.is_4ch_rgb_uv)
      : (attr.is_4ch_rgb_uv || (attr.device_name && (
          attr.device_name.toUpperCase().includes('M800') ||
          attr.device_name.toUpperCase().includes('M600') ||
          attr.device_name.toUpperCase().includes('M-PRO') ||
          attr.device_name.toUpperCase().includes('M PRO') ||
          attr.device_name.toUpperCase().includes('S-PRO') ||
          attr.device_name.toUpperCase().includes('S400') ||
          attr.device_name.toUpperCase().includes('S600') ||
          attr.device_name.toUpperCase().includes('S800') ||
          attr.device_name.toUpperCase().includes('T90') ||
          attr.device_name.toUpperCase().includes('P600') ||
          attr.device_name.toUpperCase().includes('P800') ||
          attr.device_name.toUpperCase().includes('P900') ||
          attr.device_name.toUpperCase().includes('P1200') ||
          attr.device_name.toUpperCase().includes('Z400') ||
          attr.device_name.toUpperCase().includes('Z600')
        )));
    const modelCode = attr.model_code || '';

    let total = 0;
    if (is4ChRgbUv || modelCode === '5746') {
      // 4-Channel RGB/UV (e.g. M800 Pro, M600, S-Series, T90)
      total = (r * 0.41) + (g * 0.42) + (b * 0.49) + (uv * 0.08);
    } else if (modelCode === '5748') {
      // 5-Channel Mode 5 (RGBW + UV)
      total = (r * 0.41) + (g * 0.42) + (b * 0.49) + (w * 0.08) + (uv * 0.08);
    } else if (modelCode === '5749') {
      // 6-Channel Mode 6 (RGBW + UV + Violet)
      total = (r * 0.41) + (g * 0.42) + (b * 0.49) + (w * 0.08) + (uv * 0.08) + (v * 0.08);
    } else if (modelCode === '5750' || modelCode === '5751' || modelCode === '5752') {
      // 7+ Channel Advanced High Power Models
      total = ((r * 0.29) + (g * 0.69) + (b * 0.73) + (w * 0.10) + (uv * 0.40) + (v * 0.40)) / 1.06;
    } else {
      // Standard 4-Channel RGBW
      total = (r * 0.39) + (g * 0.41) + (b * 0.53) + (w * 0.11);
    }
    return Math.min(100.0, Math.round(total * 10) / 10);
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          color: #F4F4F5;
        }
        .card {
          background: #18181B;
          border: 1px solid #27272A;
          border-radius: 12px;
          padding: 16px;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;
        }
        .title {
          font-size: 16px;
          font-weight: 700;
          color: #93C5FD;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .conn-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: #27272A;
          border-radius: 8px;
          padding: 8px 12px;
          margin-bottom: 12px;
          font-size: 13px;
          gap: 10px;
          flex-wrap: wrap;
        }
        .conn-badge {
          display: flex;
          align-items: center;
          gap: 6px;
          font-weight: 600;
          font-size: 12.5px;
          white-space: nowrap;
        }
        .device-tag {
          font-size: 12px;
          font-weight: 600;
          color: #A5F3FC;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          background: #18181B;
          padding: 3px 10px;
          border-radius: 6px;
          border: 1px solid #3F3F46;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          letter-spacing: 0.2px;
        }
        .conn-dot {
          width: 9px;
          height: 9px;
          border-radius: 50%;
          background: #71717A;
        }
        .conn-dot.online {
          background: #10B981;
          box-shadow: 0 0 8px #10B981;
        }
        .btn-conn {
          background: #3F3F46;
          color: #E4E4E7;
          border: 1px solid #52525B;
          border-radius: 6px;
          padding: 4px 10px;
          font-size: 11.5px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        .btn-conn:hover {
          background: #52525B;
        }
        .btn-conn.disconnect {
          background: #991B1B;
          border-color: #DC2626;
          color: #FFF;
        }
        .tabs {
          display: flex;
          gap: 6px;
          background: #27272A;
          padding: 3px;
          border-radius: 8px;
        }
        /* Hardware Mode Bar */
        .mode-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 12px;
          background: rgba(24, 24, 27, 0.75);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 8px;
          margin-bottom: 12px;
        }
        .mode-left {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .mode-badge {
          font-size: 11px;
          font-weight: 700;
          padding: 2px 8px;
          border-radius: 4px;
          display: inline-block;
        }
        .mode-badge.live {
          background: rgba(239, 68, 68, 0.2);
          color: #F87171;
          border: 1px solid rgba(239, 68, 68, 0.4);
        }
        .mode-badge.sched {
          background: rgba(16, 185, 129, 0.2);
          color: #34D399;
          border: 1px solid rgba(16, 185, 129, 0.4);
        }
        .btn-mode {
          background: #27272A;
          color: #A1A1AA;
          border: 1px solid #3F3F46;
          border-radius: 6px;
          padding: 5px 11px;
          font-size: 11.5px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        .btn-mode:hover {
          background: #3F3F46;
          color: #FFFFFF;
        }
        .btn-mode.active {
          background: #2563EB;
          color: #FFFFFF;
          border-color: #3B82F6;
          box-shadow: 0 0 10px rgba(37, 99, 235, 0.4);
        }
        .tab-btn {
          background: transparent;
          border: none;
          color: #A1A1AA;
          padding: 4px 10px;
          font-size: 12px;
          font-weight: 600;
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s;
        }
        .tab-btn.active {
          background: #3B82F6;
          color: #FFF;
        }
        /* Sliders */
        .slider-group {
          margin-bottom: 8px;
        }
        .slider-row {
          display: grid;
          grid-template-columns: 70px 1fr 50px;
          align-items: center;
          gap: 10px;
          margin-bottom: 6px;
        }
        .channel-label {
          font-size: 12px;
          font-weight: 700;
        }
        input[type="range"] {
          -webkit-appearance: none;
          width: 100%;
          height: 6px;
          border-radius: 3px;
          background: #27272A;
          outline: none;
        }
        input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: #FFF;
          cursor: pointer;
          box-shadow: 0 0 6px rgba(0, 0, 0, 0.5);
        }
        .val-badge {
          font-size: 11px;
          color: #A1A1AA;
          text-align: right;
          font-family: monospace;
        }
        /* Power Gauge */
        .gauge-wrap {
          background: #27272A;
          border-radius: 6px;
          padding: 8px 12px;
          margin-top: 10px;
          margin-bottom: 12px;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .gauge-bar-bg {
          flex: 1;
          height: 8px;
          background: #3F3F46;
          border-radius: 4px;
          margin: 0 10px;
          overflow: hidden;
        }
        .gauge-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, #10B981, #F59E0B, #EF4444);
          width: 0%;
          transition: width 0.3s;
        }
        /* Presets */
        .presets-title {
          font-size: 12px;
          font-weight: 600;
          color: #A1A1AA;
          margin-bottom: 6px;
        }
        .preset-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
          gap: 6px;
          margin-bottom: 12px;
        }
        .preset-btn {
          background: #27272A;
          border: 1px solid #3F3F46;
          color: #E4E4E7;
          padding: 6px;
          font-size: 11px;
          border-radius: 6px;
          cursor: pointer;
          font-weight: 500;
          transition: background 0.15s;
        }
        .preset-btn:hover {
          background: #3F3F46;
          border-color: #60A5FA;
        }
        /* Schedule Status Header */
        .sched-status-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: #27272A;
          border: 1px solid #3F3F46;
          border-radius: 8px;
          padding: 8px 12px;
          margin-bottom: 12px;
        }
        .sched-status-left {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .sched-state-badge {
          font-size: 11px;
          color: #94A3B8;
          font-weight: 600;
        }
        .sched-state-badge.active {
          color: #10B981;
        }
        .btn-toggle-sched {
          background: #3F3F46;
          color: #E4E4E7;
          border: 1px solid #52525B;
          border-radius: 6px;
          padding: 4px 10px;
          font-size: 11px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }
        .btn-toggle-sched:hover {
          background: #52525B;
        }
        .btn-toggle-sched.active {
          background: #7F1D1D;
          border-color: #EF4444;
          color: #FCA5A5;
        }
        .btn-toggle-sched.active:hover {
          background: #991B1B;
        }
        /* Schedule Config */
        .sched-config-card {
          background: #27272A;
          border: 1px solid #3F3F46;
          border-radius: 8px;
          padding: 10px 12px;
          margin-bottom: 12px;
        }
        .sched-config-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
          margin-bottom: 8px;
        }
        .config-item {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .config-item label {
          font-size: 11px;
          font-weight: 600;
          color: #93C5FD;
        }
        .config-item input, .config-item select {
          background: #18181B;
          border: 1px solid #3F3F46;
          color: #F4F4F5;
          padding: 5px 8px;
          border-radius: 6px;
          font-size: 12px;
          outline: none;
        }
        .moonlight-toggle-wrap {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: #18181B;
          border: 1px solid #3F3F46;
          border-radius: 6px;
          padding: 7px 10px;
          margin-bottom: 10px;
        }
        .moonlight-label {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 11px;
          font-weight: 600;
          color: #93C5FD;
          cursor: pointer;
          user-select: none;
        }
        .moonlight-label input[type="checkbox"] {
          cursor: pointer;
          accent-color: #3B82F6;
          width: 15px;
          height: 15px;
          margin: 0;
        }
        .moonlight-badge {
          font-size: 10px;
          color: #60A5FA;
          background: rgba(59, 130, 246, 0.15);
          padding: 2px 6px;
          border-radius: 4px;
          font-weight: 600;
        }
        .btn-auto-distribute {
          background: linear-gradient(135deg, #2563EB, #7C3AED);
          color: #FFF;
          border: none;
          padding: 8px 12px;
          border-radius: 6px;
          font-weight: 700;
          font-size: 12px;
          cursor: pointer;
          width: 100%;
          transition: opacity 0.2s;
        }
        .btn-auto-distribute:hover {
          opacity: 0.9;
        }
        .sched-wrap {
          display: none;
        }
        .sched-wrap.active {
          display: block;
        }
        .curve-svg {
          width: 100%;
          height: 100px;
          background: #09090B;
          border-radius: 8px;
          margin-bottom: 10px;
          border: 1px solid #27272A;
        }
        .table-wrap {
          max-height: 220px;
          overflow-y: auto;
          border: 1px solid #27272A;
          border-radius: 6px;
          margin-bottom: 10px;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 11px;
          text-align: center;
        }
        th {
          background: #27272A;
          color: #93C5FD;
          padding: 6px;
        }
        td {
          padding: 4px;
          border-bottom: 1px solid #27272A;
        }
        td input {
          width: 40px;
          background: #09090B;
          border: 1px solid #3F3F46;
          color: #FFF;
          border-radius: 4px;
          text-align: center;
          font-size: 11px;
        }
        .btn-action {
          background: #2563EB;
          color: #FFF;
          border: none;
          padding: 8px 12px;
          border-radius: 6px;
          font-weight: 600;
          font-size: 12px;
          cursor: pointer;
          width: 100%;
        }
        .btn-sm {
          padding: 2px 6px;
          font-size: 10px;
          background: #DC2626;
          color: #FFF;
          border: none;
          border-radius: 4px;
          cursor: pointer;
        }

        /* Collapsible BLE Packet & Queue Log Monitor */
        .log-container {
          background: #18181B;
          border: 1px solid #3F3F46;
          border-radius: 8px;
          margin-top: 14px;
          overflow: hidden;
        }
        .log-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 12px;
          background: #27272A;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
          user-select: none;
          transition: background 0.2s;
        }
        .log-header:hover {
          background: #3F3F46;
        }
        .log-badge-q {
          background: #3F3F46;
          color: #E0F2FE;
          font-size: 11px;
          font-weight: 700;
          padding: 2px 8px;
          border-radius: 12px;
          font-family: monospace;
          letter-spacing: 0.5px;
          transition: background 0.3s;
        }
        .log-toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 6px 12px;
          background: #1F2024;
          border-top: 1px solid #3F3F46;
          border-bottom: 1px solid #27272A;
        }
        .log-console {
          max-height: 220px;
          overflow-y: auto;
          background: #090A0F;
          padding: 8px 12px;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          font-size: 11px;
          line-height: 1.6;
        }
        .log-line {
          display: flex;
          align-items: baseline;
          gap: 6px;
          border-bottom: 1px solid #1E2028;
          padding: 2px 0;
          word-break: break-all;
        }
        .log-ts {
          color: #64748B;
          flex-shrink: 0;
          font-size: 10px;
        }
        .log-tag {
          font-weight: 700;
          font-size: 10px;
          padding: 1px 5px;
          border-radius: 3px;
          flex-shrink: 0;
        }
        .log-tag.ENQUEUE { background: rgba(56, 189, 248, 0.2); color: #38BDF8; }
        .log-tag.DEQUEUE { background: rgba(251, 191, 36, 0.2); color: #FBBF24; }
        .log-tag.WRITE_OK { background: rgba(52, 211, 153, 0.2); color: #34D399; }
        .log-tag.WRITE_ERR, .log-tag.QUEUE_ERR, .log-tag.CONNECT_ERR { background: rgba(248, 113, 113, 0.2); color: #F87171; }
        .log-tag.DEDUP { background: rgba(192, 132, 252, 0.2); color: #C084FC; }
        .log-tag.QUEUE_DROP, .log-tag.WRITE_SKIP, .log-tag.DISCONNECT { background: rgba(251, 146, 60, 0.2); color: #FB923C; }
        .log-tag.CONNECT_OK, .log-tag.GATT_READY { background: rgba(16, 185, 129, 0.2); color: #10B981; }
        .log-tag.CONNECT_REQ, .log-tag.DISCONNECT_REQ, .log-tag.TIMEOUT_DISCONN { background: rgba(148, 163, 184, 0.2); color: #94A3B8; }
        .log-hex {
          background: #1C1F26;
          color: #FDE047;
          padding: 0 4px;
          border-radius: 3px;
          font-weight: 600;
          letter-spacing: 0.5px;
        }
        .log-q-len {
          color: #06B6D4;
          font-weight: 700;
          font-size: 10px;
        }
        .log-msg {
          color: #E2E8F0;
        }
      </style>

      <div class="card">
        <div class="header">
          <div class="title">
            <span>🐠</span> <span id="card-title-text">${this._config.title || 'WeekAqua Light'}</span>
          </div>
          <div class="tabs">
            <button class="tab-btn active" id="tab-live">Live</button>
            <button class="tab-btn" id="tab-timer">Sunrise & Sunset</button>
            <button class="tab-btn" id="tab-sched">Custom Schedule</button>
          </div>
        </div>

        <div class="conn-bar">
          <div class="conn-badge">
            <div class="conn-dot online" id="conn-dot"></div>
            <span id="conn-status-txt">Auto-Connect (Active)</span>
          </div>
          <div class="device-tag" id="conn-device-tag" style="display: none;"></div>
          <div style="display: flex; gap: 4px;">
            <button class="btn-conn" id="btn-manual-conn">⚡ Connect</button>
            <button class="btn-conn disconnect" id="btn-manual-disconn">❌ Disconnect</button>
          </div>
        </div>

        <!-- Hardware Mode Switch (Live Mode 1 <-> Schedule Mode 2) -->
        <div class="mode-bar">
          <div class="mode-left">
            <span style="font-size: 15px;">🎛️</span>
            <div style="display: flex; flex-direction: column; gap: 1px;">
              <span style="font-size: 11px; color: #94A3B8; font-weight: 600;">Operation Mode</span>
              <span class="mode-badge live" id="mode-status-badge">🔴 Live Manual (Mode 1)</span>
            </div>
          </div>
          <div style="display: flex; gap: 6px;">
            <button class="btn-mode active" id="btn-mode-live">🎨 Live Mode</button>
            <button class="btn-mode" id="btn-mode-sched">📅 Schedule Mode</button>
          </div>
        </div>

        <!-- Tab 1: Live Manual Controls -->
        <div id="panel-live">
          <div class="slider-group" id="sliders-container">
            <div class="slider-row" id="row-r">
              <span class="channel-label" id="lbl-r" style="color: #EF4444">Red</span>
              <input type="range" id="sl-r" min="0" max="100" value="50">
              <span class="val-badge" id="txt-r">50%</span>
            </div>
            <div class="slider-row" id="row-g">
              <span class="channel-label" id="lbl-g" style="color: #22C55E">Green</span>
              <input type="range" id="sl-g" min="0" max="100" value="50">
              <span class="val-badge" id="txt-g">50%</span>
            </div>
            <div class="slider-row" id="row-b">
              <span class="channel-label" id="lbl-b" style="color: #3B82F6">Blue</span>
              <input type="range" id="sl-b" min="0" max="100" value="50">
              <span class="val-badge" id="txt-b">50%</span>
            </div>
            <div class="slider-row" id="row-uv">
              <span class="channel-label" id="lbl-uv" style="color: #C084FC">UV</span>
              <input type="range" id="sl-uv" min="0" max="100" value="0">
              <span class="val-badge" id="txt-uv">0%</span>
            </div>
            <div class="slider-row" id="row-w">
              <span class="channel-label" id="lbl-w" style="color: #F4F4F5">White</span>
              <input type="range" id="sl-w" min="0" max="100" value="50">
              <span class="val-badge" id="txt-w">50%</span>
            </div>
            <div class="slider-row" id="row-v" style="display: none;">
              <span class="channel-label" id="lbl-v" style="color: #EC4899">Violet</span>
              <input type="range" id="sl-v" min="0" max="100" value="0">
              <span class="val-badge" id="txt-v">0%</span>
            </div>
          </div>

          <div class="gauge-wrap">
            <span style="font-size: 11px; font-weight: 700; color: #10B981">⚡ Total Load:</span>
            <div class="gauge-bar-bg">
              <div class="gauge-bar-fill" id="gauge-fill" style="width: 50%"></div>
            </div>
            <span style="font-size: 11px; font-weight: 700;" id="gauge-txt">50.0%</span>
          </div>

          <div class="presets-title">🎨 Spectrum Presets (One-Click)</div>
          <div class="preset-grid">
            <button class="preset-btn" data-p="GreenGrass">🌿 Green</button>
            <button class="preset-btn" data-p="RedGrass">🍁 Red Plant</button>
            <button class="preset-btn" data-p="FishMixed">🐠 Mixed</button>
            <button class="preset-btn" data-p="Shrimp">🦐 Shrimp</button>
            <button class="preset-btn" data-p="Fish">🐟 Fish</button>
            <button class="preset-btn" data-p="CoralAb">🪸 Coral AB+</button>
            <button class="preset-btn" data-p="DeepBlue">🌊 Deep Blue</button>
            <button class="preset-btn" data-p="Max" style="color: #FBBF24; font-weight: 700;">💡 Max (100%)</button>
            <button class="preset-btn" data-p="Moonlight">🌙 Moonlight</button>
          </div>
        </div>

        <!-- Tab 2: Sunrise & Sunset Quick Ramp Timer -->
        <div id="panel-timer" style="display: none;">
          <div style="background: #27272A; border-radius: 8px; padding: 12px; margin-bottom: 12px; border: 1px solid #3F3F46;">
            <div style="font-size: 13px; font-weight: 700; color: #F59E0B; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span>☀️</span>
                <span>Sunrise & Sunset Ramp Timer (일출/일몰 모드)</span>
              </div>
              <span class="mode-badge" style="background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.4);">Mode 1 Timer</span>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
              <div>
                <label style="font-size: 11px; color: #A1A1AA; font-weight: 600; display: block; margin-bottom: 4px;">🌅 Start Time (점등/일출 시작)</label>
                <input type="text" id="timer-start-time" value="08:00" placeholder="08:00" style="width: 100%; background: #18181B; border: 1px solid #3F3F46; color: #FFF; padding: 6px 8px; border-radius: 6px; font-size: 12px; box-sizing: border-box;">
              </div>
              <div>
                <label style="font-size: 11px; color: #A1A1AA; font-weight: 600; display: block; margin-bottom: 4px;">🌇 End Time (소등/일몰 완료)</label>
                <input type="text" id="timer-end-time" value="18:00" placeholder="18:00" style="width: 100%; background: #18181B; border: 1px solid #3F3F46; color: #FFF; padding: 6px 8px; border-radius: 6px; font-size: 12px; box-sizing: border-box;">
              </div>
            </div>

            <div style="margin-bottom: 12px;">
              <label style="font-size: 11px; color: #A1A1AA; font-weight: 600; display: block; margin-bottom: 4px;">⏳ Ramp Duration (램프 시간 - 서서히 밝아지고 어두워짐)</label>
              <select id="timer-ramp-select" style="width: 100%; background: #18181B; border: 1px solid #3F3F46; color: #FFF; padding: 6px 8px; border-radius: 6px; font-size: 12px; box-sizing: border-box;">
                <option value="0">0 Hours (즉시 점등/소등)</option>
                <option value="1">0.5 Hours (30분 램프업/다운)</option>
                <option value="2" selected>1.0 Hours (60분 램프업/다운 - 기본 권장)</option>
                <option value="3">1.5 Hours (90분 램프업/다운)</option>
                <option value="4">2.0 Hours (120분 램프업/다운)</option>
                <option value="5">2.5 Hours (150분 램프업/다운)</option>
              </select>
            </div>

            <div style="margin-bottom: 14px;">
              <label style="font-size: 11px; color: #A1A1AA; font-weight: 600; display: block; margin-bottom: 6px;">🎨 Daytime Target Spectrum (주간 최고 목표 스펙트럼)</label>
              <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-bottom: 8px;" id="timer-presets-grid">
                <button class="preset-btn" data-tp="FishMixed" style="border-color: #3B82F6; background: #1E3A8A; color: #FFF;">🐠 Mixed</button>
                <button class="preset-btn" data-tp="GreenGrass">🌿 Green</button>
                <button class="preset-btn" data-tp="RedGrass">🍁 Red</button>
                <button class="preset-btn" data-tp="Shrimp">🦐 Shrimp</button>
              </div>
              <div style="font-size: 11px; color: #71717A; line-height: 1.4;">
                설정한 시작 시각에 0%부터 램프 시간 동안 서서히 밝아져 목표 스펙트럼에 도달하고, 종료 시각 전 램프 시간 동안 서서히 어두워집니다.
              </div>
            </div>

            <button id="btn-apply-sunrise" class="btn-sched" style="background: linear-gradient(135deg, #D97706, #B45309); width: 100%; padding: 10px; font-weight: 700; font-size: 13px;">
              ☀️ Apply Sunrise & Sunset Timer to Light
            </button>
          </div>
        </div>

        <!-- Tab 3: Custom Schedule Editor -->
        <div id="panel-sched" class="sched-wrap">
          <!-- Dynamic Schedule Enable/Disable Toggle Bar -->
          <div class="sched-status-bar">
            <div class="sched-status-left">
              <span style="font-size: 16px;">📅</span>
              <div style="display: flex; flex-direction: column; gap: 1px;">
                <span style="font-size: 12px; font-weight: 700; color: #F4F4F5;">Dynamic Schedule Mode</span>
                <span class="sched-state-badge active" id="sched-state-badge">🟢 Running (스케줄 가동 중)</span>
              </div>
            </div>
            <button class="btn-toggle-sched active" id="btn-toggle-sched">⏸️ 스케줄 끄기 (수동 모드)</button>
          </div>

          <!-- Start/End Time & Natural Auto Distribute Config -->
          <div class="sched-config-card">
            <div class="sched-config-grid">
              <div class="config-item">
                <label>🌅 Sunrise (시작 시각)</label>
                <input type="text" id="sched-start-time" value="18:00" placeholder="18:00">
              </div>
              <div class="config-item">
                <label>🌇 Sunset (종료 시각)</label>
                <input type="text" id="sched-end-time" value="02:00" placeholder="02:00">
              </div>
            </div>
            <div class="sched-config-grid">
              <div class="config-item">
                <label>🎛️ Slots (슬롯 수)</label>
                <input type="number" id="sched-slots-input" min="3" max="48" value="20" style="width: 100%;">
              </div>
              <div class="config-item">
                <label>🎨 Peak Preset (피크 프리셋)</label>
                <select id="sched-preset-select">
                  <option value="GreenGrass" selected>🌿 Green Plant</option>
                  <option value="RedGrass">🍁 Red Plant</option>
                  <option value="FishMixed">🐠 Mixed</option>
                  <option value="Shrimp">🦐 Shrimp</option>
                  <option value="Fish">🐟 Fish</option>
                  <option value="CoralAb">🪸 Coral AB+</option>
                  <option value="DeepBlue">🌊 Deep Blue</option>
                  <option value="Max">💡 Max (100%)</option>
                  <option value="AlgaeMax">🌿 Algae Max</option>
                  <option value="Moonlight">🌙 Moonlight</option>
                </select>
              </div>
            </div>
            <div class="moonlight-toggle-wrap">
              <label class="moonlight-label" for="sched-keep-moonlight">
                <input type="checkbox" id="sched-keep-moonlight" checked>
                <span>🌙 Keep Night Moonlight (심야 은은한 달빛 <span id="moonlight-pct-txt">4</span>% 유지)</span>
              </label>
              <span class="moonlight-badge" id="moonlight-status-badge">Blue 4%</span>
            </div>
            <button class="btn-auto-distribute" id="btn-auto-distribute">
              ⚡ Auto Distribute (수학적 자연 곡선 자동 계산)
            </button>
          </div>

          <svg class="curve-svg" id="curve-svg" viewBox="0 0 240 100" preserveAspectRatio="none">
            <path id="curve-path" d="" fill="rgba(59, 130, 246, 0.2)" stroke="#3B82F6" stroke-width="2"/>
          </svg>

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>R%</th>
                  <th>G%</th>
                  <th>B%</th>
                  <th id="th-uv">UV%</th>
                  <th id="th-w">W%</th>
                  <th id="th-v" style="display:none;">V%</th>
                  <th></th>
                </tr>
              </thead>
              <tbody id="sched-tbody"></tbody>
            </table>
          </div>

          <div style="display: flex; gap: 6px; margin-bottom: 10px;">
            <button class="preset-btn" style="flex: 1;" id="btn-add-pt">+ Add Step</button>
          </div>

          <button class="btn-action" id="btn-save-sched">💾 Save & Sync Schedule to Home Assistant</button>
        </div>

        <!-- Collapsible BLE Packet & Write Queue Monitor -->
        <div class="log-container">
          <div class="log-header" id="log-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span>📜 BLE Packet & Write Queue Monitor</span>
              <span class="log-badge-q" id="log-queue-badge">Q: 0/10</span>
            </div>
            <span id="log-toggle-icon" style="color: #94A3B8; font-size: 11px;">▼ Expand</span>
          </div>
          <div id="log-body-wrap" style="display: none;">
            <div class="log-toolbar">
              <span style="font-size: 11px; color: #94A3B8;">Real-time BLE GATT Packet Write & Queue Stream</span>
              <div style="display: flex; gap: 6px;">
                <button class="btn-conn" id="btn-log-autoscroll" style="background:#1E293B;">Auto-scroll: ON</button>
                <button class="btn-conn" id="btn-log-copy">📋 Copy</button>
                <button class="btn-conn" id="btn-log-clear">🗑️ Clear</button>
              </div>
            </div>
            <div class="log-console" id="log-console">
              <div style="color: #64748B; padding: 4px 0;">No BLE packet activity logged yet.</div>
            </div>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
    this._restoreFromLocalStorage();
    this._renderScheduleTable();
    this._renderCurve();
  }

  _restoreFromLocalStorage() {
    const key = 'weekaqua_sched_' + (this._config?.entity || 'default');
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const data = JSON.parse(raw);
        if (data.points && Array.isArray(data.points) && data.points.length > 0) {
          this._schedulePoints = data.points;
        }
        if (data) {
          this._scheduleMeta = data;
          this._applyScheduleMeta(data);
        }
      }
    } catch (e) {}
  }

  _applyScheduleMeta(meta) {
    if (!meta) return;
    const root = this.shadowRoot;
    if (!root) return;
    const activeEl = root.activeElement;

    if (meta.start_time) {
      const startEl = root.getElementById('sched-start-time');
      if (startEl && activeEl !== startEl) startEl.value = meta.start_time;
    }
    if (meta.end_time) {
      const endEl = root.getElementById('sched-end-time');
      if (endEl && activeEl !== endEl) endEl.value = meta.end_time;
    }
    if (meta.slots) {
      const slotsEl = root.getElementById('sched-slots-input');
      if (slotsEl && activeEl !== slotsEl) {
        slotsEl.value = String(meta.slots);
        this._userChangedSlots = true;
      }
    }
    if (meta.preset) {
      const presetEl = root.getElementById('sched-preset-select');
      if (presetEl && activeEl !== presetEl) presetEl.value = meta.preset;
    }
    if (meta.moonlight_brightness !== undefined) {
      this._moonlightBrightness = parseFloat(meta.moonlight_brightness) || 4;
    }
    if (meta.keep_moonlight !== undefined) {
      this._keepMoonlight = Boolean(meta.keep_moonlight);
      this._updateMoonlightUI();
    }
  }

  _updateMoonlightUI() {
    const root = this.shadowRoot;
    if (!root) return;
    const chk = root.getElementById('sched-keep-moonlight');
    const badge = root.getElementById('moonlight-status-badge');
    const pctTxt = root.getElementById('moonlight-pct-txt');
    const brightness = this._moonlightBrightness !== undefined ? this._moonlightBrightness : 4;
    if (chk && root.activeElement !== chk) {
      chk.checked = this._keepMoonlight;
    }
    if (pctTxt) {
      pctTxt.textContent = `${brightness}`;
    }
    if (badge) {
      badge.textContent = this._keepMoonlight ? `Blue ${brightness}%` : 'Off (0%)';
      badge.style.color = this._keepMoonlight ? '#60A5FA' : '#94A3B8';
    }
  }

  _bindEvents() {
    const root = this.shadowRoot;

    // Tabs
    const tabLive = root.getElementById('tab-live');
    const tabTimer = root.getElementById('tab-timer');
    const tabSched = root.getElementById('tab-sched');
    const panelLive = root.getElementById('panel-live');
    const panelTimer = root.getElementById('panel-timer');
    const panelSched = root.getElementById('panel-sched');

    const switchTab = (tab) => {
      [tabLive, tabTimer, tabSched].forEach(t => t && t.classList.remove('active'));
      [panelLive, panelTimer, panelSched].forEach(p => {
        if (p) {
          p.style.display = 'none';
          p.classList.remove('active');
        }
      });
      if (tab === 'live') {
        if (tabLive) tabLive.classList.add('active');
        if (panelLive) panelLive.style.display = 'block';
      } else if (tab === 'timer') {
        if (tabTimer) tabTimer.classList.add('active');
        if (panelTimer) panelTimer.style.display = 'block';
      } else if (tab === 'sched') {
        if (tabSched) tabSched.classList.add('active');
        if (panelSched) {
          panelSched.style.display = 'block';
          panelSched.classList.add('active');
        }
        this._renderCurve();
      }
    };

    if (tabLive) tabLive.addEventListener('click', () => switchTab('live'));
    if (tabTimer) tabTimer.addEventListener('click', () => switchTab('timer'));
    if (tabSched) tabSched.addEventListener('click', () => switchTab('sched'));

    // Sunrise/Sunset Preset picker
    let selectedTimerPreset = 'FishMixed';
    root.querySelectorAll('#timer-presets-grid .preset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        root.querySelectorAll('#timer-presets-grid .preset-btn').forEach(b => {
          b.style.background = '#27272A';
          b.style.borderColor = '#3F3F46';
          b.style.color = '#E4E4E7';
        });
        btn.style.background = '#1E3A8A';
        btn.style.borderColor = '#3B82F6';
        btn.style.color = '#FFFFFF';
        selectedTimerPreset = btn.dataset.tp || 'FishMixed';
      });
    });

    // Sunrise/Sunset Apply Button
    const btnApplySunrise = root.getElementById('btn-apply-sunrise');
    if (btnApplySunrise) {
      btnApplySunrise.addEventListener('click', () => {
        const startTime = root.getElementById('timer-start-time')?.value?.trim() || '08:00';
        const endTime = root.getElementById('timer-end-time')?.value?.trim() || '18:00';
        const rampIdx = parseInt(root.getElementById('timer-ramp-select')?.value || '2', 10);

        btnApplySunrise.textContent = '⏳ Sending Sunrise/Sunset Timer...';
        btnApplySunrise.style.background = '#059669';

        if (this._hass) {
          this._hass.callService('weekaqua', 'set_timer', {
            device_id: this._config.device_id || '',
            entity_id: this._config.entity || '',
            start_time: startTime,
            end_time: endTime,
            ramp_index: rampIdx,
            preset: selectedTimerPreset,
          });
        }
        this._setConnectionStatus(true);
        this._updateModeUI(1);

        setTimeout(() => {
          if (btnApplySunrise) {
            btnApplySunrise.textContent = '✅ Sunrise & Sunset Timer Sent to Light!';
            setTimeout(() => {
              btnApplySunrise.textContent = '☀️ Apply Sunrise & Sunset Timer to Light';
              btnApplySunrise.style.background = 'linear-gradient(135deg, #D97706, #B45309)';
            }, 3000);
          }
        }, 1200);
      });
    }

    // Operation Mode Switching (Live Mode 1 <-> Schedule Mode 2)
    const btnModeLive = root.getElementById('btn-mode-live');
    const btnModeSched = root.getElementById('btn-mode-sched');
    if (btnModeLive) {
      btnModeLive.addEventListener('click', () => {
        this._updateModeUI(1);
        if (this._hass) {
          this._hass.callService('weekaqua', 'activate_live_mode', {
            device_id: this._config.device_id || '',
            entity_id: this._config.entity || '',
          });
        }
        this._setConnectionStatus(true);
      });
    }
    if (btnModeSched) {
      btnModeSched.addEventListener('click', () => {
        this._updateModeUI(2);
        if (this._hass) {
          this._hass.callService('weekaqua', 'activate_schedule_mode', {
            device_id: this._config.device_id || '',
            entity_id: this._config.entity || '',
          });
        }
        this._setConnectionStatus(true);
      });
    }

    // Manual Connect / Disconnect buttons
    root.getElementById('btn-manual-conn').addEventListener('click', () => {
      if (this._hass) {
        this._hass.callService('weekaqua', 'connect', {
          device_id: this._config.device_id || '',
          entity_id: this._config.entity || '',
        });
      }
      this._setConnectionStatus(true);
    });

    root.getElementById('btn-manual-disconn').addEventListener('click', () => {
      if (this._hass) {
        this._hass.callService('weekaqua', 'disconnect', {
          device_id: this._config.device_id || '',
          entity_id: this._config.entity || '',
        });
      }
      this._setConnectionStatus(false);
    });

    // Sliders with user interaction tracking
    ['r', 'g', 'b', 'w', 'uv', 'v'].forEach((ch) => {
      const sl = root.getElementById(`sl-${ch}`);
      const txt = root.getElementById(`txt-${ch}`);
      if (sl && txt) {
        const onSliderStart = () => {
          this._isUserInteractingSliders = true;
          this._lastUserSliderInteractionTime = Date.now();
          if (this._sliderInteractionTimer) {
            clearTimeout(this._sliderInteractionTimer);
            this._sliderInteractionTimer = null;
          }
        };

        const onSliderEnd = () => {
          this._lastUserSliderInteractionTime = Date.now();
          if (this._sliderInteractionTimer) clearTimeout(this._sliderInteractionTimer);
          this._sliderInteractionTimer = setTimeout(() => {
            this._isUserInteractingSliders = false;
            this._sliderInteractionTimer = null;
          }, 1500);
        };

        sl.addEventListener('pointerdown', onSliderStart);
        sl.addEventListener('mousedown', onSliderStart);
        sl.addEventListener('touchstart', onSliderStart, { passive: true });
        sl.addEventListener('focus', onSliderStart);

        sl.addEventListener('pointerup', onSliderEnd);
        sl.addEventListener('mouseup', onSliderEnd);
        sl.addEventListener('touchend', onSliderEnd);
        sl.addEventListener('blur', onSliderEnd);

        sl.addEventListener('input', () => {
          onSliderStart();
          txt.textContent = `${sl.value}%`;
          this._updateGauge();
        });
        sl.addEventListener('change', () => {
          onSliderEnd();
          this._sendLiveSpectrum();
          this._setConnectionStatus(true);
        });
      }
    });

    // Presets
    root.querySelectorAll('.preset-btn[data-p]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pName = btn.dataset.p;
        this._applyPreset(pName);
        this._setConnectionStatus(true);
      });
    });

    // Schedule: Slots input listener
    const slotsInput = root.getElementById('sched-slots-input');
    if (slotsInput) {
      slotsInput.addEventListener('input', () => {
        this._userChangedSlots = true;
      });
    }

    // Schedule: Moonlight checkbox toggle
    const chkMoonlight = root.getElementById('sched-keep-moonlight');
    if (chkMoonlight) {
      chkMoonlight.addEventListener('change', () => {
        this._keepMoonlight = chkMoonlight.checked;
        this._updateMoonlightUI();
        const brightness = this._moonlightBrightness !== undefined ? this._moonlightBrightness : 4;
        if (this._schedulePoints.length > 0) {
          const lastPt = this._schedulePoints[this._schedulePoints.length - 1];
          if (lastPt.r === 0 && lastPt.g === 0 && lastPt.w === 0 && (lastPt.b === 0 || lastPt.b === brightness || lastPt.b === 4)) {
            lastPt.b = this._keepMoonlight ? brightness : 0;
            this._renderScheduleTable();
            this._renderCurve();
          }
        }
      });
    }

    // Schedule: Auto Distribute
    const btnAuto = root.getElementById('btn-auto-distribute');
    if (btnAuto) {
      btnAuto.addEventListener('click', () => this._autoDistributeSchedule());
    }

    // Schedule: Add Point
    root.getElementById('btn-add-pt').addEventListener('click', () => {
      this._schedulePoints.push({ time: '12:00', r: 50, g: 50, b: 50, w: 50, uv: 0, v: 0 });
      if (slotsInput) slotsInput.value = String(this._schedulePoints.length);
      this._renderScheduleTable();
      this._renderCurve();
    });

    // Schedule: Enable / Disable Toggle Button
    const btnToggleSched = root.getElementById('btn-toggle-sched');
    if (btnToggleSched) {
      btnToggleSched.addEventListener('click', () => {
        const nextState = !this._scheduleEnabled;
        this._scheduleEnabled = nextState;
        this._updateScheduleToggleUI(nextState);
        if (this._hass) {
          this._hass.callService('weekaqua', 'set_schedule_enabled', {
            device_id: this._config.device_id || '',
            entity_id: this._config.entity || '',
            enabled: nextState,
          });
        }
      });
    }

    // Schedule: Save
    root.getElementById('btn-save-sched').addEventListener('click', () => this._saveScheduleToHA());

    // Log Viewer Controls
    const logHeader = root.getElementById('log-header');
    const logBodyWrap = root.getElementById('log-body-wrap');
    const logToggleIcon = root.getElementById('log-toggle-icon');
    const btnLogClear = root.getElementById('btn-log-clear');
    const btnLogAutoScroll = root.getElementById('btn-log-autoscroll');

    if (logHeader && logBodyWrap && logToggleIcon) {
      logHeader.addEventListener('click', () => {
        const isHidden = logBodyWrap.style.display === 'none';
        logBodyWrap.style.display = isHidden ? 'block' : 'none';
        logToggleIcon.textContent = isHidden ? '▲ Collapse' : '▼ Expand';
        if (isHidden && this._logAutoScroll !== false) {
          const consoleEl = root.getElementById('log-console');
          if (consoleEl) consoleEl.scrollTop = consoleEl.scrollHeight;
        }
      });
    }

    if (btnLogClear) {
      btnLogClear.addEventListener('click', (e) => {
        e.stopPropagation();
        this._clearedLogId = this._maxLogId || 1;
        this._lastRenderedLogs = [];
        this._renderLogs([]);
      });
    }

    const btnLogCopy = root.getElementById('btn-log-copy');
    if (btnLogCopy) {
      btnLogCopy.addEventListener('click', (e) => {
        e.stopPropagation();
        const logs = this._lastRenderedLogs || [];
        if (logs.length === 0) {
          btnLogCopy.textContent = 'Empty';
          setTimeout(() => { btnLogCopy.textContent = '📋 Copy'; }, 1500);
          return;
        }
        const text = logs.map((l) => {
          const q = l.q_size !== undefined ? ` [Q: ${l.q_size}/10]` : '';
          const hex = l.hex ? ` ${l.hex}` : '';
          return `${l.ts || ''} [${l.event || 'LOG'}]${q} ${l.msg || ''}${hex}`;
        }).join('\n');

        const fallbackCopy = () => {
          const ta = document.createElement('textarea');
          ta.value = text;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          btnLogCopy.textContent = '✅ Copied!';
          setTimeout(() => { btnLogCopy.textContent = '📋 Copy'; }, 2000);
        };

        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(() => {
            btnLogCopy.textContent = '✅ Copied!';
            setTimeout(() => { btnLogCopy.textContent = '📋 Copy'; }, 2000);
          }).catch(() => fallbackCopy());
        } else {
          fallbackCopy();
        }
      });
    }

    if (btnLogAutoScroll) {
      btnLogAutoScroll.addEventListener('click', (e) => {
        e.stopPropagation();
        this._logAutoScroll = (this._logAutoScroll === undefined) ? false : !this._logAutoScroll;
        btnLogAutoScroll.textContent = this._logAutoScroll ? 'Auto-scroll: ON' : 'Auto-scroll: OFF';
        btnLogAutoScroll.style.background = this._logAutoScroll ? '#1E293B' : '#3F3F46';
        if (this._logAutoScroll) {
          const consoleEl = root.getElementById('log-console');
          if (consoleEl) consoleEl.scrollTop = consoleEl.scrollHeight;
        }
      });
    }
  }

  _updateModeUI(mode) {
    const root = this.shadowRoot;
    if (!root) return;
    const badge = root.getElementById('mode-status-badge');
    const btnLive = root.getElementById('btn-mode-live');
    const btnSched = root.getElementById('btn-mode-sched');

    if (mode === 2) {
      if (badge) {
        badge.textContent = '🟢 Schedule (Mode 2)';
        badge.className = 'mode-badge sched';
      }
      if (btnLive) btnLive.className = 'btn-mode';
      if (btnSched) btnSched.className = 'btn-mode active';
    } else {
      if (badge) {
        badge.textContent = '🔴 Live Manual (Mode 1)';
        badge.className = 'mode-badge live';
      }
      if (btnLive) btnLive.className = 'btn-mode active';
      if (btnSched) btnSched.className = 'btn-mode';
    }
  }

  _updateScheduleToggleUI(enabled) {
    const root = this.shadowRoot;
    const badge = root.getElementById('sched-state-badge');
    const btn = root.getElementById('btn-toggle-sched');
    if (badge) {
      if (enabled) {
        badge.textContent = '🟢 Running (스케줄 가동 중)';
        badge.className = 'sched-state-badge active';
      } else {
        badge.textContent = '⚪ Paused (스케줄 꺼짐 / 수동 모드)';
        badge.className = 'sched-state-badge';
      }
    }
    if (btn) {
      if (enabled) {
        btn.textContent = '⏸️ 스케줄 끄기 (수동 모드)';
        btn.className = 'btn-toggle-sched active';
      } else {
        btn.textContent = '▶️ 스케줄 켜기 (자동 실행)';
        btn.className = 'btn-toggle-sched';
      }
    }
  }

  _updateGauge() {
    const root = this.shadowRoot;
    const r = parseFloat(root.getElementById('sl-r').value) || 0;
    const g = parseFloat(root.getElementById('sl-g').value) || 0;
    const b = parseFloat(root.getElementById('sl-b').value) || 0;
    const w = parseFloat(root.getElementById('sl-w').value) || 0;
    const uv = parseFloat(root.getElementById('sl-uv').value) || 0;
    const v = parseFloat(root.getElementById('sl-v').value) || 0;

    const total = this._calculatePower(r, g, b, w, uv, v);
    root.getElementById('gauge-fill').style.width = `${total}%`;
    root.getElementById('gauge-txt').textContent = `${total.toFixed(1)}%`;
  }

  _sendLiveSpectrum() {
    this._updateModeUI(1);
    const root = this.shadowRoot;
    const r = parseFloat(root.getElementById('sl-r').value) || 0;
    const g = parseFloat(root.getElementById('sl-g').value) || 0;
    const b = parseFloat(root.getElementById('sl-b').value) || 0;
    const w = parseFloat(root.getElementById('sl-w').value) || 0;
    const uv = parseFloat(root.getElementById('sl-uv').value) || 0;
    const v = parseFloat(root.getElementById('sl-v').value) || 0;

    if (this._hass) {
      this._hass.callService('weekaqua', 'set_spectrum', {
        device_id: this._config.device_id || '',
        entity_id: this._config.entity || '',
        red: r,
        green: g,
        blue: b,
        white: w,
        uv: uv,
        violet: v,
        disable_schedule: true,
      });
    }
  }

  _getPresetSpectrum(presetName) {
    const p = CARD_PRESETS[presetName] || { r: 50, g: 90, b: 60, w: 80, uv: 40, v: 30 };
    const attr = (this._hass && this._config.entity && this._hass.states[this._config.entity]?.attributes) || {};
    const bleName = (attr.ble_name || attr.model_name || attr.device_name || '').toUpperCase();
    const is4ChRgbUv = attr.is_4ch_rgb_uv !== undefined
      ? Boolean(attr.is_4ch_rgb_uv)
      : (attr.model_code === '5746' || (!attr.has_white && attr.has_uv) || (bleName && (
          bleName.includes('M800') || bleName.includes('M600') || bleName.includes('M450') ||
          bleName.includes('S400') || bleName.includes('S600') || bleName.includes('S800') ||
          bleName.includes('T90') || bleName.includes('T60') || bleName.startsWith('M')
        )));

    if (is4ChRgbUv) {
      // 4-Channel RGB/UV (e.g. M800 Pro): Channel 4 is UV, no physical White channel
      return {
        r: p.r,
        g: p.g,
        b: p.b,
        w: 0,
        uv: p.w || p.uv || 0,
        v: 0
      };
    }
    return {
      r: p.r,
      g: p.g,
      b: p.b,
      w: p.w,
      uv: p.uv || 0,
      v: p.v || 0
    };
  }

  _applyPreset(presetName) {
    this._updateModeUI(1);
    const spec = this._getPresetSpectrum(presetName);
    this._setSliderValues(spec.r, spec.g, spec.b, spec.w, spec.uv, spec.v, true);
    if (this._hass) {
      this._hass.callService('weekaqua', 'apply_preset', {
        device_id: this._config.device_id || '',
        entity_id: this._config.entity || '',
        preset: presetName,
      });
    }
  }

  _setSliderValues(r, g, b, w, uv = 0, v = 0, force = false) {
    const root = this.shadowRoot;
    if (!root) return;

    if (!force) {
      const isInteracting = this._isUserInteractingSliders || (Date.now() - (this._lastUserSliderInteractionTime || 0) < 1500);
      const activeEl = root.activeElement;
      const isActiveSlider = activeEl && activeEl.id && activeEl.id.startsWith('sl-');
      if (isInteracting || isActiveSlider) {
        return; // Preserve user's active drag/edit on sliders
      }
    }

    const channels = { r, g, b, w, uv, v };
    for (const [ch, val] of Object.entries(channels)) {
      const sl = root.getElementById(`sl-${ch}`);
      const txt = root.getElementById(`txt-${ch}`);
      if (sl && txt) {
        sl.value = val;
        txt.textContent = `${Math.round(val)}%`;
      }
    }
    this._updateGauge();
  }

  _autoDistributeSchedule() {
    const root = this.shadowRoot;
    const startInput = root.getElementById('sched-start-time');
    const endInput = root.getElementById('sched-end-time');
    const slotsInput = root.getElementById('sched-slots-input');
    const presetSelect = root.getElementById('sched-preset-select');
    const chkMoonlight = root.getElementById('sched-keep-moonlight');

    const startStr = (startInput ? startInput.value : '18:00').trim() || '18:00';
    const endStr = (endInput ? endInput.value : '02:00').trim() || '02:00';
    const totalSlots = slotsInput ? Math.max(3, parseInt(slotsInput.value, 10) || 20) : 20;
    const presetName = presetSelect ? presetSelect.value : 'GreenGrass';
    const baseSpec = this._getPresetSpectrum(presetName);
    const keepMoonlight = chkMoonlight ? chkMoonlight.checked : this._keepMoonlight;
    this._keepMoonlight = keepMoonlight;

    const parseMin = (s) => {
      if (!s) return 0;
      if (s === '24:00' || s === '24:0') return 1440;
      const parts = s.split(':').map(Number);
      return (parts[0] || 0) * 60 + (parts[1] || 0);
    };

    const formatMin = (m) => {
      if (m === 1440) return '24:00';
      const norm = ((m % 1440) + 1440) % 1440;
      const h = Math.floor(norm / 60);
      const min = Math.round(norm % 60);
      return `${String(h).padStart(2, '0')}:${String(min).padStart(2, '0')}`;
    };

    const startMin = parseMin(startStr);
    const endMin = parseMin(endStr);
    const newPoints = [];
    const daySlots = totalSlots - 1; // Number of daylight steps (leaving 1 for sunset/night)

    if (endMin <= startMin) {
      // Crosses midnight (e.g. 18:00 to 02:00)
      const day1Min = 1440 - startMin; // 18:00 ~ 24:00 (360m)
      const day2Min = endMin;          // 00:00 ~ 02:00 (120m)
      const totalDayMin = day1Min + day2Min; // 480m

      let slotsDay1 = Math.max(1, Math.min(daySlots - 1, Math.round(daySlots * (day1Min / totalDayMin))));
      let slotsDay2 = daySlots - slotsDay1;

      const stepDay1 = day1Min / slotsDay1;
      const stepDay2 = day2Min / slotsDay2;

      let slotIdx = 0;

      // Day 1 Slots (Pre-midnight: 18:00 up to before 24:00)
      for (let i = 0; i < slotsDay1; i++) {
        const t = startMin + i * stepDay1;
        // Pure mathematical sinusoidal natural bell curve: sin(((i+1)/(daySlots+1)) * PI)
        const factor = Math.sin(((slotIdx + 1) / (daySlots + 1)) * Math.PI);
        slotIdx++;
        newPoints.push({
          time: formatMin(t),
          r: Math.round(baseSpec.r * factor),
          g: Math.round(baseSpec.g * factor),
          b: Math.round(baseSpec.b * factor),
          w: Math.round(baseSpec.w * factor),
          uv: Math.round((baseSpec.uv || 0) * factor),
          v: Math.round((baseSpec.v || 0) * factor),
        });
      }

      // Day 2 Slots (Post-midnight: 00:00 up to before sunset)
      for (let i = 0; i < slotsDay2; i++) {
        const t = i * stepDay2;
        const factor = Math.sin(((slotIdx + 1) / (daySlots + 1)) * Math.PI);
        slotIdx++;
        newPoints.push({
          time: formatMin(t),
          r: Math.round(baseSpec.r * factor),
          g: Math.round(baseSpec.g * factor),
          b: Math.round(baseSpec.b * factor),
          w: Math.round(baseSpec.w * factor),
          uv: Math.round((baseSpec.uv || 0) * factor),
          v: Math.round((baseSpec.v || 0) * factor),
        });
      }

      // Night Slot (At sunset endMin, e.g. 02:00)
      const mlBrightness = this._moonlightBrightness !== undefined ? this._moonlightBrightness : 4;
      newPoints.push({
        time: formatMin(endMin),
        r: 0,
        g: 0,
        b: keepMoonlight ? mlBrightness : 0,
        w: 0,
        uv: 0,
        v: 0,
      });
    } else {
      // Same-day (e.g. 08:00 to 20:00)
      const totalDayMin = endMin - startMin;
      const step = totalDayMin / daySlots;

      for (let i = 0; i < daySlots; i++) {
        const t = startMin + i * step;
        const factor = Math.sin(((i + 1) / (daySlots + 1)) * Math.PI);
        newPoints.push({
          time: formatMin(t),
          r: Math.round(baseSpec.r * factor),
          g: Math.round(baseSpec.g * factor),
          b: Math.round(baseSpec.b * factor),
          w: Math.round(baseSpec.w * factor),
          uv: Math.round((baseSpec.uv || 0) * factor),
          v: Math.round((baseSpec.v || 0) * factor),
        });
      }

      // Night Slot (At sunset endMin)
      const mlBrightness = this._moonlightBrightness !== undefined ? this._moonlightBrightness : 4;
      newPoints.push({
        time: formatMin(endMin),
        r: 0,
        g: 0,
        b: keepMoonlight ? mlBrightness : 0,
        w: 0,
        uv: 0,
        v: 0,
      });
    }

    this._schedulePoints = newPoints;
    this._renderScheduleTable();
    this._renderCurve();
  }

  _renderScheduleTable() {
    const root = this.shadowRoot;
    const tbody = root.getElementById('sched-tbody');
    if (!tbody) return;

    // Check if user is actively typing in a table input to restore focus
    const activeEl = root.activeElement;
    let focusedInfo = null;
    if (activeEl && tbody.contains(activeEl)) {
      focusedInfo = {
        rowIdx: activeEl.dataset.row ? parseInt(activeEl.dataset.row, 10) : null,
        k: activeEl.dataset.k,
        selectionStart: activeEl.selectionStart,
        selectionEnd: activeEl.selectionEnd,
      };
    }

    tbody.innerHTML = '';

    const attr = this._modelInfo || {};
    const is4ChRgbUv = this._config.is_4ch_rgb_uv !== undefined
      ? Boolean(this._config.is_4ch_rgb_uv)
      : (attr.is_4ch_rgb_uv || (attr.device_name && (
          attr.device_name.toUpperCase().includes('M800') ||
          attr.device_name.toUpperCase().includes('M600') ||
          attr.device_name.toUpperCase().includes('M-PRO') ||
          attr.device_name.toUpperCase().includes('M PRO') ||
          attr.device_name.toUpperCase().includes('S-PRO') ||
          attr.device_name.toUpperCase().includes('S400') ||
          attr.device_name.toUpperCase().includes('S600') ||
          attr.device_name.toUpperCase().includes('S800') ||
          attr.device_name.toUpperCase().includes('T90') ||
          attr.device_name.toUpperCase().includes('P600') ||
          attr.device_name.toUpperCase().includes('P800') ||
          attr.device_name.toUpperCase().includes('P900') ||
          attr.device_name.toUpperCase().includes('P1200') ||
          attr.device_name.toUpperCase().includes('Z400') ||
          attr.device_name.toUpperCase().includes('Z600')
        )));
    const hasWhite = attr.has_white !== undefined ? attr.has_white : !is4ChRgbUv;
    const hasUv = attr.has_uv !== undefined ? Boolean(attr.has_uv) : (is4ChRgbUv || false);
    const has6ch = attr.has_6ch !== undefined ? Boolean(attr.has_6ch) : false;

    // Dynamically update Table Header labels & column visibility
    const thUv = root.getElementById('th-uv');
    const thW = root.getElementById('th-w');
    const thV = root.getElementById('th-v');
    if (thUv) thUv.style.display = hasUv ? '' : 'none';
    if (thW) thW.style.display = hasWhite ? '' : 'none';
    if (thV) thV.style.display = has6ch ? '' : 'none';

    this._schedulePoints.forEach((pt, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><input type="text" value="${pt.time}" data-k="time" data-row="${idx}" style="width:48px;"></td>
        <td><input type="number" min="0" max="100" value="${pt.r}" data-k="r" data-row="${idx}"></td>
        <td><input type="number" min="0" max="100" value="${pt.g}" data-k="g" data-row="${idx}"></td>
        <td><input type="number" min="0" max="100" value="${pt.b}" data-k="b" data-row="${idx}"></td>
        <td style="${hasUv ? '' : 'display:none;'}"><input type="number" min="0" max="100" value="${pt.uv || 0}" data-k="uv" data-row="${idx}"></td>
        <td style="${hasWhite ? '' : 'display:none;'}"><input type="number" min="0" max="100" value="${pt.w || 0}" data-k="w" data-row="${idx}"></td>
        <td style="${has6ch ? '' : 'display:none;'}"><input type="number" min="0" max="100" value="${pt.v || 0}" data-k="v" data-row="${idx}"></td>
        <td><button class="btn-sm" data-del="${idx}">✕</button></td>
      `;

      tr.querySelectorAll('input').forEach((input) => {
        const updateVal = (e) => {
          const k = e.target.dataset.k;
          pt[k] = k === 'time' ? e.target.value : (parseFloat(e.target.value) || 0);
          this._renderCurve();
        };
        input.addEventListener('input', updateVal);
        input.addEventListener('change', updateVal);
      });

      tr.querySelector('button[data-del]').addEventListener('click', () => {
        this._schedulePoints.splice(idx, 1);
        const slotsInput = root.getElementById('sched-slots-input');
        if (slotsInput) slotsInput.value = String(this._schedulePoints.length);
        this._renderScheduleTable();
        this._renderCurve();
      });

      tbody.appendChild(tr);
    });

    if (focusedInfo && focusedInfo.rowIdx !== null) {
      const targetInput = tbody.querySelector(`input[data-row="${focusedInfo.rowIdx}"][data-k="${focusedInfo.k}"]`);
      if (targetInput) {
        targetInput.focus();
        if (focusedInfo.selectionStart !== null && focusedInfo.selectionEnd !== null && targetInput.setSelectionRange) {
          try {
            targetInput.setSelectionRange(focusedInfo.selectionStart, focusedInfo.selectionEnd);
          } catch (e) {}
        }
      }
    }
  }

  _getSchedulePowerAtMinute(minute) {
    if (!this._schedulePoints || this._schedulePoints.length === 0) return 0;
    if (this._schedulePoints.length === 1) {
      const pt = this._schedulePoints[0];
      return this._calculatePower(pt.r, pt.g, pt.b, pt.w, pt.uv, pt.v);
    }

    const parseMin = (s) => {
      if (!s) return 0;
      if (s === '24:00' || s === '24:0') return 1440;
      const parts = s.split(':').map(Number);
      return (parts[0] || 0) * 60 + (parts[1] || 0);
    };

    const pts = this._schedulePoints;
    const startMin = parseMin(pts[0].time);
    const endMin = parseMin(pts[pts.length - 1].time);
    const endPower = this._calculatePower(
      pts[pts.length - 1].r, pts[pts.length - 1].g, pts[pts.length - 1].b,
      pts[pts.length - 1].w, pts[pts.length - 1].uv, pts[pts.length - 1].v
    );

    // Check if current minute is in the Night / Off hold interval (from endMin until startMin)
    let inHoldInterval = false;
    if (endMin <= startMin) {
      // Crosses midnight (e.g. 18:00 to 02:00). Active: >=18:00 or <02:00. Hold: 02:00 <= min < 18:00
      if (minute >= endMin && minute < startMin) {
        inHoldInterval = true;
      }
    } else {
      // Same-day (e.g. 08:00 to 20:00). Active: 08:00 <= min < 20:00. Hold: <08:00 or >=20:00
      if (minute < startMin || minute >= endMin) {
        inHoldInterval = true;
      }
    }

    if (inHoldInterval) {
      return endPower;
    }

    // Inside active schedule interval -> Lerp along elapsed timeline from startMin
    const timeline = pts.map((pt) => {
      const m = parseMin(pt.time);
      const elapsed = (m >= startMin) ? (m - startMin) : (1440 - startMin + m);
      const p = this._calculatePower(pt.r, pt.g, pt.b, pt.w, pt.uv, pt.v);
      return { elapsed, power: p };
    }).sort((a, b) => a.elapsed - b.elapsed);

    const elapsedNow = (minute >= startMin) ? (minute - startMin) : (1440 - startMin + minute);

    for (let i = 0; i < timeline.length - 1; i++) {
      if (timeline[i].elapsed <= elapsedNow && elapsedNow <= timeline[i + 1].elapsed) {
        const t1 = timeline[i].elapsed;
        const t2 = timeline[i + 1].elapsed;
        const ratio = (t2 > t1) ? (elapsedNow - t1) / (t2 - t1) : 0;
        return timeline[i].power + (timeline[i + 1].power - timeline[i].power) * ratio;
      }
    }

    return endPower;
  }

  _renderCurve() {
    const path = this.shadowRoot.getElementById('curve-path');
    if (!path || !this._schedulePoints || this._schedulePoints.length === 0) return;

    let d = 'M 0 100 ';
    const numSamples = 240;
    for (let x = 0; x <= numSamples; x++) {
      const min = (x / numSamples) * 1440;
      const power = this._getSchedulePowerAtMinute(min);
      const y = 100 - power;
      d += `L ${x} ${y.toFixed(1)} `;
    }

    d += 'L 240 100 Z';
    path.setAttribute('d', d);
  }

  _saveScheduleToHA() {
    const root = this.shadowRoot;
    const startInput = root.getElementById('sched-start-time');
    const endInput = root.getElementById('sched-end-time');
    const slotsInput = root.getElementById('sched-slots-input');
    const presetSelect = root.getElementById('sched-preset-select');
    const chkMoonlight = root.getElementById('sched-keep-moonlight');

    const startStr = (startInput ? startInput.value : '18:00').trim() || '18:00';
    const endStr = (endInput ? endInput.value : '02:00').trim() || '02:00';
    const totalSlots = slotsInput ? Math.max(3, parseInt(slotsInput.value, 10) || 20) : 20;
    const presetName = presetSelect ? presetSelect.value : 'GreenGrass';
    const keepMoonlight = chkMoonlight ? chkMoonlight.checked : this._keepMoonlight;

    const schedMeta = {
      points: this._schedulePoints,
      start_time: startStr,
      end_time: endStr,
      slots: totalSlots,
      preset: presetName,
      keep_moonlight: keepMoonlight,
      moonlight_brightness: this._moonlightBrightness !== undefined ? this._moonlightBrightness : 4,
    };
    this._scheduleMeta = schedMeta;

    // Cache locally for instant UI reload
    const key = 'weekaqua_sched_' + (this._config?.entity || 'default');
    try {
      localStorage.setItem(key, JSON.stringify(schedMeta));
    } catch (e) {}

    if (this._hass) {
      this._scheduleEnabled = true;
      this._updateScheduleToggleUI(true);
      this._hass.callService('weekaqua', 'set_schedule', {
        device_id: this._config.device_id || '',
        entity_id: this._config.entity || '',
        points: this._schedulePoints,
        start_time: startStr,
        end_time: endStr,
        slots: totalSlots,
        preset: presetName,
        keep_moonlight: keepMoonlight,
      });
      alert('✅ WeekAqua Natural Schedule saved and synced to Home Assistant!');
    }
  }

  _setConnectionStatus(isConnected) {
    const root = this.shadowRoot;
    if (!root) return;
    const dot = root.getElementById('conn-dot');
    const txt = root.getElementById('conn-status-txt');
    if (dot && txt) {
      const targetClass = isConnected ? 'conn-dot online' : 'conn-dot';
      const targetText = isConnected ? 'Connected (Auto-off in 60s)' : 'Disconnected (Standby)';
      if (dot.className !== targetClass) dot.className = targetClass;
      if (txt.textContent !== targetText) txt.textContent = targetText;
    }
  }

  _applyModelLayout(attr) {
    if (!attr) return;
    this._modelInfo = attr;
    const root = this.shadowRoot;
    if (!root) return;

    const bleName = (attr.ble_name || attr.device_name || attr.model_name || '').trim();
    const is4ChRgbUv = this._config.is_4ch_rgb_uv !== undefined
      ? Boolean(this._config.is_4ch_rgb_uv)
      : (attr.is_4ch_rgb_uv || (bleName && (
          bleName.toUpperCase().includes('M800') ||
          bleName.toUpperCase().includes('M600') ||
          bleName.toUpperCase().includes('M-PRO') ||
          bleName.toUpperCase().includes('M PRO') ||
          bleName.toUpperCase().includes('MPRO') ||
          bleName.toUpperCase().includes('S-PRO') ||
          bleName.toUpperCase().includes('SPRO') ||
          bleName.toUpperCase().includes('S400') ||
          bleName.toUpperCase().includes('S600') ||
          bleName.toUpperCase().includes('S800') ||
          bleName.toUpperCase().includes('T90') ||
          bleName.toUpperCase().includes('P600') ||
          bleName.toUpperCase().includes('P800') ||
          bleName.toUpperCase().includes('P900') ||
          bleName.toUpperCase().includes('P1200') ||
          bleName.toUpperCase().includes('Z400') ||
          bleName.toUpperCase().includes('Z600')
        )));
    const hasWhite = attr.has_white !== undefined ? attr.has_white : !is4ChRgbUv;
    const hasUv = attr.has_uv !== undefined ? Boolean(attr.has_uv) : (is4ChRgbUv || false);
    const has6ch = attr.has_6ch !== undefined ? Boolean(attr.has_6ch) : false;

    // Check layout signature to avoid unnecessary DOM mutations
    const layoutKey = `${bleName}_${attr.model_code || ''}_${attr.mac || ''}_${this._config.title || ''}_${is4ChRgbUv}_${hasWhite}_${hasUv}_${has6ch}`;
    if (this._lastLayoutKey === layoutKey) {
      return;
    }
    this._lastLayoutKey = layoutKey;

    // Dynamic Title & Hardware Tag
    const titleEl = root.getElementById('card-title-text');
    const stateObj = (this._hass && this._config.entity) ? this._hass.states[this._config.entity] : null;
    const friendlyName = (stateObj && stateObj.attributes && stateObj.attributes.friendly_name) || '';
    const customTitle = this._config.title;
    const modelCode = (attr.model_code || '').trim();
    const mac = (attr.mac || (this._config && this._config.mac) || '').trim();

    // Strip redundant "Aquarium Light" or "Light" from parenthetical friendly tag
    let cleanFriendly = (friendlyName || '')
      .replace(/\s*Aquarium\s*Light/ig, '')
      .replace(/\s*Light/ig, '')
      .trim();
    if (!cleanFriendly) cleanFriendly = friendlyName;

    const baseTitle = customTitle || 'WeekAqua Aquarium Light';
    let titleStr = baseTitle;
    if (cleanFriendly && !baseTitle.toUpperCase().includes(cleanFriendly.toUpperCase())) {
      titleStr = `${baseTitle} (${cleanFriendly})`;
    }
    if (titleEl && titleEl.textContent !== titleStr) {
      titleEl.textContent = titleStr;
    }

    // Hardware Info Tag in Connection Bar: 🏷️ [Model / Name] • 📶 [MAC]
    const devTag = root.getElementById('conn-device-tag');
    if (devTag) {
      let modelDisplay = bleName;
      if (!modelDisplay || modelDisplay === 'WeekAqua Light' || modelDisplay === 'WeekAqua') {
        if (modelCode) {
          modelDisplay = `Model ${modelCode}`;
        } else if (is4ChRgbUv) {
          modelDisplay = '4CH-Pro (RGB/UV)';
        } else {
          modelDisplay = 'WeekAqua 4CH';
        }
      }
      let tagText = `🏷️ ${modelDisplay}`;
      if (mac) {
        tagText += ` • 📶 ${mac}`;
      }
      if (devTag.textContent !== tagText) {
        devTag.textContent = tagText;
      }
      devTag.style.display = 'block';
    }

    // Sliders Ordering & Labels
    const rowUv = root.getElementById('row-uv');
    const rowW = root.getElementById('row-w');
    const rowV = root.getElementById('row-v');
    const lblUv = root.getElementById('lbl-uv');
    const container = root.getElementById('sliders-container');

    if (rowUv) {
      rowUv.style.display = hasUv ? 'grid' : 'none';
      if (lblUv) {
        lblUv.textContent = is4ChRgbUv ? 'UV (Ultraviolet)' : 'UV/UVA';
        lblUv.style.color = '#C084FC';
      }
    }
    if (rowW) {
      rowW.style.display = hasWhite ? 'grid' : 'none';
    }
    if (rowV) {
      rowV.style.display = has6ch ? 'grid' : 'none';
    }

    if (is4ChRgbUv && rowUv && rowW && container) {
      container.insertBefore(rowUv, rowW);
    }

    // Dynamically update Table Header labels & column visibility in Schedule tab
    const thUv = root.getElementById('th-uv');
    const thW = root.getElementById('th-w');
    const thV = root.getElementById('th-v');
    if (thUv) thUv.style.display = hasUv ? '' : 'none';
    if (thW) thW.style.display = hasWhite ? '' : 'none';
    if (thV) thV.style.display = has6ch ? '' : 'none';

    // Show/hide any existing table cells for UV/W/V
    root.querySelectorAll('#sched-tbody tr').forEach((tr) => {
      const inputs = tr.querySelectorAll('input');
      inputs.forEach((input) => {
        const k = input.dataset.k;
        if (k === 'uv' && input.parentElement) {
          input.parentElement.style.display = hasUv ? '' : 'none';
        }
        if (k === 'w' && input.parentElement) {
          input.parentElement.style.display = hasWhite ? '' : 'none';
        }
        if (k === 'v' && input.parentElement) {
          input.parentElement.style.display = has6ch ? '' : 'none';
        }
      });
    });

    const slotsInput = root.getElementById('sched-slots-input');
    if (slotsInput && !this._userChangedSlots && this._schedulePoints) {
      slotsInput.value = String(this._schedulePoints.length);
    }

    this._updateGauge();
  }

  _updateState() {
    if (!this._hass || !this._config.entity) return;
    const stateObj = this._hass.states[this._config.entity];
    if (stateObj) {
      const isOnline = Boolean(stateObj.attributes && stateObj.attributes.connected);
      this._setConnectionStatus(isOnline);

      if (stateObj.attributes) {
        const attr = stateObj.attributes;
        this._applyModelLayout(attr);

        // Synchronize hardware operation mode (Mode 1 Live vs Mode 2 Schedule)
        if (attr.current_mode !== undefined) {
          this._updateModeUI(attr.current_mode);
        }

        // Synchronize dynamic schedule running state
        if (attr.schedule_enabled !== undefined) {
          this._scheduleEnabled = Boolean(attr.schedule_enabled);
          this._updateScheduleToggleUI(this._scheduleEnabled);
        }

        // Synchronize moonlight retention & brightness from entity attributes
        if (attr.moonlight_brightness !== undefined) {
          this._moonlightBrightness = parseFloat(attr.moonlight_brightness) || 4;
        }
        if (attr.keep_moonlight !== undefined) {
          this._keepMoonlight = Boolean(attr.keep_moonlight);
          this._updateMoonlightUI();
        }

        // Synchronize and restore schedule points and metadata from HA entity attributes
        if (attr.schedule_points && Array.isArray(attr.schedule_points) && attr.schedule_points.length > 0) {
          if (!this._hasLoadedInitialSchedule) {
            this._schedulePoints = JSON.parse(JSON.stringify(attr.schedule_points));
            this._hasLoadedInitialSchedule = true;
            if (attr.schedule_meta) {
              this._scheduleMeta = attr.schedule_meta;
              this._applyScheduleMeta(attr.schedule_meta);
            }
            this._renderScheduleTable();
            this._renderCurve();
          }
        }

        if ('r' in attr && 'g' in attr && 'b' in attr && 'w' in attr) {
          this._setSliderValues(attr.r, attr.g, attr.b, attr.w, attr.uv || 0, attr.v || 0);
        } else if (attr.rgbw_color) {
          const [r255, g255, b255, w255] = attr.rgbw_color;
          this._setSliderValues(
            Math.round(r255 / 2.55),
            Math.round(g255 / 2.55),
            Math.round(b255 / 2.55),
            Math.round(w255 / 2.55),
            0,
            0
          );
        }

        // Update BLE Packet Monitor Logs & Queue size badge
        const root = this.shadowRoot;
        if (root) {
          const queueBadge = root.getElementById('log-queue-badge');
          if (queueBadge) {
            const qSize = attr.queue_size !== undefined ? attr.queue_size : 0;
            queueBadge.textContent = `Q: ${qSize}/10`;
            queueBadge.style.background = qSize > 5 ? '#DC2626' : (qSize > 0 ? '#0284C7' : '#3F3F46');
          }

          if (attr.ble_logs && Array.isArray(attr.ble_logs)) {
            const logs = attr.ble_logs;
            if (logs.length > 0) {
              const latestId = logs[logs.length - 1].id || 0;
              this._maxLogId = Math.max(this._maxLogId || 0, latestId);
            }
            const visibleLogs = this._clearedLogId
              ? logs.filter((l) => (l.id !== undefined ? l.id > this._clearedLogId : true))
              : logs;
            this._renderLogs(visibleLogs);
          }
        }
      }
    }
  }

  _renderLogs(logs) {
    const root = this.shadowRoot;
    if (!root) return;
    const consoleEl = root.getElementById('log-console');
    if (!consoleEl) return;

    this._lastRenderedLogs = logs || [];

    if (!logs || logs.length === 0) {
      if (this._clearedLogId) {
        consoleEl.innerHTML = '<div style="color: #64748B; padding: 4px 0;">Logs cleared. Waiting for new BLE packets...</div>';
      } else {
        consoleEl.innerHTML = '<div style="color: #64748B; padding: 4px 0;">No BLE packet activity logged yet.</div>';
      }
      return;
    }

    const latestLog = logs[logs.length - 1];
    const logHash = `${logs.length}_${latestLog?.id || ''}_${latestLog?.ts || ''}`;
    if (this._lastLogHash === logHash) {
      return;
    }
    this._lastLogHash = logHash;

    let html = '';
    logs.forEach((item) => {
      const ts = item.ts || '';
      const event = item.event || 'LOG';
      const msg = item.msg || '';
      const hex = item.hex ? `<span class="log-hex">${item.hex}</span>` : '';
      const qSize = item.q_size !== undefined ? `<span class="log-q-len">[Q: ${item.q_size}/10]</span>` : '';

      html += `
        <div class="log-line">
          <span class="log-ts">${ts}</span>
          <span class="log-tag ${event}">[${event}]</span>
          ${qSize}
          <span class="log-msg">${msg}</span>
          ${hex}
        </div>
      `;
    });

    consoleEl.innerHTML = html;

    if (this._logAutoScroll !== false) {
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }
  }

  getCardSize() {
    return 6;
  }

  static getStubConfig(hass, entities, entitiesFallback) {
    let lightEntity = 'light.aquarium_light';
    if (entities && entities.length > 0) {
      const found = entities.find((e) => e.startsWith('light.'));
      if (found) lightEntity = found;
    }
    return {
      type: 'custom:weekaqua-card',
      title: 'WeekAqua Aquarium Light',
      entity: lightEntity,
    };
  }
}

if (!customElements.get('weekaqua-card')) {
  customElements.define('weekaqua-card', WeekAquaCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'weekaqua-card')) {
  window.customCards.push({
    type: 'weekaqua-card',
    name: 'WeekAqua Aquarium Light Card',
    description: 'WPF-style Dark Spectrum Controls & Unlimited Dynamic Schedule for WeekAqua.',
    preview: true,
    documentationURL: 'https://github.com/ad960009/ha-weekaqua',
  });
}
