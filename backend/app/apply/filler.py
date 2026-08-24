"""Actually enter the mapped plan onto the live form (type, select, upload, check), then read every
required field's state back to see what is genuinely still empty. That read-back is the point: a
page.fill() can silently no-op on a React-controlled input or a custom dropdown widget, and the only
honest way to know an application will submit is to look at what the form now holds. Fills only —
the submit click lives in engine.py behind the gate."""

from __future__ import annotations


def _sel(jr) -> str:
    return f'[data-jr="{jr}"]'


def fill(page, plan: dict) -> dict:
    """Enter every 'filled' entry. Files go LAST because async uploads re-render the form and would
    wipe earlier fields. Returns {entered:[labels], failed:[{label,reason}]}."""
    entered, failed = [], []
    items = plan.get("filled", [])
    non_files = [e for e in items if e.get("type") != "file"]
    files = [e for e in items if e.get("type") == "file"]
    for e in non_files + files:
        jr, t = e.get("jr"), e.get("type")
        label = e.get("label") or ""
        if jr is None:
            failed.append({"label": label, "reason": "no locator"}); continue
        sel = _sel(jr)
        try:
            if t == "file":
                # async dropzones (Greenhouse/S3) re-render after upload; set it and let the fresh
                # required-scan be the judge of attachment.
                page.set_input_files(sel, e["value"], timeout=8000)
                page.wait_for_timeout(1000)
            elif t == "radio" or e.get("check") or t == "checkbox":
                page.check(sel, timeout=5000)
            elif e.get("option") is not None or e.get("options"):     # a <select>
                _select(page, sel, e.get("option") or e.get("value"))
            else:
                _fill_text(page, sel, str(e["value"]))
            entered.append(label)
        except Exception as ex:
            failed.append({"label": label, "reason": type(ex).__name__})
    return {"entered": entered, "failed": failed}


def _fill_text(page, sel, value):
    """fill(), then verify it stuck; React controlled inputs sometimes revert a .value set, so retry
    by typing keystrokes (which every framework accepts) before giving up."""
    page.fill(sel, value, timeout=5000)
    try:
        if (page.eval_on_selector(sel, "e=>e.value") or "").strip() == value.strip():
            return
    except Exception:
        return                                      # can't read back (re-rendered) — assume it took
    loc = page.locator(sel)
    loc.click(timeout=3000)
    try:
        loc.fill("", timeout=2000)
    except Exception:
        pass
    loc.press_sequentially(value, delay=12, timeout=6000)


def _select(page, sel, value):
    """Try native <select> by label then value then partial; raise if nothing took."""
    try:
        page.select_option(sel, label=value, timeout=4000); return
    except Exception:
        pass
    try:
        page.select_option(sel, value=value, timeout=4000); return
    except Exception:
        pass
    # last resort: pick the option whose text contains the value
    ok = page.evaluate(
        """([s,v])=>{const el=document.querySelector(s);if(!el||!el.options)return false;
           const o=[...el.options].find(o=>o.textContent.toLowerCase().includes(v.toLowerCase()));
           if(o){el.value=o.value;el.dispatchEvent(new Event('change',{bubbles:true}));return true}return false}""",
        [sel, str(value)])
    if not ok:
        raise RuntimeError("no matching option")


# Ground truth for "will this submit": a FRESH scan of the live DOM for required controls that are
# still empty. Self-contained (re-derives required + label + value in-page) so it survives the
# framework re-renders that invalidate our earlier data-jr stamps.
_MISSING_JS = r"""
() => {
  const esc = s => (window.CSS && CSS.escape) ? CSS.escape(s) : (s||'').replace(/"/g,'\\"');
  const vis = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return s.display!=='none' && s.visibility!=='hidden' && el.type!=='hidden'
           && (r.width>0 || r.height>0 || el.type==='file' || el.tagName==='SELECT'); };
  const required = el => {
    if (el.required || el.getAttribute('aria-required')==='true') return true;
    const box = el.closest('div,li,fieldset,section'); const lab = box && box.querySelector('label,legend');
    return !!(lab && /\*/.test(lab.textContent)) || /\brequired\b/i.test((box && box.className)||'');
  };
  const labelFor = el => {
    if (el.id){ const l=document.querySelector(`label[for="${esc(el.id)}"]`); if(l&&l.innerText.trim()) return l.innerText.trim(); }
    const w=el.closest('label'); if(w&&w.innerText.trim()) return w.innerText.trim();
    if(el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
    let p=el.closest('div,section,fieldset,li');
    for(let h=0;p&&h<3;h++,p=p.parentElement){ const l=p.querySelector('label,legend,.label'); if(l&&l.innerText.trim()&&!l.contains(el)) return l.innerText.trim(); }
    return (el.placeholder||el.name||'(field)').trim();
  };
  const clean = s => (s||'').replace(/\s+/g,' ').replace(/\*$/,'').trim();
  const missing=[], groups={};
  for (const el of document.querySelectorAll('input,textarea,select')) {
    const type=(el.type||el.tagName).toLowerCase();
    if(['submit','button','reset','image','hidden'].includes(type)) continue;
    if(!vis(el) || !required(el)) continue;
    if(type==='radio'){ const g=el.name||labelFor(el); if(groups[g]) continue; groups[g]=1;
      const ok=el.name?!!document.querySelector(`input[name="${esc(el.name)}"]:checked`):el.checked;
      if(!ok) missing.push(clean(labelFor(el))); continue; }
    let ok;
    if(type==='file') ok=el.files && el.files.length>0;
    else if(type==='checkbox') ok=el.checked;
    else if(el.tagName==='SELECT') ok=el.selectedIndex>0 && (el.value||'').trim()!=='';
    else ok=(el.value||'').trim()!=='';
    if(!ok) missing.push(clean(labelFor(el)));
  }
  return [...new Set(missing)];
}
"""


def missing_required(page, fields: list[dict] | None = None) -> list[str]:
    """Labels of required fields still empty on the live form (fresh scan; ignores `fields`)."""
    try:
        return page.evaluate(_MISSING_JS) or []
    except Exception:
        return []
