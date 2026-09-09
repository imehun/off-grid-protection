# OGP --- Upute za konfiguraciju

Detaljne upute za konfiguraciju OGP-a v1.2.1.

## Promjene u V1.2.1

V1.2.1 donosi sljedeće operativne promjene:

- Ponovno omogućavanje centralne OGP integracije stvara Home Assistant
  Repair zahtjev za ispravno ponovno učitavanje integracije.
- Home Assistant se restartira tek nakon korisničke potvrde Repair
  Fix/Submit radnje.
- OGP Settings su blokirane dok je aktivna OFF-GRID zaštita.
- Ikona integracije je smanjena i optimizirana radi bržeg učitavanja.
- Repair i Settings-lock poruke prevedene su na engleski i hrvatski.

Protection, shutdown, recovery i Override logika ostaju nepromijenjene
u odnosu na V1.2.0.


## 1. Zahtjevi i opcionalne komponente

Za osnovnu konfiguraciju i zaštitnu funkcionalnost OGP-a nisu potrebni
Huawei Solar, Browser Mod, Button-card niti Stack-in-card.

Opcionalne komponente:

-   **Browser Mod** --- samo za Browser Mod popup obavijesti.
-   **Button-card** --- preporučuje se za generirano Override dashboard
    sučelje.
-   **Stack-in-card** --- preporučuje se za generirano Override
    dashboard sučelje.

Home Assistant obavijesti ne zahtijevaju Browser Mod.

Generirani Lovelace YAML je pomoćni predložak. Nije dependency OGP-a i
korisnik ga može slobodno mijenjati.

## 2. Model zaštite

OGP štiti **baterijski sustav**, a ne korisničke Home Assistant ovlasti.

Svaki OGP Device Entry je neovisan.

Ako je Device Entry disabled, OGP njime ne upravlja. Ostali enabled
Device Entryji nastavljaju normalno raditi.

Kod standardnih uređaja odabrane korisničke automatizacije dio su
strategije zaštite. OGP sprema njihovo stanje prije zaštite, isključuje
odabrane automatizacije koje su bile uključene i nakon recoveryja vraća
njihovo prethodno stanje.

Ako se zaštićeno trošilo tijekom OFF-GRID rada uključi bez aktivnog
Overridea, OGP ponovno izvršava konfiguriranu radnju gašenja.

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
tretira kao potvrdu da je inverter/glavni uređaj OFF-GRID. To je
namjerno jer tijekom prijelaza u OFF-GRID power meter može izgubiti
komunikaciju ili napajanje.

### 3.3 Recovery delay

Postavite centralnu odgodu koja se koristi nakon povratka na ON-GRID
kako bi se sustav stabilizirao prije recoveryja.

To se razlikuje od Recovery timeouta pojedinog uređaja.

### 3.4 Logovi

Centralno OGP logiranje može biti:

-   Isključeno
-   Upozorenja
-   Debug

Debug je namijenjen konfiguraciji, testiranju i dijagnostici.

### 3.5 Obavijesti

Obavijesti su opcionalne i upravljaju se kao zasebni profili obavijesti.
U **Options → Notifications** možete vidjeti postojeće profile, dodati
novi profil, urediti postojeći ili ga obrisati.

OGP podržava dvije vrste profila obavijesti.

#### Globalna obavijest

Može postojati samo jedna Globalna obavijest. Kod kreiranja ili uređivanja
odabire se:

-   **Status mreže**;
-   **Zaštita / Override**;
-   **Sigurnost**;
-   jezik obavijesti (**Hrvatski** ili **English**).

Globalna obavijest uvijek koristi ugrađenu Home Assistant uslugu
`persistent_notification`. Ne koristi Browser Mod i ne zahtijeva odabir
notification odredišta.

#### Obavijest prema uređaju

Može postojati više obavijesti prema uređaju. Svaki profil ima vlastito
odredište, odabir događaja i jezik. Vrsta odredišta može biti:

-   **Notify** --- jedno Home Assistant notification odredište;
-   **Browser Mod** --- jedan Browser Mod uređaj.

Za svaki profil zasebno mogu se odabrati Status mreže, Zaštita / Override
i Sigurnost te Hrvatski ili English jezik.

Lista obavijesti služi za neovisno upravljanje profilima. Uređivanje\ mijenja samo odabrani profil. Brisanje profila uklanja njegovu generiranu
automatizaciju. Ako Globalna obavijest već postoji, pri dodavanju nove
obavijesti Globalna opcija više nije ponuđena.

Postavke obavijesti spremaju se odvojeno i ostaju sačuvane kroz promjene
centralne konfiguracije i restart Home Assistanta.

Ako se promijene OGP postavke, OGP može prikazati trajnu Home Assistant
obavijest koja preporučuje restart Home Assistanta. OGP ne radi restart
automatski.

Početni prijelaz `unavailable`/`unknown` → valjano stanje mreže nakon
pokretanja Home Assistanta potiskuje se kako se ne bi javila lažna
obavijest o promjeni mrežnog stanja.

