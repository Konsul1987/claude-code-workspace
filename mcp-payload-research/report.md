# MCP-Payload-Limit — Analyse & Empfehlung

## TL;DR

- Das MCP-Protokoll spezifiziert **kein fixes 2–3-KB-Limit** für `tools/call.params.arguments`; es definiert JSON-RPC über stdio bzw. Streamable HTTP, Tool-Argumente als JSON-Objekt, Ressourcen als URI-lesbare Kontextobjekte und Pagination für Listenoperationen. Größenlimits sind damit überwiegend **Host-/Client-/Server-Implementierungsdetails**.
- Der n8n-MCP-Trigger-Code liest den HTTP-Body (`req.rawBody`), parst ihn mit `JSON.parse` und validiert ihn gegen die MCP-SDK-Schemas; im gelesenen Code ist **kein 2–3-KB-Stringlimit** erkennbar. n8n selbst dokumentiert für Endpoints `N8N_PAYLOAD_SIZE_MAX=16 MiB` default.
- Anthropic dokumentiert für Claude Code Output-Grenzen (Warnung >10.000 Tokens, Default max 25.000 Tokens) und für Claude.ai/Desktop bei MCP Apps ein Verhalten ab ca. 150.000 Zeichen Tool-Resultat — aber **kein öffentlich belegtes 2–3-KB-Inputlimit** für MCP-Tool-Argumente.
- Wahrscheinlichste Engstelle: **Anthropic Web-Chat/Cowork Remote-MCP-Client oder dessen Tool-Call-UI/Schema-Bridge vor n8n**, nicht die Bridge und wahrscheinlich nicht n8n-Core. Das 2–3-KB-Verhalten sollte mit n8n-Logs/Reverse-Proxy-Logs final verifiziert werden: kommt der POST bei n8n an oder nicht?
- Empfehlung: **Notion-Auftragsinbox als Top-Wahl**, ergänzt durch die bestehende `vps_file_write`-Chunking-Strecke und optional später Git-Mirror. Damit bleibt die Web-Chat-MCP-Nachricht klein, mobile Reviewbarkeit ist hoch, n8n/Notion passen in den Bestand, und die Bridge muss nicht öffentlich exponiert werden.

## A. Ursachen-Analyse

### A.1 MCP-Spec-Befund

#### Was die Spec tatsächlich festlegt

Die MCP-Spec 2025-06-18 definiert für Transporte:

- MCP-Nachrichten sind JSON-RPC und müssen UTF-8-codiert sein.
- Standard-Transporte sind `stdio` und Streamable HTTP.
- Bei Streamable HTTP wird jede Client→Server-JSON-RPC-Nachricht per HTTP POST an den MCP-Endpunkt gesendet.
- Der POST-Body ist eine einzelne JSON-RPC Request/Notification/Response.
- Die Spec erlaubt Custom Transports, solange JSON-RPC-Format und Lifecycle-Anforderungen erhalten bleiben.

Quellen:

- Transport-Übersicht und JSON-RPC/UTF-8: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#L79-L83
- HTTP POST / Body ist eine einzelne JSON-RPC-Nachricht: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#L116-L125
- Custom Transports / transport-agnostisch: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#L204-L206

Für Tools legt die Spec fest:

- Tools sind model-controlled; Implementierungen dürfen aber eigene UI-Patterns verwenden.
- `tools/list` unterstützt Pagination.
- `tools/call` enthält `params.name` und `params.arguments`.
- Tool-Resultate können Text, Bilder, Audio, Resource Links, Embedded Resources und structuredContent enthalten.
- Tools dürfen Resource Links zurückgeben, um zusätzliche Daten per URI verfügbar zu machen.

Quellen:

- Tool-Interaktionsmodell: https://modelcontextprotocol.io/specification/2025-06-18/server/tools#L84-L90
- `tools/list` mit Pagination: https://modelcontextprotocol.io/specification/2025-06-18/server/tools#L116-L153
- `tools/call.params.arguments`: https://modelcontextprotocol.io/specification/2025-06-18/server/tools#L156-L170
- Resource Links in Tool-Resultaten: https://modelcontextprotocol.io/specification/2025-06-18/server/tools#L261-L279
- Embedded Resources: https://modelcontextprotocol.io/specification/2025-06-18/server/tools#L281-L299

Für Resources legt die Spec fest:

- Resources sind URI-identifizierte Kontextdaten wie Dateien, DB-Schemas oder anwendungsspezifische Informationen.
- `resources/list` und `resources/templates/list` unterstützen Pagination.
- `resources/read` liest Resource-Inhalte per URI.
- Resource-Metadaten enthalten optional `size` in Bytes, damit Hosts Dateigrößen und Kontextnutzung einschätzen können.
- Resource-Inhalte können Text oder Base64-Binary sein.

Quellen:

- Resource-Konzept und URI: https://modelcontextprotocol.io/specification/2025-06-18/server/resources#L75-L87
- `resources/list` und Pagination: https://modelcontextprotocol.io/specification/2025-06-18/server/resources#L145-L174
- `resources/read`: https://modelcontextprotocol.io/specification/2025-06-18/server/resources#L177-L203
- Resource `size`: https://modelcontextprotocol.io/specification/2025-06-18/server/resources#L279-L289
- Text/Binary Resource Contents: https://modelcontextprotocol.io/specification/2025-06-18/server/resources#L292-L313

