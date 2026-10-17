# Dotychczasowe zmiany

## Import projektu do Git — 17 października 2026

Wcześniejsze prace były zapisane w plikach bez commitów. Bieżąca historia Git porządkuje istniejący projekt w tematyczne pakiety; nie odtwarza dat ani dokładnej kolejności wcześniejszych zmian. Poniższa lista opisuje zaimplementowane funkcje i poprawki.

### Aplikacja i dane

- Prototyp DEMO oraz aplikacja z trwałą bazą SQLite.
- Relacje ofert, aplikacji, zadań, rozmów, notatek i materiałów.
- Kontrola duplikatów, walidacja, wersje rekordów i archiwizacja.
- Eksport/import danych, załączników i pełnych kopii z manifestem.
- Kierunek „Inne” w ofertach i filtrach.
- Puste preferencje na nowej instalacji.

### Uruchamianie

- Skrypt otwierający aplikację i uruchamiający serwer w tle.
- Oddzielenie procesu serwera od okna skryptu uruchamiającego.
- Sprawdzanie tożsamości procesu przed zatrzymaniem.
- Porównywanie czasu startu odporne na konwersję dat przez PowerShell.

### AI i materiały

- Integracja z lokalnym Ollama; podgląd i zatwierdzanie wyników.
- Walidacja identyfikatorów źródeł i zachowanie stanu „W nauce”.
- Łączenie powtórzonych wskazań znanego źródła w generatorze wiadomości; odrzucanie nieznanych źródeł.
- Odczyt dokumentów tekstowych i publicznych stron, raport zakresu analizy i nieodczytanych materiałów.
- Pobieranie treści obsługiwanych ofert z linku, podgląd i edycja przed zapisem.

### Google Drive

- OAuth Desktop, PKCE i ochrona lokalnych tokenów przez DPAPI.
- Obsługa wygasłego logowania i ponownego rozpoczęcia autoryzacji.
- Przeglądanie podfolderów oraz import całego folderu z podglądem.
- Zachowanie również binarnych plików portfolio, z informacją o braku analizy treści.
- Migracja ograniczeń rozmiaru załączników z zachowaniem relacji i kopią przed zmianą schematu.

### Uproszczone CV

- Jeden ekran zamiast sześciu kroków.
- Odczyt oryginalnego CV zamiast sklejania kilku wpisów profilu.
- Zachowanie historii zatrudnienia i wykształcenia w pełnym szkicu.
- Edycja podglądu i zapis zatwierdzonego tekstu do PDF, DOCX i pliku tekstowego.
- Układ A4, nagłówki sekcji, polskie znaki; uwagi asystenta poza dokumentem.
- Osobny raport źródeł i zmian użytkownika; oryginalny plik pozostaje bez zmian.

Mały model lokalny nadal może nietrafnie dobrać podsumowanie. Podgląd wymaga sprawdzenia przez użytkownika. Brak potwierdzonej jakości ATS, OCR, transkrypcji i automatycznej wysyłki aplikacji.
