# OGP -- Upute za konfiguraciju

Detaljne upute za konfiguraciju OGP-a v1.1.3.

## 1. Zahtjevi i opcionalne komponente

Za osnovnu konfiguraciju i zaštitnu funkcionalnost OGP-a nisu potrebni Huawei Solar, Browser Mod, Button-card niti Stack-in-card.

Opcionalne komponente:

- **Browser Mod** -- samo za Browser Mod popup obavijesti.
- **Button-card** -- preporučuje se za generirano Override dashboard sučelje.
- **Stack-in-card** -- preporučuje se za generirano Override dashboard sučelje.

Home Assistant obavijesti ne zahtijevaju Browser Mod i mogu koristiti dostupna odredišta, uključujući Home Assistant Notification panel.

Generirani Lovelace YAML je pomoćni predložak. Nije dependency OGP-a i korisnik ga može slobodno mijenjati.

## 2. Model zaštite

OGP štiti **baterijski sustav, a ne pojedine uređaje**.

Odabrani uređaji su postojeća Home Assistant trošila. OGP ih nadzire i tijekom OFF-GRID rada može ih isključiti.

Odabrane korisničke automatizacije dio su strategije zaštite. OGP pamti njihovo stanje prije zaštite, isključuje odabrane automatizacije koje su bile uključene i nakon recoveryja vraća njihovo prethodno stanje.

Ako se odabrano trošilo ipak uključi tijekom OFF-GRID rada bez aktivnog Overridea, OGP ga ponovno isključuje.

### Race condition -- utrka

Ako korisnička automatizacija nije odabrana, može pokušati uključiti trošilo dok ga OGP pokušava isključiti. To je moguća **race condition (utrka)**.

Odaberite korisničke automatizacije koje tijekom OFF-GRID rada mogu pokrenuti relevantna trošila.

## 3. Centralna konfiguracija

### 3.1 Inverter Off-grid Status

Odaberite entity koji prikazuje režim rada invertera/glavnog uređaja.

Prepoznata OFF-GRID stanja:

- `off_grid`
- `offgrid`
- `island`
- `islanding`

Prepoznata ON-GRID stanja:

- `on_grid`
- `ongrid`
- `grid`
- `normal`
- `connected`

Ostala ili nedostupna stanja tretiraju se kao `UNKNOWN`.

### 3.2 Power Meter Status

Odaberite entity statusa power metera koji se koristi kao dodatna potvrda.

Ako Power Meter Status postane `unknown` ili `unavailable`, OGP to tretira kao potvrdu da je inverter/glavni uređaj OFF-GRID. To je namjerno jer tijekom prijelaza u OFF-GRID power meter može izgubiti komunikaciju ili napajanje.

### 3.3 Recovery delay

Postavite centralnu odgodu koja se koristi nakon povratka na ON-GRID kako bi se sustav stabilizirao prije recoveryja.

Ovo se razlikuje od Recovery timeouta pojedinog uređaja.

### 3.4 Logovi

Centralna konfiguracija omogućuje tri razine OGP logiranja:

- **Isključeno** -- OGP ne šalje operativne logove.
- **Upozorenja** -- bilježe se važni događaji i greške.
- **Debug** -- uz upozorenja i greške bilježe se i detaljne dijagnostičke poruke.

**Debug** koristite tijekom početne konfiguracije, testiranja i dijagnostike. Nakon uspješnog testiranja preporučuje se **Isključeno** ili **Upozorenja**.

OGP postavka je glavni prekidač za OGP operativno logiranje. Postavljanje Home Assistant loggera na DEBUG ne uključuje OGP poruke ako je OGP Logiranje isključeno.

### 3.5 Obavijesti

Obavijesti su opcionalne.

Centralna konfiguracija obavijesti otvara se kao **Obavijesti o stanju napajanja**.

Omogućene su opcije:

- **Pošalji obavijest**;
- **Primatelji obavijesti**;
- **Prikaži Browser Mod popup**;
- **Browser Mod uređaji**;
- kategorije obavijesti za status mreže, zaštitu/Override i sigurnost;
- hrvatski ili engleski jezik obavijesti.

Konfiguracija obavijesti sprema se odvojeno od Centralne konfiguracije i ostaje sačuvana kada se promijeni Centralna konfiguracija ili restartira Home Assistant.

U v1.1.3 odabrane kategorije obavijesti primjenjuju se globalno na konfigurirana notification i Browser Mod odredišta. Pojedinačno usmjeravanje različitih kategorija na različite uređaje nije dio ove verzije.

### 3.6 Browser Mod popup

Browser Mod popup je opcionalan.

Uključite ga samo ako je Browser Mod instaliran i želite popup prikaz.