#### Was die Spec nicht festlegt

Ich habe in den relevanten Spezifikationsseiten und im TypeScript-Schema keinen normativen Maximalwert für folgende Größen gefunden:

- maximale HTTP-Request-Body-Größe;
- maximale Länge eines einzelnen `arguments.prompt`-Strings;
- maximale Größe eines Tool-Result-Textblocks;
- automatische Chunking-Pflicht für Tool-Inputs.

Das Schema beschreibt `CallToolRequest.params.arguments` als frei strukturierbares JSON-Objekt (`{ [key: string]: unknown }`) ohne Längenconstraint; `CallToolResult.content` ist eine Liste von Content Blocks. Quelle: https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2025-06-18/schema.ts#L46-L50

**Zwischenbefund:** Ein 2–3-KB-Limit ist **nicht MCP-Spec-konform als Protokollgrenze belegbar**. Es kann aber sehr wohl durch Host, Client, Reverse Proxy, Body Parser, Schema-Wrapper, UI-Safety-Layer oder Tool-Result-Injection-Layer entstehen.

#### Chunked-/Large-Payload-Patterns in der Community

Explizite Large-Payload-Mechanismen sind eher Patterns/Proposals als Kernstandard:

1. **Resource-Link statt Inline-Blob:** Tool gibt URI/ID zurück; Client liest bei Bedarf über `resources/read`.
2. **Pagination und Detail-on-demand:** Listen/Suchergebnisse klein halten; Details nur auf Nachfrage.
3. **Async/Job/Resource-Polling:** Tool startet Job und gibt Operation-/Resource-URI zurück.
4. **Out-of-band File Upload:** vorgeschlagene Binary Elicitation mit Upload-Endpunkten.

Belege:

- MCP Issue #982 fasst Async-/Long-running-Vorschläge zusammen, darunter Resource-basierte Status-/Result-Ansätze, Polling und Rejoin nach Disconnect: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/982#L243-L261
- Dasselbe Issue nennt als Hauptansätze Polling, Resource-based status tracking und Async tool calls mit Rejoin: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/982#L273-L298
- SEP-1306 schlägt Binary Elicitation/File Uploads mit `maxFileSize`, Upload-URLs und multipart Upload vor: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1306#L252-L271 und https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1306#L405-L430
- GitHub Community Discussion #169224 empfiehlt bei großen MCP-Outputs Zusammenfassungen plus `downloadPayload(id)` oder virtuelle Resources statt Inline-Payloads: https://github.com/orgs/community/discussions/169224#L287-L289 und https://github.com/orgs/community/discussions/169224#L519-L523
- `mcp-framework` macht `maxMessageSize` ausdrücklich zu einer Transport-Implementierungsoption, Default 4 MB — ein Gegenbeispiel zur Idee eines universellen 2–3-KB-MCP-Limits: https://github.com/QuantGeekDev/mcp-framework#L733-L745

### A.2 n8n-MCP-Server-Befund

#### Welcher n8n-MCP-Server relevant ist

Für die beschriebene Pipeline ist am wahrscheinlichsten der **eingebaute n8n MCP Server Trigger** relevant (`@n8n/n8n-nodes-langchain`, Pfad im n8n-Monorepo: `packages/@n8n/nodes-langchain/nodes/mcp/McpTrigger`). Die n8n-Doku sagt:

- Der MCP Server Trigger macht n8n-Tools/Workflows für MCP-Clients verfügbar.
- Er unterstützt SSE und Streamable HTTP.
- Er unterstützt **nicht** stdio.
- Er kann Bearer Auth oder Header Auth verlangen.
- Bei mehreren Webhook-Replikas müssen `/mcp*`-Requests auf eine dedizierte Replica geroutet werden.
- Reverse Proxies müssen für SSE/Streamable HTTP korrekt konfiguriert werden, insbesondere Proxy Buffering aus.

Quellen:

- Funktionsbeschreibung und SSE/Streamable HTTP: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/#L1489-L1493
- Auth-Methoden: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/#L1504-L1511
- Multi-Replica-Hinweis: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/#L1578-L1586
- Reverse-Proxy-Hinweise: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/#L1593-L1624

#### Code-Lesung: Message Parser

Der n8n-Code parst den Body im `MessageParser` so:

- `parse(body: string)` macht `JSON.parse(body)`.
- Danach validiert er `JSONRPCMessageSchema.parse(message)` aus dem offiziellen MCP TypeScript SDK.
- `extractToolCallInfo(body)` extrahiert `params.name` und `params.arguments`, wenn `arguments` ein Objekt ist.
- Im Code ist kein `maxLength`, kein Byte-Counter und kein 2–3-KB-spezifischer Guard sichtbar.

Code-Link:

- `MessageParser.ts` mit `JSON.parse` und MCP-Schema-Parse: https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/protocol/MessageParser.ts#L17-L24
- `extractToolCallInfo` prüft nur Objektstruktur und gibt `arguments` zurück: https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/protocol/MessageParser.ts#L50-L74

