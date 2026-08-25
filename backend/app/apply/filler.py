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
                # async dropzones (Ashby/Greenhouse/S3) upload to a server then CLEAR input.files and
                # show a filename chip. Set it, then wait for the chip to prove it landed.
                page.set_input_files(sel, e["value"], timeout=8000)
                _await_upload(page, sel)
            elif t in ("buttons", "buttongroup"):       # <button> toggle group (Ashby yes/no) — real click
                page.click(sel, timeout=4000)
            elif t == "radio" or e.get("check") or t == "checkbox":
                _check(page, sel)
            elif e.get("option") is not None or e.get("options"):     # a <select>
                _select(page, sel, e.get("option") or e.get("value"))
            else:
                _fill_text(page, sel, str(e["value"]))
            entered.append(label)
        except Exception as ex:
            failed.append({"label": label, "reason": type(ex).__name__})
    return {"entered": entered, "failed": failed}


def _is_combobox(page, sel) -> bool:
    try:
        return bool(page.eval_on_selector(sel,
            "e=>e.getAttribute('role')==='combobox'||!!e.getAttribute('aria-autocomplete')"
            "||e.getAttribute('aria-haspopup')==='listbox'||!!e.getAttribute('aria-controls')||!!e.getAttribute('list')"))
    except Exception:
        return False


def _fill_combobox(page, sel, value) -> bool:
    """Typeahead/autocomplete (Lever location, etc.): type a few chars, then click the best matching
    suggestion so the form stores a real selection — raw text alone is often rejected. True if a
    suggestion was chosen."""
    loc = page.locator(sel)
    try:
        loc.click(timeout=3000)
        loc.fill("", timeout=2000)
        loc.press_sequentially(value[:24], delay=45)
        page.wait_for_timeout(1200)
    except Exception:
        return False
    opts = page.query_selector_all("[role=option], ul[role=listbox] li, [class*='option']:not(:empty)")
    vwords = [w for w in value.lower().replace(",", " ").split() if len(w) > 1]
    best = None
    for o in opts:
        try:
            if not o.is_visible():
                continue
            t = (o.inner_text() or "").lower()
            if any(w in t for w in vwords):
                best = o; break
            best = best or o
        except Exception:
            continue
    if best:
        try:
            best.click(timeout=2000); return True
        except Exception:
            pass
    try:                                            # some accept Enter to take the first suggestion
        loc.press("Enter")
    except Exception:
        pass
    return False


def _fill_text(page, sel, value):
    """fill(), then verify it stuck; React controlled inputs sometimes revert a .value set, so retry
    by typing keystrokes (which every framework accepts) before giving up."""
    if _is_combobox(page, sel) and _fill_combobox(page, sel, value):
        return
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


# Does the file input's field show an uploaded file (filename chip / remove control)? Async ATS
# uploaders clear input.files after processing, so this — not files.length — is the truth.
_ATTACHED_JS = r"""
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return true;                              // gone (re-rendered away) = consumed
  if (el.files && el.files.length > 0) return true;
  const box = el.closest('[data-field-path],fieldset,[class*="field" i],div') || document.body;
  const t = box.innerText || '';
  if (/[\w().-]+\.(pdf|docx?|odt|rtf|txt|md)\b/i.test(t)) return true;   // a filename is shown
  return !!box.querySelector('[class*="remove" i],[class*="delete" i],[aria-label*="remove" i],'
                             + '[class*="uploaded" i],[class*="success" i],[class*="filename" i]');
}
"""


def _await_upload(page, sel, tries: int = 12):
    """Wait (up to ~6s) for the async upload to show an attached indicator before moving on."""
    for _ in range(tries):
        page.wait_for_timeout(500)
        try:
            if page.evaluate(_ATTACHED_JS, sel):
                return
        except Exception:
            return