Normalne Home Assistant obavijesti ne zahtijevaju Browser Mod.

## 4. Konfiguracija Device Entryja

Odabrano trošilo konfigurira se kao zaseban OGP Device Entry. Svaki Device Entry sadrži glavni Home Assistant entity koji OGP treba nadzirati i kontrolirati tijekom zaštite baterijskog sustava.

### 4.1 Glavni entity

Odaberite postojeći glavni Home Assistant entity. Entity koji je već konfiguriran kao glavni entity drugog OGP Device Entryja više se ne nudi za odabir.

### 4.2 OFF stanje

Konfigurirajte stanje koje predstavlja da je trošilo OFF.

### 4.3 Korisničke automatizacije

Odaberite postojeće korisničke automatizacije koje mogu pokrenuti ovo trošilo tijekom OFF-GRID rada.

OGP sprema stanje odabranih automatizacija prije zaštite, isključuje one koje su bile uključene i tijekom recoveryja vraća njihovo prethodno stanje.

Utječu samo odabrane automatizacije.

### 4.4 Wait if unavailable

**Uključite ovo kada trošilo tijekom prijelaza u OFF-GRID može izgubiti vlastito napajanje ili komunikaciju.**

Trošilo može postati `unavailable` zato što je izgubilo vlastito napajanje.

Kada je ova opcija uključena, OGP čeka da se trošilo vrati kako bi se potrebno gašenje/zaključavanje moglo provjeriti i završiti.

Preporučuje se UPS za Home Assistant i mrežnu/komunikacijsku opremu, ali samo trošilo i dalje može izgubiti napajanje.

### 4.5 Recovery timeout

Ovo je timeout za povratak odabranog trošila i završetak potrebnog slijeda gašenja/zaključavanja.

Ako se trošilo ne vrati unutar tog vremena, OGP javlja da se trošilo nije moglo ugasiti i zaključati.

Korisnik mora ručno isključiti trošilo. Kada OGP može potvrditi OFF stanje, trošilo može prijeći u zaključano stanje.

### 4.6 Command timeout

Postavite koliko dugo OGP čeka izvršenje naredbe uređaja.

Vrijednost prilagodite uređaju i njegovoj Home Assistant integraciji.

## 5. Postavke uređaja i Lovelace YAML

Svaki OGP Device Entry ima vlastite postavke.

Device Entry može se ponovno konfigurirati bez promjene Central Entryja.

### 5.1 Ponovno generiranje Lovelace YAML-a

Koristite **Regenerate Lovelace YAML** u postavkama Device Entryja kada je generirani dashboard YAML slučajno uklonjen ili ga treba ponovno generirati.

Jezik YAML-a može biti English ili Hrvatski.

Ponovno generiranje YAML-a ne stvara niti ponovno konfigurira Device Entry.

Pri dodavanju novog Device Entryja generiranje Lovelace YAML-a je opcionalno. Ako opcija nije odabrana, Device Entry se i dalje normalno kreira.

### 5.2 Brisanje Device Entryja

Brisanje Device Entryja koristi izvorno Home Assistant brisanje Config Entryja.

Brisanje Device Entryja ne briše Central Entry niti druge OGP Device Entryje.

## 6. Override

Override je funkcija OGP-a i ne zahtijeva Browser Mod, Button-card niti Stack-in-card.

Override koristi:

- podesivo trajanje;
- PIN zaštitu.

Override ne uključuje automatski trošilo. Nakon prihvaćenog Overridea korisnik ga može ručno uključiti ili isključiti.

Generirano Lovelace Override sučelje omogućuje unos PIN-a i aktivaciju Overridea. PIN se može potvrditi normalnom tipkom Enter ili generiranom akcijom.

### Override dashboard

Button-card i Stack-in-card su opcionalne dashboard komponente koje se preporučuju za generirano Lovelace Override sučelje.

Generirani YAML je samo početni predložak i može se mijenjati.

## 7. Generirani Lovelace YAML

Pri kreiranju odabranog trošila OGP može generirati Lovelace YAML predložak.

Predložak može koristiti:

- Browser Mod;
- Button-card;
- Stack-in-card.

OGP ih ne instalira.

Ako potrebna custom kartica nije instalirana, taj dio dashboarda neće se ispravno prikazati. To ne sprječava konfiguraciju OGP-a niti njegovu osnovnu zaštitnu funkcionalnost.

## 8. Sekvenca OFF-GRID zaštite

Kada se potvrdi OFF-GRID rad:

1. potvrđuje se OFF-GRID stanje;
2. sprema se trenutno stanje odabranih korisničkih automatizacija;
3. isključuju se odabrane automatizacije koje su bile uključene;
4. provjerava se stanje odabranih trošila;
5. odabrana trošila se isključuju kada je potrebno;
6. nastavlja se njihov nadzor;
7. ako se trošilo uključi bez aktivnog Overridea, ponovno se isključuje;
8. nedostupna trošila obrađuju se prema konfiguraciji;
9. zaštita baterijskog sustava ostaje aktivna tijekom OFF-GRID rada.

## 9. Recovery sekvenca

Kada se potvrdi ON-GRID:

1. pokreće se recovery;
2. čeka se centralni Recovery delay;
3. potvrđuje se stabilan ON-GRID;
4. osvježava se stanje odabranih trošila i zaštite;
5. odabrane korisničke automatizacije vraćaju se u stanje koje su imale prije zaštite;
6. zaštitni ciklus se briše.

Ako se tijekom recoveryja ponovno pojavi OFF-GRID, zaštita baterijskog sustava ima prednost.

## 10. Huawei Solar i druge integracije

OGP je tijekom razvoja testiran s entityjima koje pruža Huawei Solar integracija.

Huawei Solar **nije dependency OGP-a**. OGP ne uključuje, ne instalira niti distribuira izvorni kod Huawei Solar integracije.

Isti princip vrijedi za druge Home Assistant integracije. OGP je projektiran za rad s Home Assistant entityjima koji pružaju potrebna stanja i servise.

## 11. Testiranje

Prije oslanjanja na OGP u energetskom sustavu testirajte:

- ON-GRID detekciju;
- OFF-GRID detekciju;
- potvrdu Power Meter Statusa;
- OFF upravljanje odabranim trošilom;
- isključivanje odabranih automatizacija;
- vraćanje automatizacija;
- ponovno izvršavanje gašenja;
- ponašanje kada trošilo postane unavailable;
- Recovery timeout;
- recovery nakon ON-GRID povratka;
- Override s ispravnim PIN-om;
- Override s pogrešnim PIN-om;
- trajanje i istek Overridea;
- Home Assistant obavijesti;
- Browser Mod popup ako je uključen;
- odabir kategorija obavijesti;
- očuvanje notification postavki nakon promjene Centralne konfiguracije;
- očuvanje notification postavki nakon restarta Home Assistanta;
- generirano Lovelace sučelje ako se koristi;
- ponašanje Logova: Isključeno / Upozorenja / Debug.

Za detaljnu dijagnostiku postavite OGP Logove na **Debug** i po potrebi Home Assistant logger za `custom_components.off_grid_protection` na DEBUG. Nakon testiranja vratite OGP Logove na Isključeno ili Upozorenja.

## 12. Rješavanje problema

### Trošilo se ne isključuje

Provjerite odabrani entity, OFF stanje, dostupnost, Home Assistant servis, Command timeout i integraciju uređaja.

### Trošilo se ponovno uključuje tijekom OFF-GRID rada

Provjerite je li automatizacija koja ga pokreće odabrana u OGP-u. Odabir relevantnih automatizacija preporučuje se radi smanjenja mogućnosti race conditiona.

### Trošilo postaje unavailable

Provjerite napajanje, **Wait if unavailable**, Recovery timeout te dostupnost Home Assistanta i mreže.

### Nema obavijesti

Provjerite je li slanje obavijesti uključeno, postoji li barem jedan notification primatelj i je li odgovarajuća kategorija obavijesti uključena.

### Nema popupa

Provjerite Browser Mod, konfiguraciju popupova, odabrane Browser Mod uređaje i dostupnost Browser Mod klijenta.

Normalne Home Assistant obavijesti ne zahtijevaju Browser Mod.

### Notification postavke nestanu nakon promjene Centralne konfiguracije

U v1.1.3 konfiguracija obavijesti sprema se odvojeno i ne smije se brisati promjenom Centralne konfiguracije. Ako nestane, provjerite OGP logove i stanje Config Entryja.

### Lovelace se ne prikazuje

Provjerite koristi li generirani YAML Button-card, Stack-in-card ili Browser Mod koji nisu instalirani. Instalirajte ih ili prilagodite YAML.

### Previše logova

Za normalan rad koristite **Upozorenja** ili nakon testiranja **Isključeno**. **Debug** koristite samo kada su potrebni detaljni dijagnostički podaci.

## 13. Pravilo verzioniranja

**v1.1.3 je zaključana stabilna verzija.**

Budući razvoj koristi novi broj verzije, primjerice:

- `v1.1.4` -- bugfix
- `v1.2.0` -- nova funkcionalnost

Release v1.1.3 ostaje točna referenca na testiranu stabilnu verziju.
