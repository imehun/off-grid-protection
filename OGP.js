/* OGP.js
 * OGP V1.3.0 - Lovelace main card
 *
 * Step 2: Devices
 *
 * Device definitions are supplied by Lovelace YAML.
 * No device names/entities are hard-coded in the card.
 *
 * Example:
 *
 * type: custom:ogp-card
 * grid_status_entity: input_select.ogp_test_grid_status
 * home_dashboard_path: /dashboard
 * devices:
 *   - name: Heat Pump
 *     entity: climate.example
 *     protection_status_entity: sensor.heat_pump_protection_status
 *     locked_entity: binary_sensor.heat_pump_off_grid_protection_locked
 *     override_duration_entity: number.heat_pump_override_duration
 *     override_remaining_entity: sensor.heat_pump_override_remaining
 *     override_pin_entity: text.heat_pump_override_pin
 *   - name: Water Heater
 *     entity: switch.example
 *     protection_status_entity: sensor.water_heater_protection_status
 *     locked_entity: binary_sensor.water_heater_off_grid_protection_locked
 *     override_duration_entity: number.water_heater_override_duration
 *     override_remaining_entity: sensor.water_heater_override_remaining
 *     override_pin_entity: text.water_heater_override_pin
 *
 * The final OGP integration will generate this YAML.
 */

class OGPCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    this._config = {};
    this._hass = null;

    this._recoveryEnd = null;
    this._recoveryTimer = null;
    this._lastGridState = null;
    this._initializedGridState = false;

    this._openDeviceId = null;
    this._overrideDevice = null;
    this._overrideDuration = null;
    this._overridePin = "";
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("OGP: invalid configuration");
    }

    this._config = config;
    this._render();
  }

  set hass(hass) {
    const entityId =
      this._config.grid_status_entity ||
      "input_select.ogp_test_grid_status";

    const newState = hass?.states?.[entityId]?.state ?? null;

    const validGridState =
      this._isOnGrid(newState) || this._isOffGrid(newState);

    if (validGridState) {
      if (this._initializedGridState) {
        if (newState !== this._lastGridState) {
          this._handleGridChange(newState);
        }
      } else {
        // Initial state is only the baseline.
        // Never start recovery from initial state.
        this._initializedGridState = true;
      }

      this._lastGridState = newState;
    }

    this._hass = hass;
    this._render();
  }

  disconnectedCallback() {
    this._stopRecoveryTimer();
  }


  _deviceId(device) {
    return device.id || device.entity || device.name || "";
  }

  _toggleDeviceDetails(device) {
    const id = this._deviceId(device);
    this._openDeviceId = this._openDeviceId === id ? null : id;
    this._render();
  }

  _openOverride(device) {
    this._overrideDevice = device;
    this._overridePin = "";
    this._overrideDuration = this._defaultOverrideDuration(device);
    this._render();
  }

  _closeOverride() {
    this._overrideDevice = null;
    this._overridePin = "";
    this._overrideDuration = null;
    this._render();
  }

  _overrideLimits(device) {
    const entityId = device.override_duration_entity;
    const entity = entityId && this._hass
      ? this._hass.states[entityId]
      : null;

    const min = Number(entity?.attributes?.min ?? 1);
    const max = Number(entity?.attributes?.max ?? 60);
    const step = Number(entity?.attributes?.step ?? 1);

    return {
      min: Number.isFinite(min) ? min : 1,
      max: Number.isFinite(max) ? max : 60,
      step: Number.isFinite(step) && step > 0 ? step : 1,
    };
  }

  _defaultOverrideDuration(device) {
    const limits = this._overrideLimits(device);
    if (30 >= limits.min && 30 <= limits.max) return 30;
    return limits.min;
  }

  _setOverrideDuration(value) {
    this._overrideDuration = Number(value);

    // Update only the duration buttons; keep the dialog and PIN focus intact.
    this.shadowRoot
      ?.querySelectorAll("[data-duration]")
      .forEach(button => {
        button.classList.toggle(
          "selected",
          Number(button.dataset.duration) === this._overrideDuration
        );
      });
  }

  _setOverridePin(value) {
    // Do NOT re-render the card while typing the PIN.
    // Re-rendering destroys the input element and therefore its focus.
    this._overridePin = String(value ?? "")
      .replace(/\D/g, "")
      .slice(0, 4);
  }

  async _activateOverride(device) {
    if (!this._hass) return;

    const pin = String(this._overridePin || "");
    const duration = Number(this._overrideDuration);

    if (!/^\d{4}$/.test(pin) || !Number.isFinite(duration)) return;

    // The duration helper is an existing OGP entity.
    if (device.override_duration_entity) {
      await this._hass.callService("number", "set_value", {
        entity_id: device.override_duration_entity,
        value: duration,
      });
    }

    // Existing OGP service: OGP performs all validation and activation.
    await this._hass.callService(
      "off_grid_protection",
      "request_override",
      {
        device_id: device.name || device.entity || device.id,
        pin: pin,
      }
    );

    this._closeOverride();
  }

  _overrideActive(device) {
    if (!device.override_remaining_entity) return false;

    const state = this._state(
      device.override_remaining_entity,
      "00:00"
    );

    const value = String(state).trim();
    return value !== "" &&
      value !== "00:00" &&
      value !== "00:00:00" &&
      value !== "0";
  }

  _renderOverrideDialog() {
    const device = this._overrideDevice;
    if (!device) return "";

    const limits = this._overrideLimits(device);
    const current = Number(
      this._overrideDuration ?? limits.min
    );

    const presets = [5, 15, 30, 60]
      .filter(value => value >= limits.min && value <= limits.max)
      .map(value => `
        <button
          class="duration ${value === current ? "selected" : ""}"
          data-duration="${value}">
          ${value < 60 ? `${value} min` : "1 h"}
        </button>
      `)
      .join("");

    return `
      <div class="modal-backdrop">
        <div class="override-dialog">
          <div class="dialog-header">
            <div>
              <div class="dialog-title">Enter Override PIN</div>
              <div class="dialog-subtitle">
                Enter your override PIN to activate manual control.
              </div>
            </div>
            <button class="close-button" id="close-override">×</button>
          </div>

          <div class="pin-row">
            ${[0, 1, 2, 3].map(index => `
              <input
                class="pin-input"
                type="password"
                inputmode="numeric"
                maxlength="1"
                data-pin-index="${index}"
                value="${this._escape(this._overridePin[index] || "")}">
            `).join("")}
          </div>

          <div class="duration-title">Select override duration</div>

          <div class="duration-grid">
            ${presets || `
              <div class="duration-info">
                ${this._escape(`${limits.min}–${limits.max} min`)}
              </div>
            `}
          </div>

          <button
            class="activate-button"
            id="activate-override"
            ${/^\d{4}$/.test(this._overridePin) ? "" : "disabled"}>
            ▶ Activate Override
          </button>

          <button class="cancel-button" id="cancel-override">
            Cancel
          </button>
        </div>
      </div>
    `;
  }

  _attachDeviceHandlers() {
    this.shadowRoot
      .querySelectorAll(".device-row")
      .forEach(row => {
        row.addEventListener("click", event => {
          if (event.target.closest("button")) return;

          const id = row.dataset.deviceId;
          const device = (this._config.devices || []).find(
            item => this._deviceId(item) === id
          );

          if (device) this._toggleDeviceDetails(device);
        });
      });

    this.shadowRoot
      .querySelectorAll('[data-action="activate"]')
      .forEach(button => {
        button.addEventListener("click", async event => {
          event.stopPropagation();

          const id = button.dataset.deviceId;
          const device = (this._config.devices || []).find(
            item => this._deviceId(item) === id
          );

          if (device) this._openOverride(device);
        });
      });
  }

  async _openHADeviceSettings(device) {
    if (!this._hass || !device) return;

    // Resolve the OGP device Config Entry from one of OGP's own helper
    // entities. The main protected entity (e.g. switch.s32_32) is not
    // itself an OGP entity.
    const candidates = [
      device.protection_status_entity,
      device.locked_entity,
      device.override_remaining_entity,
      device.override_duration_entity,
      device.override_pin_entity,
    ].filter(Boolean);

    let configEntryId = null;

    for (const entityId of candidates) {
      try {
        const registryEntry = await this._hass.callWS({
          type: "config/entity_registry/get",
          entity_id: entityId,
        });
        if (registryEntry?.config_entry_id) {
          configEntryId = registryEntry.config_entry_id;
          break;
        }
      } catch (err) {
        // Try the next OGP helper entity.
      }
    }

    if (!configEntryId) {
      console.warn("OGP: no OGP config entry found", candidates);
      return;
    }

    const token = this._hass.auth?.data?.access_token;
    if (!token) {
      console.warn("OGP: Home Assistant access token unavailable");
      return;
    }

    try {
      const response = await fetch(
        "/api/config/config_entries/options/flow",
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            handler: configEntryId,
            show_advanced_options: true,
          }),
        },
      );

      if (!response.ok) {
        const text = await response.text();
        console.error(
          "OGP: unable to start Options Flow",
          response.status,
          text,
        );
        return;
      }

      const flow = await response.json();
      if (!flow?.flow_id) {
        console.error("OGP: Options Flow returned no flow_id", flow);
        return;
      }

      this._showOptionsFlowDialog(flow);
    } catch (err) {
      console.error("OGP: unable to start Options Flow", err);
    }
  }

  _showOptionsFlowDialog(flow, dialogTitle = null) {
    this._closeOptionsFlowDialog();

    const overlay = document.createElement("div");
    overlay.className = "ogp-options-overlay";
    overlay.innerHTML = `
      <div class="ogp-options-dialog" role="dialog" aria-modal="true">
        <div class="ogp-options-header">
          <div class="ogp-options-title">${this._escape(dialogTitle || ((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr") ? "Postavke uređaja" : "Device settings"))}</div>
          <button class="ogp-options-close" type="button" aria-label="Zatvori">×</button>
        </div>
        <div class="ogp-options-body"></div>
        <div class="ogp-options-actions">
          <button class="ogp-options-cancel" type="button">Odustani</button>
          <button class="ogp-options-submit" type="button">Podnijeti</button>
        </div>
      </div>
    `;

    const style = document.createElement("style");
    style.textContent = `
      .ogp-options-overlay {
        position: fixed;
        inset: 0;
        z-index: 100000;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0,0,0,.32);
      }
      .ogp-options-dialog {
        width: min(560px, calc(100vw - 32px));
        max-height: min(760px, calc(100vh - 32px));
        overflow: hidden;
        border-radius: 12px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #111);
        box-shadow: 0 12px 40px rgba(0,0,0,.35);
        font-family: var(--paper-font-body1_-_font-family, sans-serif);
      }
      .ogp-options-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 24px 12px;
      }
      .ogp-options-title {
        font-size: 20px;
        font-weight: 500;
      }
      .ogp-options-close {
        border: 0;
        background: transparent;
        color: var(--secondary-text-color, #666);
        font-size: 28px;
        cursor: pointer;
      }
      .ogp-options-body {
        overflow: auto;
        max-height: calc(100vh - 180px);
        padding: 8px 24px 20px;
      }
      .ogp-option-field {
        margin: 14px 0;
      }
      .ogp-option-label {
        display: block;
        margin-bottom: 7px;
        font-size: 14px;
        color: var(--secondary-text-color, #666);
      }
      .ogp-option-select, .ogp-option-input {
        box-sizing: border-box;
        width: 100%;
        min-height: 42px;
        padding: 9px 10px;
        border: 1px solid var(--divider-color, #bbb);
        border-radius: 6px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #111);
        font: inherit;
      }
      .ogp-option-radio {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 0;
      }
      .ogp-multi-select {
        display: flex;
        flex-direction: column;
        gap: 6px;
        max-height: 220px;
        overflow-y: auto;
        padding: 8px;
        border: 1px solid var(--divider-color, #bbb);
        border-radius: 6px;
        background: var(--card-background-color, #fff);
      }
      .ogp-multi-option {
        display: flex;
        align-items: center;
        gap: 10px;
        min-height: 36px;
        padding: 4px 6px;
        cursor: pointer;
        color: var(--primary-text-color, #111);
      }
      .ogp-multi-option input {
        width: 18px;
        height: 18px;
        flex: 0 0 auto;
      }
      .ogp-options-actions {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        padding: 12px 20px 16px;
        border-top: 1px solid var(--divider-color, #ddd);
      }
      .ogp-options-actions button {
        min-height: 40px;
        padding: 0 18px;
        border: 0;
        border-radius: 6px;
        background: transparent;
        color: var(--primary-color, #03a9f4);
        font: inherit;
        font-weight: 500;
        cursor: pointer;
      }
      .ogp-options-submit {
        background: var(--primary-color, #03a9f4) !important;
        color: var(--text-primary-color, #fff) !important;
      }
      .ogp-options-error {
        margin: 8px 0 12px;
        color: var(--error-color, #db4437);
        white-space: pre-wrap;
      }
    `;
    document.head.appendChild(style);

    document.body.appendChild(overlay);
    this._ogpOptionsOverlay = overlay;
    this._ogpOptionsStyle = style;

    overlay.querySelector(".ogp-options-close").addEventListener(
      "click",
      () => this._closeOptionsFlowDialog(),
    );
    overlay.querySelector(".ogp-options-cancel").addEventListener(
      "click",
      () => this._abortOptionsFlow(flow.flow_id),
    );
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) this._closeOptionsFlowDialog();
    });

    this._renderOptionsFlowStep(flow);
  }

  _renderOptionsFlowStep(flow) {
    const body = this._ogpOptionsOverlay?.querySelector(".ogp-options-body");
    if (!body) return;

    body.innerHTML = "";
    const schema = Array.isArray(flow?.data_schema)
      ? flow.data_schema
      : [];

    const values = {};

    for (const field of schema) {
      const name = field.name;
      if (!name) continue;

      const wrapper = document.createElement("div");
      wrapper.className = "ogp-option-field";

      const lang = (
        this._hass?.locale?.language ||
        this._hass?.language ||
        "en"
      ).toLowerCase();
      const hr = lang.startsWith("hr");

      const labels = hr
        ? {
            name: "Naziv uređaja",
            entity_id: "Entitet uređaja",
            off_state: "OFF stanje",
            control_entity_id: "Kontrolni entitet",
            recovery_action: "Radnja oporavka",
            lovelace_language: "Jezik Lovelace YAML-a",
            generate_lovelace_yaml: "Generiraj Lovelace YAML",
            action: "Radnja",
            show_all_automations: "Prikaži sve automatizacije",
            wait_for_unavailable: "Čekaj ako je nedostupno",
            recovery_timeout: "Timeout oporavak",
            command_timeout: "Timeout naredbe",
            override_enabled: "Omogući Override",
            require_pin: "Zahtijevaj PIN",
            minimum_runtime: "Minimalno trajanje",
            maximum_runtime: "Maksimalno trajanje",
            automations: "Automatizacije",
            inverter_off_grid_status: "Status off-grid invertera",
            power_meter_status: "Status mjerača snage",
            recovery_delay: "Odgoda oporavka",
            central_pin: "Centralni PIN",
            pin_check: "Provjera PIN-a",
            recovery_enabled: "Automatski oporavak",
            logs: "Logovi",
            notifications_enabled: "Omogući obavijesti",
            shutdown_action: "Akcija gašenja",
            target_type: "Vrsta cilja",
            target: "Uređaj / primatelj",
            events: "Događaji",
            notification_mode: "Način obavijesti",
            notification_language: "Jezik obavijesti",
            notification_selection: "Obavijest",
            notification_action: "Radnja",
            confirm_delete: "Obriši ovu obavijest",
            notify_targets: "Primatelji obavijesti",
            browser_mod_targets: "Browser Mod uređaji",
            send_notification: "Pošalji obavijest",
            send_popup: "Prikaži Browser Mod popup",
            notify_grid_status: "Obavijesti o statusu mreže",
            notify_protection_status: "Obavijesti o zaštiti i Override statusu",
            notify_security: "Obavijesti o sigurnosnim događajima",
            section: "Konfiguracija",
          }
        : {
            name: "Device name",
            entity_id: "Device entity",
            off_state: "OFF state",
            wait_for_unavailable: "Wait if unavailable",
            recovery_timeout: "Recovery timeout",
            command_timeout: "Command timeout",
            override_enabled: "Enable Override",
            require_pin: "Require PIN",
            minimum_runtime: "Minimum duration",
            maximum_runtime: "Maximum duration",
            automations: "Automations",
            control_entity_id: "Control entity",
            recovery_action: "Recovery action",
            lovelace_language: "Lovelace YAML language",
            generate_lovelace_yaml: "Generate Lovelace YAML",
            action: "Action",
            show_all_automations: "Show all automations",
            wait_for_unavailable: "Wait if unavailable",
            override_enabled: "Enable Override",
            require_pin: "Require PIN",
            inverter_off_grid_status: "Inverter Off-grid Status",
            power_meter_status: "Power Meter Status",
            recovery_delay: "Recovery delay",
            central_pin: "Central PIN",
            pin_check: "PIN check",
            recovery_enabled: "Recovery enabled",
            logs: "Logs",
            notifications_enabled: "Enable notifications",
            shutdown_action: "Shutdown action",
            target_type: "Target type",
            target: "Device / recipient",
            events: "Events",
            notification_mode: "Notification mode",
            notification_language: "Notification language",
            notification_selection: "Notification",
            notification_action: "Action",
            confirm_delete: "Delete this notification",
            notify_targets: "Notification recipients",
            browser_mod_targets: "Browser Mod devices",
            send_notification: "Send notification",
            send_popup: "Show Browser Mod popup",
            notify_grid_status: "Notify grid status",
            notify_protection_status: "Notify protection and Override status",
            notify_security: "Notify security events",
            section: "Configuration",
          };

      const normalizedName = String(name).trim().toLowerCase();
      const normalizedDescription = String(
        field.description ?? ""
      ).trim().toLowerCase();

      // The REST flow may return the internal field key as either
      // `name` or `description`. Never expose those raw OGP keys when
      // we have a known localized label.
      const labelText =
        labels[normalizedName] ||
        labels[normalizedDescription] ||
        labels[name] ||
        labels[field.description] ||
        field.description ||
        name;

      const label = document.createElement("label");
      label.className = "ogp-option-label";
      label.textContent = labelText;
      wrapper.appendChild(label);

      const selector = field.selector || {};
      let input;

      if (selector.entity) {
        // Home Assistant's REST Options Flow exposes entity selectors as
        // `selector.entity`. Use the native HA selector component so the
        // user gets the same searchable entity list as a normal HA form.
        input = document.createElement("ha-selector");
        input.hass = this._hass;
        input.selector = { entity: selector.entity };
        input.value =
          field.value !== undefined
            ? field.value
            : field.default !== undefined
              ? field.default
              : "";
        input.dataset.flowField = name;
        input.style.display = "block";
        input.style.width = "100%";
        wrapper.appendChild(input);
      } else if (selector.select) {
        const multiple = Boolean(selector.select.multiple);
        const options = selector.select.options || [];
        const selected = Array.isArray(field.value)
          ? field.value.map(String)
          : Array.isArray(field.default)
            ? field.default.map(String)
            : field.value !== undefined
              ? [String(field.value)]
              : field.default !== undefined
                ? [String(field.default)]
                : [];

        if (multiple) {
          // HA SelectSelector(multiple=True) is represented by a native
          // multi-select in the REST flow schema. Keep all selected values
          // and make the interaction obvious without requiring Ctrl-click.
          const multiWrap = document.createElement("div");
          multiWrap.className = "ogp-multi-select";

          for (const option of options) {
            const value =
              typeof option === "object" ? option.value : option;
            const rawValue = String(value);
            const knownOptionLabels = hr
              ? {
                  device_settings: "Postavke uređaja",
                  regenerate_lovelace_yaml: "Ponovno generiraj Lovelace YAML",
                  en: "Engleski",
                  hr: "Hrvatski",
                  turn_off: "Isključi",
                  stay_off: "Ostavi isključeno",
                  turn_on: "Uključi",
                  climate: "Klima",
                  switch: "Prekidač",
                  custom: "Prilagođeno",
                  central: "Centralna postavka",
                }
              : {
                  device_settings: "Device settings",
                  regenerate_lovelace_yaml: "Regenerate Lovelace YAML",
                  en: "English",
                  hr: "Croatian",
                  turn_off: "Turn off",
                  stay_off: "Stay off",
                  turn_on: "Turn on",
                  climate: "Climate",
                  switch: "Switch",
                  custom: "Custom",
                  central: "Central setup",
                };
            const optionLabel =
              typeof option === "object"
                ? (option.label ?? option.value)
                : option;
            const optionKey = String(optionLabel ?? rawValue)
              .trim()
              .toLowerCase();
            const text =
              knownOptionLabels[rawValue] ||
              knownOptionLabels[optionKey] ||
              optionLabel;

            const item = document.createElement("label");
            item.className = "ogp-multi-option";

            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.value = String(value);
            checkbox.checked = selected.includes(String(value));

            const caption = document.createElement("span");
            caption.textContent = text;

            item.appendChild(checkbox);
            item.appendChild(caption);
            multiWrap.appendChild(item);
          }

          input = multiWrap;
          input.dataset.flowField = name;
          input.dataset.multiple = "true";
          wrapper.appendChild(input);
        } else {
          input = document.createElement("select");
          input.className = "ogp-option-select";
          for (const option of options) {
            const value =
              typeof option === "object" ? option.value : option;
            const rawValue = String(value);
            const knownOptionLabels = hr
              ? {
                  device_settings: "Postavke uređaja",
                  regenerate_lovelace_yaml: "Ponovno generiraj Lovelace YAML",
                  en: "Engleski",
                  hr: "Hrvatski",
                  turn_off: "Isključi",
                  stay_off: "Ostavi isključeno",
                  turn_on: "Uključi",
                  climate: "Klima",
                  switch: "Prekidač",
                  custom: "Prilagođeno",
                  central: "Centralna postavka",
                }
              : {
                  device_settings: "Device settings",
                  regenerate_lovelace_yaml: "Regenerate Lovelace YAML",
                  en: "English",
                  hr: "Croatian",
                  turn_off: "Turn off",
                  stay_off: "Stay off",
                  turn_on: "Turn on",
                  climate: "Climate",
                  switch: "Switch",
                  custom: "Custom",
                  central: "Central setup",
                };
            const optionLabel =
              typeof option === "object"
                ? (option.label ?? option.value)
                : option;
            const optionKey = String(optionLabel ?? rawValue)
              .trim()
              .toLowerCase();
            const text =
              knownOptionLabels[rawValue] ||
              knownOptionLabels[optionKey] ||
              optionLabel;
            const opt = document.createElement("option");
            opt.value = String(value);
            opt.textContent = text;
            opt.selected = selected.includes(String(value));
            input.appendChild(opt);
          }
          input.dataset.flowField = name;
          wrapper.appendChild(input);
        }
      } else if (selector.number) {
        input = document.createElement("input");
        input.className = "ogp-option-input";
        input.type = "number";
        if (selector.number.min !== undefined) input.min = selector.number.min;
        if (selector.number.max !== undefined) input.max = selector.number.max;
        if (selector.number.step !== undefined) input.step = selector.number.step;
        input.value =
          field.value !== undefined
            ? field.value
            : field.default !== undefined
              ? field.default
              : "";
      } else if (selector.boolean !== undefined || field.type === "boolean") {
        const row = document.createElement("div");
        row.className = "ogp-option-radio";
        input = document.createElement("input");
        input.type = "checkbox";
        input.checked = Boolean(
          field.value !== undefined
            ? field.value
            : field.default !== undefined
              ? field.default
              : false,
        );

        // Boolean selectors need their own label because the checkbox row
        // replaces the normal field wrapper. Do not expose the raw schema key.
        const booleanLabel =
          labels[normalizedName] ||
          labels[normalizedDescription] ||
          labels[name] ||
          labels[field.description] ||
          field.description ||
          name;

        row.appendChild(input);
        row.appendChild(document.createTextNode(booleanLabel));
        wrapper.replaceChildren(row);
      } else {
        input = document.createElement("input");
        input.className = "ogp-option-input";
        input.type = "text";
        input.value =
          field.value !== undefined
            ? field.value
            : field.default !== undefined
              ? field.default
              : "";
      }

      if (!input.dataset.flowField) {
        input.dataset.flowField = name;
        wrapper.appendChild(input);
      }
      body.appendChild(wrapper);
      values[name] = input;
    }

    const errors = flow.errors || {};
    if (Object.keys(errors).length) {
      const error = document.createElement("div");
      error.className = "ogp-options-error";
      error.textContent = Object.entries(errors)
        .map(([key, value]) => `${key}: ${value}`)
        .join("\n");
      body.prepend(error);
    }

    const submit = this._ogpOptionsOverlay.querySelector(".ogp-options-submit");
    submit.onclick = () => this._submitOptionsFlowStep(flow.flow_id, values);
  }

  async _submitOptionsFlowStep(flowId, fields) {
    const token = this._hass.auth?.data?.access_token;
    if (!token) return;

    const userInput = {};
    for (const [name, input] of Object.entries(fields)) {
      if (input?.dataset?.multiple === "true") {
        userInput[name] = Array.from(
          input.querySelectorAll('input[type="checkbox"]:checked')
        ).map((checkbox) => checkbox.value);
      } else if (input.type === "checkbox") {
        userInput[name] = input.checked;
      } else if (input.type === "number") {
        userInput[name] = input.value === "" ? null : Number(input.value);
      } else if (input.tagName === "SELECT" && input.multiple) {
        userInput[name] = Array.from(input.selectedOptions).map(
          (option) => option.value
        );
      } else {
        userInput[name] = input.value;
      }
    }

    try {
      const response = await fetch(
        `/api/config/config_entries/options/flow/${encodeURIComponent(flowId)}`,
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(userInput),
        },
      );

      const next = await response.json();

      if (!response.ok) {
        console.error("OGP: Options Flow submit failed", response.status, next);
        return;
      }

      if (next.type === "create_entry") {
        this._closeOptionsFlowDialog();
        return;
      }

      if (next.type === "abort") {
        this._closeOptionsFlowDialog();
        return;
      }

      this._renderOptionsFlowStep(next);
    } catch (err) {
      console.error("OGP: Options Flow submit error", err);
    }
  }

  async _abortOptionsFlow(flowId) {
    const token = this._hass.auth?.data?.access_token;
    try {
      await fetch(
        `/api/config/config_entries/options/flow/${encodeURIComponent(flowId)}`,
        {
          method: "DELETE",
          headers: {
            "Authorization": `Bearer ${token}`,
          },
        },
      );
    } catch (err) {
      console.warn("OGP: unable to abort Options Flow", err);
    }
    this._closeOptionsFlowDialog();
  }

  _closeOptionsFlowDialog() {
    if (this._ogpOptionsOverlay) {
      this._ogpOptionsOverlay.remove();
      this._ogpOptionsOverlay = null;
    }
    if (this._ogpOptionsStyle) {
      this._ogpOptionsStyle.remove();
      this._ogpOptionsStyle = null;
    }
  }

  async _getOGPCentralConfigEntryId() {
    if (!this._hass) return null;

    // Allow the final generated Lovelace YAML to provide the central entry
    // explicitly, while still supporting the current test YAML without it.
    if (this._config.central_entry_id) {
      return this._config.central_entry_id;
    }

    // OGP central has no dedicated helper entity. Discover it by enumerating
    // the OGP Config Entries and testing their Options Flow start step.
    // Device helper entities point to device Config Entries, not the central
    // one, so looking only through the entity registry cannot find the central.
    const entryIds = new Set();

    try {
      const entries = await this._hass.callWS({
        type: "config_entries/get",
        domain: "off_grid_protection",
      });
      for (const entry of Array.isArray(entries) ? entries : []) {
        if (entry?.entry_id) {
          entryIds.add(entry.entry_id);
        }
      }
    } catch (err) {
      console.warn("OGP: unable to enumerate OGP Config Entries", err);
    }


    const token = this._hass.auth?.data?.access_token;
    if (!token) return null;

    for (const entryId of entryIds) {
      let flowId = null;
      try {
        const response = await fetch(
          "/api/config/config_entries/options/flow",
          {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              handler: entryId,
              show_advanced_options: true,
            }),
          },
        );

        if (!response.ok) continue;
        const flow = await response.json();
        flowId = flow?.flow_id;

        // Central Options Flow starts at step "init"; device Options Flow
        // starts at "device_options". This avoids exposing private
        // ConfigEntry.data to the frontend.
        if (flow?.step_id === "init") {
          return entryId;
        }
      } catch (err) {
        // Try the next candidate Entry.
      } finally {
        if (flowId) {
          try {
            await fetch(
              `/api/config/config_entries/options/flow/${encodeURIComponent(flowId)}`,
              {
                method: "DELETE",
                headers: { "Authorization": `Bearer ${token}` },
              },
            );
          } catch (err) {
            // Ignore cleanup errors.
          }
        }
      }
    }

    return null;
  }

  async _openOGPCentralSettings() {
    if (!this._hass) return;

    const language = (this._hass?.locale?.language || this._hass?.language || "en").toLowerCase();
    const hr = language.startsWith("hr");
    const entryId = await this._getOGPCentralConfigEntryId();
    const token = this._hass.auth?.data?.access_token;

    if (!entryId || !token) {
      await this._showPersistentReloadNotification(
        "ogp_central_settings",
        hr ? "OGP centralna konfiguracija nije pronađena." : "OGP central configuration entry was not found.",
        hr ? "Greška" : "Error",
      );
      return;
    }

    let flowId = null;
    try {
      const startResponse = await fetch(
        "/api/config/config_entries/options/flow",
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            handler: entryId,
            show_advanced_options: true,
          }),
        },
      );

      if (!startResponse.ok) throw new Error(`HTTP ${startResponse.status}`);
      const startFlow = await startResponse.json();
      flowId = startFlow?.flow_id;
      if (!flowId) throw new Error("No Options Flow ID");

      // Open the Options Flow at its first (init) screen.
      // The first screen now contains Central settings, Notifications,
      // and Generate Lovelace YAML. Do not jump directly to Central.
      const flow = startFlow;

      if (flow?.type === "abort") {
        await this._showPersistentReloadNotification(
          "ogp_central_settings",
          hr ? "Centralne postavke trenutno nisu dostupne." : "Central settings are currently unavailable.",
          hr ? "Centralne postavke" : "Central settings",
        );
        return;
      }

      this._showOptionsFlowDialog(
        { ...flow, flow_id: flowId },
        hr ? "OGP postavke" : "OGP settings",
      );
      flowId = null;
    } catch (err) {
      console.error("OGP: unable to open central Options Flow", err);
      await this._showPersistentReloadNotification(
        "ogp_central_settings",
        hr ? "Greška pri otvaranju centralnih postavki." : "Failed to open central settings.",
        hr ? "Greška" : "Error",
      );
    } finally {
      if (flowId) {
        try {
          await fetch(
            `/api/config/config_entries/options/flow/${encodeURIComponent(flowId)}`,
            {
              method: "DELETE",
              headers: { "Authorization": `Bearer ${token}` },
            },
          );
        } catch (err) {
          // Ignore cleanup errors.
        }
      }
    }
  }

  async _reloadOGPCentral() {
    if (!this._hass) return;

    const language = (this._hass?.locale?.language || this._hass?.language || "en").toLowerCase();
    const hr = language.startsWith("hr");
    const entryId = await this._getOGPCentralConfigEntryId();

    if (!entryId) {
      await this._showPersistentReloadNotification(
        "ogp_central_reload",
        hr ? "OGP centralna konfiguracija nije pronađena." : "OGP central configuration entry was not found.",
        hr ? "Greška" : "Error",
      );
      return;
    }

    try {
      await this._hass.callService(
        "homeassistant",
        "reload_config_entry",
        { entry_id: entryId },
      );

      await this._showPersistentReloadNotification(
        "ogp_central_reload",
        hr ? "Centralni OGP je ponovno učitan." : "OGP central was reloaded.",
        hr ? "Centralni OGP učitan" : "OGP central reloaded",
      );
      window.setTimeout(() => this._render(), 500);
    } catch (err) {
      console.error("OGP: unable to reload central config entry", err);
      await this._showPersistentReloadNotification(
        "ogp_central_reload",
        hr ? "Greška pri ponovnom učitavanju centrale." : "Failed to reload OGP central.",
        hr ? "Greška" : "Error",
      );
    }
  }

  async _toggleOGPCentral() {
    if (!this._hass) return;

    const language = (this._hass?.locale?.language || this._hass?.language || "en").toLowerCase();
    const hr = language.startsWith("hr");
    const entryId = await this._getOGPCentralConfigEntryId();

    if (!entryId) {
      await this._showPersistentReloadNotification(
        "ogp_central_enable_disable",
        hr ? "OGP centralna konfiguracija nije pronađena." : "OGP central configuration entry was not found.",
        hr ? "Greška" : "Error",
      );
      return;
    }

    let disabled = false;
    try {
      const entry = await this._hass.callWS({
        type: "config_entries/get_single",
        entry_id: entryId,
      });
      disabled = !!entry?.config_entry?.disabled_by;
    } catch (err) {
      console.warn("OGP: unable to read central Config Entry state", err);
    }

    try {
      const result = await this._hass.callWS({
        type: "config_entries/disable",
        entry_id: entryId,
        disabled_by: disabled ? null : "user",
      });

      await this._showPersistentReloadNotification(
        "ogp_central_enable_disable",
        disabled
          ? (hr ? "Centralni OGP je omogućen." : "OGP central is enabled.")
          : (hr ? "Centralni OGP je onemogućen." : "OGP central is disabled."),
        disabled
          ? (hr ? "Centralni OGP omogućen" : "OGP central enabled")
          : (hr ? "Centralni OGP onemogućen" : "OGP central disabled"),
      );

      window.setTimeout(() => this._render(), 500);
    } catch (err) {
      console.error("OGP: unable to enable/disable central", err);
      await this._showPersistentReloadNotification(
        "ogp_central_enable_disable",
        disabled
          ? (hr ? "Greška pri omogućavanju centrale." : "Failed to enable OGP central.")
          : (hr ? "Greška pri onemogućavanju centrale." : "Failed to disable OGP central."),
        hr ? "Greška" : "Error",
      );
    }
  }

  async _getOGPConfigEntryId(device) {
    if (!this._hass || !device) return null;

    const candidates = [
      device.protection_status_entity,
      device.locked_entity,
      device.override_remaining_entity,
      device.override_duration_entity,
      device.override_pin_entity,
    ].filter(Boolean);

    for (const entityId of candidates) {
      try {
        const registryEntry = await this._hass.callWS({
          type: "config/entity_registry/get",
          entity_id: entityId,
        });
        if (registryEntry?.config_entry_id) {
          return registryEntry.config_entry_id;
        }
      } catch (err) {
        // Try the next OGP helper entity.
      }
    }

    return null;
  }

  async _getOGPConfigEntry(device) {
    const entryId = await this._getOGPConfigEntryId(device);
    if (!entryId) return null;

    try {
      return await this._hass.callWS({
        type: "config_entries/get_single",
        entry_id: entryId,
      });
    } catch (err) {
      console.error("OGP: unable to read config entry", err);
      return null;
    }
  }

  async _toggleOGPDevice(device) {
    if (!this._hass || !device) return;

    const language = (this._hass?.locale?.language || this._hass?.language || "en").toLowerCase();
    const hr = language.startsWith("hr");
    const entry = await this._getOGPConfigEntry(device);
    const configEntry = entry?.config_entry;
    const entryId = configEntry?.entry_id;

    const notificationId = `ogp_enable_disable_${this._deviceId(device)}`;

    if (!entryId) {
      await this._showPersistentReloadNotification(
        notificationId,
        hr ? "OGP konfiguracija uređaja nije pronađena." : "OGP device configuration entry was not found.",
        hr ? "Greška" : "Error"
      );
      return;
    }

    const isDisabled = !!configEntry.disabled_by;

    try {
      const result = await this._hass.callWS({
        type: "config_entries/disable",
        entry_id: entryId,
        disabled_by: isDisabled ? null : "user",
      });

      if (result?.require_restart) {
        await this._showPersistentReloadNotification(
          notificationId,
          hr
            ? `HA zahtijeva ponovno pokretanje za uređaj ${device.name || ""}.`
            : `Home Assistant requires a restart for device ${device.name || ""}.`,
          hr ? "Potrebno ponovno pokretanje" : "Restart required"
        );
      } else {
        await this._showPersistentReloadNotification(
          notificationId,
          isDisabled
            ? (hr ? `Uređaj ${device.name || ""} je omogućen.` : `Device ${device.name || ""} is enabled.`)
            : (hr ? `Uređaj ${device.name || ""} je onemogućen.` : `Device ${device.name || ""} is disabled.`),
          isDisabled
            ? (hr ? "Uređaj omogućen" : "Device enabled")
            : (hr ? "Uređaj onemogućen" : "Device disabled")
        );
      }

      window.setTimeout(() => this._render(), 500);
    } catch (err) {
      console.error("OGP: unable to enable/disable device", err);
      await this._showPersistentReloadNotification(
        notificationId,
        isDisabled
          ? (hr ? "Greška pri omogućavanju uređaja." : "Failed to enable device.")
          : (hr ? "Greška pri onemogućavanju uređaja." : "Failed to disable device."),
        hr ? "Greška" : "Error"
      );
    }
  }

  async _getOGPDeviceDetailsFromOptionsFlow(device) {
    if (!this._hass || !device) return null;

    const entryId = await this._getOGPConfigEntryId(device);
    if (!entryId) return null;

    const token = this._hass.auth?.data?.access_token;
    if (!token) return null;

    let flowId = null;
    try {
      const startResponse = await fetch(
        "/api/config/config_entries/options/flow",
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            handler: entryId,
            show_advanced_options: true,
          }),
        },
      );

      if (!startResponse.ok) return null;
      const startFlow = await startResponse.json();
      flowId = startFlow?.flow_id;
      if (!flowId) return null;

      const stepResponse = await fetch(
        `/api/config/config_entries/options/flow/${encodeURIComponent(flowId)}`,
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ action: "device_settings" }),
        },
      );

      if (!stepResponse.ok) return null;
      const flow = await stepResponse.json();
      if (flow?.type === "abort" || !Array.isArray(flow?.data_schema)) {
        return null;
      }

      const values = {};
      for (const field of flow.data_schema) {
        if (!field?.name) continue;
        if (field.value !== undefined) values[field.name] = field.value;
        else if (field.default !== undefined) values[field.name] = field.default;
      }

      return {
        name: values.name,
        entity_id: values.entity_id,
        automations: Array.isArray(values.automations)
          ? values.automations
          : [],
        // Custom devices do not use associated automations. Their
        // control_entity_id is the entity OGP uses as the external
        // control mechanism and should be shown in Device Details.
        control_entity_id:
          typeof values.control_entity_id === "string"
            ? values.control_entity_id
            : "",
      };
    } catch (err) {
      console.warn("OGP: unable to read device details from Options Flow", err);
      return null;
    } finally {
      if (flowId) {
        try {
          await fetch(
            `/api/config/config_entries/options/flow/${encodeURIComponent(flowId)}`,
            {
              method: "DELETE",
              headers: { "Authorization": `Bearer ${token}` },
            },
          );
        } catch (err) {
          console.warn("OGP: unable to abort Device Details Options Flow", err);
        }
      }
    }
  }

  async _openDeviceDetails(device) {
    if (!this._hass || !device) return;

    const language = (
      this._hass?.locale?.language || this._hass?.language || "en"
    ).toLowerCase();
    const hr = language.startsWith("hr");

    const entry = await this._getOGPConfigEntry(device);
    const configEntry = entry?.config_entry;

    if (!configEntry) {
      await this._showPersistentReloadNotification(
        `ogp_details_${this._deviceId(device)}`,
        hr
          ? "OGP konfiguracija uređaja nije pronađena."
          : "OGP device configuration entry was not found.",
        hr ? "Greška" : "Error"
      );
      return;
    }

    // ConfigEntry.as_json_fragment intentionally does not expose entry.data.
    // Read the current device values through the existing OGP Options Flow.
    const flowDetails = await this._getOGPDeviceDetailsFromOptionsFlow(device);

    const entryName = configEntry.title || flowDetails?.name || device.name || "—";
    const realEntity =
      flowDetails?.entity_id ||
      device.entity ||
      "—";

    const automationIds = Array.isArray(flowDetails?.automations)
      ? flowDetails.automations
      : [];

    const automations = automationIds.map((automationId) => {
      const state = this._hass.states?.[automationId];
      return {
        id: automationId,
        name: state?.attributes?.friendly_name || state?.name || automationId,
      };
    });

    const controlEntityId = flowDetails?.control_entity_id || "";
    const isCustomDevice = Boolean(controlEntityId);

    // The Lovelace configuration already contains the OGP-generated helper
    // entities for this device. Use those actual configured entity IDs rather
    // than trying to read private ConfigEntry.data from the frontend API.
    const generatedEntities = [
      device.locked_entity,
      device.override_duration_entity,
      device.override_remaining_entity,
      device.protection_status_entity,
      device.override_pin_entity,
    ].filter(Boolean).filter((entityId, index, list) => list.indexOf(entityId) === index);

    this._closeDeviceDetailsDialog();

    const overlay = document.createElement("div");
    overlay.className = "ogp-details-overlay";
    overlay.innerHTML = `
      <div class="ogp-details-dialog" role="dialog" aria-modal="true">
        <div class="ogp-details-header">
          <div class="ogp-details-title">${
            hr ? "Detalji uređaja" : "Device Details"
          }</div>
          <button class="ogp-details-close" type="button" aria-label="${
            hr ? "Zatvori" : "Close"
          }">×</button>
        </div>

        <div class="ogp-details-body">
          <div class="ogp-details-section">
            <div class="ogp-details-section-title">Entry name</div>
            <div class="ogp-details-value">${this._escape(entryName)}</div>
          </div>

          <div class="ogp-details-section">
            <div class="ogp-details-section-title">Real entity</div>
            <div class="ogp-details-value ogp-details-code">${
              this._escape(realEntity)
            }</div>
          </div>

          <div class="ogp-details-section">
            <div class="ogp-details-section-title">${
              isCustomDevice
                ? (hr ? "Automatizacije / entities" : "Automations / entities")
                : (hr ? "Automatizacije" : "Automations")
            }</div>
            <div class="ogp-details-list">
              ${isCustomDevice
                ? `<div class="ogp-details-list-item ogp-details-code">${
                    this._escape(controlEntityId)
                  }</div>`
                : automations.length
                  ? automations
                      .map(
                        (item) => `
                          <div class="ogp-details-list-item">
                            <div>${this._escape(item.name)}</div>
                            ${item.name !== item.id
                              ? `<div class="ogp-details-subtext">${this._escape(item.id)}</div>`
                              : ""}
                          </div>`
                      )
                      .join("")
                  : `<div class="ogp-details-empty">${hr ? "Nema povezanih automatizacija." : "No associated automations."}</div>`}
            </div>
          </div>

          <div class="ogp-details-section">
            <div class="ogp-details-section-title">${
              hr ? "Generirani OGP entiteti" : "Generated OGP entities"
            }</div>
            <div class="ogp-details-list">
              ${generatedEntities.length
                ? generatedEntities
                    .map(
                      (entityId) => `
                        <div class="ogp-details-list-item ogp-details-code">${
                          this._escape(entityId)
                        }</div>`
                    )
                    .join("")
                : `<div class="ogp-details-empty">${hr ? "Nema generiranih entiteta." : "No generated entities."}</div>`}
            </div>
          </div>
        </div>
      </div>
    `;

    const style = document.createElement("style");
    style.textContent = `
      .ogp-details-overlay {
        position: fixed;
        inset: 0;
        z-index: 100000;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0,0,0,.32);
      }
      .ogp-details-dialog {
        width: min(620px, calc(100vw - 32px));
        max-height: min(760px, calc(100vh - 32px));
        overflow: hidden;
        border-radius: 12px;
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color, #111);
        box-shadow: 0 12px 40px rgba(0,0,0,.35);
        font-family: var(--paper-font-body1_-_font-family, sans-serif);
      }
      .ogp-details-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 24px 12px;
      }
      .ogp-details-title {
        font-size: 20px;
        font-weight: 500;
      }
      .ogp-details-close {
        border: 0;
        background: transparent;
        color: var(--secondary-text-color);
        font-size: 28px;
        cursor: pointer;
      }
      .ogp-details-body {
        overflow: auto;
        max-height: calc(100vh - 100px);
        padding: 0 24px 24px;
      }
      .ogp-details-section {
        padding: 12px 0 16px;
        border-bottom: 1px solid var(--divider-color, #ddd);
      }
      .ogp-details-section:last-child {
        border-bottom: 0;
      }
      .ogp-details-section-title {
        margin-bottom: 8px;
        color: var(--secondary-text-color, #666);
        font-size: 14px;
      }
      .ogp-details-value {
        font-size: 15px;
      }
      .ogp-details-code {
        font-family: var(--paper-font-code1_-_font-family, monospace);
        overflow-wrap: anywhere;
      }
      .ogp-details-list {
        display: flex;
        flex-direction: column;
      }
      .ogp-details-list-item {
        padding: 8px 0;
      }
      .ogp-details-subtext {
        margin-top: 2px;
        color: var(--secondary-text-color, #666);
        font-family: var(--paper-font-code1_-_font-family, monospace);
        font-size: .78rem;
        overflow-wrap: anywhere;
      }
      .ogp-details-empty {
        color: var(--secondary-text-color);
        font-size: .88rem;
      }
    `;

    overlay.querySelector(".ogp-details-close").addEventListener(
      "click",
      () => this._closeDeviceDetailsDialog()
    );
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) this._closeDeviceDetailsDialog();
    });

    document.body.appendChild(overlay);
    document.head.appendChild(style);
    this._ogpDetailsOverlay = overlay;
    this._ogpDetailsStyle = style;
  }

  _closeDeviceDetailsDialog() {
    if (this._ogpDetailsOverlay) {
      this._ogpDetailsOverlay.remove();
      this._ogpDetailsOverlay = null;
    }
    if (this._ogpDetailsStyle) {
      this._ogpDetailsStyle.remove();
      this._ogpDetailsStyle = null;
    }
  }

  async _reloadOGPDevice(device) {
    if (!this._hass || !device) return;

    const language = (this._hass?.locale?.language || this._hass?.language || "en").toLowerCase();
    const hr = language.startsWith("hr");

    const candidates = [
      device.protection_status_entity,
      device.locked_entity,
      device.override_remaining_entity,
      device.override_duration_entity,
      device.override_pin_entity,
    ].filter(Boolean);

    let configEntryId = null;

    for (const entityId of candidates) {
      try {
        const registryEntry = await this._hass.callWS({
          type: "config/entity_registry/get",
          entity_id: entityId,
        });

        if (registryEntry?.config_entry_id) {
          configEntryId = registryEntry.config_entry_id;
          break;
        }
      } catch (err) {
        // Try the next OGP helper entity.
      }
    }

    const notificationId = `ogp_reload_${this._deviceId(device)}`;

    if (!configEntryId) {
      await this._showPersistentReloadNotification(
        notificationId,
        hr ? "OGP konfiguracija uređaja nije pronađena." : "OGP device configuration entry was not found.",
        hr ? "Greška" : "Error"
      );
      return;
    }

    try {
      await this._hass.callService(
        "homeassistant",
        "reload_config_entry",
        { entry_id: configEntryId },
      );

      await this._showPersistentReloadNotification(
        notificationId,
        hr
          ? `Uređaj ${device.name || ""} je ponovno učitan.`
          : `Device ${device.name || ""} reloaded.`,
        hr ? "Uređaj učitan" : "Device reloaded"
      );

      window.setTimeout(() => this._render(), 500);
    } catch (err) {
      console.error("OGP: unable to reload device config entry", err);
      await this._showPersistentReloadNotification(
        notificationId,
        hr ? "Greška pri ponovnom učitavanju uređaja." : "Failed to reload device.",
        hr ? "Greška" : "Error"
      );
    }
  }

  async _showPersistentReloadNotification(notificationId, message, title) {
    try {
      await this._hass.callService("persistent_notification", "create", {
        title,
        message,
        notification_id: notificationId,
      });
    } catch (err) {
      console.error("OGP: unable to create persistent reload notification", err);
    }
  }

  _navigateHomeDashboard() {
    const path = String(this._config.home_dashboard_path || "/dashboard").trim() || "/dashboard";
    try {
      if (this._hass?.navigate) {
        this._hass.navigate(path);
        return;
      }
    } catch (err) {
      console.warn("OGP: unable to navigate with hass.navigate", err);
    }

    // Fallback for HA frontend versions without hass.navigate().
    window.history.pushState({}, "", path);
    window.dispatchEvent(new Event("location-changed"));
  }

  async _setDevicePower(device, turnOn) {
    if (!this._hass || !device?.entity) return;

    // Manual device control is intentionally available only while the
    // existing OGP Override state is active.
    if (!this._overrideActive(device)) return;

    const service = turnOn ? "turn_on" : "turn_off";

    await this._hass.callService("switch", service, {
      entity_id: device.entity,
    });
  }

  _attachManualControlHandlers() {
    this.shadowRoot
      .querySelectorAll('[data-action="device-on"], [data-action="device-off"]')
      .forEach(button => {
        button.addEventListener("click", async event => {
          event.stopPropagation();

          const id = button.dataset.deviceId;
          const device = (this._config.devices || []).find(
            item => this._deviceId(item) === id
          );

          if (!device || !this._overrideActive(device)) return;

          const turnOn = button.dataset.action === "device-on";
          await this._setDevicePower(device, turnOn);
        });
      });

    this.shadowRoot
      .querySelectorAll(
        '[data-action="home-dashboard"], ' +
        '[data-action="central-settings"], ' +
        '[data-action="central-reload"], ' +
        '[data-action="central-enable-disable"], ' +
        '[data-action="device-settings"], ' +
        '[data-action="device-reload"], ' +
        '[data-action="device-enable-disable"], ' +
        '[data-action="device-details"]'
      )
      .forEach(button => {
        button.addEventListener("click", async event => {
          event.stopPropagation();

          const id = button.dataset.deviceId;
          const device = (this._config.devices || []).find(
            item => this._deviceId(item) === id
          );

          if (button.dataset.action === "home-dashboard") {
            this._navigateHomeDashboard();
            return;
          }

          if (button.dataset.action === "central-settings") {
            await this._openOGPCentralSettings();
            return;
          }

          if (button.dataset.action === "central-reload") {
            await this._reloadOGPCentral();
            return;
          }

          if (button.dataset.action === "central-enable-disable") {
            await this._toggleOGPCentral();
            return;
          }

          if (!device) return;

          if (button.dataset.action === "device-settings") {
            this._openHADeviceSettings(device);
            return;
          }

          if (button.dataset.action === "device-reload") {
            await this._reloadOGPDevice(device);
            return;
          }

          if (button.dataset.action === "device-enable-disable") {
            await this._toggleOGPDevice(device);
            return;
          }

          if (button.dataset.action === "device-details") {
            await this._openDeviceDetails(device);
            return;
          }
        });
      });
  }

  _attachOverrideDialogHandlers() {
    if (!this.shadowRoot.querySelector(".modal-backdrop")) return;

    this.shadowRoot
      .querySelector("#close-override")
      ?.addEventListener("click", () => this._closeOverride());

    this.shadowRoot
      .querySelector("#cancel-override")
      ?.addEventListener("click", () => this._closeOverride());

    this.shadowRoot
      .querySelectorAll("[data-duration]")
      .forEach(button => {
        button.addEventListener("click", () => {
          this._setOverrideDuration(button.dataset.duration);
        });
      });

    const inputs = [
      ...this.shadowRoot.querySelectorAll(".pin-input"),
    ];

    inputs.forEach(input => {
      input.addEventListener("input", event => {
        const index = Number(event.target.dataset.pinIndex);
        const digit = String(event.target.value || "")
          .replace(/\D/g, "")
          .slice(-1);

        const chars = ["", "", "", ""];
        for (let i = 0; i < 4; i++) {
          chars[i] = this._overridePin[i] || "";
        }
        chars[index] = digit;

        this._setOverridePin(chars.join(""));

        const activateButton =
          this.shadowRoot.querySelector("#activate-override");

        if (activateButton) {
          activateButton.disabled = !/^\d{4}$/.test(
            this._overridePin
          );
        }

        if (digit && inputs[index + 1]) {
          inputs[index + 1].focus();
        }
      });

      input.addEventListener("keydown", event => {
        if (event.key === "Backspace" && !input.value) {
          const index = Number(input.dataset.pinIndex);
          if (inputs[index - 1]) inputs[index - 1].focus();
        }
      });
    });

    this.shadowRoot
      .querySelector("#activate-override")
      ?.addEventListener("click", () => {
        this._activateOverride(this._overrideDevice);
      });

    inputs[0]?.focus();
  }

  getCardSize() {
    return 8;
  }

  _handleGridChange(state) {
    if (this._isOffGrid(state)) {
      this._cancelRecovery();
      return;
    }

    if (this._isOnGrid(state)) {
      this._startRecovery();
    }
  }

  _startRecovery() {
    this._stopRecoveryTimer();

    this._recoveryEnd = Date.now() + 60 * 1000;
    this._updateRecovery();

    this._recoveryTimer = setInterval(() => {
      this._updateRecovery();
    }, 250);
  }

  _cancelRecovery() {
    this._stopRecoveryTimer();
    this._recoveryEnd = null;
    this._render();
  }

  _stopRecoveryTimer() {
    if (this._recoveryTimer !== null) {
      clearInterval(this._recoveryTimer);
      this._recoveryTimer = null;
    }
  }

  _updateRecovery() {
    if (this._recoveryEnd === null) {
      this._render();
      return;
    }

    if (this._recoveryEnd - Date.now() <= 0) {
      this._stopRecoveryTimer();
      this._recoveryEnd = null;
    }

    this._render();
  }

  _isOnGrid(state) {
    const value = String(state || "").trim().toLowerCase();

    return [
      "on",
      "on-grid",
      "on_grid",
      "ongrid",
      "grid",
      "connected",
      "true",
    ].includes(value);
  }

  _isOffGrid(state) {
    const value = String(state || "").trim().toLowerCase();

    return [
      "off",
      "off-grid",
      "off_grid",
      "offgrid",
      "island",
      "disconnected",
      "false",
    ].includes(value);
  }

  _gridDisplay(state) {
    if (this._isOffGrid(state)) return "OFF";
    if (this._isOnGrid(state)) return "ON";
    return state || "—";
  }

  _recoveryDisplay() {
    if (this._recoveryEnd === null) return "—";

    const seconds = Math.max(
      0,
      Math.ceil((this._recoveryEnd - Date.now()) / 1000)
    );

    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;

    return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  _state(entityId, fallback = "—") {
    if (!entityId || !this._hass) return fallback;

    const entity = this._hass.states[entityId];

    return entity ? entity.state : fallback;
  }

  _deviceState(device) {
    if (!device.entity) return "—";

    return this._state(device.entity, "unavailable");
  }

  _devicePower(device) {
    if (!device.power_entity) return "—";

    const value = this._state(device.power_entity, "—");

    if (value === "—" || value === "unavailable") {
      return value;
    }

    const unit =
      this._hass?.states?.[device.power_entity]?.attributes?.unit_of_measurement;

    return `${value}${unit ? ` ${unit}` : ""}`;
  }

  _deviceProtectionStatus(device) {
    // The explicit OGP locked entity is authoritative for LOCKED.
    if (device.locked_entity) {
      const lockedState = this._state(
        device.locked_entity,
        "unavailable"
      );

      const locked = String(lockedState).trim().toLowerCase();

      if (["on", "true", "locked"].includes(locked)) {
        return {
          label: "LOCKED",
          className: "locked",
        };
      }
    }

    if (!device.protection_status_entity) {
      return null;
    }

    const state = this._state(
      device.protection_status_entity,
      "unavailable"
    );

    const normalized = String(state).trim().toLowerCase();

    if (["unavailable", "unknown"].includes(normalized)) {
      return {
        label: "UNAVAILABLE",
        className: "unavailable",
      };
    }

    if (["ready", "safe"].includes(normalized)) {
      return {
        label: "SAFE",
        className: "safe",
      };
    }

    if (["locked", "lock"].includes(normalized)) {
      return {
        label: "LOCKED",
        className: "locked",
      };
    }

    if (["override", "active"].includes(normalized)) {
      return {
        label: "OVERRIDE",
        className: "override",
      };
    }

    return {
      label: state,
      className: "neutral",
    };
  }

  _deviceStatus(device) {
    const state = this._deviceState(device);
    const normalized = String(state).toLowerCase();

    if (["unavailable", "unknown"].includes(normalized)) {
      return {
        label: "UNAVAILABLE",
        className: "unavailable",
      };
    }

    if (["on", "heat", "cool", "auto", "heat_cool", "fan_only", "dry"].includes(normalized)) {
      return {
        label: "ON",
        className: "on",
      };
    }

    if (["off"].includes(normalized)) {
      return {
        label: "OFF",
        className: "off",
      };
    }

    return {
      label: state,
      className: "neutral",
    };
  }

  _renderDevices() {
    const devices = Array.isArray(this._config.devices)
      ? this._config.devices
      : [];

    const gridEntity =
      this._config.grid_status_entity ||
      "input_select.ogp_test_grid_status";

    const gridState = this._state(gridEntity, "—");
    const offGrid = this._isOffGrid(gridState);

    if (!devices.length) {
      return `<div class="empty">No OGP devices configured.</div>`;
    }

    return devices.map((device, index) => {
      const name = device.name || `Device ${index + 1}`;
      const deviceStatus = this._deviceStatus(device);
      const protectionStatus =
        this._deviceProtectionStatus(device);
      const status = protectionStatus || deviceStatus;
      const id = this._deviceId(device);
      const open = this._openDeviceId === id;
      const active = this._overrideActive(device);

      return `
        <div class="device-block">
          <div class="device-row" data-device-id="${this._escape(id)}">
            <div class="device-main">
              <div class="device-icon">●</div>

              <div class="device-name">
                <div class="name">${this._escape(name)}</div>
                <div class="entity">
                  ${this._escape(device.entity || "—")}
                </div>
              </div>
            </div>

            <div class="device-status">
              <span class="status-dot ${status.className}"></span>
              <span class="status-badge ${status.className}">
                ${this._escape(status.label)}
              </span>
              <span class="status-badge switch-state ${deviceStatus.className}">
                ${this._escape(deviceStatus.label)}
              </span>
            </div>


            <div class="device-arrow">${open ? "⌃" : "›"}</div>
          </div>

          ${open ? `
            <div class="device-details">
              <div class="override-header">
                <div>
                  <div class="override-title">Override</div>
                  <div class="override-label">Override status</div>
                </div>
                <span class="override-state ${active ? "active" : "inactive"}">
                  ${active ? "ACTIVE" : "INACTIVE"}
                </span>
              </div>

              <div class="override-countdown">
                <span>Override countdown</span>
                <strong>
                  ${this._escape(
                    this._state(
                      device.override_remaining_entity,
                      "—"
                    )
                  )}
                </strong>
              </div>

              ${!active && offGrid && status.label === "LOCKED" ? `
                <button
                  class="override-action"
                  data-action="activate"
                  data-device-id="${this._escape(id)}">
                  ▶ Activate Override
                </button>
              ` : ""}

              ${active ? `
                <div class="manual-control">
                  <div class="manual-control-title">Manual control</div>
                  <div class="manual-control-buttons">
                    <button
                      class="manual-button on"
                      data-action="device-on"
                      data-device-id="${this._escape(id)}">
                      ⏻ On
                    </button>
                    <button
                      class="manual-button off"
                      data-action="device-off"
                      data-device-id="${this._escape(id)}">
                      ⏻ Off
                    </button>
                  </div>
                </div>
              ` : ""}

              <div class="device-options">
                <div class="device-options-title">${
                  ((this._hass?.locale?.language || this._hass?.language || "en")
                    .toLowerCase().startsWith("hr"))
                    ? "Opcije uređaja"
                    : "Device Options"
                }</div>

                <button class="option-button" data-action="device-settings"
                  data-device-id="${this._escape(id)}">
                  <span class="option-icon">⚙</span>
                  <span>${
                    ((this._hass?.locale?.language || this._hass?.language || "en")
                      .toLowerCase().startsWith("hr"))
                      ? "Postavke"
                      : "Settings"
                  }</span>
                  <span class="option-arrow">›</span>
                </button>

                <button class="option-button" data-action="device-reload"
                  data-device-id="${this._escape(id)}">
                  <span class="option-icon">↻</span>
                  <span>${
                    ((this._hass?.locale?.language || this._hass?.language || "en")
                      .toLowerCase().startsWith("hr"))
                      ? "Ponovno učitaj uređaj"
                      : "Reload Device"
                  }</span>
                  <span class="option-arrow">›</span>
                </button>

                <button class="option-button" data-action="device-enable-disable"
                  data-device-id="${this._escape(id)}">
                  <span class="option-icon">⏻</span>
                  <span>${
                    ((this._hass?.locale?.language || this._hass?.language || "en")
                      .toLowerCase().startsWith("hr"))
                      ? "Omogući / onemogući uređaj"
                      : "Enable / Disable Device"
                  }</span>
                  <span class="option-arrow">›</span>
                </button>

                <button class="option-button" data-action="device-details"
                  data-device-id="${this._escape(id)}">
                  <span class="option-icon">▤</span>
                  <span>${
                    ((this._hass?.locale?.language || this._hass?.language || "en")
                      .toLowerCase().startsWith("hr"))
                      ? "Detalji uređaja"
                      : "Device Details"
                  }</span>
                  <span class="option-arrow">›</span>
                </button>
              </div>
            </div>
          ` : ""}
        </div>
      `;
    }).join("");
  }

  _render() {
    if (!this.shadowRoot) return;

    // Keep the Override dialog DOM alive while it is open.
    // HA state updates can arrive frequently; rebuilding the dialog would
    // destroy the focused PIN input and make typing feel broken.
    if (
      this._overrideDevice &&
      this.shadowRoot.querySelector(".modal-backdrop")
    ) {
      return;
    }

    const title =
      this._config.title || "OGP – Off-grid Protection";

    const gridEntity =
      this._config.grid_status_entity ||
      "input_select.ogp_test_grid_status";

    const gridState = this._state(gridEntity, "—");
    const offGrid = this._isOffGrid(gridState);

    const systemStatus = offGrid
      ? "System is in OFF-GRID mode"
      : "System is operating normally";

    const protectionStatus =
      this._state(
        this._config.protection_status_entity,
        "ACTIVE"
      );

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }

        .ogp-reload-message {
          position: fixed;
          top: 16px;
          right: 16px;
          z-index: 10000;
          padding: 10px 14px;
          border-radius: 8px;
          font-size: 14px;
          box-shadow: 0 2px 8px rgba(0,0,0,.25);
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color);
        }

        .ogp-reload-message[data-type="success"] {
          border-left: 4px solid var(--success-color, #2e7d32);
        }

        .ogp-reload-message[data-type="error"] {
          border-left: 4px solid var(--error-color, #d32f2f);
        }

        .ogp-reload-message[data-type="loading"] {
          border-left: 4px solid var(--info-color, #1976d2);
        }

        ha-card {
          overflow: hidden;
          background: var(
            --ha-card-background,
            var(--card-background-color, var(--primary-background-color))
          );
        }

        .ogp {
          padding: 0;
        }

        .header {
          display: grid;
          grid-template-columns:
            minmax(260px, 1.7fr)
            repeat(3, minmax(130px, 1fr));
          min-height: 108px;
          align-items: stretch;
        }

        .identity {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 18px 24px;
        }

        .shield {
          width: 52px;
          height: 60px;
          display: grid;
          place-items: center;
          flex: 0 0 auto;
          color: ${offGrid
            ? "var(--warning-color, #ff9800)"
            : "var(--success-color, #4caf50)"};
          font-size: 30px;
          border-radius: 16px;
          background: color-mix(
            in srgb,
            ${offGrid
              ? "var(--warning-color, #ff9800)"
              : "var(--success-color, #4caf50)"} 12%,
            transparent
          );
          border: 1px solid color-mix(
            in srgb,
            ${offGrid
              ? "var(--warning-color, #ff9800)"
              : "var(--success-color, #4caf50)"} 35%,
            transparent
          );
        }

        .title {
          font-size: 1.35rem;
          line-height: 1.25;
          font-weight: 650;
          color: var(--primary-text-color);
        }

        .system-status {
          margin-top: 6px;
          font-size: .92rem;
          color: ${offGrid
            ? "var(--warning-color, #ff9800)"
            : "var(--success-color, #4caf50)"};
        }

        .status-cell {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 11px;
          padding: 8px 18px;
          border-left: 1px solid var(--divider-color);
        }

        .status-icon {
          width: 36px;
          height: 36px;
          display: grid;
          place-items: center;
          border-radius: 12px;
          background: var(--secondary-background-color);
          font-size: 19px;
        }

        .status-label {
          color: var(--secondary-text-color);
          font-size: .78rem;
          margin-bottom: 3px;
        }

        .status-value {
          font-size: 1rem;
          font-weight: 650;
          color: var(--primary-text-color);
        }

        .good {
          color: var(--success-color, #4caf50);
        }

        .offgrid {
          color: var(--warning-color, #ff9800);
        }

        .recovery-value {
          font-variant-numeric: tabular-nums;
        }

        .central-controls {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 12px;
          padding: 10px 20px;
          border-top: 1px solid var(--divider-color);
          border-bottom: 1px solid var(--divider-color);
          background: transparent;
        }

        .home-dashboard-button {
          display: inline-flex;
          align-items: center;
          gap: 12px;
          min-height: 48px;
          padding: 7px 16px 7px 10px;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font: inherit;
          font-size: .82rem;
          font-weight: 400;
          cursor: pointer;
          flex: 0 0 auto;
          text-align: left;
        }

        .home-dashboard-button:hover {
          background: var(--primary-background-color);
        }

        .home-dashboard-icon {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 36px;
          height: 36px;
          border-radius: 10px;
          background: color-mix(in srgb, var(--primary-color) 10%, transparent);
          color: var(--primary-color);
          flex: 0 0 auto;
        }

        .home-dashboard-icon svg {
          width: 21px;
          height: 21px;
          display: block;
        }

        .home-dashboard-text {
          font-size: .82rem;
          font-weight: 400;
          white-space: nowrap;
        }

        .central-controls-right {
          display: flex;
          justify-content: flex-end;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }

        .central-control-button {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          min-height: 38px;
          padding: 7px 12px;
          border: 1px solid var(--divider-color);
          border-radius: 9px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font: inherit;
          font-size: .82rem;
          cursor: pointer;
        }

        .central-control-button:hover {
          background: var(--primary-background-color);
        }

        .central-control-icon {
          color: var(--primary-color);
          font-size: 1rem;
        }

        .devices {
          margin-top: 1px;
          padding: 18px 20px 20px;
          border-top: 1px solid var(--divider-color);
        }

        .devices-title {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 12px;
          font-size: 1.05rem;
          font-weight: 650;
        }

        .device-count {
          color: var(--secondary-text-color);
          font-weight: 500;
          font-size: .85rem;
        }

        .device-table-header {
          display: grid;
          grid-template-columns: 2fr 1.15fr 28px;
          align-items: center;
          padding: 0 14px 8px;
          color: var(--secondary-text-color);
          font-size: .76rem;
        }

        .device-row {
          display: grid;
          grid-template-columns: 2fr 1.15fr 28px;
          align-items: center;
          min-height: 68px;
          margin-top: 8px;
          padding: 8px 14px;
          box-sizing: border-box;
          border: 1px solid var(--divider-color);
          border-radius: 12px;
          background: var(--secondary-background-color);
        }

        .device-main {
          display: flex;
          align-items: center;
          gap: 12px;
          min-width: 0;
        }

        .device-icon {
          width: 34px;
          height: 34px;
          display: grid;
          place-items: center;
          color: var(--primary-color);
          border-radius: 10px;
          background: color-mix(
            in srgb,
            var(--primary-color) 10%,
            transparent
          );
        }

        .device-name {
          min-width: 0;
        }

        .name {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-weight: 600;
        }

        .entity {
          margin-top: 3px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          color: var(--secondary-text-color);
          font-size: .75rem;
        }

        .device-status {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .status-dot {
          width: 9px;
          height: 9px;
          border-radius: 50%;
          background: var(--secondary-text-color);
        }

        .status-dot.on {
          background: var(--success-color, #4caf50);
        }

        .status-dot.off {
          background: var(--error-color, #f44336);
        }

        .status-dot.unavailable {
          background: var(--disabled-text-color, #9e9e9e);
        }

        .status-badge {
          padding: 5px 10px;
          border-radius: 7px;
          font-size: .72rem;
          font-weight: 650;
        }

        .status-badge.on,
        .status-badge.safe {
          color: var(--success-color, #4caf50);
          background: color-mix(
            in srgb,
            var(--success-color, #4caf50) 14%,
            transparent
          );
        }

        .status-badge.locked {
          color: var(--warning-color, #ff9800);
          background: color-mix(
            in srgb,
            var(--warning-color, #ff9800) 14%,
            transparent
          );
        }

        .status-badge.override {
          color: var(--primary-color);
          background: color-mix(
            in srgb,
            var(--primary-color) 14%,
            transparent
          );
        }

        .status-badge.off {
          color: var(--error-color, #f44336);
          background: color-mix(
            in srgb,
            var(--error-color, #f44336) 10%,
            transparent
          );
        }

        .status-badge.switch-state {
          min-width: 38px;
          text-align: center;
          border: 1px solid var(--divider-color);
        }

        .status-badge.switch-state.on {
          color: var(--success-color, #4caf50);
          background: color-mix(
            in srgb,
            var(--success-color, #4caf50) 8%,
            transparent
          );
        }

        .status-badge.switch-state.off {
          color: var(--error-color, #f44336);
          background: color-mix(
            in srgb,
            var(--error-color, #f44336) 7%,
            transparent
          );
        }

        .status-badge.unavailable,
        .status-badge.neutral {
          color: var(--secondary-text-color);
          background: var(--divider-color);
        }

        .device-power {
          font-variant-numeric: tabular-nums;
          color: var(--primary-text-color);
        }

        .device-arrow {
          text-align: right;
          color: var(--secondary-text-color);
          font-size: 1.6rem;
        }

        .device-block {
          margin-top: 8px;
        }

        .device-row {
          cursor: pointer;
        }

        .device-details {
          margin: 0 8px;
          padding: 14px;
          border: 1px solid var(--divider-color);
          border-top: 0;
          border-radius: 0 0 12px 12px;
          background: var(--primary-background-color);
        }

        .override-header,
        .override-countdown {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
        }

        .override-title {
          font-weight: 650;
          font-size: 1rem;
        }

        .override-label,
        .override-countdown {
          margin-top: 5px;
          color: var(--secondary-text-color);
          font-size: .82rem;
        }

        .override-countdown strong {
          color: var(--primary-text-color);
          font-variant-numeric: tabular-nums;
        }

        .override-state {
          padding: 5px 10px;
          border-radius: 7px;
          font-size: .72rem;
          font-weight: 650;
        }

        .override-state.active {
          color: var(--primary-color);
          background: color-mix(
            in srgb,
            var(--primary-color) 14%,
            transparent
          );
        }

        .override-state.inactive {
          color: var(--secondary-text-color);
          background: var(--divider-color);
        }

        .override-action,
        .activate-button {
          width: 100%;
          border: 0;
          border-radius: 8px;
          padding: 10px 14px;
          margin-top: 14px;
          font: inherit;
          font-weight: 650;
          cursor: pointer;
          color: var(--text-primary-color, white);
          background: var(--primary-color);
        }

        .activate-button:disabled {
          opacity: .45;
          cursor: not-allowed;
        }

        .manual-control {
          margin-top: 14px;
        }

        .manual-control-title {
          margin-bottom: 8px;
          color: var(--secondary-text-color);
          font-size: .82rem;
        }

        .manual-control-buttons {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
        }

        .manual-button {
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 10px 14px;
          font: inherit;
          font-weight: 650;
          cursor: pointer;
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
        }

        .manual-button.on {
          color: var(--success-color, #4caf50);
        }

        .manual-button.off {
          color: var(--error-color, #f44336);
        }

        .manual-button:hover {
          filter: brightness(1.05);
        }

        .device-options {
          margin-top: 16px;
          padding-top: 14px;
          border-top: 1px solid var(--divider-color);
        }

        .device-options-title {
          margin-bottom: 8px;
          color: var(--primary-text-color);
          font-size: .88rem;
          font-weight: 650;
        }

        .option-button {
          width: 100%;
          min-height: 42px;
          display: grid;
          grid-template-columns: 28px 1fr 24px;
          align-items: center;
          gap: 8px;
          margin-top: 6px;
          padding: 8px 12px;
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          box-sizing: border-box;
          font: inherit;
          text-align: left;
          cursor: pointer;
          color: var(--primary-text-color);
          background: var(--secondary-background-color);
        }

        .option-button:hover {
          filter: brightness(1.04);
        }

        .option-icon {
          display: grid;
          place-items: center;
          color: var(--primary-color);
          font-size: 1.05rem;
        }

        .option-arrow {
          text-align: right;
          color: var(--secondary-text-color);
          font-size: 1.3rem;
        }

        .modal-backdrop {
          position: fixed;
          inset: 0;
          z-index: 1000;
          display: grid;
          place-items: center;
          padding: 20px;
          background: rgba(0, 0, 0, .45);
        }

        .override-dialog {
          width: min(440px, 100%);
          padding: 20px;
          box-sizing: border-box;
          border: 1px solid var(--divider-color);
          border-radius: 14px;
          background: var(--card-background-color);
          box-shadow: 0 12px 40px rgba(0, 0, 0, .25);
        }

        .dialog-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }

        .dialog-title {
          font-size: 1.1rem;
          font-weight: 650;
        }

        .dialog-subtitle {
          margin-top: 5px;
          color: var(--secondary-text-color);
          font-size: .78rem;
          line-height: 1.4;
        }

        .close-button {
          border: 0;
          background: transparent;
          color: var(--secondary-text-color);
          font-size: 1.6rem;
          cursor: pointer;
        }

        .pin-row {
          display: flex;
          justify-content: center;
          gap: 10px;
          margin: 22px 0;
        }

        .pin-input {
          width: 48px;
          height: 52px;
          box-sizing: border-box;
          text-align: center;
          font-size: 1.35rem;
          border: 1px solid var(--divider-color);
          border-radius: 9px;
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
        }

        .duration-title {
          margin-bottom: 10px;
          color: var(--secondary-text-color);
          font-size: .82rem;
        }

        .duration-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 8px;
        }

        .duration {
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 9px 6px;
          font: inherit;
          cursor: pointer;
          color: var(--primary-text-color);
          background: var(--secondary-background-color);
        }

        .duration.selected {
          border-color: var(--primary-color);
          background: color-mix(
            in srgb,
            var(--primary-color) 15%,
            transparent
          );
        }

        .duration-info {
          grid-column: 1 / -1;
          padding: 10px;
          text-align: center;
          color: var(--secondary-text-color);
        }

        .cancel-button {
          width: 100%;
          border: 0;
          background: transparent;
          color: var(--secondary-text-color);
          padding: 10px;
          margin-top: 4px;
          cursor: pointer;
          font: inherit;
        }

        .empty {
          padding: 22px 14px;
          color: var(--secondary-text-color);
          text-align: center;
        }

        @media (max-width: 800px) {
          .header {
            grid-template-columns: 1fr 1fr;
          }

          .identity {
            grid-column: 1 / -1;
          }

          .device-table-header {
            display: none;
          }

          .device-row {
            grid-template-columns: 1fr auto 28px;
          }

          .device-status {
            grid-column: 2;
            grid-row: 1;
          }


          .device-arrow {
            grid-column: 3;
            grid-row: 1 / 3;
          }
        }

        @media (max-width: 520px) {
          .header {
            grid-template-columns: 1fr;
          }

          .central-controls {
            flex-direction: column;
            align-items: stretch;
          }

          .central-control-button {
            justify-content: flex-start;
          }

          .status-cell {
            justify-content: flex-start;
            border-left: 0;
            border-top: 1px solid var(--divider-color);
            padding: 12px 20px;
          }

          .identity {
            grid-column: auto;
          }
        }
      </style>

      <ha-card>
        <div class="ogp">

          <div class="header">
            <div class="identity">
              <div class="shield">🛡</div>
              <div>
                <div class="title">${this._escape(title)}</div>
                <div class="system-status">
                  ${this._escape(systemStatus)}
                </div>
              </div>
            </div>

            <div class="status-cell">
              <div class="status-icon">⚡</div>
              <div>
                <div class="status-label">Grid</div>
                <div class="status-value ${offGrid ? "offgrid" : "good"}">
                  ${this._escape(this._gridDisplay(gridState))}
                </div>
              </div>
            </div>

            <div class="status-cell">
              <div class="status-icon">🛡</div>
              <div>
                <div class="status-label">Protection</div>
                <div class="status-value good">
                  ${this._escape(protectionStatus)}
                </div>
              </div>
            </div>

            <div class="status-cell">
              <div class="status-icon">◷</div>
              <div>
                <div class="status-label">On-grid recovery</div>
                <div class="status-value recovery-value">
                  ${this._escape(this._recoveryDisplay())}
                </div>
              </div>
            </div>
          </div>

          <div class="central-controls">
            <button class="home-dashboard-button" data-action="home-dashboard" title="${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Povratak na početnu HA stranicu" : "Back to HA default dashboard"}" aria-label="${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Povratak na početnu HA stranicu" : "Back to HA default dashboard"}">
              <span class="home-dashboard-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M3 10.8 12 3l9 7.8"/>
                  <path d="M5.5 9.8V21h13V9.8"/>
                  <path d="M9.5 21v-6h5v6"/>
                </svg>
              </span>
              <span class="home-dashboard-text">${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Povratak na početnu HA stranicu" : "Back to HA default dashboard"}</span>
            </button>

            <div class="central-controls-right">
              <button class="central-control-button" data-action="central-settings">
              <span class="central-control-icon">⚙</span>
              <span>${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Centralne postavke" : "Central settings"}</span>
            </button>
            <button class="central-control-button" data-action="central-reload">
              <span class="central-control-icon">↻</span>
              <span>${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Ponovno učitaj centralu" : "Reload central"}</span>
            </button>
              <button class="central-control-button" data-action="central-enable-disable">
                <span class="central-control-icon">⏻</span>
                <span>${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Omogući / onemogući centralu" : "Enable / Disable central"}</span>
              </button>
            </div>
          </div>

          <section class="devices">
            <div class="devices-title">
              <span>${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Uređaji" : "Devices"}</span>
              <span class="device-count">
                ${Array.isArray(this._config.devices)
                  ? this._config.devices.length
                  : 0}
              </span>
            </div>

            <div class="device-table-header">
              <span>${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Uređaj" : "Device"}</span>
              <span>${((this._hass?.locale?.language || this._hass?.language || "en").toLowerCase().startsWith("hr")) ? "Status" : "Status"}</span>
              <span></span>
            </div>

            ${this._renderDevices()}
          </section>

        </div>

        ${this._renderOverrideDialog()}
      </ha-card>
    `;

    this._attachDeviceHandlers();
    this._attachManualControlHandlers();
    this._attachOverrideDialogHandlers();
  }

  _escape(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
}

if (!customElements.get("ogp-card")) {
  customElements.define("ogp-card", OGPCard);
}
