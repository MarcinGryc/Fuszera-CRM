# Integracja sklepu z CRM

CRM odbiera zdarzenia sklepu pod:

`POST /integrations/shop/orders`

W Renderze ustaw `SHOP_WEBHOOK_SECRET` w usłudze CRM oraz `CRM_WEBHOOK_URL` i
`CRM_WEBHOOK_SECRET` w usłudze sklepu. Sekret ma być identyczny w obu usługach,
losowy i mieć co najmniej 32 znaki. Nie umieszczaj go w Git ani w plikach
konfiguracyjnych repozytorium. Sklep podpisuje surowe bajty JSON nagłówkiem
`X-Fuszera-Signature` (HMAC-SHA256) i czasem z `X-Fuszera-Timestamp`; CRM
odrzuca podpisy starsze niż pięć minut.

Zdarzenia oczekujące na płatność nie tworzą zamówień ani kart klientów w CRM.
Zamówienie jest tworzone w CRM dopiero po zdarzeniu ze statusem `paid`.
Nieopłacone rekordy, które trafiły do CRM przed tą zmianą, pozostają w bazie,
ale są ukryte w listach i eksporcie; nie są kasowane. Po opłaceniu zamówienie
zostanie pokazane po odebraniu aktualizacji statusu.

Finanse są prowadzone niezależnie od zamówień. Dodanie zamówienia ręcznego ani
odebranie opłaconego zamówienia ze sklepu nie tworzy wpisu finansowego.
Przychody i wydatki dodaje się w module Finanse lub przez import finansów.
Istniejące wpisy finansowe pozostają bez zmian. Ponowienia webhooków nie tworzą
kolejnego zamówienia. Zamówienia sklepowe są chronione przed usunięciem z widoku CRM.
Podsumowania sprzedaży kawy liczą zamówienia ręczne i opłacone zamówienia
sklepowe według daty zamówienia; gramatura jest odczytywana z produktu lub nazwy pozycji.

Przy uruchomieniu CRM wykonuje wyłącznie idempotentne, addytywne zmiany schematu:
dodaje brakujące kolumny oraz unikalne indeksy. Nie usuwa tabel, kolumn ani
rekordów. Sklep zakłada osobną tabelę kolejki webhooków. Zmiany te nie zostały
uruchomione na produkcyjnych bazach; przed wdrożeniem sprawdź backup i najpierw
zweryfikuj synchronizację w środowisku testowym.

## Wysyłka ofert na Renderze

Wysyłka jest domyślnie wyłączona (`OFFERS_ENABLED=false`). Strona „Wyślij ofertę”
pokazuje „Work in progress”; również bezpośrednie żądania wysyłki i testowania
połączenia są zablokowane. Nie jest teraz wymagane konfigurowanie dostawcy poczty.

Listy dystrybucyjne łączą ręczne wpisy z aktualnymi adresami klientów, oddzielnie
dla B2B i klientów indywidualnych. Adresy są normalizowane i deduplikowane w obrębie
listy; puste i nieprawidłowe adresy są pomijane. Zmiany w kartotece klienta są od
razu widoczne na liście i w eksporcie, także dla klientów utworzonych przez sklep.

Po przejściu na hosting obsługujący SMTP ustaw `EMAIL_PROVIDER=smtp`, `SMTP_HOST`,
`SMTP_PORT` (587 dla `SMTP_SECURITY=starttls` lub 465 dla `SMTP_SECURITY=ssl`),
`SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` oraz `OFFERS_ENABLED=true` i wdróż usługę.
Kod wysyłki pozostaje gotowy do uruchomienia po tej konfiguracji.

Opcjonalną alternatywą dla SMTP jest Resend API po HTTPS, także na Render Free,
który blokuje standardowe porty SMTP. Dla tego wariantu ustaw `EMAIL_PROVIDER=resend`,
`RESEND_API_KEY`, zweryfikowany adres nadawcy `SMTP_FROM` oraz `OFFERS_ENABLED=true`.
Przycisk testu
sprawdza autoryzację API bez wysyłania wiadomości. Wysyłka ofert z listą BCC
dzieli adresatów na bezpieczne partie, a tryb osobnych maili wysyła wiadomości
oddzielnie. Nie testuj wysyłki do prawdziwej listy bez świadomego zatwierdzenia.
