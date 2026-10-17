# Architektura Centrum Kariery

## Uruchomienie i zapis

Jedna aplikacja FastAPI/Uvicorn udostępnia lokalne API i statyczny interfejs HTML/CSS/JavaScript. SQLite przechowuje rekordy, relacje, wersje oraz historię operacji. Załączniki mają nazwy UUID, a baza przechowuje ich pierwotną nazwę, rozmiar i SHA-256. Biblioteka materiałów jest wspólna; aplikacje wskazują konkretne wersje zamiast tworzyć niezależne kopie informacji.

Podstawowe relacje: firma → oferty → aplikacje; aplikacja → zadania, wydarzenia, notatki; aplikacje ↔ materiały. Profil i wpisy profilu zawierają deklaracje zawodowe ze stanem i źródłem. CV bazowe jest oddzielnym, oryginalnym materiałem.

Zapisy przechodzą przez walidację i transakcje. Rewizja bazy i wersja rekordu blokują nadpisanie zmian z innej karty. Archiwizacja jest jawna. Eksport ZIP obejmuje rekordy, załączniki i manifest; import sprawdza format, relacje, ścieżki, rozmiary i sumy plików. Kopie dzienne i tygodniowe pozwalają odtworzyć dane.

## Interfejs

Widoki: Dzisiaj, Oferty, Aplikacje, Plan, Mój profil, Materiały, CV MASTER AI i Ustawienia. Generator CV ma jeden ekran: oferta, CV bazowe, opcjonalne portfolio i edytowalny podgląd. Zapis generuje tekst, PDF, DOCX oraz raport źródeł. Dokumenty zapisuje się jako nową wersję powiązaną z aplikacją.

## AI i odczyt materiałów

`ModelProvider` oddziela logikę aplikacji od modelu. Zaimplementowany jest lokalny dostawca Ollama, z listą rzeczywiście zainstalowanych modeli. Model otrzymuje wybrane dane i zwraca wynik o ustalonym schemacie; nie dostaje SQL, danych logowania ani możliwości uruchamiania kodu.

Generator CV odczytuje oryginalny dokument. Dobór podsumowania jest oparty na cytatach; historia zatrudnienia i wykształcenie pozostają w szkicu. Użytkownik może zmienić całą treść, a zatwierdzenie zapisuje jego wersję i osobno informację o zmianie względem wygenerowanego szkicu. Trafność doboru cytatów nie jest gwarantowana.

PDF i DOCX są odczytywane w osobnym procesie z limitem czasu i rozmiaru. Odczyt stron dopuszcza publiczne adresy HTTPS, odrzuca adresy prywatne i nie uruchamia JavaScript. Adapter wybranych ogłoszeń przygotowuje podgląd treści; zapis wymaga potwierdzenia. Instrukcje zawarte w dokumentach są danymi, nie uprawnieniami do działania.

## Google Drive

OAuth dla aplikacji komputerowej używa PKCE, parametru state i tymczasowego serwera powrotu na `127.0.0.1`. Klient OAuth, token i wskazanie folderu są przechowywane poza bazą biznesową, z ochroną Windows DPAPI. Import sprawdza przynależność do wybranego folderu. Import zbiorczy pokazuje podgląd i zapisuje pliki po potwierdzeniu. Format nieobsługiwany przez czytnik może zostać zachowany jako załącznik, bez deklarowania analizy jego treści.

## Granice bezpieczeństwa

Warstwa HTTP sprawdza Host, Origin, lokalną sesję i CSRF. Interfejs ma politykę CSP, a wartości użytkownika są escapowane. Istotne operacje AI mają podgląd, właściciela sesji, termin ważności i jednorazowe potwierdzenie. Klucze i tokeny nie trafiają do frontendu ani kopii biznesowych.

Te zabezpieczenia dotyczą aplikacji lokalnej. Udostępnienie jej publicznie wymagałoby odrębnego projektu uwierzytelniania, uprawnień, wdrożenia i przeglądu bezpieczeństwa. Samo opublikowanie kodu na GitHubie nie publikuje działającej aplikacji ani jej danych.
