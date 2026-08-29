"""Lovelace card generator for Off-grid Protection."""

from __future__ import annotations

import re

from homeassistant.util import slugify




def _localize_yaml(yaml_text: str, language: str) -> str:
    """Translate all generated Lovelace user-facing text to HA language."""
    if language == "hr":
        return yaml_text

    replacements = {
        # Card / popup labels
        "🔒 ZAKLJUČANO / OFF-GRID": "🔒 LOCKED / OFF-GRID",
        "🔓 UREĐAJ OTKLJUČAN": "🔓 DEVICE UNLOCKED",
        "🔓 OTKLJUČAVANJE UREĐAJA": "🔓 DEVICE UNLOCKING",
        "Ako je PIN ispravan,": "If PIN is correct,",
        "Override će trajati **": "Override will last **",
        "Nakon toga uređaj možete **ručno uključiti**.": (
            "And then you can **turn the device on manually**."
        ),
        "Ako je PIN pogrešan, uređaj ostaje ZAKLJUČAN! - provjerite obavijest.": (
            "If PIN is wrong, device stays LOCKED! - check notification."
        ),

        "⚠️ OFF-GRID ZAŠTITA": "⚠️ OFF-GRID PROTECTION",
        "⚠️ POTVRDA POKRETANJA": "⚠️ START CONFIRMATION",
        "🔓 OFF-GRID OVERRIDE": "🔓 OFF-GRID OVERRIDE",
        "Trajanje rada": "Override duration",
        "Preostalo vrijeme": "Time remaining",
        "name: Trajanje rada": "name: Override duration",
        "name: PIN": "name: PIN",
        "POKRENI": "START",
        "ODUSTANI": "CANCEL",
        "DA": "YES",
        "NE": "NO",

        # Markdown / popup text
        "Odaberite koliko dugo želite omogućiti rad uređaja.": (
            "Select how long you want to allow the device to operate."
        ),
        "Želite li omogućiti rad uređaja?": (
            "Do you want to enable the device?"
        ),
        "Da li ste sigurni da želite pokrenuti": (
            "Are you sure you want to start"
        ),
        "Imajte na umu **opterećenje baterije**.": (
            "Please consider the **battery load**."
        ),
        "⚠️ Imajte na umu **opterećenje baterije**.": (
            "⚠️ Please consider the **battery load**."
        ),
        "Uređaj će tijekom overridea moći raditi u": (
            "The device will be allowed to operate during the override in"
        ),
        "**OFF-GRID modu**.": "**OFF-GRID mode**.",
        "OFF-GRID modu": "OFF-GRID mode",
        "Uređaj tijekom overridea neće biti automatski": (
            "The device will not be turned on automatically during the override."
        ),
        "uključen. Nakon otključavanja možete ga ručno": (
            "After unlocking, you can manually"
        ),
        "uključiti ili isključiti.": "turn it on or off.",
        "Uređaj sada možete **ručno uključiti**.": (
            "You can now **turn the device on manually**."
        ),
        "Override traje **": "Override lasts **",
        " minuta**.": " minutes**.",

        # Generated setup documentation
        "## Override tijek": "## Override flow",
        "Za Switch uređaje generator automatski uključuje cijeli tijek:": (
            "For Switch devices, the generator automatically includes the complete flow:"
        ),
        "1. Zaključani sloj → Popup 1.": (
            "1. Locked layer → Popup 1."
        ),
        "2. Potvrda → Popup 2.": "2. Confirmation → Popup 2.",
        "3. Trajanje + PIN → Popup 3.": (
            "3. Duration + PIN → Popup 3."
        ),
        "4. Popup 3 poziva": "4. Popup 3 calls",
        "5. Nakon zahtjeva prikazuje se Popup 4: uređaj je otključan.": (
            "5. Popup 4 is shown after the request: the device is unlocked."
        ),
        "6. Override ne uključuje Switch; korisnik ga uključuje ručno.": (
            "6. Override does not turn the Switch on; the user turns it on manually."
        ),
        "7. Nakon isteka Overridea OGP ponovno zaključava uređaj i, ako je ON, gasi ga.": (
            "7. After the Override expires, OGP locks the device again and turns it off if it is ON."
        ),
        "## Generirani YAML": "## Generated YAML",
    }

    for source, target in replacements.items():
        yaml_text = yaml_text.replace(source, target)

    # Device-name-dependent sentences cannot be handled by fixed-string
    # replacement, so translate them structurally.
    yaml_text = re.sub(
        r"\*\*(.+?)\*\* je zaključan jer je sustav u",
        r"**\1** is locked because the system is in",
        yaml_text,
    )
    yaml_text = re.sub(
        r"\*\*(.+?)\*\* je privremeno otključan\.",
        r"**\1** is temporarily unlocked.",
        yaml_text,
    )

    # Any remaining standalone Croatian labels used by the generator.
    yaml_text = yaml_text.replace(
        "Uređaj",
        "Device",
    )

    return yaml_text



