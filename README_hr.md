# OGP -- Off-grid Battery Protection

Prilagođena Home Assistant integracija za zaštitu **baterijskog sustava
tijekom OFF-GRID rada**.

OGP nadzire odabrana Home Assistant trošila koja mogu značajno
opteretiti baterijski sustav. Može ih isključiti, isključiti odabrane
korisničke automatizacije koje bi ih mogle ponovno uključiti te nakon
recoveryja vratiti njihove prethodne stanja.

OGP ima i drugi sigurnosni sloj: ako se zaštićeno trošilo tijekom
OFF-GRID rada uključi bez aktivnog Overridea, OGP ponovno izvršava
konfiguriranu radnju gašenja.

## Glavne funkcije

-   nadzor ON-GRID / OFF-GRID stanja
-   dodatna potvrda putem Power Meter Statusa
-   zaštita baterijskog sustava od opterećenja
-   zasebni Device Entryji za svako trošilo
-   mogućnost onemogučavanja pojedinog Device Entryja
-   nadzor i isključivanje odabranih trošila
-   snapshot, isključivanje i vraćanje odabranih korisničkih
    automatizacija
-   sigurnosno ponovno gašenje trošila bez Overridea
-   vremenski ograničen Override zaštićen PIN-om
-   recovery nakon povratka na ON-GRID
-   generički Custom Device s Control entityjem
-   Custom recovery: Stay OFF ili Turn ON
-   Home Assistant obavijesti
-   opcionalne Browser Mod popup obavijesti
-   konfiguracija putem Config Flowa
-   opcionalni generirani Lovelace YAML
-   engleski i hrvatski UI/dokumentacija
-   podesivo OGP logiranje: Isključeno, Upozorenja ili Debug

## Model zaštite

OGP štiti **baterijski sustav**, a ne korisničke Home Assistant ovlasti.

Svaki konfigurirani OGP Device Entry je neovisan. Ako je Device Entry
disabled, OGP njime ne upravlja, dok ostali enabled Device Entryji
nastavljaju normalno raditi.

Kod standardnih uređaja odabrane korisničke automatizacije dio su
strategije zaštite. OGP pamti njihovo stanje prije zaštite, isključuje
odabrane automatizacije koje su bile uključene i nakon recoveryja vraća
njihovo prethodno stanje.

Ako se zaštićeno trošilo tijekom OFF-GRID rada uključi bez aktivnog
Overridea, OGP ponovno izvršava konfiguriranu radnju gašenja.

## Custom Device

Custom Device je namjerno potpuno generički. Nije vezan uz određeni Home
Assistant domain, integraciju, naziv uređaja ili konkretnu namjenu.

Custom Device ima dva neovisno odabrana entityja:

-   **Device entity** --- entity koji OGP gasi i nadzire.
-   **Control entity** --- dodatni entity čije se stanje snapshotira,
    koji se tijekom zaštite gasi i koji se tijekom recoveryja može
    ponovno uključiti.

Oba entityja su potpuno generički Home Assistant entityji. Nisu
ograničeni na `climate`, `switch`, `light`, `input_boolean` ili bilo
koji drugi domain.

Primjer klime kojom upravlja druga integracija:

-   Device entity: `climate.example`
-   Control entity: `switch.example_control_enabled`

Control entity može predstavljati cijeli vanjski sustav upravljanja i
njegovu kompletnu automatizaciju. Zato OGP ne zahtijeva od korisnika da
odabire svaku pojedinu automatizaciju tog sustava.

### Custom sekvenca zaštite

Tijekom OFF-GRID zaštite:

1.  radi se snapshot stanja Control entityja;
2.  izvršava se postojeći OGP redoslijed gašenja Device entityja;
3.  Control entity se isključuje;
4.  Device entity ostaje pod nadzorom i zaštitom.

Tijekom ON-GRID recoveryja Device entity ostaje OFF prema standardnom
OGP recovery modelu. Control entity zatim slijedi odabranu recovery
radnju:

-   **Stay OFF** --- Control entity ostaje OFF.
-   **Turn ON** --- Control entity se uključi kako bi vanjski sustav
    upravljanja mogao ponovno preuzeti uređaj.

Custom Device za ovaj mehanizam ne zahtijeva odabir pojedinačnih
internih automatizacija.

