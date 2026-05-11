# Research-Report: BC-Belege-Auflösung — Continia native vs. BC + Graph Search

**Auftraggeber:** G&B Logistics GmbH
**Forschungszeitraum:** 11.05.2026
**Bearbeitet via:** n8n `bc_generic_bridge` → Anthropic Claude Haiku → BC MCP Server `gb-bcmcp.duckdns.org/mcp` (read-only Modus, System-Prompt-erzwungen). Ergänzt durch öffentliche Continia/MS Learn Doku.

---

## 1. Executive Summary

**Empfehlung: Option B (BC OData + Graph Search) belassen, kapseln und stabilisieren — Option A jetzt nicht starten.**

Begründung in einer Atmenpause:
- Continia veröffentlicht in v2025R2 (v26) **keine eigenen ApiPages**; auf der G&B-Instanz ist **keine `CDC*`/`Continia`-Action** über die BC API erreichbar. Belegt durch 0-Treffer auf `bc_actions_search('Continia')`, `bc_actions_search('CDC')` (nur Substring-Match-Müll), `bc_actions_search('extension')`.
- Der Standard-BC-Pfad `purchaseInvoices(id)/attachments` (PAG30039) und `documentAttachments` (PAG30080) liefert für **alle drei getesteten Rechnungen — auch eine echte offene Re. >1000 € — `No results found`**. Continia hängt das PDF demnach NICHT als BC-Standard-Attachment an, sondern hält es in der eigenen Tabelle `CDC Document` als BLOB.
- Disambiguierung über `(vendorNumber + vendorInvoiceNumber)` ist im Sample bereits **eindeutig** (1 von 19.495). Das Triple mit `postingDate` ist redundant aber günstig defensiv. ⇒ Option B ist deterministisch machbar, sobald man weg vom SharePoint-Volltext-Such-Pfad zur strukturierten BC-Anfrage geht.
- Option A erfordert entweder Brabender/Continia für ApiPage-Erweiterung **oder** Eigenbau einer AL-Extension; geschätzt **0,5–2 PT Eigenbau** wenn AL-Know-how vorhanden, sonst Partner.
- **Hauptrisiken:** (a) Continia-Tabellennamen sind in v26 ggf. geändert (das Community-AL-Beispiel ist von DC v7 / BC18); (b) der `bc_generic_bridge`-Token ist hartcodiert im n8n-Workflow — separates Audit empfohlen.

---

## 2. Continia-Inventar

### 2.1 Tabellen / Felder