#### Code-Lesung: Request Handling / Tool-Aufruf

Im `McpServer.ts`-Pfad ist der relevante Ablauf:

- `handleStreamableHttpSetup` reicht `req.body` an den Transport weiter.
- `handlePostMessage` liest `req.rawBody.toString()`.
- Daraus wird `toolCallInfo` extrahiert.
- Wenn eine Session/Transport existiert, wird die Nachricht über `transport.handleRequest(...)` an den MCP SDK Server gegeben.
- Der Tool-Handler übernimmt `request.params.arguments` als `toolArguments` und ruft `executionCoordinator.executeTool(requestedTool, toolArguments, ...)` auf.
- Auch hier: keine sichtbare harte 2–3-KB-Begrenzung für ein `prompt`-Feld.

Code-Links:

- `handleStreamableHttpSetup` nutzt `transport.handleRequest(req, resp, req.body)`: https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/McpServer.ts#L79-L104
- `handlePostMessage` liest `req.rawBody.toString()` und extrahiert Tool-Call-Info: https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/McpServer.ts#L106-L130
- Request wird an `transport.handleRequest(...)` übergeben: https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/McpServer.ts#L163-L176
- Tool-Handler übernimmt `request.params.arguments` und führt Tool aus: https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/McpServer.ts#L431-L494

#### n8n allgemeines Body-Limit

n8n dokumentiert für Endpoints:

- `N8N_PAYLOAD_SIZE_MAX` default `16`, Beschreibung: maximale Payload-Größe in MiB.
- `N8N_FORMDATA_FILE_SIZE_MAX` default `200` MiB.

Quelle: https://docs.n8n.io/hosting/configuration/environment-variables/endpoints/#L1452-L1461

**Bewertung:** Ein 2–3-KB-Limit passt nicht zu n8n's dokumentiertem Endpoint-Limit und ist im gelesenen MCP-Trigger-Code nicht auffindbar. Ein n8n-Problem bleibt möglich, aber dann eher in einem vorgelagerten Auth-/Webhook-/Proxy-/Execution-Wrapper, nicht in der sichtbaren Tool-Input-Logik.

#### n8n Issue-Hinweis zu Parametern

Issue #16989 berichtet, dass bei Cursor/Claude nur Query-Parameter im MCP Server Trigger sichtbar seien, während Body/Header/Env nicht wie erwartet im Workflow ankämen. Das ist kein Payload-Size-Beweis, zeigt aber, dass **Client→n8n Parameterdurchreichung im MCP Trigger praktisch verwirrend/limitiert wirken kann** und dass n8n/Client-Semantik getrennt betrachtet werden muss. Quelle: https://github.com/n8n-io/n8n/issues/16989#L203-L220

### A.3 Anthropic-Client-Befund

#### Claude Code

Anthropic dokumentiert für Claude Code MCP:

- Claude Code zeigt eine Warnung, wenn MCP-Tool-Output >10.000 Tokens ist.
- `MAX_MCP_OUTPUT_TOKENS` konfiguriert den maximal erlaubten MCP-Tool-Output.
- Default Maximum ist 25.000 Tokens.
- Ressourcen können per `@server:protocol://resource/path` referenziert werden; Claude Code listet/liest MCP Resources, wenn Server das unterstützen.

Quellen:

- MCP Output Limits: https://docs.claude.com/en/docs/claude-code/mcp#mcp-output-limits-and-warnings
- Snippet im Suchindex mit Warnschwelle und Default: https://docs.claude.com/en/docs/claude-code/mcp
- Resource-Referenzierung: https://docs.claude.com/en/docs/claude-code/mcp#use-mcp-resources

Wichtig: Das betrifft **Tool-Output**, nicht den Input-Body eines Web-Chat-Tool-Calls. Für `tools/call.params.arguments.prompt` habe ich in den öffentlichen Claude-Code-Docs kein 2–3-KB-Limit gefunden.

#### Claude.ai / Claude Desktop / MCP Apps

Anthropic dokumentiert für MCP Apps:

- Wenn ein Tool-Result ungefähr 150.000 Zeichen überschreitet und Claude's Code Execution Sandbox aktiv ist, wird das Resultat in das Sandbox-Dateisystem geschrieben und die App bekommt einen Pointer statt strukturierter Inline-Daten.
- Diese ~150.000-Zeichen-Schwelle ist spezifisch für Claude.ai und Claude Desktop.
- Claude Code verwendet stattdessen das separate 25.000-Token-Default-Limit.
- Empfohlen werden Pagination, Fetch-details-on-demand und Defer-heavy-content.

Quelle: https://claude.com/docs/connectors/building/mcp-apps/troubleshooting#L133-L141

Auch das ist ein **Output-/Rendering-/Hydration-Limit**, kein belegtes 2–3-KB-Inputlimit.

#### Claude.ai Remote MCP / Custom Connectors

Anthropic Help Center sagt für Custom Integrations via Remote MCP, dass Claude von Anthropic Cloud Infrastructure zum Remote-MCP-Server verbindet; lokale Claude Desktop MCP-Server sind davon getrennt und nicht in Cowork/claude.ai verfügbar. Quelle: https://support.anthropic.com/en/articles/11175166-getting-started-with-custom-integrations-using-remote-mcp