def generate_stack_in_card_yaml(*, device_name: str, device_entity_id: str, language: str = "hr") -> str:
    """Generate the Lovelace configuration for a protected device."""
    slug = slugify(device_name)
    locked_entity = f"binary_sensor.{slug}_off_grid_protection_locked"
    duration_entity = f"number.{slug}_override_duration"
    remaining_entity = f"sensor.{slug}_override_remaining"
    pin_entity = f"text.{slug}_override_pin"

    if device_entity_id.startswith("climate."):
        # Climate devices use the V1-style thermostat + stack-in-card
        # conditional lock overlay. During a successful override the lock
        # entity becomes OFF, so the thermostat becomes directly controllable.
        lines = [
            "type: custom:stack-in-card",
            "mode: vertical",
            "cards:",
            "  - type: thermostat",
            f"    entity: {device_entity_id}",
            "    features:",
            "      - type: climate-hvac-modes",
            "        hvac_modes:",
            "          - fan_only",
            "          - dry",
            "          - cool",
            "          - heat",
            "          - auto",
            '          - "off"',
            "  - type: conditional",
            "    conditions:",
            f"      - entity: {locked_entity}",
            '        state: "on"',
            "    card:",
            "      type: custom:button-card",
            "      name: 🔒 ZAKLJUČANO / OFF-GRID",
            "      show_icon: false",
            "      show_state: false",
            "      tap_action:",
            "        action: fire-dom-event",
            "        browser_mod:",
            "          service: browser_mod.popup",
            "          data:",
            "            title: ⚠️ OFF-GRID ZAŠTITA",
            "            content:",
            "              type: markdown",
            "              content: |",
            "                ## ⚠️ OFF-GRID ZAŠTITA",
            "",
            f"                **{device_name}** je zaključan jer je sustav u",
            "                **OFF-GRID modu**.",
            "",
            "                Želite li omogućiti rad uređaja?",
            "            right_button: DA",
            "            right_button_action:",
            "              service: browser_mod.popup",
            "              data:",
            "                title: ⚠️ POTVRDA POKRETANJA",
            "                content:",
            "                  type: markdown",
            "                  content: |",
            "                    ## ⚠️ POTVRDA POKRETANJA",
            "",
            f"                    Da li ste sigurni da želite pokrenuti **{device_name}**?",
            "",
            "                    ⚠️ Imajte na umu **opterećenje baterije**.",
            "",
            "                    Uređaj će tijekom overridea moći raditi u",
            "                    **OFF-GRID modu**.",
            "                right_button: DA",
            "                right_button_action:",
            "                  service: browser_mod.popup",
            "                  data:",
            "                    title: 🔓 OFF-GRID OVERRIDE",
            "                    content:",
            "                      type: vertical-stack",
            "                      cards:",
            "                        - type: entities",
            "                          entities:",
            f"                            - entity: {duration_entity}",
            "                              name: Trajanje rada",
            f"                            - entity: {pin_entity}",
            "                              name: PIN",
            "                        - type: markdown",
            "                          content: >",
            "                            Odaberite koliko dugo želite omogućiti rad uređaja.",
            "",
            "                            ⚠️ Uređaj tijekom overridea neće biti automatski",
            "                            uključen. Nakon otključavanja možete ga ručno",
            "                            uključiti ili isključiti.",
            "                    right_button: POKRENI",
            "                    right_button_action:",
            "                      service: off_grid_protection.request_override",
            "                      data:",
            f"                        device_id: {device_entity_id}",
            "                    left_button: ODUSTANI",
            "                    dismissable: true",
            "                left_button: NE",
            "                dismissable: true",
            "            left_button: NE",
            "            dismissable: true",
            "      hold_action:",
            "        action: none",
            "      styles:",
            "        card:",
            "          - height: 100px",
            "          - margin-top: -100px",
            "          - z-index: 10",
            "          - opacity: 0.8",
            "        name:",
            "          - font-size: 18px",
            "          - font-weight: bold",
        ]
        return _localize_yaml("\n".join(lines) + "\n", language)

    if device_entity_id.startswith("switch."):
        lines = [
            "type: custom:button-card",
            "show_name: false",
            "show_icon: false",
            "show_state: false",
            "styles:",
            "  card:",
            "    - padding: 0",
            "    - margin: 0",
            "    - border-radius: 12px",
            "    - overflow: hidden",
            "    - pointer-events: none",
            "  grid:",
            "    - grid-template-areas: '\"base\"'",
            "    - grid-template-columns: 1fr",
            "    - grid-template-rows: auto",
            "  custom_fields:",
            "    base:",
            "      - grid-area: 1 / 1",
            "      - width: 100%",
            "      - height: 100%",
            "      - z-index: 1",
            "      - pointer-events: auto",
            "    overlay:",
            "      - grid-area: 1 / 1",
            "      - width: 100%",
            "      - height: 100%",
            "      - z-index: 10",
            "      - align-self: stretch",
            "      - justify-self: stretch",
            "custom_fields:",
            "  base:",
            "    card:",
            "      type: custom:stack-in-card",
            "      mode: vertical",
            "      cards:",
            "        - type: entity",
            f"          entity: {device_entity_id}",
            f"          name: {device_name}",
            "  overlay:",
            "    card:",
            "      type: custom:button-card",
            f"      entity: {locked_entity}",
            "      name: 🔒 ZAKLJUČANO / OFF-GRID",
            "      show_icon: false",
            "      show_state: false",
            "      tap_action:",
            "        action: fire-dom-event",
            "        browser_mod:",
            "          service: browser_mod.popup",
            "          data:",
            "            title: ⚠️ OFF-GRID ZAŠTITA",
            "            content:",
            "              type: markdown",
            "              content: |",
            "                ## ⚠️ OFF-GRID ZAŠTITA",
            "",
            f"                **{device_name}** je zaključan jer je sustav u",
            "                **OFF-GRID modu**.",
            "",
            "                Želite li omogućiti rad uređaja?",
            "            right_button: DA",
            "            right_button_action:",
            "              service: browser_mod.popup",
            "              data:",
            "                title: ⚠️ POTVRDA POKRETANJA",
            "                content:",
            "                  type: markdown",
            "                  content: |",
            "                    ## ⚠️ POTVRDA POKRETANJA",
            "",
            f"                    Da li ste sigurni da želite pokrenuti **{device_name}**?",
            "",
            "                    ⚠️ Imajte na umu **opterećenje baterije**.",
            "",
            "                    Uređaj će tijekom overridea moći raditi u",
            "                    **OFF-GRID modu**.",
            "                right_button: DA",
            "                right_button_action:",
            "                  service: browser_mod.popup",
            "                  data:",
            "                    title: 🔓 OFF-GRID OVERRIDE",
            "                    content:",
            "                      type: vertical-stack",
            "                      cards:",
            "                        - type: entities",
            "                          entities:",
            f"                            - entity: {duration_entity}",
            "                              name: Trajanje rada",
            f"                            - entity: {pin_entity}",
            "                              name: PIN",
            "                        - type: markdown",
            "                          content: >",
            "                            Odaberite koliko dugo želite omogućiti rad uređaja.",
            "",
            "                            ⚠️ Uređaj tijekom overridea neće biti automatski",
            "                            uključen. Nakon otključavanja možete ga ručno",
            "                            uključiti ili isključiti.",
            "                    right_button: POKRENI",
            "                    right_button_action:",
            "                      service: off_grid_protection.request_override",
            "                      data:",
            f"                        device_id: {device_entity_id}",
            "                    left_button: ODUSTANI",
            "                    dismissable: true",
            "                left_button: NE",
            "                dismissable: true",
            "            left_button: NE",
            "            dismissable: true",
            "      hold_action:",
            "        action: none",
            "      styles:",
            "        card:",
            "          - width: 100%",
            "          - height: 100%",
            "          - min-height: 100%",
            "          - margin: 0",
            "          - padding: 0 16px",
            "          - border-radius: 12px",
            "          - background: rgba(255, 255, 255, 0.88)",
            "          - display: flex",
            "          - align-items: center",
            "          - justify-content: center",
            "          - box-sizing: border-box",
            "          - pointer-events: auto",
            "        grid:",
            "          - grid-template-areas: '\"n\"'",
            "          - grid-template-columns: minmax(0, 1fr)",
            "          - grid-template-rows: 1fr",
            "        name:",
            "          - width: 100%",
            "          - color: black",
            "          - font-size: 43px",
            "          - font-style: italic",
            "          - font-weight: normal",
            "          - text-align: center",
            "          - line-height: 1.15",
            "          - white-space: normal",
            "          - overflow-wrap: anywhere",
            "          - word-break: normal",
            "      state:",
            '        - value: "off"',
            "          styles:",
            "            card:",
            "              - display: none",
            "              - pointer-events: none",
            '        - value: "on"',
            "          styles:",
            "            card:",
            "              - display: flex",
            "              - visibility: visible",
            "              - pointer-events: auto",
        ]
        return _localize_yaml("\n".join(lines) + "\n", language)

    # Existing Climate/default generator remains unchanged.
    lines = [
        "type: custom:stack-in-card",
        "mode: vertical",
        "cards:",
        "  - type: entity",
        f"    entity: {device_entity_id}",
        f"    name: {device_name}",
        "  - type: conditional",
        "    conditions:",
        f"      - entity: {locked_entity}",
        '        state: "on"',
        "    card:",
        "      type: custom:button-card",
        "      name: 🔒 ZAKLJUČANO / OFF-GRID",
        "      show_icon: false",
        "      tap_action:",
        "        action: fire-dom-event",
        "        browser_mod:",
        "          service: browser_mod.popup",
        "          data:",
        "            title: ⚠️ OFF-GRID ZAŠTITA",
        "            content:",
        "              type: markdown",
        "              content: |",
        "                ## ⚠️ OFF-GRID ZAŠTITA",
        "",
        f"                **{device_name}** je zaključan jer je sustav u",
        "                **OFF-GRID modu**.",
        "",
        "                Želite li omogućiti rad uređaja?",
        "            right_button: DA",
        "            left_button: NE",
        "            dismissable: true",
        "      hold_action:",
        "        action: none",
        "      styles:",
        "        card:",
        "          - position: absolute",
        "          - top: 0",
        "          - left: 0",
        "          - width: 100%",
        "          - height: 100%",
        "          - z-index: 10",
        "          - opacity: 0.8",
        "        name:",
        "          - font-size: 18px",
        "          - font-weight: bold",
    ]
    return _localize_yaml("\n".join(lines) + "\n", language)