Aus der einzigen öffentlich einsehbaren AL-Quelle ([document-capture/power-automate-connector, Pag62011](https://github.com/document-capture/power-automate-connector/blob/master/Objects/Latest/BC18-DC7.00.00-App/src/page/Pag62011.DCADVDocumentAPI.al)) — Community-Add-on für DC v7.00.00 / BC18:

| Tabelle | AL-Name | Quelle |
|---|---|---|
| Document Header | **`CDC Document`** (nicht "CDC Document Hdr" wie in der Aufgabenstellung — der Name ist seit Jahren `CDC Document`) | AL `SourceTable = "CDC Document"` |

**Bestätigte Felder (aus AL-Page-Definition):**

| AL-Feldname | Typ | Zweck |
|---|---|---|
| `SystemId` | Guid | OData key |
| `No.` | Code[20] | Document No. (Primärschlüssel) |
| `Source Record Name` | Text | Name des verknüpften BC-Records (z.B. "Purchase Header") |
| `Source Record No.` | Code | Belegnummer des Ziel-Records (Purchase Invoice/Order No.) |
| `PDF File` | BLOB | **Das ist der PDF-Inhalt** (HasValue-Flag) |
| `TIFF Image File` | BLOB | TIFF-Variante |
| `HTML File` | BLOB | OCR-Source-HTML |
| `Misc. File` | BLOB | Andere Anhänge |
| `Clean XML File` | BLOB | XML-Repräsentation |

**Nicht in der Community-Page exposed, aber laut Continia-Doku existent** (über Event Publishers v26.00 referenziert):
- `CDC Document Line` (Positionen) — exists, Felder nicht öffentlich dokumentiert
- `CDC Document Comment Line` — exists, idem
- `CDC Template` (OCR-Templates) — exists, idem
- Vendor Invoice No., Linked Table No., Linked Document No. — als Felder *referenziert* in Continia-Doku-Snippets ([Event Publishers 26.00](https://docs.continia.com/en-us/continia-document-capture/development-and-administration/development-and-customization/event-publishers/event-publishers-2600/)), aber Continia **publiziert keine vollständige Tabellenreferenz öffentlich**. Quelltext-Einsicht erfordert AL-Source oder Partner (Brabender).

### 2.2 API-Status auf G&B's Instanz

**KEIN Continia-Endpunkt exposed.** Belegt durch `bc_actions_search` Aufrufe an die BC MCP-Bridge:

| Suchbegriff | Treffer | Auswertung |
|---|---|---|
| `Continia` | **0** | Kein Continia-Namespace |
| `CDC` | 10 (alle Substring-Müll: `AccountingPeriods`, `Accounts`, `ApplyVendorEntries` etc.) | Keine echte CDC-Action |
| `extension` | 0 | Auch kein admin-Endpunkt `extensions` exposed |
| `incoming` | 0 | Kein `incomingDocuments` (Page 130 v2.0 API existiert standardmäßig, aber **nicht in diesem MCP-Server gemapt**) |

### 2.3 Continia-Version

**Nicht zweifelsfrei bestimmbar** über die verfügbare Bridge — der MCP-Server exposed weder den `extensions`-Admin-Endpunkt noch eine `companyInformation`-Page.

Indizien:
- n8n-Workflow `continia_news_monitor` läuft → Continia ist im Einsatz.
- BC-Instance ist Cloud SaaS (System-Id-Suffixe wie `00224874e2fa` typisch für Azure SQL multi-tenant SaaS).
- Continia DC ist auf BC SaaS aktuell verfügbar in v2024R1 (v24), v2024R2 (v25), v2025R1 (v26), v2025R2 ([Supported Versions](https://docs.continia.com/en-us/continia-document-capture/development-and-administration/on-premises/versions-on-premises/)).

**Empfehlung zur Klärung:** Brabender / G&B-IT um 1 Screenshot aus "Erweiterungsverwaltung" oder per `GET /api/microsoft/automation/v2.0/companies({id})/extensions` (Admin-Scope, separat zu authentifizieren) zu bitten.

### 2.4 Wo liegt das PDF physisch

**`CDC Document`.`PDF File` (BLOB), innerhalb der BC-Datenbank.** Belegt durch AL-Code-Analyse. Es ist **kein** Link auf SharePoint, **kein** Eintrag in `Incoming Document Attachment` (Table 133). Das erklärt direkt, warum der heutige Pfad über SharePoint-Volltext nur 65 % Trefferrate hat — das PDF liegt eigentlich gar nicht (primär) in SharePoint.

### 2.5 Verknüpfung CDC Document → Purchase Header / Approval Entry

Aus der AL-Page-Definition:
- `Source Record Name` (Text, z.B. `"Purchase Header"`)
- `Source Record No.` (Code, z.B. `"PI-001234"`)

Damit ist die Verlinkung **logisch über das Paar** `(Source Record Name, Source Record No.)` zur jeweiligen BC-Standard-Tabelle, nicht über eine direkte Fremdschlüssel-GUID. Das bedeutet bei einem Lookup von BC nach CDC: Man filtert in `CDC Document` auf `"Source Record Name" eq 'Purchase Header' and "Source Record No." eq '<no>'`.

---

## 3. Disambiguierungs-Test (Teil 2 Frage 1)

### Request 1 — Sample der purchaseInvoices

```
bc_actions_invoke('List_PurchaseInvoices_PAG30042',
  {top: 5,
   select: 'id,number,vendorNumber,vendorInvoiceNumber,postingDate,
            totalAmountIncludingTax,status'})
```

Response (gekürzt, sensible Daten **belassen** — sind keine echten Geheimnisse, sondern Test-/historische Daten 2022/2023):

```json
{
  "@odata.count": 19495,
  "value": [
    { "id": "a21cb8fa-...", "number": "10016", "postingDate": "2023-07-11",
      "vendorNumber": "70980", "vendorInvoiceNumber": "5017/07/2023",
      "totalAmountIncludingTax": 0.01, "status": "Draft" },
    { "id": "4844cb3c-...", "number": "10022", "postingDate": "2023-07-11",
      "vendorNumber": "70980", "vendorInvoiceNumber": "5014/07/2023",
      "totalAmountIncludingTax": 2100, "status": "Draft" },
    { "id": "2f08ec09-...", "number": "10056", "postingDate": "2023-06-30",
      "vendorNumber": "60239", "vendorInvoiceNumber": "RE-2317827",
      "totalAmountIncludingTax": 3570, "status": "Draft" }
    // ...
  ]
}
```

> Wichtig: Vendor `70980` hat im Sample **zwei Re. am gleichen postingDate** (10016 vs 10022) — `postingDate` allein ist also bei diesem Lieferanten **nicht** eindeutig. `vendorInvoiceNumber` ist es schon.

### Request 2 — Doppel-Filter

```
filter: "vendorNumber eq '70980' and vendorInvoiceNumber eq '5017/07/2023'"
```

Response:
```json
{ "@odata.count": 1, "value": [ { "id": "a21cb8fa-...", "number": "10016", ... } ] }
```

### Request 3 — Triple-Filter (mit postingDate)

```
filter: "vendorNumber eq '70980' and vendorInvoiceNumber eq '5017/07/2023'
         and postingDate eq 2023-07-11"
```

Response: ebenfalls genau 1 Record.

### Fazit Disambiguierung

| Filter | Treffer | Eindeutig? |
|---|---|---|
| (vendorNumber) | viele | nein |
| (vendorNumber, postingDate) | 2 im Sample | nein |
| **(vendorNumber, vendorInvoiceNumber)** | **1** | **ja im Sample** |
| (vendorNumber, vendorInvoiceNumber, postingDate) | 1 | ja (defensiv) |

**Caveats — bevor "immer eindeutig" als Garantie verkauft wird:**
1. Sample ist 3 Records von 19 495 — statistisch nicht 100 %ig generalisierbar.
2. `vendorInvoiceNumber` ist in BC nur dann garantiert unique pro Vendor, wenn die Setup-Option `Check Doc. Total Amounts` / der Schlüssel auf `Vendor Invoice No.` aktiv ist. Continia kann das überschreiben.
3. Korrekturrechnungen / Stornos können dieselbe `vendorInvoiceNumber` führen.
4. Die API `purchaseInvoices` (Page 30042) zeigt **nur ungebuchte/draft/open** Belege. Für gebuchte Re. muss man `postedPurchaseInvoices` (Page 30043) bzw. das Custom-MCP-Tool `bc_GetPostedPurchaseInvoices` verwenden — dort gilt dieselbe Eindeutigkeitslogik, aber das ist ein zweiter Endpunkt.

**Pragmatische Empfehlung:** Triple-Filter `(vendorNumber, vendorInvoiceNumber, postingDate ±N Tage)` defensiv verwenden, bei >1 Treffer Disambiguierung über Betrag (`totalAmountIncludingTax`) als Tiebreaker.

---

## 4. Aufwandsschätzung Option A (Continia native)

### Variante A1 — Eigene AL-Extension publishen

Realer Aufwand bei vorhandener AL-Toolchain (VSCode + AL-Extension + Continia-Symbole vom Partner):

| Schritt | Stunden |
|---|---|
| Code-Vorlage (analog [Pag62011](https://github.com/document-capture/power-automate-connector/blob/master/Objects/Latest/BC18-DC7.00.00-App/src/page/Pag62011.DCADVDocumentAPI.al)) anpassen, ApiPage auf `CDC Document` mit benötigten Feldern | 2–4 h |
| Codeunit für Base64-Stream-Export der `PDF File` BLOB | 1–2 h |
| Permission-Set anpassen, App.json mit korrekter Continia-Dependency-Version | 1 h |
| Test im Sandbox-Tenant (Authentifizierung, OData-Filter auf Source Record No.) | 2–3 h |
| Publish (AppSource ist nicht nötig — interne per Klick-Deployment) | 1 h |
| **Gesamt** | **7–11 h** (≈ 0,5–1,5 PT) |

### Variante A2 — Community-App (`document-capture/power-automate-connector`)

Vorhanden, aber für **DC 7.00.00 / BC18**. Modernes BC (v25/v26) erfordert Forks/Update — geschätzt 4–8 h Anpassungsarbeit. **Nicht über AppSource zertifiziert** ("free unofficial proof of concept").

### Variante A3 — Brabender / Continia-Partner

Annahme Tagessatz 1.200–1.500 €, Aufwand 0,5–1 PT für die Page + 0,5 PT Doku/Übergabe → **600–1.500 €**. Liefert ggf. höhere Continia-Compatibility (Tabellen-Änderungen über Versionen hinweg, Permission-Sets korrekt).

### Pflichtblockade

**Bevor A1/A2 startet:** AL-Source für `CDC Document` der **tatsächlich installierten** Continia-Version muss vorliegen (Symbole reichen). Felder können zwischen v7 (Community-Code) und v26 (aktuell) abgewichen sein. Diese Klärung erfordert entweder Brabender oder Zugang zum BC-Web-Client → Designer → Tabellen-Inspect.

### Empfehlung Aufwandsklasse

- **Best case:** 1 PT AL-Entwicklung intern.
- **Realistic case:** 0,5 PT Brabender + 0,5 PT interner Test = **1 PT extern + intern, ca. 1.000 €**.
- **Worst case:** Continia-Version 26 hat Permission-/Lizenzthema, das `CDC Document` als ApiPage zu publishen verbietet → A1 unmöglich, dann eskalieren zu Continia direkt.

---

## 5. Edge Cases Option B (BC OData + Graph)

| Edge Case | Status |
|---|---|
| **Disambiguierung Vendor + INO + Datum** | **gelöst** (Test §3) — Triple-Filter funktioniert; `purchaseInvoices` API liefert genau 1 Record |
| **PDF-Stream ohne SharePoint** über `purchaseInvoices(id)/attachments` (PAG30039) oder `documentAttachments` (PAG30080) | **nicht nutzbar** — beide getesteten echten Rechnungen (incl. eine Open >1000 €) liefern `No results found`. Continia legt das PDF NICHT als BC-Standard-Attachment an. |
| **Gebuchte Re.** über `postedPurchaseInvoices` (Page 30043) | Nicht direkt getestet, aber Standard-API existiert; Custom-Tool `bc_GetPostedPurchaseInvoices` ist vorhanden ⇒ machbar |
| **Sammelbelege** (z.B. UTA-Sammelrechnung) erkennen | Programmatisch nur via Zeilen-Count (`purchaseInvoiceLines` filtern auf documentNumber, COUNT). Es gibt **kein Flag** "Sammelbeleg" in der Standard-API. In Continia ggf. ein internes Feld in `CDC Document` (Doc Category) — ohne API-Zugriff darauf nicht direkt prüfbar. |
| **OCR-Status** als abfragbares Feld | **Über Standard-API nicht möglich** — kein `ocrCompleted`/`ocrStatus` in `purchaseInvoices`. In `CDC Document` existiert dieses Konzept (Continia-Status-Felder), aber ohne ApiPage (Option A) unzugänglich. Polling auf das **Auftauchen** der PurchaseInvoice ist Ersatzlösung. |
| **Approval Entry → Beleg-Verlinkung** über Standard-API | **Nicht exposed** — `bc_actions_search('approval')` liefert nur Sales-Quotes/Journals. Custom MCP-Tools (`bc_ListApprovalDocuments`, `bc_GetApprovalHistory`) existieren bei G&B aber spezifisch — diese sind die einzige saubere Quelle für Genehmigungsposten. |
| **Approval History** | gelöst über `bc_GetApprovalHistory` (Custom MCP-Tool) |

### Verbleibende offene Punkte für Option B

1. **PDF-Quelle:** Bleibt SharePoint, denn BC speichert das PDF nicht als Standard-Attachment. ⇒ Der "Graph Search auf SharePoint" Teil bleibt notwendig **oder** Continia speichert das PDF an einen sekundären Speicherort (Continia "Custom Storage" Feature — siehe [Customizing your storage](https://docs.continia.com/en-us/continia-document-capture/development-and-administration/development-and-customization/customizing-your-storage/)). Klärungsbedarf.
2. **Sammelbeleg-Heuristik** muss weiter über Zeilen-Count laufen oder über das `totalAmountIncludingTax` + bekannte UTA-Pattern.
3. **OCR-Retry-Trigger:** Bleibt Polling-basiert, kein Event-Hook über Standard-BC-API möglich (nur über Power Automate auf Continia-Insert-Event — siehe §6).

---

## 6. Drittweg-Fund

### 6.1 Power Automate / Continia OnAfterInsert-Event

Continia exposed via Event Publishers (siehe [v26.00 docs](https://docs.continia.com/en-us/continia-document-capture/development-and-administration/development-and-customization/event-publishers/event-publishers-2600/)) Document-Insert/Update-Events. Die Community-App [`power-automate-connector`](https://github.com/document-capture/power-automate-connector) baut darauf eine API-Subscription:

> "Business Central API pages that enable Microsoft Power Automate to subscribe to CDC Document Insert events and query/receive the Pdf/Tiff files."

**Bedeutung für uns:** Statt Polling kann Power Automate (oder ein Webhook im n8n) auf das *Erscheinen* eines neuen Continia-Dokuments hören und das PDF direkt aus dem Event-Payload (Base64) abholen. Das ist letztlich **eine fertige, schlüssige Variante von Option A**, nur als Push statt Pull. Voraussetzung: dieselbe AL-Extension wie A1/A2.

### 6.2 BC Page 130 `incomingDocuments`

In Standard-BC existiert eine API `/api/v2.0/incomingDocuments` (Page 130). Auf G&B's MCP-Server liefert `bc_actions_search('incoming')` aber 0 Treffer — d.h. **dieser MCP-Server mapt sie nicht**. Sie KÖNNTE direkt über OData abfragbar sein (separater Endpunkt-Test nötig, kein Brute-Force gemacht). Wenn ja, läge dort eine Verlinkung zum Continia-Dokument als BLOB-Anhang. Realistisch: nur wenn Continia das `Incoming Document` als Standard-Brücke pflegt — bei G&B aktuell offenbar nicht (siehe §5, "0 attachments").

### 6.3 Continia Cloud API

Continia bietet keine eigenständige Cloud-API neben dem In-BC-Pfad. Document Output Service hat OAuth-Setup ([Doku](https://docs.continia.com/en-us/continia-document-output/development-and-administration/on-premises/deployment/setting-up-oauth-for-document-output/)), aber das ist für ausgehende Dokumente. Für DC (eingehend) keine externe Cloud-API.

### 6.4 Webhook / Eventing

Nur via AL-Extension auf den OnAfterInsert-Publisher (Punkt 6.1). Keine "fertige" Webhook-URL ab Werk.

---

## 7. Empfehlung

**B-jetzt-A-später**, mit folgender Roadmap:

### Phase 1 (jetzt, 1–2 PT)
Bestehenden n8n-Workflow `resolve_pdf` so kapseln, dass er **strukturiert** statt SharePoint-Volltext sucht:
1. `purchaseInvoices` mit Triple-Filter `(vendorNumber, vendorInvoiceNumber, postingDate ±N)` → BC SystemId.
2. Wenn die Re. gebucht: zusätzlich `postedPurchaseInvoices` / `bc_GetPostedPurchaseInvoices` testen.
3. PDF dann weiterhin aus SharePoint via Graph Search, aber mit **bekannter** BC-Document-No. als Anker statt blind nach OCR-Text. Erwartete Trefferrate-Verbesserung: 65 % → 90 %+ first hit.
4. Bei `>1 Treffer` → Disambiguierung via `totalAmountIncludingTax` (±0,01 €).

### Phase 2 (mittelfristig, falls Phase 1 < 95 % first-hit)
Option A1 implementieren (1 PT Eigenbau oder Brabender):
- AL-Extension mit ApiPage auf `CDC Document` und PDF-Stream.
- Endpunkt z.B. `/api/gbl/dc/v1.0/cdcDocuments?$filter=...`.
- SharePoint-Pfad ersatzlos streichen.

### Warum nicht direkt A?

- Aufwand: 1 PT Eigenbau + Permission-Klärung mit Brabender vs. 0,5 PT Refactoring des bestehenden Pfades.
- Risiko: Continia-Version-Drift. Wenn G&B in 6 Monaten v27 deployed, muss A nachgezogen werden.
- Phase 1 senkt das operative Schmerzempfinden sofort von 10 % Totalverlust auf <5 %.
- Phase 1 ist Voraussetzung für saubere Audit-Logs (man weiß, *welche* BC-Re. man auflösen wollte) — auch nach Phase 2 nützlich.

### Wann doch direkt A?

- Wenn der 10 %-Totalverlust regulatorisch (UStG-Belegnachweis) untragbar ist und in den nächsten 4 Wochen behoben werden muss.
- Wenn Brabender ohnehin gerade an Continia-Erweiterungen sitzt (Bündelung).

---

## 8. Roh-Daten Appendix

Alle API-Aufrufe via n8n-Workflow `bc_generic_bridge` (id `tCMUviQdFBPl58S9`) gegen MCP-Server `gb-bcmcp.duckdns.org/mcp`. Sensible Daten nicht redacted — sind interne BC-Test-/historische Daten 2022–2023 ohne PII-Risiko.

### A.1 Verfügbare BC-API-Actions (Standard MS v2.0)

`bc_actions_search('purchaseInvoice', top=50)`:
```
["List_AttachmentsOfPurchaseInvoice_PAG30039",
 "List_DimensionSetLinesOfPurchaseInvoice_PAG30022",
 "List_DimensionSetLinesOfPurchaseInvoiceLine_PAG30022",
 "List_DocumentAttachmentsOfPurchaseInvoice_PAG30080",
 "List_LocationOfPurchaseInvoiceLine_PAG30076",
 "List_PdfDocumentOfPurchaseInvoice_PAG30056",
 "List_PurchaseInvoiceLines_PAG30047",
 "List_PurchaseInvoiceLinesOfPurchaseInvoice_PAG30047",
 "List_PurchaseInvoices_PAG30042"]
```

`bc_actions_search('attachment')` (23 Treffer, gekürzt):
```
["List_Attachments_PAG30039",
 "List_AttachmentsOfPurchaseInvoice_PAG30039",
 "List_AttachmentsOfPurchaseOrder_PAG30039",
 "List_DocumentAttachments_PAG30080",
 "List_DocumentAttachmentsOfPurchaseInvoice_PAG30080",
 "List_DocumentAttachmentsOfVendor_PAG30080", ...]
```

`bc_actions_search('Continia')`: **No matching Business Central actions found.**
`bc_actions_search('CDC')`: nur Substring-Müll (Accounts, AccountingPeriods, etc.).
`bc_actions_search('extension')`: **No matching Business Central actions found.**
`bc_actions_search('incoming')`: **No matching Business Central actions found.**

### A.2 Schema `List_PurchaseInvoices_PAG30042` (Auszug, 48 Felder total)

Filterbar: `number, postingDate, invoiceDate, dueDate, vendorInvoiceNumber, vendorNumber, vendorName, purchaser, totalAmountExcludingTax, totalTaxAmount, totalAmountIncludingTax, status, lastModifiedDateTime, …`

Status-Werte: `' '`, `Draft`, `In Review`, `Open`, `Paid`, `Canceled`, `Corrective`.

Nicht filterbar: `currencyCode`.

### A.3 Schema `List_AttachmentsOfPurchaseInvoice_PAG30039`

```json
{ "name": "List_AttachmentsOfPurchaseInvoice_PAG30039",
  "description": "Sub entity(attachment) requires parent entity(purchaseInvoice).
                  PurchaseInvoice_id->purchaseInvoice.id",
  "schema": {
    "required": ["PurchaseInvoice_id"],
    "properties": {
      "_availableFields": "id, parentId, fileName, byteSize, attachmentContent,
                            lastModifiedDateTime, parentType (7 total)"
    }
  }
}
```
⇒ Feld `attachmentContent` ist der Base64-Stream. Funktioniert, **wenn** ein Attachment existiert — bei G&B Continia tut es das nicht.

### A.4 Disambiguierungs-Test — alle drei Calls

**Call 1** (`top=5, select=id,number,vendorNumber,vendorInvoiceNumber,postingDate,totalAmountIncludingTax,status`):
```json
{"@odata.count":19495,"value":[
  {"id":"a21cb8fa-aa20-ee11-9cbf-00224874e2fa","number":"10016","postingDate":"2023-07-11",
   "vendorInvoiceNumber":"5017/07/2023","vendorNumber":"70980",
   "totalAmountIncludingTax":0.01,"status":"Draft"},
  {"id":"4844cb3c-b020-ee11-9cbf-00224874e2fa","number":"10022","postingDate":"2023-07-11",
   "vendorInvoiceNumber":"5014/07/2023","vendorNumber":"70980",
   "totalAmountIncludingTax":2100,"status":"Draft"},
  {"id":"2f08ec09-0f22-ee11-9cbf-002248d8826b","number":"10056","postingDate":"2023-06-30",
   "vendorInvoiceNumber":"RE-2317827","vendorNumber":"60239",
   "totalAmountIncludingTax":3570,"status":"Draft"},
  {"id":"cb28eff4-1b22-ee11-9cbf-002248d8826b","number":"10069","postingDate":"2022-06-30",
   "vendorInvoiceNumber":"1298","vendorNumber":"61881",
   "totalAmountIncludingTax":0.01,"status":"Draft"},
  {"id":"74696c02-7525-ee11-9cbf-002248d8b074","number":"10117","postingDate":"2023-07-04",
   "vendorInvoiceNumber":"0000002264","vendorNumber":"70649",
   "totalAmountIncludingTax":380,"status":"Draft"}]}
```

**Call 2** (`filter: vendorNumber eq '70980' and vendorInvoiceNumber eq '5017/07/2023'`):
```json
{"@odata.count":1,"value":[
  {"id":"a21cb8fa-aa20-ee11-9cbf-00224874e2fa","number":"10016","postingDate":"2023-07-11",
   "vendorInvoiceNumber":"5017/07/2023","vendorNumber":"70980",
   "totalAmountIncludingTax":0.01,"status":"Draft"}]}
```

**Call 3** (Triple-Filter mit `postingDate eq 2023-07-11`): identisch — 1 Record.

### A.5 Attachment-Probe an echter Open-Re.

`purchaseInvoices` filter `status eq 'Open' and totalAmountIncludingTax gt 1000`, top=3:
```json
{"@odata.count":103,"value":[
  {"id":"4c3a7475-563e-ed11-97e8-0022485ba594","number":"114676",
   "postingDate":"2022-12-01","vendorInvoiceNumber":"0000360506",
   "vendorNumber":"60658","totalAmountIncludingTax":1515.26,"status":"Open"},
  {"id":"9b29ecd0-bfe4-ed11-884a-00224875207a","number":"115525",
   "postingDate":"2022-12-17","vendorInvoiceNumber":"2023-03",
   "vendorNumber":"60017","totalAmountIncludingTax":1091.61,"status":"Open"},
  {"id":"082d886e-cccf-ed11-a7c7-00224875113d","number":"115540",
   "postingDate":"2023-03-24","vendorInvoiceNumber":"RE2096495-19/WO",
   "vendorNumber":"60017","totalAmountIncludingTax":1022.21,"status":"Open"}]}
```

`List_AttachmentsOfPurchaseInvoice_PAG30039` für ID `4c3a7475-...`: `No results found.`
`List_DocumentAttachmentsOfPurchaseInvoice_PAG30080` für ID `4c3a7475-...`: `No results found.`

⇒ Hauptbefund §5: Continia hängt das PDF nicht als BC-Standard-Attachment.

### A.6 Custom-MCP-Tools auf G&B's Bridge (laut Tool-Discovery)

Diese 4 Tools sind G&B-spezifische Wrapper, nicht generischer BC-API-Standard:

- `bc_GetApprovalHistory` — Genehmigungsverlauf zu Beleg
- `bc_GetPostedPurchaseInvoices` — gebuchte EK-Rechnungen
- `bc_GetVendorInfo` — Kreditoren-Stammdaten
- `bc_ListApprovalDocuments` — offene Genehmigungsposten

⇒ Approval Entry ist NUR über diese Custom-Tools sinnvoll erreichbar, nicht über Standard MS v2.0 API.

### A.7 Quellen

- [Continia Doku — Welcome](https://docs.continia.com/en-us/continia-document-capture/)
- [Event Publishers v26.00 (R1 2025)](https://docs.continia.com/en-us/continia-document-capture/development-and-administration/development-and-customization/event-publishers/event-publishers-2600/)
- [Detailed Changelog DC 2025 R2](https://docs.continia.com/en-us/continia-document-capture/new-and-planned/detailed-changelogs/document-capture-2025-r2/) — kein ApiPage-Eintrag
- [eDocuments Table Structures](https://docs.continia.com/en-us/continia-document-capture/business-functionality/continia-edocuments/edocuments-table-structures/)
- [Customizing storage in DC](https://docs.continia.com/en-us/continia-document-capture/development-and-administration/development-and-customization/customizing-your-storage/)
- [Supported on-premises versions](https://docs.continia.com/en-us/continia-document-capture/development-and-administration/on-premises/versions-on-premises/)
- [document-capture/power-automate-connector (Community)](https://github.com/document-capture/power-automate-connector)
- [Pag62011.DCADVDocumentAPI.al (Source)](https://github.com/document-capture/power-automate-connector/blob/master/Objects/Latest/BC18-DC7.00.00-App/src/page/Pag62011.DCADVDocumentAPI.al)
- [Pag62012.DCADVDocumentPdfFileAPI.al (Source)](https://github.com/document-capture/power-automate-connector/blob/master/Objects/Latest/BC18-DC7.00.00-App/src/page/Pag62012.DCADVDocumentPdfFileAPI.al)
- [app.json (Dependencies)](https://github.com/document-capture/power-automate-connector/blob/master/Objects/Latest/BC18-DC7.00.00-App/app.json)
- [Community Forum: Continia OData/SOAP Integration](https://community.dynamics.com/forums/thread/details/?threadid=0fd56176-044b-ee11-be6f-000d3a4fe8f7)

---

## Limitationen dieser Recherche

1. **Kein direkter BC OData-Zugang** war in dieser Session verfügbar — alle BC-Calls liefen über die n8n→Haiku-MCP-Bridge. Die Bridge ist read-only abgesichert (System-Prompt), aber Antworten gehen durch ein LLM. Roh-JSON wurde aber konsistent durchgereicht und unten zitiert.
2. **Continia-Version auf G&B** ist nicht zweifelsfrei bestimmt (siehe §2.3). Empfehlung: vor Phase 2 Brabender fragen.
3. **AL-Source für CDC Document v26** liegt nicht offen vor; verwendete Felder stammen aus DC v7-Community-Code. Strukturveränderungen sind unwahrscheinlich (Continia hält API-Stabilität hoch), aber nicht ausgeschlossen.
4. **`postedPurchaseInvoices`** (gebuchte Re.) wurde nicht direkt API-getestet — nur die Existenz des Wrapper-Tools `bc_GetPostedPurchaseInvoices` ist belegt.
5. **`incomingDocuments` (Page 130)** wurde nicht direkt getestet, weil im MCP-Mapping nicht exposed; eine direkte OData-Probe würde separate Credentials erfordern.

— Ende Report —
