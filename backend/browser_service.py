import logging
import uuid
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright

logger = logging.getLogger("formpilot-browser-service")

HARVEST_OPTIONS_SCRIPT = """
() => {
    const selectors = [
        '[role="listbox"] [role="option"]',
        '[role="listbox"] li',
        '[role="option"]',
        '[role="menuitem"]',
        '.select__option',
        '[class*="option--"]',
        '.pac-item',
        '[data-value]',
    ];
    const seen = new Set();
    const results = [];
    for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            if (rect.width <= 0 || rect.height <= 0) continue;
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const label = (el.textContent || '').replace(/\\s+/g, ' ').trim();
            const value = el.getAttribute('data-value') || el.getAttribute('value') || label;
            if (!label || label.length < 1) continue;
            const key = label.toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            results.push({ value, label });
        }
        if (results.length > 0) break;
    }
    return results;
}
"""


async def _find_locator(page, selector: str):
    """Find the first matching locator across the page and its frames."""
    if await page.locator(selector).count() > 0:
        return page.locator(selector).first
    for frame in page.frames:
        try:
            if await frame.locator(selector).count() > 0:
                return frame.locator(selector).first
        except Exception:
            continue
    return None


def get_likely_values_for_field(field: dict, profile: dict) -> List[str]:
    """Helper to return likely values from profile to type into searchable comboboxes."""
    label = (field.get("label") or "").lower()
    placeholder = (field.get("placeholder") or "").lower()
    nearby = (field.get("nearby_text") or "").lower()
    search_text = f"{label} {placeholder} {nearby}"

    personal = profile.get("personal_info", {}) or {}
    education = profile.get("education", []) or []
    additional = profile.get("additional_info", {}) or {}

    likely_values = []

    # 1. School / University
    if any(kw in search_text for kw in ("school", "university", "college", "institution", "alma mater")):
        for edu in education:
            if isinstance(edu, dict) and edu.get("school"):
                likely_values.append(edu.get("school"))

    # 2. Degree
    if any(kw in search_text for kw in ("degree", "qualification", "highest education")):
        for edu in education:
            if isinstance(edu, dict) and edu.get("degree"):
                likely_values.append(edu.get("degree"))

    # 3. Major / Discipline
    if any(kw in search_text for kw in ("discipline", "major", "field of study", "specialization", "concentration")):
        for edu in education:
            if isinstance(edu, dict) and edu.get("discipline"):
                likely_values.append(edu.get("discipline"))

    # 4. Country
    if any(kw in search_text for kw in ("country", "nation")):
        loc = personal.get("location")
        if loc:
            likely_values.append(loc)

    # 5. Location
    if any(kw in search_text for kw in ("location", "city", "state", "address")):
        loc = personal.get("location")
        if loc:
            likely_values.append(loc)

    # Filter out empty values and return deduplicated list
    return list(dict.fromkeys([v for v in likely_values if v]))