Das passt zur Beobachtung: Web-Chat/Cowork kann `localhost:9999` nicht erreichen; nur der remote erreichbare n8n-MCP-Endpunkt ist erreichbar.

#### Ergebnis Anthropic

Öffentlich belegbar sind:

- Output-Limits und Warnungen;
- Claude.ai/Desktop-spezifische große Tool-Result-Behandlung;
- Remote-MCP-Verbindungsmodell aus Anthropic Cloud.

Nicht öffentlich belegt ist:

- ein offizielles 2–3-KB-Limit für MCP Tool-Input-Argumente im Web-Chat.

Daher ist ein Anthropic-seitiges 2–3-KB-Inputlimit derzeit **Hypothese**, aber angesichts n8n-Code und n8n-Default-Limit die wahrscheinlichste Hypothese.

### A.4 Konkrete Engstelle

#### Wahrscheinlichkeitsbewertung

| Layer | Befund | Wahrscheinlichkeit als 2–3-KB-Engstelle |
|---|---|---:|
| Bridge 9999/9998 | Laut Problemstatement schluckt Express MB; kein Research-Gegenbeleg. | niedrig |
| n8n allgemeiner HTTP Endpoint | Default `N8N_PAYLOAD_SIZE_MAX=16 MiB`. | niedrig |
| n8n MCP Trigger Code | `req.rawBody` → `JSON.parse` → MCP-Schema; kein Größenlimit sichtbar. | niedrig bis mittel |
| Reverse Proxy / Hostinger / nginx | Nicht geprüft; kann Limits setzen, aber 2–3 KB wäre ungewöhnlich. | mittel, falls Requests n8n gar nicht erreichen |
| Anthropic Remote MCP Client / Web-Chat Tool-Call Layer | Kein öffentliches Inputlimit, aber Remote-MCP-Cloud-Layer ist der letzte nicht einsehbare Layer und passt zu stillem „Error occurred during tool execution“. | hoch |
| Tool schema / prompt field schema | n8n-Code validiert nur JSON-RPC/MCP-Struktur; Tool-spezifische Zod/LangChain-Schema-Validierung könnte ein Limit setzen, falls im Workflow-Schema definiert. | mittel, durch Workflow zu prüfen |

#### Prominentestes Zwischenfazit

**Der Research widerspricht der Hypothese „n8n MCP Server hat ein generisches 2–3-KB-Bodylimit“.** In öffentlich sichtbarem n8n-Code und n8n-Doku ist dieses Limit nicht belegt. Die Engstelle liegt wahrscheinlich **vor n8n** im Anthropic-Web-Chat/Remote-MCP-Client-Pfad oder in einer spezifischen Tool-Schema-/Workflow-Konfiguration.

#### Konkreter Verifikationsplan

Ohne Betrieb zu brechen, sollte ein einziger Diagnose-Durchlauf klären, wo die Grenze liegt:

1. **n8n Reverse-Proxy Access Log aktivieren/prüfen:** Kommt ein 4-KB-Tool-Call-POST am `/mcp...`-Endpoint an?
2. **n8n Workflow Execution Log prüfen:** Wird eine Execution gestartet, bevor Claude „Error occurred during tool execution“ zeigt?
3. **n8n MCP Trigger Debug-Workflow:** Temporär ein Tool, das nur `Object.keys(arguments)` und `prompt.length` zurückgibt, ohne Bridge-Aufruf.
4. **Direkter MCP-HTTP-Test außerhalb Claude:** Mit `curl` oder MCP Inspector 4 KB, 16 KB, 64 KB an n8n senden. Wenn das klappt, ist Anthropic/Web-Chat sicherer Kandidat.
5. **Tool-Schema prüfen:** Falls die n8n Custom Workflow Tool ein JSON Schema/Zod-Limit auf `prompt` enthält, explizit entfernen/erhöhen.

## B. Lösungs-Evaluation

### B.1 Option 1: Notion-Auftragsinbox

**Pattern:** Der Web-Chat-MCP-Call enthält nur `notion_page_id` oder `task_id`. Der eigentliche Auftrag steht in Notion. n8n/Bridge liest Notion via API, normalisiert in eine lokale Markdown-Datei und ruft Claude Code/Codex mit „Read task file and execute“ auf.

**Warum das zum Stack passt:**

- Notion ist bereits zentrale Doku-/Datenbank-Plattform.
- Mobile Eingabe/Review am iPhone ist stark.
- Notion-Seiten sind versioniert und kommentierbar.
- MCP-Payload bleibt klein und stabil.
- Kein öffentlicher Tunnel zur Bridge nötig.

**Empfohlene Zielstruktur in Notion:**

- Database: `AI Task Inbox`
- Properties:
  - `Status`: Draft / Ready / Running / Needs Review / Done / Failed
  - `Target`: Claude / Codex / Dual Review
  - `Priority`
  - `Repo/Project`
  - `Created by`
  - `Approved`: Checkbox
  - `Execution ID`
  - `Result URL/File`
  - `Last Error`
