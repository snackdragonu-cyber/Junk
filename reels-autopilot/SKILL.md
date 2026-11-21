---
name: reels-autopilot
description: Agent autonom care transformă un video lung (podcast, vlog, live, interviu, link YouTube sau fișier MP4/MOV) în Reels verticale 9:16 montate complet automat — alege momentele, taie pauzele, reîncadrează pe vertical, adaugă subtitrări dinamice în română cuvânt cu cuvânt — scrie descrierea și hashtag-urile și le programează pe pagina de Facebook. Folosește-l ori de câte ori utilizatorul vrea reels, shorts, clipuri scurte, „momente bune”, „taie-mi clipuri”, „pune subtitrări”, „fă-mi conținut pentru Facebook” dintr-un video mai lung, sau dă doar un link/fișier video cu „/reels”, chiar dacă nu pomenește Facebook sau vidIQ.
---

# Reels Autopilot

Primești un video lung. Livrezi reels montate și programate pe Facebook. Montajul (alegerea momentelor, tăieturile, subtitrările) îl faci **complet automat, fără nicio întrebare**. Te oprești o singură dată, înainte de publicare: utilizatorul aprobă tot lotul dintr-un singur „da”.

## De ce o singură oprire și unde e ea

Montajul e reversibil, deci nu cere nimic: nu întreba de stil, număr de clipuri sau dacă să continui. Folosește valorile implicite de mai jos. Publicarea e publică și nu se poate anula din unealtă, iar `vidiq_social_post_publish` acceptă doar o aprobare dată *după* ce utilizatorul a văzut drafturile, nu cererea inițială. Așa că strângi aprobarea într-un singur pas, la final.

## Valori implicite (schimbă-le doar la cerere)

| Setare | Valoare |
|---|---|
| Motor de montaj | **local** (ffmpeg + Whisper, gratuit). vidIQ doar dacă localul nu poate rula sau utilizatorul îl cere |
| Număr reels | 3 (până la 5 dacă video-ul are peste 30 de minute și momente bune) |
| Durată | 25–60 s după tăieturi (Facebook acceptă 3–90 s) |
| Subtitrări | română, majuscule, 3 cuvinte pe rând, cuvântul curent galben și mărit |
| Pauze | tăiate dacă sunt mai lungi de 0,45 s |
| Încadrare | crop vertical centrat; `--reframe blur` dacă sunt mai mulți vorbitori în cadru sau e un ecran partajat |
| Publicare | pagina Facebook conectată în vidIQ (ex. „CleverStorm”), câte un reel pe zi la 19:00, ora României |

Lucrează într-un director de lucru, ex. `./reels-<nume-video>/`. `SKILL_DIR` e directorul acestui fișier.

## 1. Pregătire (o dată pe sesiune)

```bash
python3 -c "import faster_whisper" 2>/dev/null || pip install -q faster-whisper
which ffmpeg ffprobe
```
Modelul Whisper se descarcă de pe Hugging Face la prima rulare. Scriptul setează singur `HF_HUB_DISABLE_XET=1`. Dacă proxy-ul refuză un server (`403 ... no rule allows host`), numele lui apare în eroare. Cere adăugarea lui în mediu sau treci pe motorul vidIQ (secțiunea B).

În paralel, verifică publicarea: `vidiq_social_account_list` cu `platform: "FACEBOOK_PAGES"` și păstrează `platformAccountId` al paginii cu `canPublish: true`.

## 2. Sursa → fișier local
- **Fișier local** → îl folosești direct.
- **Link direct MP4/MOV** → `curl -L -o sursa.mp4 <url>`.
- **YouTube sau link pe care nu-l poți descărca** → `vidiq_video_upload` cu `url`. Pentru YouTube faci poll cu `vidiq_job_poll`. Apoi descarci `videoUrl` cu `curl`. E gratuit.
- **Fișier atașat în chat** → `vidiq_file_upload` (selector de fișiere), apoi `vidiq_video_upload` cu `uploadId` → `videoUrl` → `curl`.

## A. Motorul local (implicit)

### A1. Transcriere
```bash
python3 $SKILL_DIR/scripts/transcribe.py sursa.mp4 work/ --model small --language ro
```
Rezultatul: `work/transcript.json` (cuvinte cu timpi) și `work/transcript.txt` (de citit). Modelul `small` procesează cam 3× mai repede decât timpul real pe 4 nuclee. Pentru video de peste 20 de minute rulează-l în fundal (`run_in_background`) și așteaptă notificarea. Folosește `--model medium` dacă audio-ul e zgomotos sau vorbitorul are accent puternic.