def _check(page, sel):
    """Select a radio/checkbox robustly. Custom-styled controls hide the real input (opacity:0) under
    a label (Ashby, many ATS); a programmatic check silently no-ops and doesn't fire the framework's
    onChange, so fall back to a real click on the controlling label/option wrapper."""
    try:
        page.check(sel, timeout=2500)
        if page.eval_on_selector(sel, "e=>e.checked"):
            return
    except Exception:
        pass
    h = page.query_selector(sel)
    if not h:
        return
    target = h.evaluate_handle(
        "e=>{const id=e.id; return (id && document.querySelector(`label[for='${CSS.escape(id)}']`))"
        " || e.closest('label') || e.closest('[class*=option i]') || e;}").as_element()
    try:
        (target or h).click(timeout=3000)
    except Exception:
        pass


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
    if(type==='file'){
      ok = el.files && el.files.length>0;
      if(!ok){                                        // async uploaders clear files + show a filename chip
        const fb = el.closest('[data-field-path],fieldset,[class*="field" i],div') || document.body;
        const ft = fb.innerText || '';
        ok = /[\w().-]+\.(pdf|docx?|odt|rtf|txt|md)\b/i.test(ft)
             || !!fb.querySelector('[class*="remove" i],[class*="delete" i],[class*="uploaded" i],[class*="success" i],[class*="filename" i]');
      }
    }
    else if(type==='checkbox') ok=el.checked;
    else if(el.tagName==='SELECT') ok=el.selectedIndex>0 && (el.value||'').trim()!=='';
    else ok=(el.value||'').trim()!=='';
    if(!ok) missing.push(clean(labelFor(el)));
  }
  // required <button> toggle groups (Ashby yes/no): missing if no button is pressed/selected
  const seenG = new Set();
  for (const btn of document.querySelectorAll('button[aria-pressed], button[class*="option" i], button[class*="yesno" i], [role="radio"]')) {
    const g = btn.closest('[data-field-path],fieldset,[class*="field-entry" i],[class*="fieldEntry" i],[role="radiogroup"]');
    if (!g || seenG.has(g)) continue; seenG.add(g);
    const head = g.querySelector('label,legend,[class*="heading" i]');
    const req = !!head && (/\*/.test(head.textContent) || /required/i.test(head.className||''))
                || g.getAttribute('aria-required')==='true';
    if (!req) continue;
    const btns = [...g.querySelectorAll('button[aria-pressed],button[class*="option" i],[role="radio"]')];
    const anySel = btns.some(b => b.getAttribute('aria-pressed')==='true' || b.getAttribute('aria-checked')==='true'
                                  || /selected|active|checked/i.test(b.className||''));
    if (!anySel) missing.push(clean((head&&head.innerText)||'(choice)'));
  }
  return [...new Set(missing)];
}
"""


# Validation-error field discovery: read the form's OWN error state (aria-invalid + visible error
# messages) → the labels of fields it is flagging. Authoritative for fields our reader can't see
# (custom controls), and the point of "the form tells us what it wants".
_FLAGGED_JS = r"""
() => {
  const clean = s => (s||'').replace(/\s+/g,' ').replace(/\*$/,'').trim();
  const esc = s => (window.CSS && CSS.escape) ? CSS.escape(s) : (s||'').replace(/"/g,'\\"');
  const labelOf = el => {
    if (el.id){ const l=document.querySelector(`label[for="${esc(el.id)}"]`); if(l&&l.innerText.trim()) return clean(l.innerText); }
    const fld = el.closest('[data-field-path],fieldset,[class*="field" i],div');
    const h = fld && fld.querySelector('label,legend,[class*="heading" i]');
    return h ? clean(h.innerText) : clean(el.getAttribute('aria-label')||el.name||'');
  };
  const out = new Set();
  for (const el of document.querySelectorAll('[aria-invalid="true"]')) { const l=labelOf(el); if(l) out.add(l); }
  for (const err of document.querySelectorAll('[class*="error" i]:not(:empty),[role="alert"],[aria-live="assertive"],[aria-live="polite"]')) {
    const t = (err.innerText||'').trim();
    if (!t || t.length>200 || !/required|please|must|invalid|missing|select|enter|provide|cannot be/i.test(t)) continue;
    const fld = err.closest('[data-field-path],fieldset,[class*="field" i]');
    const h = fld && fld.querySelector('label,legend,[class*="heading" i]');
    if (h && h.innerText.trim()) out.add(clean(h.innerText));
  }
  return [...out];
}
"""


def flagged_fields(page) -> list[str]:
    """Labels of fields the form's own validation is flagging (aria-invalid / error messages)."""
    try:
        return page.evaluate(_FLAGGED_JS) or []
    except Exception:
        return []


def missing_required(page, fields: list[dict] | None = None) -> list[str]:
    """Labels of required fields still empty on the live form (fresh scan) MERGED with fields the
    form's own validation is flagging (`fields` arg ignored)."""
    try:
        miss = page.evaluate(_MISSING_JS) or []
    except Exception:
        miss = []
    seen = {m.lower() for m in miss}
    for f in flagged_fields(page):
        if f.lower() not in seen:
            miss.append(f); seen.add(f.lower())
    return miss