- Page body: voller Auftrag in Markdown.

**Security-Konzept:**

- Notion Integration Token nur mit Zugriff auf diese eine DB.
- Bridge nimmt nur `page_id`, nicht freien Prompt.
- n8n prüft `Status=Ready` und `Approved=true`.
- Bridge schreibt Task-Datei mit `0600` und loggt Hash + Page-ID.
- Optional: Allowlist für Zielpfade/Repos.

**Risiken:**

- Notion API Rate Limits / Verfügbarkeit.
- Notion-Versionierung ist für Review gut, aber nicht so diff-/merge-stark wie Git.
- Notion-Seiteninhalt muss zuverlässig in Markdown normalisiert werden.

### B.2 Option 2: Git-basierte Inbox

**Pattern:** Repository `gb-tasks` auf VPS. Aufträge liegen als Markdown in `tasks/queue/`; Worker pollt, lockt Task, führt aus, verschiebt nach `tasks/done/` oder `tasks/failed/` und committet Resultate/Logs.

**Vorteile:**

- Exzellente Auditierbarkeit, Diffs, Branches, Reverts.
- Anbieterarm und austauschbar.
- Passt zu Code-Arbeit und PR-Review.
- Offline-/CLI-freundlich.

**Nachteile im konkreten Kontext:**

- Konstantin nutzt GitHub bisher sporadisch.
- Mobile-first Auftragserstellung ist schlechter als Notion, wenn keine gute Mobile-Web-UI davor liegt.
- Zusätzlicher Worker-/Locking-/Retry-Code nötig.

**Security-Konzept:**

- Private Repo oder VPS-local Git bare repo.
- Deploy key mit minimalen Rechten.
- Worker läuft als eigener User.
- Task-Dateien dürfen nur aus `tasks/queue/` gelesen werden; keine beliebigen Pfade.
- Signierte Commits optional.

**Empfehlung:** Nicht als erster Schritt, aber als **Audit-Mirror** sehr attraktiv: Notion bleibt UI, n8n exportiert jede freigegebene Task als Markdown nach Git.

### B.3 Option 3: Direkter Bridge-Zugang via Tailscale / Cloudflare Tunnel

**Pattern:** Bridge-Port 9999/9998 wird über Tailscale Funnel/Serve, Cloudflare Tunnel oder ähnlichen Zero-Trust-Tunnel erreichbar. Web-Chat-Claude könnte theoretisch direkt HTTP POSTs absetzen, wenn der Client externe HTTP Tools/Connectors nutzen darf.

**Vorteile:**

- Umgeht n8n-MCP-Payload-Pfad.
- Niedrige Latenz.
- Kein Notion-/Git-Indirection nötig.
- Direkter Debug einfacher.

**Schwerwiegende Risiken:**

- Bridge ist ein Code-Ausführungs-Gateway. Öffnen ohne starkes Auth-Konzept ist ein RCE-Risiko.
- Auth darf nicht nur „Bearer Token im Prompt“ sein; der Token kann in Chat-Kontexten landen.
- Rate limiting, request signing, replay protection, audit logs und path allowlists wären Pflicht.
- Lokale `localhost`-Bindung der Bridge ist aktuell eine Sicherheitsbarriere. Die Spec warnt ausdrücklich: lokale Server sollten localhost binden und Proper Auth verwenden, um DNS-Rebinding/Remote-Missbrauch zu verhindern. Quelle: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#L105-L113

**Minimal akzeptables Auth-Konzept:**

- Tunnel vor Bridge, nicht Bridge direkt ins Internet.
- Cloudflare Access oder Tailscale ACL mit Identitätsprüfung.
- Zusätzlich HMAC-Signatur je Request: `X-Timestamp`, `X-Nonce`, `X-Signature=HMAC(secret, timestamp.nonce.body)`.
- 60-Sekunden Zeitfenster, Nonce-Store gegen Replay.
- Per-Target allowlist: `claude`, `codex`, erlaubte Working Dirs.
- Max Body Size explizit, z. B. 2 MiB.
- Audit Log: requester, hash, bytes, target, command mode, exit status.
- Human approval für destructive modes.

**Bewertung:** Als interner Admin-/Cowork-Weg interessant, aber **nicht Top-Wahl** für Web-Chat-Mobile-Aufträge, weil die Security-Oberfläche deutlich größer wird.

### B.4 Option 4+: weitere Patterns aus GitHub / Community

#### Option 4 — MCP Resource Pointer / Job-Resource Pattern

Tool call bleibt klein: `create_task({source_uri})` oder `start_job({task_ref})`. Tool antwortet mit `resource_link` oder Job-ID. Der Client/Bridge liest Details über `resources/read` oder per separatem Storage.

Belege:

- MCP Tools können Resource Links zurückgeben: https://modelcontextprotocol.io/specification/2025-06-18/server/tools#L261-L279
- MCP Resources sind URI-basierte Kontextdaten und per `resources/read` abrufbar: https://modelcontextprotocol.io/specification/2025-06-18/server/resources#L75-L87 und https://modelcontextprotocol.io/specification/2025-06-18/server/resources#L177-L203
- Async-/long-running-Issue #982 nennt Resource-basierte Status-/Result-Patterns: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/982#L243-L261

