// Node: "Ergebnisse sammeln"
// Ersetzt den bisherigen jsCode. Rendert pro Post eine Kurzbeschreibung + Link.

const all = $input.all().map(i => i.json);
const today = new Date().toLocaleDateString('de-DE', {
  weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
});
// Robust: tatsächliche Posts zählen, nicht nur das postCount-Feld.
const withNews = all.filter(c => Array.isArray(c.posts) && c.posts.length > 0);
const withoutNews = all.filter(c => !Array.isArray(c.posts) || c.posts.length === 0);
const hasApifyError = all.some(c => c.apifyError);

const relevanzColor = {
  'Hoch': '#c0392b', 'Mittel': '#e67e22',
  'Niedrig': '#7f8c8d', 'Info': '#2980b9'
};
const kategorieColor = {
  'Personal': '#8e44ad', 'M&A': '#c0392b', 'Finanzen': '#27ae60',
  'Produkte': '#2980b9', 'Partnerschaften': '#16a085', 'Events': '#d35400',
  'CSR': '#27ae60', 'Sonstiges': '#7f8c8d'
};

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeAttr(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// Defense-in-Depth: nur http(s) durchlassen, sonst leeren String → kein Link gerendert.
function safeUrl(s) {
  const raw = String(s == null ? '' : s).trim();
  if (!/^https?:\/\//i.test(raw)) return '';
  return escapeAttr(raw);
}

let html = `<html><body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; color: #333;">`;

if (hasApifyError) {
  html += `<table width="100%" cellpadding="12" cellspacing="0" style="margin-bottom: 16px; border: 2px solid #e74c3c; border-radius: 4px;">
    <tr><td bgcolor="#fdf2f2" style="padding: 12px;">
      <b style="color: #c0392b;">⚠️ Apify-Fehler:</b> LinkedIn-Daten konnten nicht vollständig abgerufen werden. Die Analyse basiert auf unvollständigen Daten.
    </td></tr>
  </table>`;
}

html += `<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 24px;">
  <tr><td bgcolor="#1a1a2e" style="padding: 20px; border-radius: 4px;">
    <h1 style="color: #ffffff; margin: 0; font-size: 20px;">📊 Unternehmens-Monitoring</h1>
    <p style="color: #aaaacc; margin: 4px 0 0 0; font-size: 14px;">${escapeHtml(today)} · ${withNews.length} von ${all.length} Unternehmen mit News</p>
  </td></tr>
</table>`;

for (const company of withNews) {
  const relColor = relevanzColor[company.relevanz] || '#7f8c8d';
  const katColor = kategorieColor[company.kategorie] || '#7f8c8d';

  // Outlook (Word-Renderer) ignoriert padding auf <ul>/<li>. Daher Tabellen-Layout
  // mit eigenem Bullet-<td>, identisch zum Stil der restlichen Mail.
  const postRows = (company.posts || []).map(p => {
    const desc = escapeHtml(p.kurzbeschreibung || '');
    const href = safeUrl(p.url);
    const linkPart = href
      ? ` <a href="${href}" style="color: #2980b9; white-space: nowrap; text-decoration: none;">🔗 LinkedIn</a>`
      : '';
    return `<tr>
      <td valign="top" width="14" style="padding: 0 6px 8px 0; color: #888; font-size: 13px; line-height: 1.45;">•</td>
      <td valign="top" style="padding: 0 0 8px 0; font-size: 13px; line-height: 1.45; word-wrap: break-word; overflow-wrap: break-word;">${desc}${linkPart}</td>
    </tr>`;
  }).join('');

  const postsCount = (company.posts || []).length;

  html += `<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 16px; border: 1px solid #e0e0e0; border-radius: 4px;">
    <tr><td bgcolor="#f8f9fa" style="padding: 12px 16px; border-bottom: 1px solid #e0e0e0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td><b style="font-size: 16px;">${escapeHtml(company.name)}</b> <span style="color: #888; font-size: 12px;">${postsCount} Post${postsCount !== 1 ? 's' : ''}</span></td>
          <td align="right">
            <span style="background-color: ${katColor}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin-right: 4px;">${escapeHtml(company.kategorie)}</span>
            <span style="background-color: ${relColor}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px;">${escapeHtml(String(company.relevanz || '').toUpperCase())}</span>
          </td>
        </tr>
      </table>
    </td></tr>
    <tr><td style="padding: 12px 16px;">
      ${company.relevanz_begruendung ? `<p style="margin: 0 0 12px 0; color: #666; font-size: 12px;"><i>${escapeHtml(company.relevanz_begruendung)}</i></p>` : ''}
      <table width="100%" cellpadding="0" cellspacing="0" style="margin: 0;">${postRows}</table>
    </td></tr>
  </table>`;
}

if (withoutNews.length > 0) {
  html += `<table width="100%" cellpadding="12" cellspacing="0" style="margin-bottom: 16px; border: 1px solid #e0e0e0; border-radius: 4px;">
    <tr><td bgcolor="#f8f9fa" style="padding: 12px 16px; border-bottom: 1px solid #e0e0e0;">
      <b style="color: #888;">Keine Neuigkeiten heute</b>
    </td></tr>
    <tr><td style="padding: 12px 16px; color: #888; font-size: 13px;">
      ${withoutNews.map(c => escapeHtml(c.name)).join(' · ')}
    </td></tr>
  </table>`;
}

html += `<p style="color: #aaa; font-size: 11px; text-align: center; margin-top: 24px;">Automatisch generiert · Hermès Monitor v9 · G&amp;B Logistics GmbH</p>`;
html += `</body></html>`;

const subject = `📊 Unternehmens-Monitoring ${new Date().toLocaleDateString('de-DE')} — ${withNews.length} Unternehmen mit News`;

return [{ json: { html, subject, withNewsCount: withNews.length, totalCount: all.length } }];