## Disabled Device Entryji

Pojedini Device Entry može se disableati bez disableanja centralnog OGP
entryja.

Kada je Device Entry disabled:

-   OGP njime ne upravlja;
-   OGP ga ne gasi;
-   OGP nad njim ne izvršava Override/recovery radnje;
-   uređaj se i dalje može normalno koristiti iz Home Assistanta i
    drugih integracija;
-   ostali enabled OGP Device Entryji nastavljaju raditi.

Ovo je posebno korisno tijekom developmenta, testiranja i održavanja
kada se stvarni uređaji žele potpuno izuzeti iz OGP upravljanja.

## Obavijesti

Obavijesti su opcionalne i upravljaju se kao zasebni profili obavijesti.
Svaki profil može se zasebno uređivati ili obrisati.

OGP podržava dvije vrste profila obavijesti:

-   **Globalna obavijest** --- može postojati najviše jedan globalni
    profil. Uvijek koristi ugrađenu Home Assistant uslugu
    `persistent_notification`. Korisnik odabire proizvoljnu kombinaciju
    događaja Status mreže, Zaštita / Override i Sigurnost te jezik
    obavijesti.
-   **Obavijest prema uređaju** --- može se kreirati više profila. Svaki
    profil cilja jedno Home Assistant notification odredište ili jedan
    Browser Mod uređaj te ima vlastiti odabir događaja i jezika.

Browser Mod dostupan je samo za obavijesti prema uređaju. Globalna
obavijest ga ne koristi.

Jezik obavijesti podržava hrvatski i engleski.

OGP sprječava lažne početne obavijesti o promjeni mrežnog stanja kada
Home Assistant nakon restarta prijeđe iz početnog
`unavailable`/`unknown` stanja u valjano stanje mreže.

Kada se promijene OGP postavke, OGP može prikazati trajnu Home Assistant
obavijest koja preporučuje restart Home Assistanta. Restart se ne
izvršava automatski.

## Override

Override je privremena, kontrolirana iznimka od OFF-GRID zaštite.

Može koristiti:

-   minimalno trajanje;
-   maksimalno trajanje;
-   traženo trajanje;
-   PIN zaštitu.

Override ne uključuje automatski zaštićeno trošilo. Korisnik odlučuje
hoće li i kada uređaj stvarno raditi.

## Generirani entityji i Lovelace

OGP prati resurse koje sam generira kako bi ih razlikovao od postojećih
Home Assistant resursa.

Generirani Lovelace YAML je početni predložak i nije dependency osnovne
OGP zaštitne funkcionalnosti.

Opcionalne frontend komponente:

-   Browser Mod --- samo za Browser Mod popup obavijesti;
-   Button-card --- preporučuje se za generirano Override dashboard
    sučelje;
-   Stack-in-card --- preporučuje se za generirano Override dashboard
    sučelje.

## Testirane integracije

OGP je testiran s Home Assistant entityjima koje pruža Huawei Solar te s
različitim vrstama Home Assistant entityja.

Huawei Solar **nije dependency OGP-a**. OGP ne uključuje, ne instalira
niti distribuira izvorni kod Huawei Solar integracije.

## Dokumentacija

-   [`README.md`](README.md) --- pregled projekta
-   [`README_hr.md`](README_hr.md) --- hrvatski pregled
-   [`CONFIGURATION.md`](CONFIGURATION.md) --- detaljna konfiguracija
-   [`CONFIGURATION_hr.md`](CONFIGURATION_hr.md) --- detaljne hrvatske upute

## Verzija

**v1.2.0 --- Stable**

v1.2.0 dodaje zasebne profile obavijesti s Globalnom i obavijesti prema
uređaju, uključujući zasebna Notify i Browser Mod odredišta, odabir
događaja, izbor jezika te upravljanje profilima obavijesti (dodavanje,
uređivanje i brisanje).

## Odricanje od odgovornosti

OGP je pomoćni softver za zaštitu baterijskog sustava od opterećenja u
Home Assistantu. Nije zamjena za sigurnosne funkcije invertera,
baterijskog sustava, električne instalacije ili druge hardverske
zaštite.

Prije oslanjanja na OGP za automatsku zaštitu opterećenja obavezno
testirajte cijeli sustav.