**Bewertung:** Architektonisch sauber, aber hängt davon ab, ob Claude Web-Chat/Cowork die Resources im benötigten Flow zuverlässig nutzt. Für euren bestehenden n8n-Workflow ist Notion als Resource-Backend einfacher.

#### Option 5 — Chunked Upload als generischer Task-Blob

Bestehendes `vps_file_write`-Chunking wird zum Standard: Web-Chat sendet Chunks an n8n, finalisiert `/home/claude-code/projects/tasks/<id>.md`, zweiter MCP-Call startet Ausführung per `task_file`.

**Bewertung:** Schon vorhanden und robust, aber aus UX-Sicht schlechter als Notion: mehrere Calls, Fehler bei Chunk-Reihenfolge, keine angenehme mobile Review-Oberfläche. Gute Fallback-/Bulk-Upload-Route.

#### Option 6 — Microsoft-affine Alternative: SharePoint/OneDrive/Graph Task Inbox

Da Microsoft-Stack-affine Wahl bevorzugt wird, wäre SharePoint/OneDrive technisch ähnlich zu Notion: Auftrag als `.md`/Loop/Word-Seite, MCP enthält File-ID, Bridge liest via Microsoft Graph.

**Bewertung:** Nur wählen, wenn bestehende Microsoft-365-Governance/Auth deutlich stärker ist als Notion. Da Notion bereits gesetzt ist und nicht migriert werden soll, wäre es zusätzlicher Lock-in/Aufwand ohne genug Mehrwert.

#### Option 7 — MCP Gateway/Mediator

Ein eigener MCP Gateway sitzt zwischen Anthropic und n8n/Bridge, erzwingt kleine Tool-Calls, verwaltet Storage, Auth, Pagination, Job-Status und Resources. Community/RFCs diskutieren Mediator-/Gateway-ähnliche Patterns und Async/Resource-Status.

**Bewertung:** Langfristig sauber, kurzfristig Overengineering. Könnte Phase 4 werden, wenn mehrere Clients/Agents/Teams angebunden werden.

### B.5 Bewertungsmatrix

Skala bei qualitativen Spalten: 1 = schlecht/hoch riskant, 5 = sehr gut. Aufwände sind grobe Netto-Schätzungen für MVP im bestehenden Stack.

| Option | Aufwand initial (h) | Wartung (h/Monat) | Robustheit gegen MCP-Änderungen | Mobile-Freundlichkeit | Sicherheit (Auth, Surface) | Auditierbarkeit | Kosten laufend | Lock-in |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 Notion-Auftragsinbox | 6–10 | 1–2 | 5 — MCP enthält nur ID | 5 — Notion iPhone stark | 4 — kleiner MCP-Call, Notion token scoped | 4 — Notion history + n8n logs | niedrig, bestehender Plan/API | mittel — Notion API, aber Markdown exportierbar |
| 2 Git-basierte Inbox | 10–16 | 1–2 | 5 — außerhalb MCP | 2–3 ohne Extra-UI | 4 — SSH/deploy keys gut kontrollierbar | 5 — Git-Historie perfekt | sehr niedrig | niedrig |
| 3 Tunnel zur Bridge | 8–14 für sicher, 2–3 unsicher | 2–4 | 5 — MCP umgangen | 3 — abhängig von Tool/Connector | 2 ohne HMAC/Zero Trust, 4 mit vollem Konzept | 3–4 bei gutem Logging | Tailscale/Cloudflare niedrig | mittel — Tunnel-Provider austauschbar, aber Betriebsmodell bindet |
| 4 MCP Resource/Job Pattern | 12–24 | 2–4 | 3–4 — Spec-konform, Client-Support variiert | 3 — hängt vom Client-UX ab | 4 — kleine Calls + Resource ACL | 4 | niedrig | niedrig bis mittel |
| 5 Chunked Upload standardisieren | 4–8, da Basis existiert | 1–2 | 5 — payload wird in Chunks begrenzt | 2 — mehrere Calls nervig am iPhone | 4 — bestehende n8n Auth + Pfadkontrolle | 3–4 | niedrig | niedrig |
| 6 SharePoint/OneDrive Inbox | 10–18 | 2–3 | 5 — MCP enthält nur ID | 4 — M365 Mobile gut | 4–5 — Entra/Graph stark, wenn vorhanden | 4–5 | M365 ggf. bestehend | mittel bis hoch — Graph/SharePoint |
| 7 Eigener MCP Gateway/Mediator | 24–60 | 4–8 | 4 — kontrollierte Abstraktion, aber selbst MCP pflegen | 3–4 | 4 bei sauberer Implementierung | 5 | VPS niedrig, Dev-Aufwand hoch | niedrig, wenn Open Source |

## C. Empfehlung

### C.1 Top-Empfehlung & Begründung

**Klare Top-Wahl: Option 1 — Notion-Auftragsinbox, kombiniert mit bestehendem `vps_file_write` als Fallback und optionalem Git-Mirror ab Phase 2.**

Begründung:

