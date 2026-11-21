---
name: reels-autopilot
description: Agent autonom care transformă un video lung (podcast, vlog, live, interviu, link YouTube sau fișier MP4/MOV) în Reels verticale 9:16 cu subtitrări dinamice în română, le scrie descrierea și hashtag-urile și le programează pe pagina de Facebook prin vidIQ. Folosește-l ori de câte ori utilizatorul vrea reels, shorts, clipuri scurte, „momente bune”, „taie-mi clipuri”, „fă-mi conținut pentru Facebook” dintr-un video mai lung, sau spune doar „/reels” + un link, chiar dacă nu pomenește Facebook sau vidIQ.
---

# Reels Autopilot

Primești un video lung. Livrezi reels gata publicate (sau programate) pe Facebook. Duci singur tot fluxul, de la link la postare, și te oprești o singură dată: utilizatorul aprobă tot lotul dintr-un singur „da”.

## De ce există o singură oprire

Publicarea e publică și nu se poate anula din unealtă. În plus, `vidiq_social_post_publish` acceptă doar aprobarea dată *după* ce utilizatorul a văzut drafturile, nu cererea inițială. Așa că faci tot restul autonom și strângi aprobarea într-un singur pas, ca să-l coste pe utilizator câteva secunde. Nu cere confirmări intermediare („să continui?”, „ce stil vrei?”). Folosește valorile implicite de mai jos.

## Valori implicite (schimbă-le doar dacă utilizatorul cere altceva)

| Setare | Valoare | De ce |
|---|---|---|
| Platformă | Facebook Pages (pagina conectată în vidIQ, ex. „CleverStorm”) | singurul cont conectat cu `canPublish: true` |
| Număr reels | 3 | destul pentru o săptămână, fără să consume tot |
| Durată clip | 30–60 s (`clipDuration: 45`) | Facebook Reels acceptă 3–90 s, iar 30–60 s rețin cel mai bine atenția |
| Subtitrări | `captionStyle: "Hype Mode"`, `videoLanguage: "ro"` | dinamice, cuvânt cu cuvânt, în română |
| Program | câte un reel pe zi, la 19:00 ora României (Europe/Bucharest), începând de mâine | posturile adunate în aceeași zi își fac concurență |

## Fluxul

### 1. Verificări (gratuite)
- `vidiq_social_account_list` cu `platform: "FACEBOOK_PAGES"`. Ia `platformAccountId` al paginii cu `canPublish: true`. Dacă nu există, oferă `reconnect.tool` și oprește-te.
- `vidiq_balance`. Cost estimat = 9 credite × minutele procesate (rotunjit în sus). Dacă nu ajung creditele, **nu porni generarea**. Spune câte credite ar trebui, când se reînnoiesc (`renewableResetsAt`) și propune o secțiune mai scurtă (`processingStartSeconds` / `processingEndSeconds`, minimum 30 s), de exemplu „cele mai bune X minute pe care le permite soldul”.

### 2. Sursa
- **Link YouTube** → îl dai direct ca `videoUrl`.
- **Link public MP4/MOV sau Google Drive** („oricine are linkul”) → `vidiq_video_upload` cu `url`, apoi folosești `videoUrl` rezultat ca `uploadedVideoUrl`.
- **Fișier local în shell** → `vidiq_video_upload` cu `localFile`. Durata o afli cu `ffprobe -v error -show_entries format=duration -of csv=p=0 <fișier>`.
- **Fișier atașat în chat** → `vidiq_file_upload` (deschide un selector de fișiere), apoi `vidiq_video_upload` cu `uploadId`.

Pentru `uploadedVideoUrl` ai nevoie și de `videoDuration` (secunde) și `videoFilename`.

### 3. Generarea clipurilor
`vidiq_generate_clips` cu valorile de mai sus și un `prompt` care cere momente bune pentru reels, de exemplu:

