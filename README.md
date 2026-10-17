# Centrum Kariery

Lokalna aplikacja do organizowania poszukiwania pracy: oferty, aplikacje, zadania, rozmowy, materiały i przygotowanie CV. Interfejs jest po polsku. Dane są przechowywane w jednej bazie SQLite na komputerze użytkownika.

## Funkcje

- Oferty z filtrowaniem, kontrolą duplikatów i kierunkiem „Inne”.
- Aplikacje powiązane z firmą, ofertą, zadaniami, terminami, notatkami i wersjami dokumentów.
- Przygotowanie CV z oryginalnego pliku, edycja podglądu i eksport zatwierdzonej treści do PDF oraz DOCX.
- Opcjonalne lokalne AI przez Ollama: dobór fragmentów CV, analiza zapisanych danych, podgląd poleceń dodających zadania i notatki.
- Opcjonalny import Google Drive, również folderu z podfolderami. Zapisanie pliku nie oznacza odczytania jego treści przez AI.
- Odczyt wybranych ogłoszeń z linku, z podglądem treści przed zapisem.
- Pełny eksport i import ZIP z załącznikami, automatyczne kopie dzienne i tygodniowe oraz kontrola spójności plików.

## Uruchomienie w Windows

Wymagany Python 3.12. W folderze sklonowanego projektu:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app\requirements.txt
```

Następnie otwórz **Otworz-centrum.cmd**. Skrypt uruchamia aplikację na [127.0.0.1:8766](http://127.0.0.1:8766/). Po restarcie komputera trzeba ponownie otworzyć ten plik. Zatrzymanie:

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\Zatrzymaj-centrum.ps1
```

Można też uruchomić serwer w terminalu i zatrzymać go przez Ctrl+C:

```powershell
.\.venv\Scripts\python.exe -m app.run
```

Domyślny katalog danych: `%LOCALAPPDATA%\CentrumKariery`. Zawiera bazę, załączniki i kopie. Kod nie wymaga umieszczania danych użytkownika w repozytorium. Na świeżej instalacji profil jest pusty; dane DEMO są wyłącznie w osobnym prototypie.

## AI i Google Drive

AI jest domyślnie wyłączone. Do użycia lokalnego modelu potrzebna jest osobno działająca Ollama na `127.0.0.1:11434` i zainstalowany model lokalny. W Ustawieniach wybierz model oraz włącz integrację. Dotychczasowe próby wykonywano z `qwen3:1.7b`. Modele chmurowe są wyłączone; abonament ChatGPT nie jest połączeniem tej aplikacji z API.

CV MASTER AI: dodaj ofertę i oryginalne CV, wybierz je na jednym ekranie, kliknij **Przygotuj CV**, popraw treść i zatwierdź zapis. Nie trzeba przepisywać historii zatrudnienia do profilu.

Google Drive wymaga własnego klienta OAuth typu Desktop, dodania pliku JSON w Ustawieniach, udzielenia zgody oraz wyboru folderu. Uprawnienie `drive.readonly` obejmuje odczyt Dysku; aplikacja ogranicza import do wybranego folderu. Pliki konfiguracji i tokeny są chronione przez Windows DPAPI i nie wchodzą do eksportów biznesowych.

## Ograniczenia

- Aplikacja jest przeznaczona dla jednego użytkownika i nasłuchuje tylko na `127.0.0.1`. Nie jest gotową usługą publiczną ani systemem wieloosobowym.
- Model dobiera dosłowne cytaty do podsumowania. Mały model może dobrać je nietrafnie; dokument wymaga przeglądu i poprawek. Nie deklarujemy jakości ATS ani gotowości do wysłania.
- Odczyt CV: PDF z tekstem, DOCX i tekstowe pliki do 5 MB, 30 stron i 24 000 znaków. Niepełny odczyt CV jest blokowany. Brak OCR, transkrypcji oraz analizy treści XLSX/PPTX.
- Poczta i kalendarz zewnętrzny nie są podłączone. Aplikacja nie wysyła zgłoszeń ani wiadomości.
- Odczyt oferty z linku obsługuje wybrane strony i jednoznaczne dane `JobPosting`; inne ogłoszenia wymagają wklejenia treści.
- Bieżący interfejs sprawdzono testami funkcji i adapterów. Ostatniego uproszczenia nie sprawdzono wizualnie w przeglądarce; eksporty PDF i DOCX sprawdzono osobno.

## Testy

Testy używają oddzielnych katalogów `.test-data`, nie domyślnej bazy użytkownika. Przed uruchomieniem utwórz ten katalog:

```powershell
New-Item -ItemType Directory -Force .test-data | Out-Null
.\.venv\Scripts\python.exe app\tests\check_backend.py
.\.venv\Scripts\python.exe app\tests\check_simple_cv.py
node app\tests\check_simple_cv_ui.cjs
node app\tests\check_offer_import_ui.cjs
```

Testy JavaScript powyżej wymagają Node.js i korzystają z jego standardowej biblioteki. Testy z rzeczywistym modelem wymagają dodatkowo Ollama; testy sterujące przeglądarką mają osobne zależności i część z nich opisuje starszy interfejs. Nie są częścią powyższego zestawu.

## Struktura

| Katalog | Zawartość |
| --- | --- |
| `app/` | FastAPI, SQLite, integracje i aktualny interfejs |
| `app/tests/` | Testy danych, API, integracji i funkcji interfejsu |
| `prototype/` | Historyczny prototyp DEMO; zmiany tylko w pamięci karty |
| `design/` | Historyczne makiety interfejsu |
| `docs/` | Publiczny opis architektury i dotychczasowych zmian |

[Architektura](docs/ARCHITECTURE.md) · [Dotychczasowe poprawki](docs/CHANGELOG.md)

Repozytorium zawiera kod i przykłady DEMO. Prywatne CV, portfolio, baza, tokeny, kopie, raporty z lokalnymi danymi oraz notatki z wywiadu są wyłączone z wersjonowania. Historia Git zaczyna się od uporządkowanego importu istniejących plików; wcześniejsze poprawki nie miały osobnych commitów.
