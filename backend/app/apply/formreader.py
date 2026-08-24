"""Read an application form from a live page into a flat list of fields (label, type, options,
required). Pure DOM extraction in one page.evaluate() — no ATS-specific knowledge here, so it
works on Greenhouse/Lever/Ashby/generic forms alike. Reading only; nothing is filled or submitted."""

from __future__ import annotations

# Runs in the page. Returns one entry per real, visible form control with a best-effort label.
# Radios are collapsed to one entry per group (by name) carrying all option labels.
_EXTRACT_JS = r"""
() => {
  const visible = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && el.type !== 'hidden'
           && (r.width > 0 || r.height > 0 || el.type === 'file');
  };
  const labelFor = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                 if (l && l.innerText.trim()) return l.innerText.trim(); }
    const wrap = el.closest('label'); if (wrap && wrap.innerText.trim()) return wrap.innerText.trim();
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const t = lb.split(' ').map(i => document.getElementById(i)).filter(Boolean)
                          .map(n => n.innerText.trim()).join(' '); if (t) return t; }
    // nearest preceding label-ish text within the field's container
    let p = el.closest('div,section,fieldset,li');
    for (let hop = 0; p && hop < 3; hop++, p = p.parentElement) {
      const lab = p.querySelector('label,legend,.label,[class*="label"]');
      if (lab && lab.innerText.trim() && !lab.contains(el)) return lab.innerText.trim();
    }
    return (el.placeholder || el.name || '').trim();
  };
  const clean = s => (s || '').replace(/\s+/g, ' ').replace(/\*$/, '').trim();
  const out = [], seenRadio = {};
  for (const el of document.querySelectorAll('input,textarea,select')) {
    if (!visible(el)) continue;
    const type = (el.type || el.tagName).toLowerCase();
    if (['submit','button','reset','image','search'].includes(type)) continue;
    if (type === 'radio') {
      const g = el.name || labelFor(el);
      if (seenRadio[g]) { seenRadio[g].options.push(clean(labelFor(el)) || el.value); continue; }
      const e = { tag:'radio', type:'radio', name:el.name||'', id:el.id||'',
                  label:'', required:el.required, options:[clean(labelFor(el)) || el.value] };
      seenRadio[g] = e; out.push(e); continue;
    }
    let options = [];
    if (el.tagName === 'SELECT')
      options = [...el.options].map(o => clean(o.textContent)).filter(o => o && !/^select/i.test(o));
    out.push({ tag: el.tagName.toLowerCase(), type, name: el.name || '', id: el.id || '',
               label: clean(labelFor(el)), required: !!el.required, options });
  }
  // radio groups: hoist a group label from the surrounding fieldset/container
  for (const e of out) if (e.tag === 'radio' && !e.label) {
    const first = document.getElementsByName(e.name)[0];
    let p = first && first.closest('fieldset,div,section');
    e.label = p ? clean((p.querySelector('legend,label,.label')||{}).innerText) : e.name;
  }
  return out;
}
"""


def read_form(page) -> list[dict]:
    """Return the page's form fields. Best-effort; empty list means no reachable form
    (likely behind a login/redirect/adapter step)."""
    try:
        return page.evaluate(_EXTRACT_JS) or []
    except Exception:
        return []