def generate_setup_instructions(*, device_name: str, device_entity_id: str, language: str = "hr") -> str:
    """Generate setup instructions for a protected device."""
    yaml_text = generate_stack_in_card_yaml(
        device_name=device_name,
        device_entity_id=device_entity_id,
        language=language,
    )
    if language == "hr":
        intro = (
            f"# OGP Lovelace — {device_name}\n\n"
            "## Override tijek\n\n"
            "Za Switch uređaje generator automatski uključuje cijeli tijek:\n\n"
            "1. Zaključani sloj → Popup 1.\n"
            "2. Potvrda → Popup 2.\n"
            "3. Trajanje + PIN → Popup 3.\n"
            "4. Popup 3 poziva `off_grid_protection.request_override`.\n"
            "5. Nakon zahtjeva prikazuje se Popup 4: uređaj je otključan.\n"
            "6. Override ne uključuje Switch; korisnik ga uključuje ručno.\n"
            "7. Nakon isteka Overridea OGP ponovno zaključava uređaj i, ako je ON, gasi ga.\n\n"
            "## Generirani YAML\n\n"
        )
    else:
        intro = (
            f"# OGP Lovelace — {device_name}\n\n"
            "## Override flow\n\n"
            "For Switch devices, the generator automatically includes the complete flow:\n\n"
            "1. Locked layer → Popup 1.\n"
            "2. Confirmation → Popup 2.\n"
            "3. Duration + PIN → Popup 3.\n"
            "4. Popup 3 calls `off_grid_protection.request_override`.\n"
            "5. Popup 4 is shown after the request: the device is unlocked.\n"
            "6. Override does not turn the Switch on; the user turns it on manually.\n"
            "7. After the Override expires, OGP locks the device again and turns it off if it is ON.\n\n"
            "## Generated YAML\n\n"
        )
    return intro + "```yaml\n" + yaml_text + "```\n"
