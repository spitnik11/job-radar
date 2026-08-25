"""Read an application form from a live page into a flat list of fields — and stamp each control
with a data-jr handle so the filler can locate it later regardless of framework (React/Ashby,
plain Greenhouse, etc.). Pure DOM work in one page.evaluate(); reading only."""

from __future__ import annotations

# Runs in the page. Stamps every visible control with data-jr=<n> and returns one entry per field.
# Radios/checkbox-groups collapse to one entry per name carrying each option's own jr, so the
# filler can click the exact option. 'required' reflects the HTML flag OR an aria-required/'*' hint.
_EXTRACT_JS = r"""
() => {
  const vis = el => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && el.type !== 'hidden'
           && (r.width > 0 || r.height > 0 || el.type === 'file' || el.tagName === 'SELECT');
  };
  const req = el => {
    if (el.required || el.getAttribute('aria-required') === 'true') return true;
    const box = el.closest('fieldset,div,li,section');
    if (!box) return false;
    const lab = box.querySelector('label,legend');
    if (lab && /\*/.test(lab.textContent)) return true;
    // class-based required marker on a label/heading in this field (Ashby uses `_required` on the heading)
    for (const m of box.querySelectorAll('label,legend,[class*="heading" i]'))
      if (/required/i.test(m.className || '')) return true;
    return /\brequired\b/i.test(box.className || '');
  };
  const labelFor = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                 if (l && l.innerText.trim()) return l.innerText.trim(); }
    const wrap = el.closest('label'); if (wrap && wrap.innerText.trim()) return wrap.innerText.trim();
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(' ').map(i => document.getElementById(i)).filter(Boolean)
                          .map(n => n.innerText.trim()).join(' '); if (t) return t; }
    let p = el.closest('div,section,fieldset,li');
    for (let hop = 0; p && hop < 3; hop++, p = p.parentElement) {
      const lab = p.querySelector('label,legend,.label,[class*="label"]');
      if (lab && lab.innerText.trim() && !lab.contains(el)) return lab.innerText.trim();
    }
    return (el.placeholder || el.name || '').trim();
  };
  const clean = s => (s || '').replace(/\s+/g, ' ').replace(/\*$/, '').trim();
  const out = [], radios = {};
  let i = 0;
  for (const el of document.querySelectorAll('input,textarea,select')) {
    if (!vis(el)) continue;
    const type = (el.type || el.tagName).toLowerCase();
    if (['submit','button','reset','image','search'].includes(type)) continue;
    el.setAttribute('data-jr', i);
    if (type === 'radio') {
      const g = el.name || ('r' + i);
      const opt = { text: clean(labelFor(el)) || el.value, jr: i };
      if (radios[g]) radios[g].options.push(opt);
      else { const e = { tag:'radio', type:'radio', name:el.name||'', label:'', required:req(el),
                         options:[opt] }; radios[g] = e; out.push(e); }
      i++; continue;
    }
    let options = [];
    if (el.tagName === 'SELECT')
      options = [...el.options].map(o => clean(o.textContent)).filter(o => o && !/^\s*select/i.test(o));
    out.push({ jr:i, tag:el.tagName.toLowerCase(), type, name:el.name||'', id:el.id||'',
               label:clean(labelFor(el)), required:req(el), options });
    i++;
  }
  // radio group label + required come from the GROUP container (fieldset/radiogroup), not the nearest
  // div — which is the single option's wrapper and holds only the option text ("Yes") + no heading.
  for (const e of out) if (e.tag === 'radio') {
    const first = document.querySelector(`[data-jr="${e.options[0].jr}"]`);
    let grp = first && first.closest('fieldset,[role="radiogroup"]');
    if (!grp && first) {                              // no fieldset: climb to the ancestor holding all options
      const nm = first.name; let p = first.parentElement;
      while (p && !(nm && p.querySelectorAll(`input[name="${CSS.escape(nm)}"]`).length >= e.options.length))
        p = p.parentElement;
      grp = p || first.closest('div,section');
    }
    let q = '', required = false;
    if (grp) {
      const cand = [...grp.querySelectorAll('label,legend,[class*="heading" i],[class*="question" i]')]
        .find(l => !l.closest('[class*="option" i]') && (l.innerText || '').trim());
      if (cand) { q = clean(cand.innerText);
                  required = /\*/.test(cand.textContent) || /required/i.test(cand.className || ''); }
      if (!required) {
        if (grp.getAttribute && grp.getAttribute('aria-required') === 'true') required = true;
        else for (const m of grp.querySelectorAll('label,legend,[class*="heading" i]'))
          if (/required/i.test(m.className || '')) { required = true; break; }
      }
    }
    if (q) e.label = q; else if (!e.label) e.label = e.name || '';
    if (required) e.required = true;
  }

  // Button-group choice questions: some ATS (Ashby yes/no) render single-select as <button> toggles,
  // not <input>. Group candidate buttons by their field container and emit one buttongroup field each.
  const groups = new Map();
  const cand = document.querySelectorAll(
    'button[aria-pressed], button[class*="option" i], button[class*="yesno" i], button[class*="choice" i], [role="radio"]');
  for (const btn of cand) {
    if (!vis(btn) || btn.hasAttribute('data-jr')) continue;
    const txt = clean(btn.innerText || btn.getAttribute('aria-label') || '');
    if (!txt || /\b(submit|apply|continue|next|back|upload|remove|add another|sign in|log in)\b/i.test(txt)) continue;
    const g = btn.closest('[data-field-path],fieldset,[class*="field-entry" i],[class*="fieldEntry" i],[role="radiogroup"]');
    if (!g) continue;
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(btn);
  }
  for (const [g, btns] of groups) {
    if (btns.length < 2) continue;                    // need a real choice
    const options = [];
    for (const btn of btns) { btn.setAttribute('data-jr', i); options.push({ text: clean(btn.innerText || btn.getAttribute('aria-label')), jr: i }); i++; }
    const cand2 = [...g.querySelectorAll('label,legend,[class*="heading" i],[class*="question" i]')]
      .find(l => !l.closest('[class*="option" i]') && (l.innerText || '').trim());
    let label = cand2 ? clean(cand2.innerText) : '';
    let required = cand2 ? (/\*/.test(cand2.textContent) || /required/i.test(cand2.className || '')) : false;
    if (!required) for (const m of g.querySelectorAll('label,legend,[class*="heading" i]'))
      if (/required/i.test(m.className || '')) { required = true; break; }
    out.push({ tag: 'buttongroup', type: 'buttons', name: g.getAttribute('data-field-path') || '',
               id: '', label: label || (options[0] && options[0].text) || '', required, options });
  }
  return out;
}
"""


def read_form(page) -> list[dict]:
    """Return the page's form fields (each stamped data-jr). Empty = no reachable form."""
    try:
        return page.evaluate(_EXTRACT_JS) or []
    except Exception:
        return []
