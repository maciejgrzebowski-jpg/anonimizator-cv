# Anonimizator CV

Program na Windows do usuwania danych osobowych z CV. Działa **w pełni offline**, bez sztucznej inteligencji i bez wysyłania czegokolwiek do internetu.

Wczytujesz CV (PDF, Word .docx, obrazek JPG/PNG/TIFF albo .txt), program pokazuje, co znalazł, a po Twojej akceptacji zapisuje **ten sam plik** z danymi zamienionymi na etykiety (`[KANDYDAT]`, `[E-MAIL]`…) albo zamazanymi na czarno.

Obrazki i zeskanowane PDF-y są odczytywane przez **OCR** (Tesseract), który działa lokalnie na komputerze. Nic nie jest wysyłane do internetu. Żeby wyciągnąć jak najwięcej:
- obraz jest czytany dwa razy, normalnie i w negatywie (biały tekst na kolorowych paskach), a program wybiera pewniejszy odczyt,
- imię i nazwisko program rozpoznaje jako największy napis na stronie, nawet gdy OCR przekręci litery,
- reguły uwzględniają typowe pomyłki OCR (B zamiast 8, ® zamiast @, zgubione kropki i polskie znaki),
- po zapisie program czyta wynik jeszcze raz i zamazuje to, co dopiero wtedy stało się czytelne.

Jeden obrazek trwa ok. 5–20 sekund. Im lepsza jakość pliku (skan 200–300 dpi zamiast małego obrazka z internetu), tym lepszy wynik.

## Co jest usuwane

| Dane | Przykład |
|---|---|
| Imię i nazwisko kandydata, także odmienione | Katarzyna Wiśniewska → Katarzynę Wiśniewską, KATARZYNA WIŚNIEWSKA |
| Inne osoby (np. referencje) | Tomasz Zieliński, kierownik HR |
| E-mail, telefon (PL i zagraniczne) | jan@x.pl, +48 601 234 567, 12 345 67 89 |
| Adres, kod pocztowy z miastem | ul. Długa 5/3, 00-950 Warszawa |
| PESEL (ze sprawdzeniem sumy kontrolnej), nr dowodu | 44051401359 |
| Data i miejsce urodzenia | Data urodzenia: 14.05.1991 |
| Profile i linki | linkedin.com/in/…, github.com/… |
| Zdjęcie kandydata | w PDF/Word usuwane automatycznie; w obrazkach i skanach wykrywane i zaznaczane do sprawdzenia |
| Ukryte dane | autor i tytuł w metadanych, klikalne linki `mailto:`, dane EXIF w zdjęciach (np. GPS) |

Wszystko, co zostaje w dokumencie, program sprawdza jeszcze raz po zapisie. Jeśli jakaś zaznaczona fraza nadal jest widoczna, pojawi się ostrzeżenie.

Nazwa pliku wynikowego to np. `CV_anonim_20261122_214512.pdf`, a nie nazwa oryginału, bo ta często zawiera imię i nazwisko.

## Jak z tego korzystać (użytkownik na Windows)

1. Uruchom `AnonimizatorCV-Setup-1.0.0.exe` i kliknij „Dalej”. Uprawnienia administratora nie są potrzebne.
2. Otwórz **Anonimizator CV** z menu Start. Możesz też kliknąć plik PDF albo DOCX prawym przyciskiem i wybrać **Anonimizuj CV**.
3. Przejrzyj listę po lewej. Klikając ☑, wyłączasz pozycje, które nie są danymi osobowymi. Na podglądzie po prawej zaznaczone fragmenty są podświetlone na żółto.
4. Jeśli coś zostało pominięte, dopisz to w polu „Coś zostało pominięte?” albo zaznacz myszką w podglądzie i kliknij **Usuń zaznaczone**.
5. Kliknij **Zapisz zanonimizowane CV…**.

Dwuklik na pozycji pozwala zmienić zamianę, np. `[KANDYDAT]` → `Kandydat A`.

**Wiele plików naraz:** w oknie wyboru zaznacz kilka CV (Ctrl/Shift + klik). Każde możesz przejrzeć i zatwierdzić przyciskiem **Zapisz i dalej ▶** albo kliknąć **Pozostałe zapisz automatycznie**. Wyniki trafiają do folderu `Dokumenty\CV zanonimizowane\<data i godzina>` (krótka ścieżka, bo Windows nie otwiera plików o ścieżce dłuższej niż 260 znaków) i dostają numery (`CV_01`, `CV_02`…). Plik `lista_kandydatow.csv` w tym folderze mówi, który numer to który oryginał. Zostaw go u siebie, nie wysyłaj razem z CV. Na końcu program wypisuje pliki, które warto sprawdzić ręcznie.

