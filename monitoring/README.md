# Fix: E-Mail "Tägliches Unternehmens-Monitoring"

n8n-Workflow: **Tägliches Unternehmens-Monitoring v5 (LinkedIn + Web)** (`SR2IpdCe93MS26tW`)

## Beobachtung

Im Tages-Report werden pro Unternehmen nur die LinkedIn-Links als Symbol-Reihe
ausgegeben (`🔗 LinkedIn 🔗 LinkedIn ...`). Es fehlt jeglicher Hinweis darauf,
worum es im jeweiligen Beitrag geht. Außerdem fallen alle Einträge auf die
Defaults `Sonstiges` / `NIEDRIG` zurück.

## Ursache

In Node `Ergebnis extrahieren` schlägt das Parsen der GPT-Antwort still fehl
(`try { JSON.parse(...) } catch(e) {}`) und das Default-Objekt
`{ zusammenfassung: '', kategorie: 'Sonstiges', relevanz: 'Niedrig', ... }`
bleibt stehen. Wahrscheinliche Auslöser:

- nicht-escapete Anführungszeichen in GPT-Strings (Markennamen, Zitate)
- gelegentliche Markdown-Wrapper, die die Greedy-Regex `/\{[\s\S]+\}/`
  zwar matcht, deren Inhalt dann aber kein valides JSON ist
- kein `response_format: json_object` aktiv → kein vom Modell garantiertes JSON

Eine alternative Hypothese — `$('Pro Unternehmen einzeln').first()` liefert im
Loop fälschlich das erste Item — wird durch das Beobachtungsmaterial widerlegt:
DP World wird mit 3 Posts und Alberdingk Boley mit 1 Post angezeigt, also ist
das Per-Iteration-Mapping intakt. Nur die GPT-abhängigen Felder
(`zusammenfassung`, `relevanz_begruendung`, `kategorie`, `relevanz`) fallen
weg bzw. auf Defaults zurück.

Zusätzlich entspricht das Ausgabeformat (eine Sammel-Zusammenfassung pro
Unternehmen + Linkliste) nicht dem gewünschten Layout: pro Post eine kurze
Beschreibung mit eigenem Link.

## Fix (Übersicht)

1. **GPT-Prompt** liefert pro Post eine `kurzbeschreibung` (1 Satz, ≤ 25 Wörter)
   und auf Unternehmensebene `kategorie` / `relevanz` / `relevanz_begruendung`.
2. **OpenAI-Node**: `jsonOutput: true` aktivieren (n8n v1.4) bzw. equivalent
   `responseFormat = json_object`.
3. **Ergebnis extrahieren**: neues Schema parsen, per `index` mit den
   ursprünglichen Post-URLs joinen, robuster Fallback auf gekürzten Originaltext,
   wenn GPT keine Beschreibung liefert.
4. **Ergebnisse sammeln**: HTML-Block pro Post (Beschreibung + Link),
   HTML-Escaping aller GPT-/Apify-Strings, Header- und Footer-Logik bleibt
   unverändert.

## Dateien

- `nodes/01-gpt-system-prompt.md` – neuer System-Prompt
- `nodes/02-gpt-user-prompt.md` – neue User-Message (n8n-Expression)
- `nodes/03-ergebnis-extrahieren.js` – ersetzt `jsCode` von `Ergebnis extrahieren`
- `nodes/04-ergebnisse-sammeln.js` – ersetzt `jsCode` von `Ergebnisse sammeln`

## Anwenden in n8n

Workflow `Tägliches Unternehmens-Monitoring v5` öffnen und die jeweiligen Nodes
mit dem Inhalt aus `nodes/` überschreiben. Zusätzlich im Node
`GPT LinkedIn-Analyse` unter **Options** den Schalter **JSON Output / Output
Content as JSON** aktivieren (Details: `nodes/05-openai-options.md`) — das
garantiert valides JSON und schließt damit die Wurzel des ursprünglichen Bugs.

Anschließend Test-Run starten und Ergebnis im Postfach prüfen, bevor der
Schedule am nächsten Morgen feuert.