### A2. Alegerea momentelor (partea ta de judecată)
Citește `work/transcript.txt` și alege clipurile. La video de peste o oră, unește întâi segmentele în blocuri de ~45 s, câte un bloc pe rând, ca să parcurgi mai repede. Sari peste intro, sponsori și reclame. Un moment bun:
- **începe direct cu cârligul**: o afirmație surprinzătoare, o întrebare, o cifră, o emoție. Nu cu „deci”, „și”, salutări sau context. Primele 2 secunde decid dacă omul derulează mai departe;
- **se înțelege singur**, fără ce s-a spus înainte;
- **se termină pe o idee închisă**: concluzie, punchline, sfat. Nu în mijlocul unei fraze;
- e **diferit** de celelalte clipuri alese.

Evită fragmentele care se sprijină pe cifre (prețuri, procente, sume): transcrierea greșește des numerele, iar o cifră greșită în subtitrare schimbă ce a spus omul. La interviuri politice sau declarații despre persoane reale, păstrează sensul: nu tăia o frază astfel încât să pară că spune altceva.

Pune `start` la începutul segmentului cu cârligul și `end` la sfârșitul frazei care închide ideea. Scriptul taie singur pauzele, așa că ținta e 30–70 s din sursă.

Corectează și greșelile evidente de transcriere din clipurile alese (nume proprii, cuvinte stâlcite) prin `fixes`. Înlocuirea se aplică fiecărui cuvânt identic, așa că pune doar forme greșite care nu sunt cuvinte reale („călpuiesc” → „cheltuiesc”). Nu pune cuvinte comune ca „un”, „și”, „e”: le-ai strica peste tot. O corectură care ține doar de un clip o pui în `fixes` din interiorul acelui clip.

Scrie `work/clips.json`:
```json
{"fixes": {"călpuiesc": "cheltuiesc"},
 "clips": [
  {"id": 1, "start": 7.0, "end": 21.5, "hook": "Greșeala pe care o faci cu salariul"},
  {"id": 2, "start": 123.3, "end": 171.9, "hook": "Fă asta după ce asculți", "crop_x": 0.35, "fixes": {"lani": "ani"}}
 ]}
```
`hook` e textul afișat sus în primele 3 s: maximum ~35 de caractere, fără emoji (fontul nu le are). `crop_x` mută cadrul vertical (0 = stânga, 1 = dreapta) când vorbitorul nu e la centru. Ca să afli unde e, extrage un cadru (`ffmpeg -ss <t> -i sursa.mp4 -frames:v 1 f.png`) și uită-te la el.

### A2b. Retranscriere fină a fragmentelor alese
Transcrierea completă cu `small` e rapidă, dar greșește cuvinte. Refă doar fragmentele alese cu modelul `medium`; durează câteva minute și dă subtitrări vizibil mai curate:
```bash
python3 $SKILL_DIR/scripts/refine.py sursa.mp4 work/transcript.json work/clips.json work/transcript_refined.json
```
Citește textul afișat. Dacă mai rămân greșeli, corectează-le prin `fixes`, aplicate pe cuvântul deja lipit (ex. `"ne-au": "n-au"`). Ce nu se poate rezolva prin `fixes`, cum ar fi două cuvinte care trebuie unite, corectezi direct în `transcript_refined.json`. Apoi montezi din `transcript_refined.json`.

### A3. Montaj
```bash
python3 $SKILL_DIR/scripts/render.py sursa.mp4 work/transcript_refined.json work/clips.json out/
```
Încadrarea `auto` alege singură: pentru o sursă orizontală la rezoluție mică (sub 900 px înălțime) folosește **square**, adică un pătrat pe vorbitor peste fundal estompat, cu titlul deasupra și subtitrările dedesubt. Un crop 9:16 dintr-o sursă de 360p ar mări imaginea de 5 ori și ar ieși neclar. Pentru surse HD folosește crop vertical. Scriptul unește singur cuvintele despărțite la cratimă („n” + „-au”) și trece ş/ţ cu sedilă la ș/ț cu virgulă.
Pentru fiecare clip, scriptul taie, elimină pauzele, reîncadrează la 1080×1920, arde subtitrările dinamice și normalizează sunetul la -14 LUFS. Rezultatul: `out/reel_01.mp4`, … și `out/render_report.json`. Opțiuni utile: `--reframe blur`, `--gap 0.6` (tăieturi mai blânde), `--no-jumpcut`, `--words-per-line 2`, `--font-size 96`, `--highlight "&H0000FF00&"` (verde; culorile ASS sunt `&HBBGGRR&`).