async def harvest_dropdown_options(page, field: dict, profile: Optional[dict] = None) -> List[Dict[str, Any]]:
    """
    Open a combobox/custom dropdown and scrape visible options.
    Used when the static DOM scan cannot read options until the menu is opened.
    For searchable comboboxes, if a profile likely value is provided, it types it in to harvest suggestions.
    """
    existing = field.get("options") or []
    # If it is a native select and already has options, return it
    if field.get("type") == "select" and len(existing) > 1:
        return existing

    selector = field.get("selector")
    if not selector:
        return existing

    selectors_to_try = [selector]
    if field.get("type") == "combobox":
        selectors_to_try.extend([
            f"{selector} input[role='combobox']",
            f"{selector} [role='combobox']",
            f"{selector} .select__control",
            f"{selector} button[aria-haspopup='listbox']",
        ])

    all_options = []
    seen_keys = set()

    def add_options(options_list):
        for opt in options_list:
            lbl = opt.get("label") or ""
            val = opt.get("value") or lbl
            key = (lbl.strip().lower(), str(val).strip().lower())
            if key not in seen_keys:
                seen_keys.add(key)
                all_options.append({"value": val, "label": lbl})

    # Add existing options first
    add_options(existing)

    for sel in selectors_to_try:
        locator = await _find_locator(page, sel)
        if not locator:
            continue
        try:
            await locator.scroll_into_view_if_needed(timeout=2000)
            await locator.click(timeout=2000)
            await page.wait_for_timeout(500)
            
            # 1. Harvest default options
            default_harvested = await page.evaluate(HARVEST_OPTIONS_SCRIPT)
            if default_harvested:
                add_options(default_harvested)

            # 2. For searchable comboboxes, type likely values and harvest suggestions
            if field.get("type") == "combobox" and profile:
                likely_values = get_likely_values_for_field(field, profile)
                # Find input to type into
                el = await _find_locator(page, sel)
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                inp_el = None
                if tag == "input":
                    inp_el = el
                else:
                    inps = el.locator("input")
                    if await inps.count() > 0:
                        inp_el = inps.first

                if inp_el:
                    for val in likely_values:
                        try:
                            # Focus and clear
                            await inp_el.focus()
                            await inp_el.fill("")
                            # Type the likely value
                            await inp_el.type(val, delay=20)
                            await page.wait_for_timeout(500)
                            
                            # Scrape filtered suggestions
                            suggestions = await page.evaluate(HARVEST_OPTIONS_SCRIPT)
                            if suggestions:
                                add_options(suggestions)
                            
                            # Clear typing
                            await inp_el.fill("")
                            await page.wait_for_timeout(200)
                        except Exception as type_err:
                            logger.debug(f"Failed typing suggestions for '{val}': {type_err}")

            await page.keyboard.press("Escape")
            await page.wait_for_timeout(200)
            break
        except Exception as exc:
            logger.debug(f"Option harvest failed for '{sel}': {exc}")
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

    if all_options:
        # Print logs for Options Harvested
        logger.info(f"[Options Harvested] Field: '{field.get('label') or selector}', Options: {all_options[:10]} (total: {len(all_options)})")
        return all_options[:120]

    return existing


async def enrich_fields_with_dropdown_options(page, fields: List[Dict[str, Any]], profile: Optional[dict] = None) -> List[Dict[str, Any]]:
    """Post-process scanned fields to attach dropdown options for select/combobox fields."""
    enriched = []
    for field in fields:
        ftype = field.get("type", "text")
        if ftype in ("select", "combobox", "radio"):
            options = await harvest_dropdown_options(page, field, profile)
            if options:
                field = {**field, "options": options}
                if ftype == "combobox" and not field.get("options"):
                    field["type"] = "combobox"
        enriched.append(field)
    return enriched