1. **Löst das eigentliche Problem:** Der MCP-Tool-Call wird auf eine kleine ID reduziert. Das 2–3-KB-Limit wird irrelevant, egal ob es bei Anthropic, n8n oder Schema-Wrapper sitzt.
2. **Passt maximal in den Bestand:** Notion ist gesetzt, n8n ist da, Bridge ist da, Mobile ist wichtig.
3. **Sicherer als Tunnel:** Die Bridge bleibt localhost-only. Es wird kein RCE-Gateway ins Internet gestellt.
4. **Mobile-first:** Konstantin kann am iPhone lange Aufträge schreiben/reviewen, Status setzen und später Resultate sehen.
5. **Auditierbar genug für MVP:** Notion-History + n8n Execution Logs + lokale Task-Dateien mit Hash. Git-Mirror kann Audit auf 5/5 erhöhen.
6. **Geringer Lock-in:** Task-Body ist Markdown; Export nach Git oder SharePoint bleibt möglich.
7. **Automation-first:** Sobald Status `Ready` + `Approved=true`, kann n8n/Bridge automatisch ausführen.

Nicht empfohlen als erste Wahl:

- **Tunnel zur Bridge**: technisch attraktiv, aber Security-Surface zu groß für den Nutzen.
- **Git-only Inbox**: auditierbar, aber schlechtere mobile UX und höhere Adoption-Hürde.
- **Eigener MCP Gateway**: sauber, aber für das aktuelle Problem zu groß.

### C.2 Migrationsplan in Phasen

#### Phase 0 — Diagnose und Sicherheits-Baseline (0,5 Tag)

Ziel: Erkenntnis absichern, ohne Betrieb zu ändern.

- Test-Tool in n8n anlegen: nimmt `prompt`, gibt `prompt.length`, SHA-256 und `received=true` zurück.
- Von Claude Web-Chat mit 1 KB, 2 KB, 3 KB, 4 KB testen.
- n8n Access-/Execution-Logs prüfen: erreicht der Request n8n?
- Mit direktem HTTP/MCP-Test gegen n8n dieselben Größen testen.
- Ergebnis dokumentieren: Anthropic-vorgelagert vs. n8n/schema.

Exit-Kriterium: Engstelle ist operational eingegrenzt.

#### Phase 1 — Notion Inbox MVP (1–2 Tage)

Ziel: Produktionsfähiger Weg für lange Aufträge ohne große MCP-Prompts.

- Notion DB `AI Task Inbox` erstellen.
- Notion Integration Token scoped auf diese DB.
- n8n Workflow `task_inbox_execute`:
  1. MCP Tool nimmt `{ page_id, target }` entgegen.
  2. Notion Page abrufen.
  3. Prüfen: `Status=Ready`, `Approved=true`, Target allowlisted.
  4. Page Content nach Markdown serialisieren.
  5. Lokale Task-Datei schreiben: `/home/claude-code/projects/inbox/<page_id>.md` bzw. Codex-Pfad.
  6. Bridge mit kurzem Prompt aufrufen: `Read <file> and execute. Report result to task id <page_id>.`
  7. Status auf `Running`, später `Done`/`Failed` setzen.
- Resultat in Notion zurückschreiben: Summary, Log-Link, Exit Code, PR/Commit-Link falls vorhanden.

Exit-Kriterium: Ein >20-KB-Auftrag kann vom iPhone in Notion erstellt und per kleinem MCP-Call gestartet werden.

#### Phase 2 — Git-Mirror und Audit-Härtung (0,5–1 Tag)

Ziel: Auditierbarkeit verbessern, ohne Notion UX zu verlieren.

- Repo `gb-tasks` anlegen, privat oder VPS-local.
- n8n exportiert jede freigegebene Task als Markdown nach `tasks/YYYY/MM/<page_id>.md`.
- Resultate nach `results/<page_id>.md`.
- Automatische Commits mit Author `n8n-task-bot`.
- Commit-Hash zurück in Notion speichern.

Exit-Kriterium: Jede Task hat Notion-ID, Datei-Hash und Git-Commit.

#### Phase 3 — Queue/Locking/Retry (1 Tag)

Ziel: Betriebssicherheit.

- Lock-Datei oder DB-Property `Execution Lock` setzen.
- Idempotency Key: `page_id + last_edited_time + target`.
- Retry-Regeln: z. B. 2 automatische Retries bei transienten Fehlern, sonst `Failed`.
- `deep_health_check` erweitert um Notion Token, Workflow aktiv, Bridge erreichbar, Schreibrechte Inbox.
- Alert bei `Running` > X Minuten.

Exit-Kriterium: Keine Doppelstarts, klare Fehlerzustände, Health Check deckt neue Route ab.

#### Phase 4 — Optional: MCP Resource/Gateway oder sicherer Tunnel (später)

Nur wenn nötig:

- MCP Resource Server für `notion-task://<page_id>` oder `gb-task://<id>` implementieren.
- Oder Cloudflare/Tailscale Tunnel nur mit Zero Trust + HMAC + Allowlist.
- Kein direkter Bridge-Tunnel ohne Phase-3-Audit und Auth.

### C.3 Risiken

