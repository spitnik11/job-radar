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
    const box = el.closest('div,li,fieldset,section');
    const lab = box && box.querySelector('label,legend');
    return !!(lab && /\*/.test(lab.textContent)) || /\brequired\b/i.test((box && box.className) || '');
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
  for (const e of out) if (e.tag === 'radio' && !e.label) {
    const first = document.querySelector(`[data-jr="${e.options[0].jr}"]`);
    const p = first && first.closest('fieldset,div,section');
    e.label = p ? clean((p.querySelector('legend,label,.label')||{}).innerText) : (e.name || '');
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
