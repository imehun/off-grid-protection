# OGP -- Upute za konfiguraciju

Detaljne upute za konfiguraciju OGP-a v1.1.0.

## 1. Zahtjevi i opcionalne komponente

Za osnovnu konfiguraciju i zaštitnu funkcionalnost OGP-a nisu potrebni
Huawei Solar, Browser Mod, Button-card niti Stack-in-card.

Opcionalne komponente:

-   **Browser Mod** -- samo za Browser Mod popup obavijesti.
-   **Button-card** -- preporučuje se za generirano Override dashboard
    sučelje.
-   **Stack-in-card** -- preporučuje se za generirano Override dashboard
    sučelje.

Home Assistant obavijesti ne zahtijevaju Browser Mod i mogu koristiti
dostupna odredišta, uključujući Home Assistant Notification panel.

Generirani Lovelace YAML je pomoćni predložak. Nije dependency OGP-a i
korisnik ga može slobodno mijenjati.

## 2. Model zaštite

OGP štiti **baterijski sustav, a ne pojedine uređaje**.

Odabrani uređaji su postojeća Home Assistant trošila. OGP ih nadzire i
tijekom OFF-GRID rada može ih isključiti.

Odabrane korisničke automatizacije dio su strategije zaštite. OGP pamti
njihovo stanje prije zaštite, isključuje odabrane automatizacije koje su
bile uključene i nakon recoveryja vraća njihovo prethodno stanje.

Time se sprječava da korisnička automatizacija pokuša pokrenuti trošilo
dok je aktivna zaštita baterijskog sustava.

Ako se odabrano trošilo ipak uključi tijekom OFF-GRID rada bez aktivnog
Overridea, OGP ga ponovno isključuje.

### Race condition -- utrka

Ako korisnička automatizacija nije odabrana, može pokušati uključiti
trošilo dok ga OGP pokušava isključiti. To je moguća **race condition
(utrka)**.

Odaberite korisničke automatizacije koje tijekom OFF-GRID rada mogu
pokrenuti relevantna trošila.

## 3. Centralna konfiguracija

### 3.1 Inverter Off-grid Status

Odaberite entity koji prikazuje režim rada invertera/glavnog uređaja.

Prepoznata OFF-GRID stanja:

-   `off_grid`
-   `offgrid`
-   `island`
-   `islanding`

Prepoznata ON-GRID stanja:

-   `on_grid`
-   `ongrid`
-   `grid`
-   `normal`
-   `connected`

Ostala ili nedostupna stanja tretiraju se kao `UNKNOWN`.

### 3.2 Power Meter Status

Odaberite entity statusa power metera koji se koristi kao dodatna
potvrda.

Ako Power Meter Status postane `unknown` ili `unavailable`, OGP to
tretira kao potvrdu da je inverter/glavni uređaj OFF-GRID.

To je namjerno jer tijekom prijelaza u OFF-GRID power meter može
izgubiti komunikaciju ili napajanje.

### 3.3 Recovery delay

Postavite centralnu odgodu koja se koristi nakon povratka na ON-GRID
kako bi se sustav stabilizirao prije recoveryja.

Ovo se razlikuje od Recovery timeouta pojedinog uređaja.

### 3.4 Obavijesti

Obavijesti su opcionalne.

Odaberite dostupno Home Assistant odredište, primjerice:

-   Home Assistant Notification panel;
-   servis za mobilne obavijesti;
-   drugi podržani notification servis.

Browser Mod nije potreban za ove obavijesti.

### 3.5 Browser Mod popup

Browser Mod popup je opcionalan.

Uključite ga samo ako je Browser Mod instaliran i želite popup prikaz.

## 4. Dodavanje odabranog trošila

Dodajte Home Assistant uređaj/entity koji OGP treba nadzirati i
kontrolirati tijekom zaštite baterijskog sustava.

### 4.1 Uređaj

Odaberite postojeći Home Assistant uređaj/entity.

### 4.2 OFF stanje

Konfigurirajte stanje koje predstavlja da je trošilo OFF.

### 4.3 Korisničke automatizacije

Odaberite postojeće korisničke automatizacije koje mogu pokrenuti ovo
trošilo tijekom OFF-GRID rada.

OGP sprema stanje odabranih automatizacija prije zaštite, isključuje one
koje su bile uključene i tijekom recoveryja vraća njihovo prethodno
stanje.

Odnosi se samo na odabrane automatizacije.

### 4.4 Wait if unavailable

**Uključite kada trošilo tijekom prijelaza u OFF-GRID može izgubiti
vlastito napajanje ili komunikaciju.**

Trošilo može postati `unavailable` zato što je izgubilo vlastito
napajanje.

Kada je opcija uključena, OGP čeka da se trošilo vrati kako bi se moglo
provjeriti i dovršiti potrebno gašenje/zaključavanje.

UPS napajanje preporučuje se za Home Assistant i mrežnu/komunikacijsku
opremu, ali samo trošilo i dalje može izgubiti napajanje.

### 4.5 Recovery timeout

Ovo je timeout za povratak odabranog trošila i dovršetak potrebne
sekvence gašenja/zaključavanja.

Ako se ne vrati u tom vremenu, OGP javlja da trošilo nije bilo moguće
ugasiti i zaključati.