| Risiko | Auswirkung | Gegenmaßnahme |
|---|---|---|
| Notion API Ausfall / Rate Limit | Tasks können nicht gestartet/gelesen werden | Retry, Status `Blocked`, Fallback `vps_file_write` |
| Falsche Page-ID / unfreigegebene Task | Falsche oder unfertige Ausführung | `Approved=true`, Status `Ready`, Created-by/Workspace-Prüfung |
| Prompt Injection in Notion-Task | Agent macht unerwünschte Aktionen | Systemprompt/Bridge-Regeln: Task ist untrusted input; allowlisted paths; Human approval für destructive ops |
| Doppelte Ausführung | Konflikte/Mehrfachänderungen | Lock + Idempotency Key + Statuswechsel atomar |
| Notion Markdown-Konvertierung verliert Struktur | Agent arbeitet mit kaputtem Auftrag | Serializer testen; Original-Block-JSON optional als Anhang speichern |
| Secrets im Task-Text | Leaks in Logs/Git | Secret Scanner vor Git-Mirror; Warnung/Block bei API-Key-Mustern |
| GitHub-Adoption gering | Git-Mirror wird nicht genutzt | Git nur im Hintergrund; Notion bleibt UI |
| Tunnel wird „mal schnell“ unsicher geöffnet | RCE-Surface | Policy: Bridge bleibt localhost-only bis HMAC/Zero Trust/Logs umgesetzt |
| Anthropic ändert MCP-Client-Verhalten | Bestehende große Live-Prompts brechen weiter | ID-only-Pattern bleibt robust |

### C.4 Offene Fragen an Konstantin

1. **Welche Notion-Datenbank soll die Inbox hosten?** Neue DB `AI Task Inbox` oder bestehende zentrale Operations-/Memory-DB erweitern?
2. **Welche Freigabelogik ist gewünscht?** Reicht `Status=Ready`, oder zusätzlich `Approved=true` zwingend?
3. **Welche Targets sind in Phase 1 erlaubt?** Nur Claude, nur Codex, oder direkt `Dual Review`?
4. **Wo sollen Task-Dateien lokal liegen?** Vorschlag: `/home/claude-code/projects/inbox/` und `/home/codex/projects/inbox/`.
5. **Soll Git-Mirror sofort in Phase 1 oder erst Phase 2 kommen?** Empfehlung: Phase 2, damit MVP schnell steht.
6. **Wie lange sollen lokale Task-/Log-Dateien aufbewahrt werden?** Vorschlag: 180 Tage lokal, dauerhaft in Git/Notion-Metadaten.
7. **Welche Aktionen brauchen manuelle Bestätigung?** Vorschlag: Deployment, Credential-Änderung, Datenbank-Migration, externe E-Mails, Löschoperationen.
8. **Soll Microsoft 365/SharePoint trotz Notion-Präferenz parallel geprüft werden?** Empfehlung: Nein, nur wenn Compliance/Auth dafür spricht.
9. **Welche Nutzer außer Konstantin dürfen Tasks freigeben?** Für fünf Mitarbeiter-Instanzen wichtig.
10. **Welche Fehler sollen automatisch retryen?** Vorschlag: HTTP 5xx/Timeout ja, Agent-Fehler/neue Anforderungen nein.

## Quellenverzeichnis

### MCP Spec / offizielles MCP GitHub

- MCP Transports 2025-06-18: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP Tools 2025-06-18: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- MCP Resources 2025-06-18: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- MCP TypeScript Schema 2025-06-18: https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/schema/2025-06-18/schema.ts
- modelcontextprotocol/modelcontextprotocol Issue #982 — Long running tools / async / resumability: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/982
- modelcontextprotocol/modelcontextprotocol Issue #1306 — Binary Mode Elicitation for File Uploads: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1306
- modelcontextprotocol Discussion #2547 — Maintainer Meeting NYC 2026, sessions/client config context: https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2547

### n8n

- n8n MCP Server Trigger docs: https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger/
- n8n endpoint env vars (`N8N_PAYLOAD_SIZE_MAX`): https://docs.n8n.io/hosting/configuration/environment-variables/endpoints/
- n8n `MessageParser.ts`: https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/protocol/MessageParser.ts
- n8n `McpServer.ts`: https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/McpServer.ts
- n8n Issue #16989 — parameters in MCP Server Trigger: https://github.com/n8n-io/n8n/issues/16989

### Anthropic / Claude

- Claude Code MCP docs: https://docs.claude.com/en/docs/claude-code/mcp
- Claude MCP Apps Troubleshooting — large tool results: https://claude.com/docs/connectors/building/mcp-apps/troubleshooting
- Anthropic Help Center — Remote MCP custom integrations: https://support.anthropic.com/en/articles/11175166-getting-started-with-custom-integrations-using-remote-mcp

### Community / weitere GitHub-Quellen

- GitHub Community Discussion #169224 — Handling large text output from MCP server: https://github.com/orgs/community/discussions/169224
- QuantGeekDev/mcp-framework — configurable `maxMessageSize`: https://github.com/QuantGeekDev/mcp-framework
- Docker MCP Catalog entry for `czlonkowski/n8n-mcp` as separate n8n-management MCP server, not the same as n8n MCP Server Trigger: https://hub.docker.com/mcp/server/n8n
