// Node: "Ergebnis extrahieren"
// Ersetzt den bisherigen jsCode. Erwartet GPT-Output mit per-Post kurzbeschreibung.

const company = $('Pro Unternehmen einzeln').first().json;
const gptResp = $input.first().json;

let analysis = {
  posts: [],
  kategorie: 'Sonstiges',
  relevanz: 'Niedrig',
  relevanz_begruendung: ''
};

try {
  const content =
    gptResp.message?.content ||
    gptResp.choices?.[0]?.message?.content ||
    '';
  if (content) {
    const jsonMatch = content.match(/\{[\s\S]+\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      analysis = {
        posts: Array.isArray(parsed.posts) ? parsed.posts : [],
        kategorie: parsed.kategorie || 'Sonstiges',
        relevanz: parsed.relevanz || 'Niedrig',
        relevanz_begruendung: parsed.relevanz_begruendung || ''
      };
    }
  }
} catch (e) {
  // analysis bleibt auf Defaults, Fallback unten greift
}

function fallbackBeschreibung(text) {
  const t = String(text || '').replace(/\s+/g, ' ').trim();
  if (!t) return 'Beitrag ohne Textvorschau.';
  const cut = t.substring(0, 140);
  return cut + (t.length > 140 ? '…' : '');
}

const enrichedPosts = (company.posts || []).map((p, i) => {
  // 1) per Index 1-basiert (so wie der Prompt es verlangt)
  let match = analysis.posts.find(x => Number(x.index) === i + 1);
  // 2) Modell-Slip: 0-basiert
  if (!match) match = analysis.posts.find(x => Number(x.index) === i);
  // 3) Positional NUR, wenn die Längen identisch sind. Sonst riskieren wir,
  //    dass ein dedupliziertes GPT-Array (z.B. nur 2 statt 3 Einträge) falsch
  //    auf die Original-Posts gemappt wird.
  if (!match
      && analysis.posts.length === (company.posts || []).length
      && analysis.posts[i]) {
    match = analysis.posts[i];
  }

  const beschreibung = match && match.kurzbeschreibung
    ? String(match.kurzbeschreibung).trim()
    : fallbackBeschreibung(p.text);

  return {
    text: p.text,
    url: p.url,
    date: p.date,
    likes: p.likes,
    comments: p.comments,
    kurzbeschreibung: beschreibung
  };
});

return [{
  json: {
    name: company.name,
    linkedinUrls: company.linkedinUrls,
    postCount: company.postCount,
    posts: enrichedPosts,
    apifyError: company.apifyError,
    kategorie: analysis.kategorie,
    relevanz: analysis.relevanz,
    relevanz_begruendung: analysis.relevanz_begruendung
  }
}];