Korisnik tada mora ručno isključiti trošilo. Kada OGP potvrdi OFF
stanje, trošilo može prijeći u zaključano stanje.

### 4.6 Command timeout

Postavite koliko dugo OGP čeka izvršenje naredbe uređaja.

Vrijednost prilagodite uređaju i njegovoj Home Assistant integraciji.

## 5. Override

Override je funkcija OGP-a i ne zahtijeva Browser Mod, Button-card niti
Stack-in-card.

Override koristi:

-   podesivo trajanje;
-   PIN zaštitu.

Override ne uključuje automatski trošilo. Nakon prihvaćenog Overridea
korisnik ga može ručno uključiti ili isključiti.

Override se može izravno testirati putem Home Assistant alata za
pozivanje servisa/akcija.

### Override dashboard

Button-card i Stack-in-card su opcionalne dashboard komponente koje se
preporučuju za generirano Lovelace Override sučelje.

Generirani YAML je samo početni predložak i može se mijenjati.

## 6. Generirani Lovelace YAML

Pri kreiranju odabranog trošila OGP može generirati Lovelace YAML
predložak.

Predložak može koristiti:

-   Browser Mod;
-   Button-card;
-   Stack-in-card.

OGP ih ne instalira.

Ako potrebna custom kartica nije instalirana, taj dio dashboarda neće se
ispravno prikazati. To ne sprječava konfiguraciju OGP-a niti njegovu
osnovnu zaštitnu funkcionalnost.

## 7. Sekvenca OFF-GRID zaštite

Kada se potvrdi OFF-GRID rad:

1.  potvrđuje se OFF-GRID stanje;
2.  sprema se trenutno stanje odabranih korisničkih automatizacija;
3.  isključuju se odabrane automatizacije koje su bile uključene;
4.  provjerava se stanje odabranih trošila;
5.  odabrana trošila se isključuju kada je potrebno;
6.  nastavlja se njihov nadzor;
7.  ako se trošilo uključi bez aktivnog Overridea, ponovno se
    isključuje;
8.  nedostupna trošila obrađuju se prema konfiguraciji;
9.  zaštita baterijskog sustava ostaje aktivna tijekom OFF-GRID rada.

## 8. Recovery sekvenca

Kada se potvrdi ON-GRID:

1.  pokreće se recovery;
2.  čeka se centralni Recovery delay;
3.  potvrđuje se stabilan ON-GRID;
4.  osvježava se stanje odabranih trošila i zaštite;
5.  odabrane korisničke automatizacije vraćaju se u stanje koje su imale
    prije zaštite;
6.  zaštitni ciklus se briše.

Ako se tijekom recoveryja ponovno pojavi OFF-GRID, zaštita baterijskog
sustava ima prednost.

## 9. Huawei Solar i druge integracije

OGP je tijekom razvoja testiran s entityjima koje pruža Huawei Solar
integracija.

Huawei Solar **nije dependency OGP-a**. OGP ne uključuje, ne instalira
niti distribuira izvorni kod Huawei Solar integracije.

Isti princip vrijedi za druge Home Assistant integracije. OGP je
projektiran za rad s Home Assistant entityjima koji pružaju potrebna
stanja i servise.

## 10. Testiranje

Prije oslanjanja na OGP u energetskom sustavu testirajte:

-   ON-GRID detekciju;
-   OFF-GRID detekciju;
-   potvrdu Power Meter Statusa;
-   OFF upravljanje odabranim trošilom;
-   isključivanje odabranih automatizacija;
-   vraćanje automatizacija;
-   ponovno izvršavanje gašenja;
-   ponašanje kada trošilo postane unavailable;
-   Recovery timeout;
-   recovery nakon ON-GRID povratka;
-   Override s ispravnim i pogrešnim PIN-om;
-   Home Assistant obavijesti;
-   Browser Mod popup ako je uključen;
-   generirano Lovelace sučelje ako se koristi.

## 11. Rješavanje problema

### Trošilo se ne isključuje

Provjerite odabrani entity, OFF stanje, dostupnost, Home Assistant
servis, Command timeout i integraciju uređaja.

### Trošilo se ponovno uključuje tijekom OFF-GRID rada

Provjerite je li automatizacija koja ga pokreće odabrana u OGP-u. Odabir
relevantnih automatizacija preporučuje se radi smanjenja mogućnosti race
conditiona.

### Trošilo postaje unavailable

Provjerite napajanje, **Wait if unavailable**, Recovery timeout te
dostupnost Home Assistanta i mreže.

### Nema popupa

Provjerite Browser Mod, konfiguraciju popupova i dostupnost Browser Mod
klijenta.

Normalne Home Assistant obavijesti ne zahtijevaju Browser Mod.

### Lovelace se ne prikazuje

Provjerite koristi li generirani YAML Button-card, Stack-in-card ili
Browser Mod koji nisu instalirani. Instalirajte ih ili prilagodite YAML.

## 12. Pravilo verzioniranja

**v1.1.0 je zaključana stabilna verzija.**

Budući razvoj koristi novi broj verzije, primjerice:

-   `v1.1.1` -- bugfix
-   `v1.2.0` -- nova funkcionalnost

Release v1.1.0 ostaje točna referenca na testiranu stabilnu verziju.
