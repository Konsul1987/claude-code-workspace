# OpenAI-Node `GPT LinkedIn-Analyse` – Options

In n8n `OpenAI` Node (typeVersion 1.4), Operation **Message Model**:

1. Node öffnen
2. Abschnitt **Options** ausklappen (unten)
3. **Add Option → Output Content as JSON** auf `true` setzen

Damit verlangt der OpenAI-API-Call `response_format: { type: "json_object" }`
und das Modell garantiert ein parsebares JSON-Objekt. Das schließt die
Hauptursache des Bugs (silent JSON.parse-Fail mit Defaults `Sonstiges` /
`NIEDRIG`).

Wenn diese Option in der vorhandenen Node-Version nicht angeboten wird:
Modell auf einen Endpoint stellen, der `json_object` unterstützt
(`gpt-4.1-mini` tut das).
