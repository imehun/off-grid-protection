# OGP -- Off-grid Protection

Prilagođena Home Assistant integracija za zaštitu **baterijskog sustava
tijekom OFF-GRID rada**.

OGP nadzire odabrana Home Assistant trošila koja mogu značajno
opteretiti baterijski sustav. Može ih isključiti, isključiti odabrane
korisničke automatizacije koje bi ih mogle ponovno uključiti te nakon
recoveryja vratiti te automatizacije u njihovo prethodno stanje.

OGP ima i drugi sigurnosni sloj: ako se odabrano trošilo tijekom
OFF-GRID rada uključi bez aktivnog Overridea, OGP ga ponovno isključuje.

## Glavne funkcije

-   nadzor ON-GRID / OFF-GRID stanja
-   dodatna potvrda putem Power Meter Statusa
-   zaštita baterijskog sustava od opterećenja
-   nadzor i isključivanje odabranih trošila
-   isključivanje i vraćanje odabranih korisničkih automatizacija
-   ponovno isključivanje trošila bez Overridea
-   vremenski ograničen Override zaštićen PIN-om
-   recovery nakon povratka na ON-GRID
-   Home Assistant obavijesti
-   opcionalne Browser Mod popup obavijesti
-   konfiguracija putem Config Flowa
-   opcionalni generirani Lovelace YAML za dashboard
-   dokumentacija na engleskom i hrvatskom

## Opcionalne Lovelace komponente

Za osnovnu konfiguraciju i zaštitnu funkcionalnost OGP-a **nisu
potrebni** Browser Mod, Button-card niti Stack-in-card.

-   **Browser Mod** je opcionalan i potreban samo za Browser Mod popup
    obavijesti.
-   **Button-card** i **Stack-in-card** su opcionalni i preporučuju se
    za generirano Override dashboard sučelje.

Generirani Lovelace YAML je početni predložak. Nije dependency OGP-a i
korisnik ga može mijenjati.

## Testirane integracije

OGP je tijekom razvoja i testiranja provjeren s Home Assistant
entityjima koje pruža **Huawei Solar**.

Huawei Solar **nije dependency OGP-a**. OGP ne uključuje, ne instalira
niti distribuira izvorni kod Huawei Solar integracije.

OGP je projektiran za rad s različitim Home Assistant entityjima koji
pružaju potrebna stanja i servise.

## Dokumentacija

-   `README.md` -- pregled projekta
-   `README_hr.md` -- hrvatski pregled
-   `CONFIGURATION.md` -- detaljna konfiguracija
-   `CONFIGURATION_hr.md` -- detaljne upute

## Verzija

**v1.1.0 -- Stable**

v1.1.0 je zaključana stabilna verzija. Buduće promjene razvijaju se kao
nove verzije.

## Odricanje od odgovornosti

OGP je pomoćni softver za zaštitu baterijskog sustava od opterećenja u
Home Assistantu. Nije zamjena za sigurnosne funkcije invertera,
baterijskog sustava, električne instalacije ili druge hardverske
zaštite.

Prije oslanjanja na OGP za automatsku zaštitu opterećenja obavezno
testirajte cijeli sustav.