## 3.6 Settings tijekom OFF-GRID zaštite

OGP Settings nije moguće mijenjati dok je aktivna OFF-GRID zaštita.

Blokada vrijedi za centralnu i Device Entry konfiguraciju, uključujući
postavke obavijesti. Time se sprječava promjena konfiguracije i ponovno
učitavanje OGP-a tijekom aktivnog zaštitnog ciklusa.

Ako su Settings već otvorene prije početka OFF-GRID zaštite, kasniji
Submit također se odbija dok je zaštita aktivna.

Settings ponovno postaju dostupne nakon završetka OFF-GRID zaštitnog
ciklusa i recoveryja.

## 3.7 Ponovno omogućavanje centralnog OGP entryja

Ako se centralni OGP entry onemogući i zatim ponovno omogući, Home
Assistant može zahtijevati potpuni restart kako bi se svi OGP Device
Entryji ponovno ispravno učitali.

OGP stvara Home Assistant Repair zahtjev koji preporučuje restart.

Restart nije automatski. Korisnik mora otvoriti Repair, odabrati
popravak i potvrditi ga. Ako se popravak ne potvrdi, Repair zahtjev
ostaje aktivan.

Ovo ne mijenja OGP protection, shutdown, recovery niti Override
sekvencu.

## 4. Konfiguracija Device Entryja

Svako zaštićeno trošilo konfigurira se kao zaseban OGP Device Entry.

### 4.1 Enabled / Disabled

Pojedini Device Entry može se onemogučiti bez onemogučavanja centralnog OGP
entryja.

Kada je Device Entry disabled, OGP:

-   ne upravlja uređajem;
-   ne gasi uređaj;
-   ne izvršava safety reassertion;
-   ne izvršava Override/recovery radnje nad njim;
-   ne uključuje uređaj u aktivni protection ciklus.

Uređaj i dalje ostaje dostupan Home Assistantu i drugim integracijama.

Ovo je posebno korisno tijekom developmenta, testiranja i održavanja
kada se određeni stvarni uređaj želi potpuno izuzeti iz OGP upravljanja.

### 4.2 Device entity

Kod Switch i Climate uređaja odaberite glavni entity koji OGP treba
nadzirati i kontrolirati.

Kod Custom Devicea to je **Device entity** --- entity koji OGP gasi i
čije stanje nastavlja pratiti tijekom zaštite.

Custom Device entity je potpuno generički i nije ograničen na određeni
Home Assistant domain.

### 4.3 OFF stanje

Konfigurirajte stanje koje predstavlja da je Device entity OFF.

### 4.4 Korisničke automatizacije

Kod standardnih Switch i Climate uređaja odaberite postojeće korisničke
automatizacije koje mogu pokrenuti uređaj tijekom OFF-GRID rada.

OGP sprema njihovo stanje prije zaštite, isključuje one koje su bile
uključene i nakon recoveryja vraća njihovo prethodno stanje.

Utječu samo odabrane automatizacije.

Custom Device za svoj Control entity ne zahtijeva ovaj odabir
automatizacija.

### 4.5 Custom Control entity

Custom Device ima zaseban **Control entity**.

Control entity je potpuno generički i može biti bilo koji Home Assistant
entity koji odgovara korisnikovoj upravljačkoj logici.

Tijekom OFF-GRID zaštite:

1.  OGP napravi snapshot stanja Control entityja;
2.  izvrši postojeći OGP redoslijed gašenja Device entityja;
3.  isključi Control entity;
4.  nastavlja nadzirati Device entity.

Control entity može predstavljati cijelu vanjsku integraciju
upravljanja. Zato OGP ne mora znati niti upravljati svakom pojedinom
automatizacijom te integracije.

### 4.6 Custom recovery radnja

Za Custom Device odaberite:

-   **Stay OFF** --- Control entity ostaje OFF nakon recoveryja.
-   **Turn ON** --- Control entity se uključi nakon normalnog recovery
    slijeda.

Sam Device entity ostaje OFF prema standardnom OGP recovery modelu.

### 4.7 Wait if unavailable

Uključite kada uređaj tijekom prijelaza u OFF-GRID može izgubiti
vlastito napajanje ili komunikaciju.

### 4.8 Recovery timeout

Postavite koliko dugo OGP čeka potreban status uređaja i završetak
potrebnog slijeda zaštite.

Ako se uređaj ne može sigurno isključiti i zaključati unutar
postavljenog timeouta, OGP prijavljuje neuspjeh i korisnik ga mora ručno
isključiti.

### 4.9 Command timeout

Postavite koliko dugo OGP čeka izvršenje naredbe uređaja.

## 5. Override

Override je privremena iznimka od aktivne OFF-GRID zaštite.

Može koristiti:

-   minimalno trajanje;
-   maksimalno trajanje;
-   traženo trajanje;
-   PIN zaštitu.

Override ne uključuje automatski uređaj. Korisnik odlučuje hoće li ga
stvarno uključiti.