async def scan_web_form(url: str, profile: Optional[dict] = None) -> Dict[str, Any]:
    """
    Launches a headless browser, navigates to the target URL,
    and runs a DOM scanning script to identify fillable input elements.
    Recursively scans all frames (iframes) and traverses shadow DOM boundaries.
    Filters out hidden, tracking, search, and CSRF elements.
    Groups checkboxes and radio collections into single logical fields based on containers.
    Logs the counted, ignored, and grouped elements.
    """
    logger.info(f"Launching Playwright to scan URL: {url}")
    
    detected_fields = []
    total_dom_scanned = 0
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            logger.info("Navigating to URL...")
            await page.goto(url, wait_until="load", timeout=30000)
            await page.wait_for_timeout(1000)

            # Enhanced DOM scanner script with advanced grouping & filtering
            scanner_script = r"""
            () => {
                const root = document;
                
                // Helper: recursively find all inputs including Shadow DOM
                const getAllInputs = (nodeRoot) => {
                    const inputs = [];
                    const walk = (node) => {
                        if (!node) return;
                        const tag = node.tagName ? node.tagName.toLowerCase() : "";
                        if (["input", "select", "textarea"].includes(tag)) {
                            inputs.push(node);
                        }
                        if (node.shadowRoot) {
                            walk(node.shadowRoot);
                        }
                        if (node.childNodes && node.childNodes.length > 0) {
                            for (let i = 0; i < node.childNodes.length; i++) {
                                walk(node.childNodes[i]);
                            }
                        }
                    };
                    walk(nodeRoot);
                    return inputs;
                };

                const getSelector = (el) => {
                    if (el.id) return `#${CSS.escape(el.id)}`;
                    const tagName = el.tagName.toLowerCase();
                    const name = el.getAttribute('name');
                    if (name) return `${tagName}[name="${name}"]`;
                    const classes = el.className ? String(el.className).trim().split(/\s+/).filter(Boolean) : [];
                    if (classes.length > 0) {
                        return `${tagName}.${classes.slice(0, 2).join('.')}`;
                    }
                    return tagName;
                };

                const isGenericLabel = (lbl) => {
                    if (!lbl) return true;
                    const s = lbl.trim().toLowerCase();
                    // Match field_5, field-5, field5, input_5, input-5, f_5, f-5, f5, etc.
                    const genericPatterns = [
                        /^field[_-]?\d+$/i,
                        /^input[_-]?\d+$/i,
                        /^f[_-]?\d+$/i,
                        /^unlabeled$/i,
                        /^untitled$/i,
                        /^placeholder$/i,
                        /^unnamed$/i,
                        /^auto[_-]?generated$/i
                    ];
                    if (genericPatterns.some(pat => pat.test(s))) return true;
                    if (s.includes('input (') || s.includes('select (') || s.includes('textarea (')) return true;
                    if (s.length <= 1) return true;
                    return false;
                };

                const getNearestLabelElement = (el, nodeRoot) => {
                    if (el.id) {
                        const lbl = nodeRoot.querySelector(`label[for="${el.id}"]`);
                        if (lbl && lbl.innerText.trim()) return lbl.innerText.trim();
                    }
                    let parent = el.parentElement;
                    while (parent) {
                        if (parent.tagName === 'LABEL') {
                            const clone = parent.cloneNode(true);
                            clone.querySelectorAll('input, select, textarea').forEach(c => c.remove());
                            if (clone.innerText.trim()) return clone.innerText.trim();
                        }
                        parent = parent.parentElement;
                    }
                    let sibling = el.previousElementSibling;
                    while (sibling) {
                        if (sibling.tagName === 'LABEL' && sibling.innerText.trim()) {
                            return sibling.innerText.trim();
                        }
                        const lblInside = sibling.querySelector('label');
                        if (lblInside && lblInside.innerText.trim()) {
                            return lblInside.innerText.trim();
                        }
                        sibling = sibling.previousElementSibling;
                    }
                    if (el.parentElement) {
                        let parentSibling = el.parentElement.previousElementSibling;
                        if (parentSibling) {
                            const lbl = parentSibling.querySelector('label') || 
                                        (parentSibling.tagName === 'LABEL' ? parentSibling : null);
                            if (lbl && lbl.innerText.trim()) return lbl.innerText.trim();
                        }
                    }
                    return '';
                };

                const getMeaningfulLabel = (el, nodeRoot) => {
                    // 1. Associated label[for=id] or parent label
                    const nearestLabel = getNearestLabelElement(el, nodeRoot);
                    if (nearestLabel && nearestLabel.trim() && !isGenericLabel(nearestLabel)) {
                        return nearestLabel.trim();
                    }
                    
                    // 2. Aria-label
                    const ariaLabel = el.getAttribute('aria-label');
                    if (ariaLabel && ariaLabel.trim() && !isGenericLabel(ariaLabel.trim())) {
                        return ariaLabel.trim();
                    }
                    
                    // 3. Placeholder
                    const placeholder = el.getAttribute('placeholder');
                    if (placeholder && placeholder.trim() && !isGenericLabel(placeholder.trim())) {
                        return placeholder.trim();
                    }
                    
                    // 4. Name attribute (cleaned)
                    const name = el.getAttribute('name');
                    if (name && name.trim()) {
                        const cleanedName = name.replace(/[\[\]_\-]/g, ' ').trim();
                        if (cleanedName && !isGenericLabel(cleanedName)) {
                            return cleanedName;
                        }
                    }
                    
                    // 5. Id attribute
                    if (el.id && el.id.trim()) {
                        const cleanedId = el.id.replace(/[\[\]_\-]/g, ' ').trim();
                        if (cleanedId && !isGenericLabel(cleanedId)) {
                            return cleanedId;
                        }
                    }
                    
                    return null;
                };

                const getSectionHeading = (el, nodeRoot) => {
                    let parent = el.parentElement;
                    while (parent && parent !== nodeRoot) {
                        let sibling = parent.previousElementSibling;
                        while (sibling) {
                            const headings = sibling.querySelectorAll('h1, h2, h3, h4, h5, h6, legend, [class*="heading"], [class*="title"]');
                            if (headings.length > 0) {
                                return headings[headings.length - 1].innerText.trim();
                            }
                            if (['H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LEGEND'].includes(sibling.tagName)) {
                                return sibling.innerText.trim();
                            }
                            sibling = sibling.previousElementSibling;
                        }
                        parent = parent.parentElement;
                    }
                    const headings = Array.from(nodeRoot.querySelectorAll('h1, h2, h3, h4, h5, h6, legend'));
                    let closestHeading = '';
                    let closestOffset = Infinity;
                    const elRect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
                    if (elRect) {
                        headings.forEach(h => {
                            const hRect = h.getBoundingClientRect();
                            if (hRect.top < elRect.top) {
                                const offset = elRect.top - hRect.top;
                                if (offset < closestOffset) {
                                    closestOffset = offset;
                                    closestHeading = h.innerText.trim();
                                }
                            }
                        });
                    }
                    return closestHeading;
                };

                const getNearbyText = (el) => {
                    let parent = el.parentElement;
                    if (parent) {
                        return parent.innerText.substring(0, 150).replace(/\s+/g, ' ').trim();
                    }
                    return '';
                };

                // Finds lowest common ancestor of elements
                const getLCA = (elements) => {
                    if (elements.length === 0) return null;
                    if (elements.length === 1) return elements[0].parentElement;
                    
                    const ancestors = [];
                    let parent = elements[0].parentElement;
                    while (parent) {
                        ancestors.push(parent);
                        parent = parent.parentElement;
                    }
                    
                    let commonAncestor = null;
                    for (let i = 1; i < elements.length; i++) {
                        let p = elements[i].parentElement;
                        const currentAncestors = new Set();
                        while (p) {
                            currentAncestors.add(p);
                            p = p.parentElement;
                        }
                        for (const anc of ancestors) {
                            if (currentAncestors.has(anc)) {
                                commonAncestor = anc;
                                break;
                            }
                        }
                        if (!commonAncestor) return null;
                    }
                    return commonAncestor;
                };

                // Finds container for radio/checkbox groups
                const getGroupContainer = (el) => {
                    let parent = el.parentElement;
                    while (parent && parent !== document.body) {
                        const tag = parent.tagName.toLowerCase();
                        const classes = parent.className ? String(parent.className).toLowerCase() : "";
                        const inputsOfSameType = parent.querySelectorAll(`input[type="${el.type}"]`);
                        
                        if (tag === 'fieldset' || classes.includes('field') || classes.includes('question') || classes.includes('group') || classes.includes('container') || classes.includes('wrapper') || classes.includes('row')) {
                            if (inputsOfSameType.length > 1) {
                                return parent;
                            }
                        }
                        parent = parent.parentElement;
                    }
                    if (el.parentElement) {
                        const siblings = el.parentElement.querySelectorAll(`input[type="${el.type}"]`);
                        if (siblings.length > 1) return el.parentElement;
                    }
                    return null;
                };

                const getGroupLabel = (container) => {
                    const legend = container.querySelector('legend');
                    if (legend && legend.innerText.trim()) return legend.innerText.trim();
                    
                    const heading = container.querySelector('h1, h2, h3, h4, h5, h6, [class*="legend"], legend');
                    if (heading && heading.innerText.trim()) return heading.innerText.trim();
                    
                    const labels = Array.from(container.querySelectorAll('label'));
                    for (const lbl of labels) {
                        const wrapsInput = lbl.querySelector('input[type="checkbox"], input[type="radio"]');
                        if (!wrapsInput && lbl.innerText.trim()) {
                            return lbl.innerText.trim();
                        }
                    }
                    
                    const labelClasses = container.querySelectorAll('[class*="label"], [class*="title"], [class*="question"]');
                    for (const el of labelClasses) {
                        if (el.innerText.trim() && !el.querySelector('input[type="checkbox"], input[type="radio"]')) {
                            return el.innerText.trim();
                        }
                    }
                    
                    if (labels.length > 0) {
                        const clone = labels[0].cloneNode(true);
                        clone.querySelectorAll('input, select, textarea').forEach(c => c.remove());
                        if (clone.innerText.trim()) return clone.innerText.trim();
                    }
                    
                    return '';
                };

                const allInputs = getAllInputs(root);
                const debugInfo = [];
                
                // We will do filtering first
                const activeElements = [];
                
                allInputs.forEach((el) => {
                    const tagName = el.tagName.toLowerCase();
                    const typeAttr = (el.getAttribute('type') || '').toLowerCase();
                    const nameAttr = el.getAttribute('name') || '';
                    const idAttr = el.id || '';
                    
                    let isIgnored = false;
                    let ignoreReason = '';

                    // 1. Skip hidden inputs
                    if (tagName === 'input' && ['hidden', 'submit', 'button', 'reset', 'image'].includes(typeAttr)) {
                        isIgnored = true;
                        ignoreReason = `Unfillable input type: '${typeAttr}'`;
                    }
                    
                    // CSS / visual visibility check
                    if (!isIgnored) {
                        const isVisible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                        if (!isVisible) {
                            isIgnored = true;
                            ignoreReason = "Element is visually hidden / invisible (zero offsets)";
                        } else {
                            const style = window.getComputedStyle(el);
                            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                                isIgnored = true;
                                ignoreReason = `Element has CSS display: ${style.display}, visibility: ${style.visibility}, or opacity: ${style.opacity}`;
                            }
                        }
                    }
                    
                    // aria-hidden check
                    if (!isIgnored) {
                        if (el.getAttribute('aria-hidden') === 'true' || el.closest('[aria-hidden="true"]')) {
                            isIgnored = true;
                            ignoreReason = "Element or ancestor has aria-hidden='true'";
                        }
                    }

                    // 2. Skip search helper inputs
                    if (!isIgnored) {
                        if (typeAttr === 'search') {
                            isIgnored = true;
                            ignoreReason = "Type is search helper input";
                        } else {
                            const idLower = idAttr.toLowerCase();
                            const nameLower = nameAttr.toLowerCase();
                            const classLower = (el.className || '').toLowerCase();
                            const placeholderLower = (el.getAttribute('placeholder') || '').toLowerCase();
                            const ariaLabelLower = (el.getAttribute('aria-label') || '').toLowerCase();
                            const textToMatch = [idLower, nameLower, classLower, placeholderLower, ariaLabelLower].join(' ');
                            
                            const searchKeywords = ['search', 'query', 'filter', 'find', 'helper', 'search-helper', 'search_helper'];
                            const matchedKw = searchKeywords.find(kw => textToMatch.includes(kw));
                            if (matchedKw) {
                                isIgnored = true;
                                ignoreReason = `Search helper input (matches keyword '${matchedKw}')`;
                            }
                        }
                    }

                    // 3. Skip internal Greenhouse controls / csrf / analytics
                    if (!isIgnored) {
                        const idLower = idAttr.toLowerCase();
                        const nameLower = nameAttr.toLowerCase();
                        const classLower = (el.className || '').toLowerCase();
                        const textToMatch = [idLower, nameLower, classLower].join(' ');
                        
                        const greenhouseKeywords = ['greenhouse_id', 'hiring_manager', 'job_board', 'greenhouse-only', 'greenhouse_only', 'csrf', 'token', 'utm_', 'analytics', 'tracker', 'tracking', 'click_id', 'authenticity_token', '__requestverificationtoken'];
                        const matchedGreenhouse = greenhouseKeywords.find(kw => textToMatch.includes(kw));
                        if (matchedGreenhouse) {
                            isIgnored = true;
                            ignoreReason = `Greenhouse internal / CSRF / tracking input (matches '${matchedGreenhouse}')`;
                        }
                    }

                    // 4. Remove generic labels & check if meaningful label exists (includes autogenerated unnamed check)
                    let meaningfulLabel = null;
                    if (!isIgnored) {
                        meaningfulLabel = getMeaningfulLabel(el, root);
                        if (!meaningfulLabel) {
                            isIgnored = true;
                            ignoreReason = "No meaningful label exists (unnamed/autogenerated/generic candidates only)";
                        }
                    }

                    let fieldType = 'text';
                    if (tagName === 'textarea') {
                        fieldType = 'textarea';
                    } else if (tagName === 'select') {
                        fieldType = 'select';
                    } else if (tagName === 'button' && el.getAttribute('aria-haspopup') === 'listbox') {
                        fieldType = 'combobox';
                    } else {
                        if (typeAttr === 'email') fieldType = 'email';
                        else if (['tel', 'phone'].includes(typeAttr)) fieldType = 'phone';
                        else if (typeAttr === 'checkbox') fieldType = 'checkbox';
                        else if (typeAttr === 'radio') fieldType = 'radio';
                        else if (typeAttr === 'file') fieldType = 'file';
                        else fieldType = typeAttr || 'text';
                        const role = el.getAttribute('role') || '';
                        const haspopup = el.getAttribute('aria-haspopup') || '';
                        const autocomplete = el.getAttribute('aria-autocomplete') || '';
                        const classLower = (el.className || '').toLowerCase();
                        if (
                            role === 'combobox' ||
                            haspopup === 'listbox' ||
                            autocomplete === 'list' ||
                            classLower.includes('select') ||
                            el.closest('[class*="select"]') ||
                            idAttr.toLowerCase().includes('location') ||
                            nameAttr.toLowerCase().includes('location') ||
                            classLower.includes('location')
                        ) {
                            fieldType = 'combobox';
                        }
                    }

                    const selector = getSelector(el);
                    debugInfo.push({
                        name: nameAttr,
                        id: idAttr,
                        type: fieldType,
                        selector: selector,
                        label: meaningfulLabel || `Generic/Internal Field (${selector})`,
                        is_ignored: isIgnored,
                        ignore_reason: ignoreReason
                    });

                    if (!isIgnored) {
                        activeElements.push({
                            element: el,
                            type: fieldType,
                            selector: selector,
                            label: meaningfulLabel,
                            name: nameAttr,
                            id: idAttr,
                            placeholder: el.getAttribute('placeholder') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            required: el.hasAttribute('required') || el.getAttribute('aria-required') === 'true'
                        });
                    }
                });

                const logicalFields = [];
                
                // Grouping collections
                const checkboxRadioGroups = {}; // key -> array of elements
                const otherFields = [];

                activeElements.forEach((item) => {
                    if (item.type === 'checkbox' || item.type === 'radio') {
                        // Determine group key
                        let groupKey = '';
                        if (item.name) {
                            groupKey = `${item.type}_name_${item.name}`;
                        } else {
                            const groupContainer = getGroupContainer(item.element);
                            if (groupContainer) {
                                groupKey = `${item.type}_container_${getSelector(groupContainer)}`;
                            } else {
                                groupKey = `${item.type}_standalone_${item.selector}`;
                            }
                        }
                        
                        if (!checkboxRadioGroups[groupKey]) {
                            checkboxRadioGroups[groupKey] = [];
                        }
                        checkboxRadioGroups[groupKey].push(item);
                    } else {
                        otherFields.push(item);
                    }
                });

                // Process grouped checkbox/radio collections
                Object.keys(checkboxRadioGroups).forEach((key) => {
                    const groupItems = checkboxRadioGroups[key];
                    const firstItem = groupItems[0];
                    
                    // Find LCA (lowest common ancestor) of all elements in the group
                    const lca = getLCA(groupItems.map(item => item.element));
                    
                    // Find group label
                    let groupLabel = '';
                    if (lca) {
                        groupLabel = getGroupLabel(lca);
                    }
                    
                    // Clean or fallback group label
                    if (!groupLabel || isGenericLabel(groupLabel)) {
                        // Try cleaning name
                        if (firstItem.name) {
                            groupLabel = firstItem.name.replace(/[\[\]_\-]/g, ' ').trim();
                        }
                    }
                    
                    // If still generic/empty, use first option's label or fallback
                    if (!groupLabel || isGenericLabel(groupLabel)) {
                        groupLabel = firstItem.label || 'Options Group';
                    }

                    // Final generic label check for the group label itself
                    if (isGenericLabel(groupLabel)) {
                        // Exclude this group as internal/unlabeled
                        groupItems.forEach(item => {
                            const dbg = debugInfo.find(d => d.selector === item.selector);
                            if (dbg) {
                                dbg.is_ignored = true;
                                dbg.ignore_reason = "Group has generic label: " + groupLabel;
                            }
                        });
                        return;
                    }

                    // Aggregate option choices
                    const options = groupItems.map(item => {
                        let optionLabel = '';
                        if (item.element.id) {
                            const lbl = root.querySelector(`label[for="${item.element.id}"]`);
                            if (lbl && lbl.innerText.trim()) optionLabel = lbl.innerText.trim();
                        }
                        if (!optionLabel) {
                            let parent = item.element.parentElement;
                            while (parent && parent !== lca) {
                                if (parent.tagName === 'LABEL') {
                                    const clone = parent.cloneNode(true);
                                    clone.querySelectorAll('input, select, textarea').forEach(c => c.remove());
                                    if (clone.innerText.trim()) {
                                        optionLabel = clone.innerText.trim();
                                        break;
                                    }
                                }
                                parent = parent.parentElement;
                            }
                        }
                        if (!optionLabel) {
                            let sibling = item.element.nextElementSibling;
                            if (sibling && sibling.tagName === 'LABEL' && sibling.innerText.trim()) {
                                optionLabel = sibling.innerText.trim();
                            } else {
                                sibling = item.element.previousElementSibling;
                                if (sibling && sibling.tagName === 'LABEL' && sibling.innerText.trim()) {
                                    optionLabel = sibling.innerText.trim();
                                }
                            }
                        }
                        if (!optionLabel) {
                            optionLabel = item.label || item.element.value || 'Option';
                        }
                        
                        return {
                            value: item.element.value || optionLabel,
                            label: optionLabel,
                            selector: item.selector
                        };
                    });

                    const isGrouped = groupItems.length > 1;
                    const finalType = firstItem.type === 'checkbox' 
                        ? (isGrouped ? 'checkbox_group' : 'checkbox') 
                        : 'radio';

                    const isRequired = groupItems.some(item => item.required);
                    const lcaSelector = lca ? getSelector(lca) : firstItem.selector;
                    
                    logicalFields.push({
                        field_id: firstItem.id || firstItem.name || `group_${firstItem.type}_${Math.random().toString(36).substr(2, 9)}`,
                        selector: lcaSelector,
                        type: finalType,
                        label: groupLabel || "",
                        placeholder: firstItem.placeholder || "",
                        name: firstItem.name || "",
                        aria_label: firstItem.ariaLabel || "",
                        required: isRequired,
                        nearby_text: lca ? getNearbyText(lca) : getNearbyText(firstItem.element),
                        section: getSectionHeading(firstItem.element, root) || "",
                        options: options
                    });
                });

                // Process other non-group fields
                otherFields.forEach((item) => {
                    let options = [];
                    if (item.element.tagName.toLowerCase() === 'select') {
                        options = Array.from(item.element.options)
                            .map(opt => ({
                                value: opt.value,
                                label: opt.text.trim()
                            }))
                            .filter(opt => opt.label && opt.label.toLowerCase() !== 'select...');
                    }

                    logicalFields.push({
                        field_id: item.id || item.name || `field_${Math.random().toString(36).substr(2, 9)}`,
                        selector: item.selector,
                        type: item.type,
                        label: item.label || "",
                        placeholder: item.placeholder || "",
                        name: item.name || "",
                        aria_label: item.ariaLabel || "",
                        required: item.required || false,
                        nearby_text: getNearbyText(item.element) || "",
                        section: getSectionHeading(item.element, root) || "",
                        options: options
                    });
                });

                return {
                    total_dom_elements: allInputs.length,
                    debug_info: debugInfo,
                    logical_fields: logicalFields
                };
            }
            """

            frames = page.frames
            logger.info(f"Form scraping started. {len(frames)} frames found in page context.")
            
            for idx, frame in enumerate(frames):
                try:
                    logger.info(f"Crawling frame {idx}: URL: {frame.url}")
                    analysis = await frame.evaluate(scanner_script)
                    
                    if not analysis:
                        continue
                        
                    total_dom_scanned += analysis.get("total_dom_elements", 0)
                    debug_info = analysis.get("debug_info", [])
                    logical_fields = analysis.get("logical_fields", [])
                    
                    # Log details of ignored vs counted DOM inputs
                    for d in debug_info:
                        name_str = f"name='{d['name']}'" if d['name'] else "no-name"
                        id_str = f"id='{d['id']}'" if d['id'] else "no-id"
                        
                        if d['is_ignored']:
                            logger.info(
                                f"[Frame {idx}] DOM Input ({d['type']}): {name_str} {id_str} "
                                f"➔ IGNORED (Reason: {d['ignore_reason']})"
                            )
                        else:
                            logger.info(
                                f"[Frame {idx}] DOM Input ({d['type']}): {name_str} {id_str} "
                                f"➔ COUNTED as logical field: '{d['label']}'"
                            )
                            
                    # Log grouped fields explicitly
                    for field in logical_fields:
                        field["frame_url"] = frame.url
                        field["frame_index"] = idx
                        if "field_id" not in field:
                            field["field_id"] = field.get("id") or field.get("name") or f"f_{idx}_{len(detected_fields)}"
                        
                        if field.get("is_grouped"):
                            opt_labels = [o["label"] for o in field.get("options", [])]
                            logger.info(
                                f"[Frame {idx}] Grouped Field: '{field['label']}' (type: {field['type']}) "
                                f"collapsing {len(opt_labels)} options: {opt_labels}"
                            )
                            
                        detected_fields.append(field)
                        
                except Exception as fe:
                    logger.warning(f"Could not scrape sub-frame {idx} context: {str(fe)}")

            # Log summary statistics
            total_logical = len(detected_fields)
            logger.info(
                f"=== FIELD DETECTION STATISTICS ===\n"
                f"  Total Raw DOM Elements Inspected: {total_dom_scanned}\n"
                f"  Total Logical Fields Counted:     {total_logical}\n"
                f"================================="
            )

            detected_fields = await enrich_fields_with_dropdown_options(page, detected_fields, profile)
            logger.info(f"After dropdown option harvest: {len(detected_fields)} fields ready for mapping.")
            
            return {
                "detected_fields": detected_fields,
                "total_dom_elements": total_dom_scanned,
                "total_logical_fields": total_logical
            }

        except Exception as e:
            logger.error(f"Error while executing browser scanner: {str(e)}")
            raise e
        finally:
            await browser.close()


async def scan_form_url(url: str, profile_json: Optional[dict] = None) -> dict:
    """
    Tool 2: Scan form URL to extract schema and harvest dropdown/radio/checkbox options.
    """
    res = await scan_web_form(url, profile_json)
    import json
    logger.info("[Form Fields Extracted]")
    logger.info(json.dumps(res.get("detected_fields", []), indent=2))

    # Aggregate harvested options
    options_summary = {}
    for f in res.get("detected_fields", []):
        if f.get("options"):
            options_summary[f.get("field_id")] = f.get("options")
    logger.info("[Options Harvested]")
    logger.info(json.dumps(options_summary, indent=2))
    
    return res