### A4. Control de calitate (automat, fără să întrebi)
Pentru fiecare reel extrage 2–3 cadre (ex. la 1 s, la mijloc, la final). Combină-le cu `hstack` într-o singură imagine și uită-te la ea. Verifică:
- vorbitorul e în cadru (dacă nu, ajustează `crop_x` sau pune `--reframe blur`);
- subtitrările se citesc, nu acoperă fața și nu ies din ecran;
- în `render_report.json`, `facebook_ok` e `true` (3–90 s).

Repară și re-randează doar ce nu e în regulă. Fă maximum 2 runde, ca să nu intri într-o buclă.

## B. Motorul vidIQ (alternativă)
Când localul nu merge (lipsă rețea sau ffmpeg) sau utilizatorul cere explicit:
1. `vidiq_balance`. Costul e 9 credite × minutele procesate. Dacă nu ajung, **nu porni**: spune câte credite trebuie și când se reînnoiesc, și propune o secțiune (`processingStartSeconds` / `processingEndSeconds`, minimum 30 s) sau motorul local.
2. `vidiq_generate_clips` cu `videoLanguage: "ro"`, `captionStyle: "Hype Mode"`, `clipDuration: 45` și un `prompt` cu criteriile din A2. Apoi faci poll cu `vidiq_job_poll` până nu mai e `inprogress`.
3. Alege cele mai bune N clipuri după aceleași criterii. Clipurile vin deja găzduite, deci la pasul 3 de mai jos folosești `vidiq_video_upload` cu `url`.

## 3. Drafturi pentru Facebook
**Drepturi:** dacă nu reiese clar că video-ul e al utilizatorului (de exemplu e un podcast, o emisiune sau un interviu al altcuiva), întreabă o dată, la începutul fluxului: „Ai drepturi asupra acestui video?” Dacă răspunsul e nu, montajul se face oricum, iar reels-urile se livrează ca fișiere MP4, dar nu se fac drafturi și nu se publică nimic.

Pentru fiecare reel:
1. **Încărcare:** `vidiq_video_upload` cu `localFile` (`path` absolut, `sizeBytes` din `wc -c`, `contentType: "video/mp4"`). Rulează comanda primită, apoi apelează din nou cu `uploadId` până e gata.
2. **Text (în română, în tonul vorbitorului):**
   - rândul 1: cârligul, maximum ~80 de caractere;
   - 1–2 propoziții de valoare;
   - un îndemn natural („Salvează-l”, „Tu ce ai face?”);
   - 3–5 hashtag-uri relevante;
   - fără linkuri, pentru că Facebook reduce distribuirea reels-urilor cu linkuri.
3. **Draft:** `vidiq_social_post_draft_create` cu `media: [{type: "video", id: uploadId}]`, `text`, destinația `FACEBOOK_PAGES` și `publishAt` propriu (ISO 8601 cu fus orar: `+02:00` iarna, `+03:00` vara). Câte un draft pentru fiecare reel. Dacă un draft vine cu `ready: false`, îl repari cu `vidiq_social_post_draft_update`. Păstrează `postId` și `revision`.

## 4. Singura oprire: aprobarea lotului
Trimite reels-urile cu `SendUserFile` (dacă e disponibil), ca utilizatorul să le poată viziona, apoi un tabel:

```
Am montat 3 reels pentru pagina CleverStorm:

| # | Când | Durată | Cârlig | Pauze tăiate |
|---|------|--------|--------|--------------|
| 1 | dum. 22 nov, 19:00 | 0:42 | „Greșeala pe care o faci cu salariul” | 6 (−4,1 s) |

Răspunde „da” ca să le programez pe toate, sau spune ce schimb (ex. „scoate-l pe 2”, „postează-l pe 1 acum”).
```
La „da”, apelezi `vidiq_social_post_publish` pentru fiecare `postId` cu `revision`-ul lui. Dacă cere modificări de montaj, re-randezi doar clipul respectiv și actualizezi draftul cu `draft_update`, apoi arăți doar ce s-a schimbat.

## 5. Raport final
`vidiq_social_post_status` pentru fiecare post. Raportează pe scurt: ce s-a programat sau publicat și când, linkurile live (când există), unde sunt fișierele MP4 și creditele vidIQ folosite (0 cu motorul local). Dacă o destinație a eșuat, urmează câmpul `next` și nu publica de două ori același conținut.

## Ce să nu faci
- Nu cere confirmări în timpul montajului: utilizatorul a ales automat complet.
- Nu publica fără „da”-ul de la pasul 4.
- Nu porni vidIQ fără credite suficiente.
- Nu inventa scoruri de viralitate sau statistici.
