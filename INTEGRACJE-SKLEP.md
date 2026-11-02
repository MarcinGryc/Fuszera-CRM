# Integracja sklepu z CRM

CRM odbiera zdarzenia sklepu pod:

`POST /integrations/shop/orders`

W Renderze ustaw `SHOP_WEBHOOK_SECRET` w usłudze CRM oraz `CRM_WEBHOOK_URL` i
`CRM_WEBHOOK_SECRET` w usłudze sklepu. Sekret ma być identyczny w obu usługach,
losowy i mieć co najmniej 32 znaki. Nie umieszczaj go w Git ani w plikach
konfiguracyjnych repozytorium. Sklep podpisuje surowe bajty JSON nagłówkiem
`X-Fuszera-Signature` (HMAC-SHA256) i czasem z `X-Fuszera-Timestamp`; CRM
odrzuca podpisy starsze niż pięć minut.

Zamówienie jest tworzone w CRM przy zdarzeniu `order.created`, a kolejne
zdarzenia `order.updated` zmieniają jego status płatności. Przychód jest
księgowany wyłącznie dla statusu `paid` i zawiera kwotę całkowitą sklepu wraz z
dostawą. Ponowienia nie tworzą kolejnego zamówienia ani wpisu finansowego.
Zamówienia sklepowe są chronione przed usunięciem z widoku CRM.

Przy uruchomieniu CRM wykonuje wyłącznie idempotentne, addytywne zmiany schematu:
dodaje brakujące kolumny oraz unikalne indeksy. Nie usuwa tabel, kolumn ani
rekordów. Sklep zakłada osobną tabelę kolejki webhooków. Zmiany te nie zostały
uruchomione na produkcyjnych bazach; przed wdrożeniem sprawdź backup i najpierw
zweryfikuj synchronizację w środowisku testowym.

## Wysyłka ofert na Renderze

Usługa CRM jest na planie Render Free; ten plan może blokować bezpośrednie
połączenia SMTP. Kod zachowuje SMTP dla hostów, które je obsługują, i dodaje
wysyłkę przez Resend API po HTTPS. W Renderze CRM ustaw `EMAIL_PROVIDER=resend`,
`RESEND_API_KEY` oraz zweryfikowany adres nadawcy `SMTP_FROM`. Przycisk testu
sprawdza autoryzację API bez wysyłania wiadomości. Wysyłka ofert z listą BCC
dzieli adresatów na bezpieczne partie, a tryb osobnych maili wysyła wiadomości
oddzielnie. Nie testuj wysyłki do prawdziwej listy bez świadomego zatwierdzenia.