> Alege momente care încep cu un cârlig puternic în primele 3 secunde (o afirmație surprinzătoare, o întrebare, o emoție), care se înțeleg fără context și se termină cu o idee închisă. Evită introducerile, salutările și momentele care depind de ce s-a spus înainte.

Dacă utilizatorul a spus pe ce să se concentreze („părțile amuzante”, „sfaturile despre bani”), adaugă asta în prompt.

Apoi apelează `vidiq_job_poll` cu `mcpJobId` până când `status` nu mai e `inprogress`. Nu folosi `sleep` în foreground. Dacă jobul eșuează, creditele se rambursează automat: spune asta utilizatorului și oprește-te.

### 4. Alegerea clipurilor
Din clipurile generate, păstrează primele N (implicit 3), după:
1. scorul de viralitate, dacă vine în rezultat;
2. cât de tare e cârligul din primele secunde (după titlu sau transcriere);
3. diversitate: nu alege două clipuri despre aceeași idee.

Elimină clipurile sub 3 s sau peste 90 s, pentru că Facebook le respinge.

### 5. Textul fiecărui post (în română)
Scrie-l tu, în tonul vorbitorului:
- **Rândul 1:** cârligul, maximum ~80 de caractere, pentru că doar atât se vede înainte de „Vezi mai mult”.
- **1–2 propoziții** de context sau valoare.
- **Un îndemn** potrivit („Salvează-l pentru mai târziu”, „Tu ce ai fi făcut?”), nu „like & share”.
- **3–5 hashtag-uri** relevante, mixte (ex. `#podcastromania #sfaturi #antreprenoriat`).
- **Fără linkuri**, pentru că Facebook reduce distribuirea reels-urilor cu linkuri.

### 6. Drafturi
Pentru fiecare clip:
1. `vidiq_video_upload` cu `url` = URL-ul clipului → `uploadId`.
2. `vidiq_social_post_draft_create` cu `media: [{type:"video", id: uploadId}]`, `text`, o destinație `FACEBOOK_PAGES` și `publishAt` propriu (ISO 8601 cu fus orar, ex. `2026-11-22T19:00:00+02:00`; atenție la ora de vară, +03:00).

Câte un draft pentru fiecare reel. Dacă un draft vine cu `ready: false`, repară-l cu `vidiq_social_post_draft_update`, nu cu un draft nou. Păstrează `postId` și `revision` pentru fiecare.

### 7. Singura oprire: aprobarea lotului
Arată un tabel compact și întreabă o singură dată:

```
Am pregătit 3 reels pentru pagina CleverStorm:

| # | Când | Durată | Cârlig | Previzualizare |
|---|------|--------|--------|----------------|
| 1 | dum. 22 nov, 19:00 | 0:42 | „Nimeni nu-ți spune asta despre…” | <link clip> |
| 2 | ... |

Răspunde „da” ca să le programez pe toate, sau spune ce schimb (ex. „scoate-l pe 2”, „postează-l pe 1 acum”).
```

La „da”, apelează `vidiq_social_post_publish` pentru fiecare `postId` cu `revision`-ul lui. Dacă cere modificări, fă-le cu `draft_update` și arată din nou doar ce s-a schimbat.

### 8. Raport final
`vidiq_social_post_status` pentru fiecare post. Raportează pe scurt: ce s-a programat sau publicat, când, linkurile live (când există), creditele folosite și cele rămase. Dacă o destinație a eșuat, spune motivul și urmează câmpul `next`, dar nu publica de două ori același conținut.

## Ce să nu faci
- Nu porni generarea fără credite suficiente: un job pornit pe jumătate doar irosește timpul.
- Nu publica fără „da”-ul de la pasul 7 și nu considera cererea inițială drept aprobare.
- Nu inventa statistici sau scoruri care nu vin din unelte.
- Nu folosi OpusClip sau Tella pentru acest flux decât dacă utilizatorul spune că și-a schimbat planul sau a conectat conturi acolo. Altfel apelurile eșuează.