Dok je Override aktivan, normalni safety reassertion za taj uređaj
namjerno je izuzet.

Kada Override istekne, zaštita se vraća i uređaj koji je ON ponovno se
gasi.

## 6. OFF-GRID sekvenca zaštite

Kada se potvrdi OFF-GRID:

1.  OGP potvrđuje OFF-GRID stanje;
2.  kod standardnih uređaja radi snapshot odabranih korisničkih
    automatizacija;
3.  isključuju se odabrane automatizacije koje su bile uključene;
4.  provjerava se stanje uređaja;
5.  izvršavaju se potrebne radnje gašenja;
6.  kod Custom Devicea nakon snapshota Control entity se također
    isključuje;
7.  zaštita ostaje aktivna;
8.  zaštićeni uređaji nastavljaju se nadzirati;
9.  ako se zaštićeni Device entity uključi bez Overridea, OGP ponovno
    izvršava njegovu radnju gašenja;
10. neuspjeh sigurnog gašenja obrađuje se kroz postojeći timeout/failure
    mehanizam.

## 7. Recovery sekvenca

Kada se potvrdi ON-GRID:

1.  pokreće se recovery;
2.  primjenjuje se centralni Recovery delay;
3.  potvrđuje se stabilan ON-GRID;
4.  osvježava se stanje uređaja i zaštite;
5.  kod standardnih uređaja odabrane automatizacije vraćaju se u stanje
    koje su imale prije zaštite;
6.  kod Custom Devicea Control entity slijedi odabranu recovery radnju;
7.  Device entity ostaje OFF prema standardnom OGP recovery modelu;
8.  zaštitni ciklus se briše.

Ako se tijekom recoveryja ponovno pojavi OFF-GRID, zaštita baterijskog
sustava ima prednost.

## 8. Safety reassertion i neuspjeh gašenja

OGP se ne oslanja samo na jednu naredbu za gašenje.

Dok je zaštita aktivna, OGP nastavlja nadzirati zaštićene Device
entityje.

Ako se zaštićeni uređaj uključi bez Overridea, OGP ponovno izvršava
konfiguriranu radnju gašenja.

Ako se uređaj ne može sigurno isključiti ili potvrditi kao OFF unutar
odgovarajućeg timeouta, OGP javlja da uređaj nije moguće sigurno
isključiti i zaključati. Korisnik ga mora ručno isključiti.

Override je namjerna iznimka od safety reassertiona.

## 9. Generirani Lovelace YAML

Generirani Lovelace YAML je početni predložak.

Može koristiti Browser Mod, Button-card i Stack-in-card, ali oni nisu
dependency osnovne OGP zaštitne funkcionalnosti.

Custom Device YAML može zahtijevati prilagodbu stvarnom Device entityju
i željenom sučelju.

## 10. Brisanje uređaja i vlasništvo nad resursima

OGP prati resurse koje sam generira.

Pri brisanju Device Entryja OGP uklanja samo resurse koji su
evidentirani kao OGP-generirani.

Postojeći korisnički resursi ne brišu se samo zato što ih OGP koristi
ili odabire.

## 11. Testiranje

Prije oslanjanja na OGP testirajte:

-   ON-GRID detekciju;
-   OFF-GRID detekciju;
-   Power Meter Status potvrdu;
-   standardni Switch protection;
-   standardni Climate protection;
-   Custom Device protection;
-   snapshot i OFF Control entityja;
-   Custom recovery Stay OFF;
-   Custom recovery Turn ON;
-   ponašanje disabled Device Entryja;
-   safety reassertion;
-   failure/timeout obavijest;
-   Override;
-   istek Overridea;
-   ON-GRID recovery;
-   trajnost notification postavki;
-   potiskivanje početne startup obavijesti;
-   preporuku za restart nakon promjene postavki;
-   generirani Lovelace UI ako se koristi.

## 12. Rješavanje problema

### Uređajem se ne upravlja

Provjerite je li Device Entry enabled, je li entity ispravan, je li OFF
stanje ispravno, je li entity dostupan i podržava li odabranu Home
Assistant radnju.

### Uređaj se ponovno uključi tijekom OFF-GRID rada

Provjerite safety reassertion logove i je li aktivan Override.

### Custom Device ne isključuje vanjski sustav upravljanja

Provjerite Control entity. Mora biti entity koji predstavlja stanje
uključeno/isključeno vanjskog sustava upravljanja.

### Custom Device ne vraća vanjsko upravljanje

Provjerite da je Custom recovery postavljen na **Turn ON** i da Control
entity podržava ON radnju.

### Uređaj se ne može sigurno isključiti

Provjerite entity, OFF stanje, Command timeout, Recovery timeout i
integraciju uređaja. Ako OGP prijavi neuspjeh gašenja, uređaj treba
ručno isključiti.

### Previše logova

Nakon testiranja koristite Upozorenja ili Isključeno. Debug koristite za
dijagnostiku.
