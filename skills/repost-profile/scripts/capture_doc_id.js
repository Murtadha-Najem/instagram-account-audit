// Run in a logged-in Instagram tab on https://www.instagram.com/<any account>/reposts/ , then scroll the grid once.
// Afterwards evaluate: JSON.stringify(window.__cap)  and copy the doc_id of PolarisProfileRepostsTabContentRefetchQuery
// into scripts/config.json ("reposts_doc_id").
window.__cap = [];
(() => {
  const keep = (url, body) => {
    if (!String(url).includes('graphql')) return;
    const p = new URLSearchParams(typeof body === 'string' ? body : '');
    window.__cap.push({ name: p.get('fb_api_req_friendly_name'), doc_id: p.get('doc_id') });
  };
  const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return open.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) { try { keep(this.__u, b); } catch (e) {} return send.apply(this, arguments); };
  const f = window.fetch;
  window.fetch = function (u, o) { try { keep(typeof u === 'string' ? u : u.url, o && o.body); } catch (e) {} return f.apply(this, arguments); };
})();
'capturing';