Przycisk **Zamaż obszar…** otwiera podgląd strony, na którym myszką zaznacza się prostokąt do zamazania, np. zdjęcie, podpis albo logo. W obrazkach i skanach program sam proponuje obszar zdjęcia. Warto to sprawdzić.

> **Ostrzeżenie Windows „System Windows ochronił ten komputer”**: tak wygląda każdy program bez płatnego certyfikatu podpisu. Kliknij **Więcej informacji → Uruchom mimo to**. Pozbycie się tego komunikatu wymaga certyfikatu Code Signing (kilkaset zł rocznie).

## Jak przekazać program innej osobie

Wymagania: **Windows 10 lub 11, 64-bit**. Python ani nic innego nie musi być zainstalowane, bo instalator zawiera wszystko, także pliki OCR.

Każde budowanie na GitHubie sprawdza instalator automatycznie na czystym Windowsie: instaluje go, uruchamia program na przykładowych CV (PDF, Word, JPG) i odinstalowuje. Jeśli którykolwiek krok się nie powiedzie, instalator w ogóle nie powstaje.

**Link do pobrania:**
- Repozytorium **publiczne**: oznacz wersję tagiem (`git tag v1.0.0 && git push --tags`), a w zakładce **Releases** pojawi się stały link do pliku `.exe`. Kod i tak jest na licencji AGPL, a w repozytorium nie ma żadnych danych.
- Repozytorium **prywatne**: link z GitHuba wymaga zalogowania. Pobierz instalator sam (Actions → Artifacts) i udostępnij go przez Google Drive, OneDrive albo WeTransfer. Nie wysyłaj `.exe` mailem, bo Gmail i Outlook blokują takie załączniki.

**Ostrzeżenia, które zobaczy odbiorca (to normalne):**
1. Przeglądarka może napisać, że plik „nie jest często pobierany”: **⋯ → Zachowaj → Zachowaj mimo to**.
2. Windows SmartScreen pokaże komunikat „System Windows ochronił ten komputer”: **Więcej informacji → Uruchom mimo to**.

Oba komunikaty biorą się z braku płatnego podpisu cyfrowego. Firma z UE może go uzyskać przez Microsoft Azure Artifact Signing (ok. 10 USD miesięcznie). Osoba prywatna w Polsce obecnie nie może.

**Gdy coś pójdzie nie tak:** program zapisuje opis błędu w pliku `%LOCALAPPDATA%\AnonimizatorCV\bledy.log` i kopiuje go do schowka, więc wystarczy wkleić go w wiadomości. Treść CV nie trafia do tego pliku, ale może się w nim znaleźć nazwa pliku z CV.

## Jak zbudować instalator (z MacBooka, bez Windowsa)

Instalator buduje się automatycznie i za darmo na serwerach GitHuba, na prawdziwym Windowsie.

1. Załóż konto na github.com i utwórz nowe repozytorium (może być **prywatne**).
2. Wgraj do niego zawartość tego folderu. Najprościej z Terminala:
   ```bash
   cd ~/Ścieżka/do/anonimizator-cv
   git init && git add . && git commit -m "Anonimizator CV"
   git branch -M main
   git remote add origin https://github.com/TWOJ-LOGIN/anonimizator-cv.git
   git push -u origin main
   ```
   Możesz też użyć aplikacji **GitHub Desktop** (przeciągnij folder, „Publish repository”).
3. Na GitHubie otwórz zakładkę **Actions** i poczekaj ok. 5–8 minut, aż pojawi się zielony ✓. Budowanie najpierw uruchamia testy, potem buduje program i sprawdza go.
4. Kliknij zakończone zadanie i na dole, w sekcji **Artifacts**, pobierz `AnonimizatorCV-instalator`. W środku jest `AnonimizatorCV-Setup-1.0.0.exe`. Ten plik wysyłasz ludziom.

Każda zmiana wgrana na GitHuba buduje nowy instalator automatycznie. Jeśli chcesz stałą stronę do pobrania, oznacz wersję tagiem (`git tag v1.0.1 && git push --tags`). Wcześniej zmień numer wersji w `anonimizator/__init__.py`. Instalator pojawi się wtedy w zakładce **Releases**.

## Testowanie na Macu

Program działa też na macOS, więc możesz go wypróbować przed zbudowaniem instalatora. Wszystkie polecenia wpisujesz w aplikacji **Terminal**.

