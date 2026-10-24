# OGP v1.4.1 – Setup fix and bundled Lovelace card

- Fixed an undefined `central_changed` variable in the initial Central Setup notification flow.
- Bundled the OGP Lovelace card at `custom_components/off_grid_protection/www/ogp-card.js`.
- Registered the card through Home Assistant's async static-path API and automatically added it as a Lovelace resource in storage mode.
- Updated the English and Croatian documentation. YAML resource mode instructions use `/off_grid_protection/ogp-card.js?v=1.4.1`.

The OGP protection and Override logic is otherwise unchanged.
