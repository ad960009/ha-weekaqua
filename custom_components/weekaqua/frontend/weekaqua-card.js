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
    this._schedulePoints = [
      { time: '08:00', r: 0, g: 0, b: 0, w: 0, uv: 0, v: 0 },
      { time: '09:30', r: 20, g: 30, b: 20, w: 30, uv: 10, v: 10 },
      { time: '11:30', r: 60, g: 85, b: 60, w: 75, uv: 40, v: 30 },
      { time: '14:00', r: 70, g: 100, b: 70, w: 90, uv: 50, v: 40 },
      { time: '17:00', r: 50, g: 75, b: 50, w: 70, uv: 30, v: 20 },
      { time: '19:00', r: 25, g: 30, b: 20, w: 25, uv: 10, v: 5 },
      { time: '20:30', r: 0, g: 0, b: 4, w: 0, uv: 0, v: 0 },
      { time: '23:00', r: 0, g: 0, b: 0, w: 0, uv: 0, v: 0 },
    ];
  }

  setConfig(config) {
    if (!config.entity && !config.device_id) {
      throw new Error('Please define an entity (e.g. light.aquarium_light) or device_id.');
    }
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateState();
  }

  _calculatePower(r, g, b, w, uv = 0, v = 0) {
    return Math.min(100.0, Math.round((r * 0.41 + g * 0.42 + b * 0.49 + w * 0.08 + uv * 0.08 + v * 0.08) * 10) / 10);
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
          padding: 6px 10px;
          margin-bottom: 12px;
          font-size: 11px;
        }
        .conn-badge {
          display: flex;
          align-items: center;
          gap: 5px;
          font-weight: 600;
        }
        .conn-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #71717A;
        }
        .conn-dot.online {
          background: #10B981;
          box-shadow: 0 0 6px #10B981;
        }
        .btn-conn {
          background: #3F3F46;
          color: #E4E4E7;
          border: 1px solid #52525B;
          border-radius: 4px;
          padding: 3px 8px;
          font-size: 10px;
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
      </style>

      <div class="card">
        <div class="header">
          <div class="title">
            <span>🐠</span> <span id="card-title-text">${this._config.title || 'WeekAqua Light'}</span>
          </div>
          <div class="tabs">
            <button class="tab-btn active" id="tab-live">Live</button>
            <button class="tab-btn" id="tab-sched">Unlimited Schedule</button>
          </div>
        </div>

        <div class="conn-bar">
          <div class="conn-badge">
            <div class="conn-dot online" id="conn-dot"></div>
            <span id="conn-status-txt">Auto-Connect (Active)</span>
          </div>
          <div style="display: flex; gap: 4px;">
            <button class="btn-conn" id="btn-manual-conn">⚡ Connect</button>
            <button class="btn-conn disconnect" id="btn-manual-disconn">❌ Disconnect</button>
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
              <span class="channel-label" id="lbl-uv" style="color: #C084FC">UV/UVA</span>
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

        <!-- Tab 2: Unlimited Schedule Editor -->
        <div id="panel-sched" class="sched-wrap">
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
                <input type="number" id="sched-slots-input" min="3" max="32" value="8" style="width: 100%;">
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
                  <th>Time</th><th>R%</th><th>G%</th><th>B%</th><th id="th-ch4">UV%</th><th id="th-ch5">W%</th><th id="th-ch6" style="display:none;">V%</th><th></th>
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
      </div>
    `;

    this._bindEvents();
    this._renderScheduleTable();
    this._renderCurve();
  }

  _bindEvents() {
    const root = this.shadowRoot;

    // Tabs
    const tabLive = root.getElementById('tab-live');
    const tabSched = root.getElementById('tab-sched');
    const panelLive = root.getElementById('panel-live');
    const panelSched = root.getElementById('panel-sched');

    tabLive.addEventListener('click', () => {
      tabLive.classList.add('active');
      tabSched.classList.remove('active');
      panelLive.style.display = 'block';
      panelSched.classList.remove('active');
    });

    tabSched.addEventListener('click', () => {
      tabSched.classList.add('active');
      tabLive.classList.remove('active');
      panelLive.style.display = 'none';
      panelSched.classList.add('active');
      this._renderCurve();
    });

    // Manual Connect / Disconnect buttons
    root.getElementById('btn-manual-conn').addEventListener('click', () => {
      if (this._hass) {
        this._hass.callService('weekaqua', 'connect', {
          device_id: this._config.device_id || '',
        });
      }
      this._setConnectionStatus(true);
    });

    root.getElementById('btn-manual-disconn').addEventListener('click', () => {
      if (this._hass) {
        this._hass.callService('weekaqua', 'disconnect', {
          device_id: this._config.device_id || '',
        });
      }
      this._setConnectionStatus(false);
    });

    // Sliders
    ['r', 'g', 'b', 'w', 'uv', 'v'].forEach((ch) => {
      const sl = root.getElementById(`sl-${ch}`);
      const txt = root.getElementById(`txt-${ch}`);
      if (sl && txt) {
        sl.addEventListener('input', () => {
          txt.textContent = `${sl.value}%`;
          this._updateGauge();
        });
        sl.addEventListener('change', () => {
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

    // Schedule: Auto Distribute
    const btnAuto = root.getElementById('btn-auto-distribute');
    if (btnAuto) {
      btnAuto.addEventListener('click', () => this._autoDistributeSchedule());
    }

    // Schedule: Add Point
    root.getElementById('btn-add-pt').addEventListener('click', () => {
      this._schedulePoints.push({ time: '12:00', r: 50, g: 50, b: 50, w: 50, uv: 0, v: 0 });
      const slotsInput = root.getElementById('sched-slots-input');
      if (slotsInput) slotsInput.value = String(this._schedulePoints.length);
      this._renderScheduleTable();
      this._renderCurve();
    });

    // Schedule: Save
    root.getElementById('btn-save-sched').addEventListener('click', () => this._saveScheduleToHA());
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

  _applyPreset(presetName) {
    const p = CARD_PRESETS[presetName];
    if (p) {
      this._setSliderValues(p.r, p.g, p.b, p.w, p.uv || 0, p.v || 0);
    }
    if (this._hass) {
      this._hass.callService('weekaqua', 'apply_preset', {
        device_id: this._config.device_id || '',
        preset: presetName,
      });
    }
  }

  _setSliderValues(r, g, b, w, uv = 0, v = 0) {
    const root = this.shadowRoot;
    if (!root) return;
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

    const startStr = (startInput ? startInput.value : '18:00').trim() || '18:00';
    const endStr = (endInput ? endInput.value : '02:00').trim() || '02:00';
    const totalSlots = slotsInput ? Math.max(3, parseInt(slotsInput.value, 10) || 8) : 8;
    const presetName = presetSelect ? presetSelect.value : 'GreenGrass';
    const baseSpec = CARD_PRESETS[presetName] || { r: 50, g: 90, b: 60, w: 80, uv: 40, v: 30 };

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
      newPoints.push({
        time: formatMin(endMin),
        r: 0, g: 0, b: 0, w: 0, uv: 0, v: 0,
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
      newPoints.push({
        time: formatMin(endMin),
        r: 0, g: 0, b: 0, w: 0, uv: 0, v: 0,
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
    tbody.innerHTML = '';

    const is4ChRgbUv = this._modelInfo ? this._modelInfo.is_4ch_rgb_uv : true;
    const has6ch = this._modelInfo ? this._modelInfo.has_6ch : false;

    this._schedulePoints.forEach((pt, idx) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><input type="text" value="${pt.time}" data-k="time" style="width:48px;"></td>
        <td><input type="number" min="0" max="100" value="${pt.r}" data-k="r"></td>
        <td><input type="number" min="0" max="100" value="${pt.g}" data-k="g"></td>
        <td><input type="number" min="0" max="100" value="${pt.b}" data-k="b"></td>
        <td><input type="number" min="0" max="100" value="${is4ChRgbUv ? (pt.uv || 0) : pt.w}" data-k="${is4ChRgbUv ? 'uv' : 'w'}"></td>
        <td><input type="number" min="0" max="100" value="${is4ChRgbUv ? pt.w : (pt.uv || 0)}" data-k="${is4ChRgbUv ? 'w' : 'uv'}"></td>
        <td style="${has6ch ? '' : 'display:none;'}"><input type="number" min="0" max="100" value="${pt.v || 0}" data-k="v"></td>
        <td><button class="btn-sm" data-del="${idx}">✕</button></td>
      `;

      tr.querySelectorAll('input').forEach((input) => {
        input.addEventListener('change', (e) => {
          const k = e.target.dataset.k;
          pt[k] = k === 'time' ? e.target.value : parseFloat(e.target.value) || 0;
          this._renderCurve();
        });
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
  }

  _renderCurve() {
    const path = this.shadowRoot.getElementById('curve-path');
    if (!path || this._schedulePoints.length === 0) return;

    const parseMin = (s) => {
      if (!s) return 0;
      if (s === '24:00' || s === '24:0') return 1440;
      const parts = s.split(':').map(Number);
      return (parts[0] || 0) * 60 + (parts[1] || 0);
    };

    const sorted = [...this._schedulePoints].sort((a, b) => {
      return parseMin(a.time) - parseMin(b.time);
    });

    let d = 'M 0 100 ';
    sorted.forEach((pt, i) => {
      const min = parseMin(pt.time);
      const x = (min / 1440) * 240;
      const power = this._calculatePower(pt.r, pt.g, pt.b, pt.w, pt.uv, pt.v);
      const y = 100 - power;
      if (i === 0) d += `L ${x} ${y} `;
      d += `L ${x} ${y} `;
    });

    d += 'L 240 100 Z';
    path.setAttribute('d', d);
  }

  _saveScheduleToHA() {
    if (this._hass) {
      this._hass.callService('weekaqua', 'set_schedule', {
        device_id: this._config.device_id || '',
        points: this._schedulePoints,
      });
      alert('✅ WeekAqua Natural Schedule saved and synced to Home Assistant!');
    }
  }

  _setConnectionStatus(isConnected) {
    const root = this.shadowRoot;
    const dot = root.getElementById('conn-dot');
    const txt = root.getElementById('conn-status-txt');
    if (dot && txt) {
      if (isConnected) {
        dot.className = 'conn-dot online';
        txt.textContent = 'Connected (Auto-off in 60s)';
      } else {
        dot.className = 'conn-dot';
        txt.textContent = 'Disconnected (Standby)';
      }
    }
  }

  _applyModelLayout(attr) {
    if (!attr) return;
    this._modelInfo = attr;
    const root = this.shadowRoot;
    if (!root) return;

    const is4ChRgbUv = this._config.is_4ch_rgb_uv !== undefined
      ? Boolean(this._config.is_4ch_rgb_uv)
      : (attr.is_4ch_rgb_uv || (attr.device_name && (attr.device_name.includes('M800') || attr.device_name.includes('M600') || attr.device_name.includes('M-PRO') || attr.device_name.includes('S-PRO') || attr.device_name.includes('T90'))));
    const hasUv = this._config.has_uv !== undefined ? Boolean(this._config.has_uv) : (attr.has_uv || is4ChRgbUv);
    const has6ch = this._config.has_6ch !== undefined ? Boolean(this._config.has_6ch) : attr.has_6ch;
    const maxSlots = attr.max_slots || (is4ChRgbUv ? 8 : 8);

    // Dynamic Title
    const titleEl = root.getElementById('card-title-text');
    if (titleEl && !this._config.title && attr.device_name) {
      titleEl.textContent = attr.device_name;
    }

    // Sliders Ordering & Labels
    const rowUv = root.getElementById('row-uv');
    const rowW = root.getElementById('row-w');
    const rowV = root.getElementById('row-v');
    const lblUv = root.getElementById('lbl-uv');
    const lblW = root.getElementById('lbl-w');
    const container = root.getElementById('sliders-container');

    const thCh4 = root.getElementById('th-ch4');
    const thCh5 = root.getElementById('th-ch5');
    const thCh6 = root.getElementById('th-ch6');

    if (is4ChRgbUv) {
      // 4-CH RGB/UV (e.g. M800 Pro): Place UV directly after Blue
      if (lblUv) {
        lblUv.textContent = 'UV (Ultraviolet)';
        lblUv.style.color = '#C084FC';
      }
      if (lblW) lblW.textContent = 'White (W)';
      if (rowUv && rowW && container) {
        container.insertBefore(rowUv, rowW);
      }
      if (rowV) rowV.style.display = 'none';
      if (thCh4) thCh4.textContent = 'UV%';
      if (thCh5) thCh5.textContent = 'W%';
      if (thCh6) thCh6.style.display = 'none';
    } else {
      // Standard RGBW / RGBW+UV / 6CH
      if (lblW) lblW.textContent = 'White (W)';
      if (lblUv) {
        lblUv.textContent = 'UV/UVA';
        lblUv.style.color = '#8B5CF6';
      }
      if (rowW && rowUv && container) {
        container.insertBefore(rowW, rowUv);
      }
      if (rowV) rowV.style.display = has6ch ? 'grid' : 'none';
      if (thCh4) thCh4.textContent = 'W%';
      if (thCh5) thCh5.textContent = 'UV%';
      if (thCh6) thCh6.style.display = has6ch ? '' : 'none';
    }

    const slotsInput = root.getElementById('sched-slots-input');
    if (slotsInput && !this._userChangedSlots && this._schedulePoints) {
      slotsInput.value = String(this._schedulePoints.length);
    }
  }

  _updateState() {
    if (!this._hass || !this._config.entity) return;
    const stateObj = this._hass.states[this._config.entity];
    if (stateObj) {
      const isOnline = stateObj.state === 'on' || (stateObj.attributes && stateObj.attributes.connected);
      this._setConnectionStatus(isOnline);

      if (stateObj.attributes) {
        const attr = stateObj.attributes;
        this._applyModelLayout(attr);

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
      }
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

customElements.define('weekaqua-card', WeekAquaCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'weekaqua-card',
  name: 'WeekAqua Aquarium Light Card',
  description: 'WPF-style Dark Spectrum Controls & Unlimited Dynamic Schedule for WeekAqua.',
  preview: true,
  documentationURL: 'https://github.com/ad960009/ha-weekaqua',
});