1. **Python.** Sprawdź `python3 --version`. Jeśli pokaże się 3.10 albo nowszy, jest dobrze. Jeśli nie, zainstaluj Pythona z python.org (wersja „macOS 64-bit universal installer”). Ma on wbudowane okienka (tkinter). Python z Homebrew wymaga dodatkowo `brew install python-tk`.
2. **Przygotowanie (raz).** Przejdź do rozpakowanego folderu i zainstaluj biblioteki:
   ```bash
   cd ~/Downloads/anonimizator-cv        # albo tam, gdzie rozpakowałeś
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt pytest
   python pobierz_ocr.py                 # pliki do OCR, ok. 30 MB, tylko raz
   ```
   **Zalecane:** zainstaluj też program Tesseract, `brew install tesseract`. Ta sama wersja jest dołączona do instalatora Windows, więc na Macu zobaczysz identyczne wyniki OCR. Bez niego program użyje słabszego OCR z PyMuPDF. Jeśli nie masz Homebrew (`brew --version` zwraca błąd), zainstaluj go poleceniem ze strony brew.sh.
3. **Testy automatyczne** (opcjonalnie, ok. 10 s):
   ```bash
   python -m pytest -q
   ```
   Wszystko powinno być „passed”. Pominięty („skipped”) może zostać co najwyżej test okna.
4. **Uruchomienie programu:**
   ```bash
   python app.py
   ```
   Kliknij **Wybierz plik CV…** i wskaż swoje JPG albo pliki z folderu `przyklady`.

Przy każdym kolejnym uruchomieniu wystarczy: `cd` do folderu, `source .venv/bin/activate`, `python app.py`.

> Jeśli `pobierz_ocr.py` zgłosi błąd certyfikatu SSL (częste w Pythonie z python.org), uruchom raz program „Install Certificates.command” z folderu Programy → Python 3.x albo zainstaluj Tesseracta przez Homebrew: `brew install tesseract tesseract-lang`. Program sam wykryje każdą z tych opcji.

## Ograniczenia (bez AI nie da się ich w pełni uniknąć)

- **Reguły, nie rozumienie tekstu.** Nietypowe imię spoza słownika, użyte w środku tekstu, może zostać pominięte. Dlatego jest krok przeglądu przed zapisem. Imię i nazwisko z nagłówka CV program wykrywa także bez słownika.
- **OCR nie jest doskonały.** Krzywe zdjęcia z telefonu, mała rozdzielczość i ozdobne czcionki pogarszają odczyt. Dobry skan (200–300 dpi) działa bardzo dobrze. Zawsze sprawdź podgląd, a po zapisie otwórz wynik.
- **Wykrywanie zdjęcia na obrazkach** działa na prostych regułach (zwarty prostokąt bez tekstu w górnej części strony). Może przeoczyć zdjęcie albo zaznaczyć logo, więc zawsze sprawdź przycisk „Zamaż obszar…”.
- **Stary format .doc** trzeba najpierw zapisać w Wordzie jako .docx.
- W PDF etykieta musi zmieścić się w miejscu po usuniętym tekście, więc przy krótkich słowach bywa mała albo jest zastępowana przez `***`.
- Zdjęcie w PDF jest wykrywane jako obraz na 1. stronie średniej wielkości. Duże tła i małe ikonki zostają.

## Słownik imion

Plik `anonimizator/data/imiona.txt` zawiera jedno imię w każdej linii. Możesz dopisywać własne, a po zmianie trzeba zbudować instalator ponownie.

## Licencje

Szczegóły są w pliku `LICENCJE.txt`, który instaluje się razem z programem. Najważniejsze: program korzysta z biblioteki **PyMuPDF** (licencja AGPL-3.0), a pozostałe składniki mają licencje bez dodatkowych warunków (MIT, BSD, Apache). Do użytku wewnątrz firmy AGPL nie stawia dodatkowych wymagań. Jeśli program ma być **sprzedawany albo rozdawany klientom**, AGPL wymaga udostępnienia im kodu źródłowego. Alternatywą jest licencja komercyjna PyMuPDF (Artifex).

## Struktura

```
app.py                       start programu
anonimizator/detector.py     reguły wykrywania danych
anonimizator/pdf_handler.py  obsługa PDF
anonimizator/docx_handler.py obsługa Word
anonimizator/image_handler.py obsługa obrazków (JPG, PNG…)
anonimizator/ocr.py          rozpoznawanie tekstu (Tesseract, lokalnie)
pobierz_ocr.py               pobiera pliki językowe OCR (raz, przy budowie)
anonimizator/gui.py          okno programu
instalator/setup.iss         instalator Windows (Inno Setup)
.github/workflows/           automatyczne budowanie instalatora
przyklady/                   zmyślone CV do testów
tests/                       testy
```
