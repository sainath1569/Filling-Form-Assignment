"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle2,
  Edit2,
  ExternalLink,
  Loader2,
  Monitor,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  XCircle,
} from "lucide-react";
import { FieldMapping } from "@/store/formStore";

type FieldStatus = "pending" | "injecting" | "completed" | "failed" | "skipped";

interface FieldState {
  status: FieldStatus;
  verificationValue?: string;
  error?: string;
  editedValue?: string;
  note?: string;
}

interface RunSession {
  run_id: string;
  target_url: string;
  mapping_plan: FieldMapping[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const statusStyles: Record<FieldStatus, string> = {
  pending: "text-zinc-400",
  injecting: "text-violet-600",
  completed: "text-emerald-600",
  failed: "text-rose-600",
  skipped: "text-zinc-400",
};

function getFieldValue(field: FieldMapping, state?: FieldState): string {
  return state?.editedValue ?? field.value ?? field.selected_option ?? "";
}

function hasFillableValue(field: FieldMapping, state?: FieldState): boolean {
  if (field.action === "upload_file") return true;
  if (field.action === "multi_select") {
    return (field.selected_options?.length ?? 0) > 0;
  }
  return Boolean(getFieldValue(field, state));
}

export interface FormFieldOption {
  value: string;
  label: string;
  selector?: string;
}

export type InjectResult = {
  ok: boolean;
  verification?: string;
  error?: string;
};

function cssEscape(value: string): string {
  return value.replace(/([!"#$%&'()*+,.\/:;<=>?@[\\\]^`{|}~])/g, "\\$1");
}

function normalizeText(value: unknown): string {
  return String(value ?? "")
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const ABBREVIATIONS: Record<string, string> = {
  btech: "bachelor of technology",
  "b tech": "bachelor of technology",
  "b.tech": "bachelor of technology",
  "bachelor tech": "bachelor of technology",
  be: "bachelor of engineering",
  "b e": "bachelor of engineering",
  "b.e": "bachelor of engineering",
  bs: "bachelor of science",
  bsc: "bachelor of science",
  "b.sc": "bachelor of science",
  cs: "computer science",
  cse: "computer science and engineering",
  "comp sci": "computer science",
  compsci: "computer science",
  it: "information technology",
  iit: "indian institute of technology",
  iisc: "indian institute of science",
  nit: "national institute of technology",
  bits: "birla institute of technology and science",
  mit: "massachusetts institute of technology",
  iim: "indian institute of management",
};

function expandText(value: unknown): string {
  const normalized = normalizeText(value);
  if (ABBREVIATIONS[normalized]) return ABBREVIATIONS[normalized];
  return normalized
    .split(" ")
    .map((word) => ABBREVIATIONS[word] || word)
    .join(" ");
}

const _termCache = new Map<string, string[]>();

function getOptionSearchTerms(field: FieldMapping, value: string): string[] {
  const cacheKey = field.field_id + "\x00" + value;
  if (_termCache.has(cacheKey)) return _termCache.get(cacheKey)!;
  const rawTerms = [
    field.selected_option_label,
    field.selected_option,
    value,
    field.value,
    expandText(field.selected_option_label),
    expandText(field.selected_option),
    expandText(value),
    expandText(field.value),
  ];

  const terms = Array.from(
    new Set(
      rawTerms
        .filter(Boolean)
        .map((item) => String(item).trim())
        .filter(Boolean)
    )
  );
  _termCache.set(cacheKey, terms);
  return terms;
}

function findElement(doc: Document, selector: string): HTMLElement | null {
  try {
    const el = doc.querySelector(selector);
    if (el) return el as HTMLElement;
  } catch {}

  if (selector.startsWith("#")) {
    const byId = doc.getElementById(selector.slice(1));
    if (byId) return byId as HTMLElement;
  }

  return null;
}

function fireReactEvents(el: HTMLElement) {
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur", { bubbles: true }));
}

function setNativeValue(el: HTMLElement, value: string) {
  const isTextArea = el.tagName.toLowerCase() === "textarea";
  const win = el.ownerDocument?.defaultView || window;
  const proto = isTextArea ? win.HTMLTextAreaElement.prototype : win.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, value);
  else (el as HTMLInputElement | HTMLTextAreaElement).value = value;
  fireReactEvents(el);
}

function selectNativeOption(select: HTMLSelectElement, field: FieldMapping, value: string): InjectResult {
  const terms = getOptionSearchTerms(field, value);
  const options = Array.from(select.options);

  // Pre-normalize all terms and options once
  const normTerms = terms.map((t) => ({ raw: t, norm: normalizeText(t), exp: expandText(t) }));
  const normOpts = options.map((opt) => ({
    opt,
    normVal: normalizeText(opt.value),
    normText: normalizeText(opt.textContent ?? ""),
    expVal: expandText(opt.value),
    expText: expandText(opt.textContent ?? ""),
  }));

  // Exact match pass
  for (const { norm } of normTerms) {
    const hit = normOpts.find((o) => o.normVal === norm || o.normText === norm);
    if (hit) {
      select.value = hit.opt.value;
      fireReactEvents(select);
      return { ok: true, verification: hit.opt.textContent?.trim() || hit.opt.value };
    }
  }

  // Expanded match pass
  for (const { exp } of normTerms) {
    const hit = normOpts.find((o) => o.expVal === exp || o.expText === exp);
    if (hit) {
      select.value = hit.opt.value;
      fireReactEvents(select);
      return { ok: true, verification: hit.opt.textContent?.trim() || hit.opt.value };
    }
  }

  // Fuzzy pass
  let best: HTMLOptionElement | null = null;
  let bestScore = 0;

  for (const o of normOpts) {
    for (const { raw, exp } of normTerms) {
      const score = Math.max(
        similarity(raw, o.opt.value),
        similarity(raw, o.opt.textContent ?? ""),
        similarity(exp, o.expText),
        similarity(exp, o.expVal)
      );
      if (score > bestScore) {
        bestScore = score;
        best = o.opt;
      }
    }
  }

  if (best && bestScore >= 0.72) {
    select.value = best.value;
    fireReactEvents(select);
    return {
      ok: true,
      verification: `${best.textContent?.trim() || best.value} (fuzzy ${Math.round(bestScore * 100)}%)`,
    };
  }

  return { ok: false, error: `No matching dropdown option found for '${terms[0] || value}'.` };
}

function similarity(a: string, b: string): number {
  const x = normalizeText(a);
  const y = normalizeText(b);
  if (!x || !y) return 0;
  if (x === y) return 1;
  if (x.includes(y) || y.includes(x)) return 0.92;

  const xs = new Set(x.split(" ").filter((t) => t.length > 1));
  const ys = new Set(y.split(" ").filter((t) => t.length > 1));
  const overlap = [...xs].filter((t) => ys.has(t)).length;
  const tokenScore = overlap / Math.max(xs.size, ys.size, 1);

  let matches = 0;
  const minLen = Math.min(x.length, y.length);
  for (let i = 0; i < minLen; i++) if (x[i] === y[i]) matches++;
  const charScore = matches / Math.max(x.length, y.length, 1);

  return Math.max(tokenScore, charScore);
}

function getCombinedScore(originalTarget: string, optionText: string): number {
  const normOpt = normalizeText(optionText);
  const normTarget = normalizeText(originalTarget);
  const expOpt = expandText(optionText);
  const expTarget = expandText(originalTarget);

  if (normOpt === normTarget) return 1.0;
  if (expOpt === expTarget) return 0.98;

  let containsScore = 0;
  if (normOpt.includes(normTarget) || normTarget.includes(normOpt)) containsScore = 0.9;
  if (expOpt.includes(expTarget) || expTarget.includes(expOpt)) containsScore = 0.92;

  const overlapScore = similarity(expTarget, expOpt);

  return Math.max(containsScore, overlapScore);
}

function getVisibleOptionElements(doc: Document): HTMLElement[] {
  const selectors = [
    ".pac-item",
    '[role="option"]',
    '[role="listbox"] li',
    '[role="menuitem"]',
    ".select__option",
    '[class*="option"]',
    "[data-value]",
    "li",
  ];
  const seen = new Set<HTMLElement>();
  const results: HTMLElement[] = [];

  for (const selector of selectors) {
    for (const raw of Array.from(doc.querySelectorAll(selector))) {
      const el = raw as HTMLElement;
      if (seen.has(el)) continue;
      const text = el.textContent?.replace(/\s+/g, " ").trim();
      if (!text || text.length > 120) continue;
      const rect = el.getBoundingClientRect();
      const style = doc.defaultView?.getComputedStyle(el);
      if (rect.width <= 0 || rect.height <= 0) continue;
      if (style?.display === "none" || style?.visibility === "hidden") continue;
      seen.add(el);
      results.push(el);
    }
  }

  return results;
}

function getClickableOption(el: HTMLElement): HTMLElement {
  return (
    el.closest(".select2-results__option") ||
    el.closest("[role='option']") ||
    el.closest("[data-value]") ||
    el.closest("li") ||
    el
  ) as HTMLElement;
}

async function simulateClick(el: HTMLElement) {
  el.scrollIntoView({ block: "nearest", inline: "nearest" });
  const win = el.ownerDocument?.defaultView || window;
  el.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, cancelable: true, view: win }));
  el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: win }));
  await new Promise((r) => setTimeout(r, 120));
  el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: win }));
  el.click();
}

async function waitForStableOptions(
  doc: Document,
  currentQuery: string,
  timeoutMs: number
): Promise<HTMLElement[]> {
  const deadline = Date.now() + timeoutMs;
  let lastCount = -1;
  let stableFor = 0;

  while (Date.now() < deadline) {
    const opts = getVisibleOptionElements(doc).filter((el) => {
      const t = el.textContent?.toLowerCase() || "";
      return !t.includes("searching") && !t.includes("loading") && !t.includes("no results");
    });

    if (opts.length > 0 && opts.length === lastCount) {
      stableFor += 150;
      if (stableFor >= 300) return opts; // stable for 300ms = safe to evaluate
    } else {
      stableFor = 0;
    }

    lastCount = opts.length;
    await new Promise((r) => setTimeout(r, 150));
  }

  // Return whatever we have at deadline
  return getVisibleOptionElements(doc).filter((el) => {
    const t = el.textContent?.toLowerCase() || "";
    return !t.includes("searching") && !t.includes("loading");
  });
}

function pickBestOption(
  options: HTMLElement[],
  queryTerms: string[],
  threshold = 0.85
): { option: HTMLElement; score: number } | null {
  let best: HTMLElement | null = null;
  let bestScore = 0;

  for (const opt of options) {
    const optText = opt.textContent || "";
    let maxScore = 0;
    for (const term of queryTerms) {
      maxScore = Math.max(maxScore, getCombinedScore(term, optText));
    }
    if (maxScore > bestScore) {
      bestScore = maxScore;
      best = opt;
    }
  }

  if (best && bestScore >= threshold) {
    return { option: best, score: bestScore };
  }
  return null;
}

async function commitOptionClick(
  doc: Document,
  option: HTMLElement,
  queryTerms: string[]
): Promise<boolean> {
  const clickable = getClickableOption(option);

  // Re-find by text if element was detached (Places API re-renders)
  const target = doc.body.contains(clickable)
    ? clickable
    : (() => {
        const text = clickable.textContent?.trim();
        if (!text) return null;
        return Array.from(
          doc.querySelectorAll(".pac-item, .select2-results__option, [role='option'], li")
        ).find((e) => e.textContent?.trim() === text) as HTMLElement | null;
      })();

  if (!target) return false;

  await simulateClick(target);
  target.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));
  return true;
}

async function searchWithRightBacktracking(
  doc: Document,
  searchTarget: HTMLElement | null,
  queryTerms: string[]
): Promise<InjectResult> {

  // ── No search input: options already visible (search-disabled dropdown) ──
  if (!searchTarget) {
    await new Promise((r) => setTimeout(r, 200));
    const options = await waitForStableOptions(doc, "", 2000);
    const match = pickBestOption(options, queryTerms);
    if (match) {
      const ok = await commitOptionClick(doc, match.option, queryTerms);
      if (ok) {
        (doc.activeElement as HTMLElement | null)?.blur();
        doc.body.click();
        return { ok: true, verification: match.option.textContent?.trim() || queryTerms[0] };
      }
    }
    return {
      ok: false,
      error: "No search input found and no options matched.",
    };
  }

  // ── Build prefix ladder: full → 60% → 40% → first word only ──
  // This replaces character-by-character backtracking with a small set of
  // meaningful prefixes. Each is tried once with a proper stability wait.
  function buildPrefixLadder(term: string): string[] {
    const words = term.trim().split(/\s+/);
    const full = term.trim();
    const p60 = full.slice(0, Math.max(3, Math.ceil(full.length * 0.6)));
    const p40 = full.slice(0, Math.max(3, Math.ceil(full.length * 0.4)));
    const firstWord = words[0] || full;
    // Deduplicate while preserving order
    return Array.from(new Set([full, p60, p40, firstWord].filter((s) => s.length >= 3)));
  }

  // Collect all prefixes across all terms, deduped by normalized form
  const seenPrefix = new Set<string>();
  const prefixQueue: { prefix: string; sourceTerms: string[] }[] = [];

  for (const term of queryTerms) {
    if (!term) continue;
    for (const prefix of buildPrefixLadder(term)) {
      const norm = normalizeText(prefix);
      if (seenPrefix.has(norm)) continue;
      seenPrefix.add(norm);
      prefixQueue.push({ prefix, sourceTerms: queryTerms });
    }
  }

  for (const { prefix, sourceTerms } of prefixQueue) {
    // Clear and type the prefix
    setNativeValue(searchTarget, "");
    searchTarget.dispatchEvent(new Event("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 100));

    setNativeValue(searchTarget, prefix);
    searchTarget.dispatchEvent(new Event("input", { bubbles: true }));
    searchTarget.dispatchEvent(
      new KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: prefix.slice(-1), keyCode: prefix.charCodeAt(prefix.length - 1) })
    );

    console.log("PREFIX_SEARCH", { prefix, termsCount: sourceTerms.length });

    // Wait for results to appear and stabilise
    const waitMs = prefix === prefixQueue[0].prefix ? 2500 : 1500;
    const options = await waitForStableOptions(doc, prefix, waitMs);

    console.log("PREFIX_RESULTS", { prefix, optionsFound: options.length });

    if (options.length === 0) continue;

    const match = pickBestOption(options, sourceTerms);

    console.log("PREFIX_MATCH", {
      prefix,
      matched: match?.option.textContent?.trim(),
      score: match?.score,
    });

    if (match) {
      const ok = await commitOptionClick(doc, match.option, sourceTerms);
      if (ok) {
        (doc.activeElement as HTMLElement | null)?.blur();
        doc.body.click();
        return { ok: true, verification: match.option.textContent?.trim() || sourceTerms[0] };
      }
    }
  }

  // ── Final fallback: clear input and check if any options remain visible ──
  setNativeValue(searchTarget, "");
  searchTarget.dispatchEvent(new Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));
  ;(doc.activeElement as HTMLElement | null)?.blur();
  doc.body.click();

  return { ok: false, error: `No options matched for '${queryTerms[0]}'` };
}

async function selectCustomDropdown(
  doc: Document,
  rootEl: HTMLElement,
  field: FieldMapping,
  value: string
): Promise<InjectResult> {
  const terms = getOptionSearchTerms(field, value);

  let clickableTarget: HTMLElement = rootEl;
  if (rootEl.tagName.toLowerCase() === "select") {
    const sibling = rootEl.nextElementSibling as HTMLElement | null;
    if (sibling?.classList?.contains("select2-container")) {
      clickableTarget = (sibling.querySelector(".select2-selection") as HTMLElement) || sibling;
    }
  } else {
    const sel2 = rootEl.querySelector(".select2-selection");
    if (sel2) clickableTarget = sel2 as HTMLElement;
  }

  const findDropdownSearchInput = (): HTMLElement | null => {
    const openSelect2Input = doc.querySelector(
      ".select2-container--open .select2-search__field"
    ) as HTMLElement | null;
    if (openSelect2Input) {
      const rect = openSelect2Input.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return openSelect2Input;
    }

    if (
      doc.activeElement &&
      (doc.activeElement.tagName === "INPUT" || doc.activeElement.tagName === "TEXTAREA")
    ) {
      const active = doc.activeElement as HTMLInputElement;
      if (!["checkbox", "radio", "file", "hidden", "submit", "button"].includes(active.type)) {
        if (
          rootEl.contains(active) ||
          active.classList.contains("select2-search__field") ||
          active.closest('[role="dialog"]') ||
          active.closest('[role="listbox"]')
        ) {
          return active;
        }
      }
    }

    const searchArea = rootEl.parentElement || rootEl;
    const innerInputs = Array.from(searchArea.querySelectorAll("input")) as HTMLInputElement[];
    if (rootEl.tagName.toLowerCase() === "input") innerInputs.unshift(rootEl as HTMLInputElement);

    for (const input of innerInputs) {
      if (["checkbox", "radio", "file", "hidden", "submit", "button"].includes(input.type)) continue;
      const rect = input.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) return input;
    }

    return null;
  };

  let inputEl = findDropdownSearchInput();

  if (!inputEl) {
    clickableTarget.scrollIntoView({ block: "center", inline: "nearest" });
    await simulateClick(clickableTarget);

    // FIX: Give the dropdown a full 600ms to open on first tick (cold iframe),
    // then poll every 200ms for up to 2.4s more — replaces the old 8 × 150ms loop
    await new Promise((r) => setTimeout(r, 600));
    inputEl = findDropdownSearchInput();
    if (!inputEl) {
      for (let i = 0; i < 12; i++) {
        await new Promise((r) => setTimeout(r, 200));
        inputEl = findDropdownSearchInput();
        if (inputEl) break;
      }
    }
  }

  return await searchWithRightBacktracking(doc, inputEl, terms);
}

async function injectLocationAutocomplete(
  doc: Document,
  inputEl: HTMLInputElement,
  field: FieldMapping,
  value: string
): Promise<InjectResult> {
  const terms = getOptionSearchTerms(field, value);

  inputEl.scrollIntoView({ block: "center", inline: "nearest" });
  await simulateClick(inputEl);

  // Wait for the autocomplete widget to initialise (cold iframe needs up to 800ms)
  await new Promise((resolve) => setTimeout(resolve, 800));

  // If no options visible yet, keep polling up to 2.4s more
  let ready = false;
  for (let i = 0; i < 12; i++) {
    const opts = getVisibleOptionElements(doc);
    // pac-container present in DOM means Places API is awake, even if empty
    if (opts.length > 0 || doc.querySelector(".pac-container")) {
      ready = true;
      break;
    }
    await new Promise((r) => setTimeout(r, 200));
  }

  if (!ready) {
    // Last resort: focus + keyboard event to nudge the widget
    inputEl.focus();
    inputEl.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    await new Promise((r) => setTimeout(r, 300));
  }

  return await searchWithRightBacktracking(doc, inputEl, terms);
}

function uploadResumeFile(el: HTMLElement, resumeFile: File | null): InjectResult {
  if (!resumeFile)
    return {
      ok: false,
      error: "Resume PDF file is not loaded yet. Please wait or attach manually.",
    };
  const input = el as HTMLInputElement;
  if (
    input.tagName.toLowerCase() !== "input" ||
    input.getAttribute("type")?.toLowerCase() !== "file"
  ) {
    return { ok: false, error: "Target element is not a file input." };
  }

  try {
    const dt = new DataTransfer();
    dt.items.add(resumeFile);
    input.files = dt.files;
    fireReactEvents(input);
    input.dispatchEvent(new Event("change", { bubbles: true }));
    return { ok: true, verification: `${resumeFile.name} attached` };
  } catch (error) {
    return {
      ok: false,
      error:
        error instanceof Error
          ? error.message
          : "Browser blocked programmatic file attachment. Attach manually.",
    };
  }
}

function injectMultiSelect(doc: Document, field: FieldMapping): InjectResult {
  const selected = field.selected_options || [];
  if (!selected.length) return { ok: false, error: "No checkbox options selected." };

  const checked: string[] = [];

  for (const option of selected) {
    const optionObj = field.options?.find((o) => o.value === option || o.label === option);
    const candidates = [option, optionObj?.value, optionObj?.label].filter(Boolean) as string[];
    let input: HTMLInputElement | null = null;

    for (const candidate of candidates) {
      try {
        input = doc.querySelector(
          `input[type="checkbox"][value="${cssEscape(candidate)}"]`
        ) as HTMLInputElement | null;
        if (input) break;
      } catch {}
    }

    if (!input) {
      const labels = Array.from(doc.querySelectorAll("label")) as HTMLLabelElement[];
      const matchingLabel = labels.find((label) =>
        candidates.some((candidate) =>
          normalizeText(label.textContent).includes(normalizeText(candidate))
        )
      );
      input = matchingLabel?.querySelector(
        'input[type="checkbox"]'
      ) as HTMLInputElement | null;
    }

    if (input) {
      input.checked = true;
      fireReactEvents(input);
      checked.push(optionObj?.label || option);
    }
  }

  if (!checked.length) return { ok: false, error: "No matching checkbox options were found." };
  return { ok: true, verification: `Checked: ${checked.join(", ")}` };
}

function isSelectHiddenBySelect2(el: HTMLElement, doc: Document): boolean {
  const style = doc.defaultView?.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return (
    style?.display === "none" ||
    style?.visibility === "hidden" ||
    el.classList.contains("hidden") ||
    el.classList.contains("select2-hidden-accessible") ||
    rect.width <= 1 ||
    rect.height <= 1 ||
    (el.nextElementSibling?.classList.contains("select2-container") ?? false)
  );
}

export async function injectIntoIframe(
  iframeDoc: Document,
  field: FieldMapping,
  value: string,
  resumeFile: File | null
): Promise<InjectResult> {
  try {
    const action = field.action;
    const effectiveValue =
      value || field.selected_option_label || field.selected_option || field.value || "";

    console.log("[FormPilot Inject]", {
      label: field.field_label || field.field_id,
      action,
      selector: field.selector,
      selected_option: field.selected_option,
      selected_option_label: field.selected_option_label,
      value: field.value,
      effectiveValue,
    });

    if (action === "skip") return { ok: true, verification: "skipped" };

    const el = findElement(iframeDoc, field.selector);
    if (!el) return { ok: false, error: `Element '${field.selector}' was not found.` };

    if (action === "upload_file") return uploadResumeFile(el, resumeFile);
    if (action === "multi_select") return injectMultiSelect(iframeDoc, field);

    const tagName = el.tagName.toLowerCase();
    const hiddenBySelect2 = tagName === "select" && isSelectHiddenBySelect2(el, iframeDoc);
    const useNative = tagName === "select" && !hiddenBySelect2;

    if (action === "select") {
      if (useNative) return selectNativeOption(el as HTMLSelectElement, field, effectiveValue);
      return await selectCustomDropdown(iframeDoc, el, field, effectiveValue);
    }

    if (action === "fill" || action === "type") {
      const type = (el.getAttribute("type") || "").toLowerCase();

      const isLocationField =
        el.id.toLowerCase().includes("location") ||
        (el.getAttribute("name") || "").toLowerCase().includes("location") ||
        (el.getAttribute("placeholder") || "").toLowerCase().includes("location");

      if (isLocationField && tagName === "input") {
        return await injectLocationAutocomplete(
          iframeDoc,
          el as HTMLInputElement,
          field,
          effectiveValue
        );
      }

      const isCustomDropdownInput =
        el.getAttribute("role") === "combobox" ||
        el.getAttribute("aria-haspopup") === "listbox" ||
        el.closest('[class*="select"]') !== null ||
        el.closest('[class*="Select"]') !== null ||
        el.closest('[class*="combobox"]') !== null;

      if (tagName === "select" || field.type === "select" || field.type === "combobox" || isCustomDropdownInput) {
        if (useNative) return selectNativeOption(el as HTMLSelectElement, field, effectiveValue);
        return await selectCustomDropdown(iframeDoc, el, field, effectiveValue);
      }

      if (tagName === "input") {
        const input = el as HTMLInputElement;
        if (type === "file") return uploadResumeFile(input, resumeFile);
        if (type === "checkbox") {
          input.checked = ["true", "checked", "yes", "1"].includes(effectiveValue.toLowerCase());
          fireReactEvents(input);
          return { ok: true, verification: input.checked ? "checked" : "unchecked" };
        }
        if (type === "radio") {
          const radio = iframeDoc.querySelector(
            `input[type="radio"][value="${cssEscape(effectiveValue)}"]`
          ) as HTMLInputElement | null;
          if (!radio)
            return { ok: false, error: `Radio value '${effectiveValue}' was not found.` };
          radio.checked = true;
          fireReactEvents(radio);
          return { ok: true, verification: effectiveValue };
        }
        setNativeValue(input, effectiveValue);
        return { ok: true, verification: input.value };
      }

      if (tagName === "textarea") {
        const textarea = el as HTMLTextAreaElement;
        setNativeValue(textarea, effectiveValue);
        return { ok: true, verification: textarea.value };
      }

      if (el.getAttribute("contenteditable") === "true") {
        el.textContent = effectiveValue;
        fireReactEvents(el);
        return { ok: true, verification: effectiveValue };
      }

      return { ok: false, error: `Unsupported fill target: ${el.tagName.toLowerCase()}` };
    }

    return { ok: false, error: `Unsupported action '${action}'.` };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : "Unexpected injection error.",
    };
  }
}

export default function AutomationConsolePage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.id as string;

  const iframeRef = useRef<HTMLIFrameElement>(null);
  const fieldStatesRef = useRef<Record<string, FieldState>>({});

  const [runData, setRunData] = useState<RunSession | null>(null);
  const [fieldStates, setFieldStates] = useState<Record<string, FieldState>>({});
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [iframeReady, setIframeReady] = useState(false);
  const [isAutomating, setIsAutomating] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [editingFieldId, setEditingFieldId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const [resumeFile, setResumeFileState] = useState<File | null>(null);
  const resumeFileRef = useRef<File | null>(null);

  const setResumeFile = (file: File | null) => {
    resumeFileRef.current = file;
    setResumeFileState(file);
  };

  useEffect(() => {
    fieldStatesRef.current = fieldStates;
  }, [fieldStates]);

  useEffect(() => {
    if (!runId) return;

    async function loadResume() {
      try {
        const response = await fetch(`${API_BASE}/api/runs/${runId}/resume-file`);
        if (response.ok) {
          const blob = await response.blob();
          const contentDisposition = response.headers.get("Content-Disposition");
          let filename = "resume.pdf";
          if (contentDisposition) {
            const matches = /filename="?([^"]+)"?/.exec(contentDisposition);
            if (matches?.[1]) filename = matches[1];
          }
          setResumeFile(new File([blob], filename, { type: "application/pdf" }));
        } else {
          console.error("Failed to load resume file:", response.statusText);
        }
      } catch (error) {
        console.error("Failed to fetch resume file:", error);
      }
    }

    loadResume();
  }, [runId]);

  useEffect(() => {
    if (!runId) return;

    async function loadRun() {
      try {
        setIsLoading(true);
        const response = await fetch(`${API_BASE}/api/runs/${runId}`);
        if (!response.ok) throw new Error("Failed to load the automation session.");
        const data = (await response.json()) as RunSession;
        const plan = data.mapping_plan || [];
        const initialStates: Record<string, FieldState> = {};

        plan.forEach((field) => {
          const skippedByPlan =
            field.action === "skip" ||
            field.strategy === "safety_skip" ||
            field.status === "skipped";

          initialStates[field.field_id] = {
            status: skippedByPlan ? "skipped" : "pending",
            note: skippedByPlan ? "Skipped by mapping plan" : undefined,
          };
        });

        setRunData(data);
        setFieldStates(initialStates);
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "Run session not found.");
      } finally {
        setIsLoading(false);
      }
    }

    loadRun();
  }, [runId]);

  const activeFields = useMemo(() => {
    return (runData?.mapping_plan || []).filter(
      (field) =>
        field.action !== "skip" &&
        field.strategy !== "safety_skip" &&
        field.status !== "skipped"
    );
  }, [runData]);

  const counts = useMemo(() => {
    const states = Object.values(fieldStates);
    return {
      total: runData?.mapping_plan.length || 0,
      active: activeFields.length,
      completed: states.filter((s) => s.status === "completed").length,
      failed: states.filter((s) => s.status === "failed").length,
      skipped: states.filter((s) => s.status === "skipped").length,
    };
  }, [activeFields.length, fieldStates, runData]);

  const progressPct = counts.active
    ? Math.round(Math.min(100, ((counts.completed + counts.skipped) / counts.active) * 100))
    : 0;

  const currentField = activeFields[currentIndex] ?? null;
  const currentFieldState = currentField ? fieldStates[currentField.field_id] : null;
  const proxyUrl = runData?.target_url
    ? `/proxy?url=${encodeURIComponent(runData.target_url)}`
    : "";

  const skipField = useCallback((field: FieldMapping, note = "Skipped") => {
    setFieldStates((prev) => ({
      ...prev,
      [field.field_id]: {
        ...prev[field.field_id],
        status: "skipped",
        note,
        error: undefined,
      },
    }));
  }, []);

  const injectFieldClient = useCallback(
    async (field: FieldMapping, valueOverride?: string): Promise<boolean> => {
      const value =
        valueOverride ?? getFieldValue(field, fieldStatesRef.current[field.field_id]);

      if (!hasFillableValue(field, fieldStatesRef.current[field.field_id])) {
        skipField(field, "No mapped value available");
        return true;
      }

      setFieldStates((prev) => ({
        ...prev,
        [field.field_id]: { ...prev[field.field_id], status: "injecting", error: undefined },
      }));

      const iframeDoc =
        iframeRef.current?.contentDocument || iframeRef.current?.contentWindow?.document;
      if (!iframeDoc) {
        setFieldStates((prev) => ({
          ...prev,
          [field.field_id]: {
            ...prev[field.field_id],
            status: "failed",
            error: "Cannot access the embedded form document.",
          },
        }));
        return false;
      }

      // FIX: Only blur/reset focus for non-dropdown fields.
      // Calling body.click() before a dropdown field closes any dropdown that was
      // already open, breaking the cold-open sequence in selectCustomDropdown.
      const isDropdownField =
        field.action === "select" ||
        field.type === "select" ||
        field.type === "combobox" ||
        field.selector.toLowerCase().includes("location");

      (iframeDoc.activeElement as HTMLElement | null)?.blur();
      if (!isDropdownField) iframeDoc.body.click();

      console.log("FIELD START", {
        label: field.field_label || field.field_id,
        selector: field.selector,
        action: field.action,
        value,
        activeElement: iframeDoc.activeElement,
      });

      const el = findElement(iframeDoc, field.selector);
      if (el) {
        try {
          const iframeWin = iframeRef.current?.contentWindow;
          if (iframeWin) {
            const rect = el.getBoundingClientRect();
            const iframeRect = iframeRef.current!.getBoundingClientRect();
            const absTop = rect.top - iframeRect.top + (iframeWin.scrollY ?? 0);
            iframeWin.scrollTo({ top: absTop - 120, behavior: "instant" });
          }
        } catch {}
      }

      const result = await injectIntoIframe(iframeDoc, field, value, resumeFileRef.current);

      console.log("FIELD END", { label: field.field_label || field.field_id, result });

      if (!result.ok) {
        console.warn("FIELD FAILED", {
          label: field.field_label || field.field_id,
          selector: field.selector,
          reason: result.error,
        });
      }

      if (isDropdownField) {
        const waitEnd = Date.now() + 2500;
        while (Date.now() < waitEnd) {
          if (!iframeDoc.querySelector('.select2-container--open, [aria-expanded="true"]')) break;
          await new Promise((r) => setTimeout(r, 100));
        }
        await new Promise((r) => setTimeout(r, 300));
      } else {
        await new Promise((r) => setTimeout(r, 50));
      }

      setFieldStates((prev) => ({
        ...prev,
        [field.field_id]: {
          ...prev[field.field_id],
          status: result.ok ? "completed" : "failed",
          verificationValue: result.verification,
          error: result.error,
        },
      }));

      return result.ok;
    },
    [skipField]
  );

  const automationLockRef = useRef(false);

  useEffect(() => {
    if (!isAutomating || !iframeReady || !activeFields.length) return;
    if (currentIndex >= activeFields.length) return;

    const field = activeFields[currentIndex];
    const state = fieldStates[field.field_id];

    if (state?.status === "completed" || state?.status === "skipped") {
      const next = currentIndex + 1;
      window.setTimeout(() => {
        setCurrentIndex(next);
        if (next >= activeFields.length) {
          setIsAutomating(false);
          setIsComplete(true);
        }
      }, 0);
      return;
    }

    if (automationLockRef.current) return;
    automationLockRef.current = true;

    let cancelled = false;

    const run = async () => {
      await new Promise((resolve) => setTimeout(resolve, 300));
      if (cancelled) {
        automationLockRef.current = false;
        return;
      }
      const ok = await injectFieldClient(field);
      automationLockRef.current = false;
      if (cancelled) return;
      if (ok) {
        const next = currentIndex + 1;
        setCurrentIndex(next);
        if (next >= activeFields.length) {
          setIsAutomating(false);
          setIsComplete(true);
        }
      } else {
        setIsAutomating(false);
      }
    };

    run();

    return () => {
      cancelled = true;
    };
  }, [activeFields, currentIndex, fieldStates, iframeReady, injectFieldClient, isAutomating]);

  const handleIframeLoad = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    const checkReady = () => {
      const doc = iframe.contentDocument;
      if (doc?.readyState === "complete") {
        setIframeReady(true);
        window.setTimeout(() => setIsAutomating(true), 300);
      } else {
        window.setTimeout(checkReady, 100);
      }
    };

    checkReady();
  }, []);

  const handleRestart = () => {
    if (!runData) return;
    const resetStates: Record<string, FieldState> = {};
    runData.mapping_plan.forEach((field) => {
      const skippedByPlan =
        field.action === "skip" ||
        field.strategy === "safety_skip" ||
        field.status === "skipped";
      resetStates[field.field_id] = {
        status: skippedByPlan ? "skipped" : "pending",
        note: skippedByPlan ? "Skipped by mapping plan" : undefined,
      };
    });
    automationLockRef.current = false;
    setFieldStates(resetStates);
    setCurrentIndex(0);
    setIsComplete(false);
    setIsAutomating(false);
    setIframeReady(false);
    if (iframeRef.current) iframeRef.current.src = iframeRef.current.src;
  };

  const handleResume = () => {
    if (!isComplete) setIsAutomating(true);
  };

  const handleManualInject = async (field: FieldMapping) => {
    let overrideValue = undefined;
    if (editingFieldId === field.field_id) {
      commitEdit(field.field_id);
      overrideValue = editValue;
    }
    const ok = await injectFieldClient(field, overrideValue);
    if (ok) {
      const isCurrentField = activeFields[currentIndex]?.field_id === field.field_id;
      if (isCurrentField) {
        const next = currentIndex + 1;
        setCurrentIndex(next);
        if (next < activeFields.length) {
          setIsAutomating(true);
        } else {
          setIsComplete(true);
        }
      }
    }
  };

  const handleSkipField = (field: FieldMapping) => {
    skipField(field, "Skipped by user");
    if (activeFields[currentIndex]?.field_id === field.field_id) {
      const next = currentIndex + 1;
      setCurrentIndex(next);
      if (next >= activeFields.length) {
        setIsComplete(true);
      }
    }
  };

  const startInlineEdit = (field: FieldMapping) => {
    setEditingFieldId(field.field_id);
    setEditValue(getFieldValue(field, fieldStates[field.field_id]));
  };

  const commitEdit = (fieldId: string) => {
    setFieldStates((prev) => {
      const current = prev[fieldId];
      const wasTerminal = current?.status === "failed" || current?.status === "skipped";
      return {
        ...prev,
        [fieldId]: {
          ...current,
          editedValue: editValue,
          status: wasTerminal ? "pending" : current?.status ?? "pending",
          note: wasTerminal ? undefined : current?.note,
          error: undefined,
        },
      };
    });
    setEditingFieldId(null);
  };

  const handleFieldClick = (field: FieldMapping) => {
    const iframeDoc =
      iframeRef.current?.contentDocument || iframeRef.current?.contentWindow?.document;
    if (!iframeDoc) return;
    const el = findElement(iframeDoc, field.selector);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });

      // FIX: Capture all original style values synchronously before applying the
      // highlight — the timeout callback runs async and may fire after another
      // field has already changed these values.
      const savedOutline = el.style.outline;
      const savedBoxShadow = el.style.boxShadow;
      const savedTransition = el.style.transition;

      el.style.transition = "outline 0.25s ease-in-out, box-shadow 0.25s ease-in-out";
      el.style.outline = "3px solid #7c3aed";
      el.style.boxShadow = "0 0 10px rgba(124, 58, 237, 0.5)";

      try {
        el.focus();
      } catch {}

      setTimeout(() => {
        el.style.outline = savedOutline;
        el.style.boxShadow = savedBoxShadow;
        setTimeout(() => {
          el.style.transition = savedTransition;
        }, 250);
      }, 1200);
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#F3F0FA]">
        <Loader2 className="mb-4 h-12 w-12 animate-spin text-violet-600" />
        <h2 className="text-lg font-bold text-zinc-800">Loading Automation Console...</h2>
      </div>
    );
  }

  if (loadError || !runData) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#F3F0FA] p-6 text-center">
        <XCircle className="mb-4 h-14 w-14 text-rose-500" />
        <h2 className="text-xl font-bold text-zinc-800">Session Load Failed</h2>
        <p className="mb-6 mt-2 max-w-md text-zinc-600">{loadError || "Run session not found."}</p>
        <button
          onClick={() => router.push("/form/new")}
          className="rounded-xl bg-violet-600 px-5 py-3 font-bold text-white hover:bg-violet-700"
        >
          Return to Form Scanner
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#F3F0FA]">
      <header className="z-30 flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white/90 px-5 py-2.5 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <span className="bg-gradient-to-r from-violet-700 to-purple-600 bg-clip-text text-lg font-bold text-transparent">
            FormPilot
          </span>
          <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-bold text-violet-700">
            In-App Browser
          </span>
        </div>

        <div className="flex items-center gap-2">
          {isComplete ? (
            <span className="flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[11px] font-bold text-emerald-700">
              <CheckCircle2 className="h-3.5 w-3.5" /> Done. Review and submit.
            </span>
          ) : isAutomating ? (
            <span className="flex items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-[11px] font-bold text-violet-700">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Filling...
            </span>
          ) : (
            <span className="flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] font-bold text-amber-700">
              <Pause className="h-3.5 w-3.5" /> Paused
            </span>
          )}
        </div>

        <button
          onClick={() => router.push("/form/new")}
          className="flex items-center gap-1.5 text-xs font-bold text-zinc-500 transition hover:text-zinc-800"
        >
          <ArrowLeft className="h-4 w-4" /> New Form
        </button>
      </header>

      <main className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-12">
        <aside className="flex flex-col overflow-hidden border-r border-zinc-200 bg-white lg:col-span-3">
          <section className="shrink-0 border-b border-zinc-100 p-4">
            <p className="mb-2 text-[10px] font-extrabold uppercase tracking-wider text-zinc-400">
              Automation Progress
            </p>
            <div className="mb-1 flex justify-between text-xs font-bold">
              <span className="text-zinc-500">
                {counts.completed}/{counts.active} filled
              </span>
              <span className="text-violet-700">{progressPct}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-zinc-100">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-violet-500 to-purple-500"
                animate={{ width: `${progressPct}%` }}
                transition={{ duration: 0.35 }}
              />
            </div>
            <div className="mt-3 grid grid-cols-4 gap-1.5">
              {(
                [
                  ["Done", counts.completed, "text-emerald-600"],
                  ["Fail", counts.failed, "text-rose-600"],
                  ["Skip", counts.skipped, "text-zinc-500"],
                  ["All", counts.total, "text-zinc-700"],
                ] as const
              ).map(([label, value, className]) => (
                <div key={label} className="rounded-lg bg-zinc-50 p-1.5 text-center">
                  <p className={`text-base font-extrabold ${className}`}>{value}</p>
                  <p className="text-[9px] font-semibold text-zinc-400">{label}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="flex shrink-0 flex-col gap-2 border-b border-zinc-100 p-3">
            {isComplete ? (
              <button
                onClick={handleRestart}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-2 text-xs font-bold text-zinc-600 transition hover:bg-zinc-50"
              >
                <RotateCcw className="h-3.5 w-3.5" /> Restart Automation
              </button>
            ) : isAutomating ? (
              <button
                onClick={() => setIsAutomating(false)}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-extrabold text-white transition hover:bg-amber-600"
              >
                <Pause className="h-4 w-4" /> Pause
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={handleResume}
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-violet-600 px-3 py-2.5 text-sm font-extrabold text-white transition hover:bg-violet-700"
                >
                  <Play className="h-4 w-4 fill-white" /> Resume
                </button>
                <button
                  onClick={handleRestart}
                  className="rounded-xl border border-zinc-200 px-3 py-2.5 text-zinc-500 transition hover:bg-zinc-50"
                  title="Restart"
                >
                  <RotateCcw className="h-4 w-4" />
                </button>
              </div>
            )}
          </section>

          <section className="flex-1 overflow-y-auto">
            <div className="px-3 pb-1 pt-2">
              <p className="text-[10px] font-extrabold uppercase tracking-wider text-zinc-400">
                Fields ({runData.mapping_plan.length})
              </p>
            </div>
            <div className="divide-y divide-zinc-50">
              {runData.mapping_plan.map((field) => {
                const state = fieldStates[field.field_id] ?? { status: "pending" as FieldStatus };
                const isActive = currentField?.field_id === field.field_id && !isComplete;
                const isEditingThis = editingFieldId === field.field_id;
                const displayValue = getFieldValue(field, state);

                return (
                  <div
                    key={field.mapping_id}
                    onClick={() => handleFieldClick(field)}
                    className={`cursor-pointer border-l-2 px-3 py-2 transition-colors ${
                      isActive
                        ? "border-violet-500 bg-violet-50"
                        : "border-transparent hover:bg-zinc-50/70"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      {state.status === "completed" ? (
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                      ) : state.status === "failed" ? (
                        <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-500" />
                      ) : state.status === "injecting" ? (
                        <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-violet-500" />
                      ) : state.status === "skipped" ? (
                        <SkipForward className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-400" />
                      ) : (
                        <AlertCircle
                          className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${statusStyles.pending}`}
                        />
                      )}

                      <div className="min-w-0 flex-1">
                        <p
                          className={`truncate text-[11px] font-bold ${
                            isActive ? "text-violet-800" : "text-zinc-700"
                          }`}
                        >
                          {field.field_label || field.field_id}
                        </p>
                        {isEditingThis ? (
                          <div className="mt-1 flex gap-1">
                            <input
                              autoFocus
                              type="text"
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onClick={(e) => e.stopPropagation()}
                              onKeyDown={(e) => {
                                e.stopPropagation();
                                if (e.key === "Enter") commitEdit(field.field_id);
                                if (e.key === "Escape") setEditingFieldId(null);
                              }}
                              className="min-w-0 flex-1 rounded-md border border-violet-400 px-2 py-1 text-[10px] focus:outline-none"
                            />
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                commitEdit(field.field_id);
                              }}
                              className="rounded-md bg-violet-600 p-1 text-white"
                              title="Save value"
                            >
                              <Check className="h-2.5 w-2.5" />
                            </button>
                          </div>
                        ) : (
                          <p
                            className={`truncate text-[10px] ${
                              displayValue ? "text-zinc-500" : "italic text-zinc-300"
                            }`}
                          >
                            {state.note || displayValue || "No mapped value"}
                          </p>
                        )}
                        {state.error && (
                          <p className="mt-0.5 truncate text-[9px] font-semibold text-rose-600">
                            {state.error}
                          </p>
                        )}
                      </div>

                      {field.action !== "skip" && field.strategy !== "safety_skip" && (
                        <div className="flex shrink-0 items-center gap-0.5">
                          {field.action !== "upload_file" && !isEditingThis && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                startInlineEdit(field);
                              }}
                              className="rounded p-1 text-zinc-300 hover:text-violet-500"
                              title="Edit value"
                            >
                              <Edit2 className="h-3 w-3" />
                            </button>
                          )}
                          {state.status !== "injecting" && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleManualInject(field);
                              }}
                              className="rounded p-1 text-zinc-300 hover:text-emerald-500"
                              title="Inject now"
                            >
                              <Play className="h-3 w-3" />
                            </button>
                          )}
                          {state.status !== "completed" &&
                            state.status !== "skipped" &&
                            state.status !== "injecting" && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSkipField(field);
                                }}
                                className="rounded p-1 text-zinc-300 hover:text-rose-400"
                                title="Skip field"
                              >
                                <SkipForward className="h-3 w-3" />
                              </button>
                            )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <footer className="shrink-0 border-t border-zinc-100 p-3">
            <a
              href={runData.target_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-[11px] font-semibold text-violet-600 transition hover:text-violet-800"
            >
              <ExternalLink className="h-3 w-3" /> Open original form
            </a>
          </footer>
        </aside>

        <section className="relative flex flex-col overflow-hidden bg-zinc-100 lg:col-span-9">
          <div className="flex shrink-0 items-center gap-3 border-b border-zinc-300 bg-zinc-200/80 px-4 py-2">
            <div className="flex items-center gap-1.5">
              <div className="h-2.5 w-2.5 rounded-full bg-rose-400" />
              <div className="h-2.5 w-2.5 rounded-full bg-amber-400" />
              <div className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
            </div>
            <div className="flex flex-1 items-center gap-2 rounded-lg border border-zinc-300 bg-white px-3 py-1">
              <Monitor className="h-3 w-3 shrink-0 text-zinc-400" />
              <span className="truncate font-mono text-[11px] text-zinc-500">
                {runData.target_url}
              </span>
            </div>
            {isAutomating && (
              <div className="flex shrink-0 items-center gap-1.5 text-[11px] font-bold text-violet-600">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Filling
              </div>
            )}
          </div>

          <div className="relative flex-1">
            {!iframeReady && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-white/90 backdrop-blur-sm">
                <Loader2 className="h-10 w-10 animate-spin text-violet-500" />
                <p className="text-sm font-bold text-zinc-700">
                  Opening form inside FormPilot...
                </p>
                <p className="text-xs text-zinc-400">
                  Automation starts as soon as the form is ready.
                </p>
              </div>
            )}

            <iframe
              ref={iframeRef}
              src={proxyUrl}
              onLoad={handleIframeLoad}
              className="h-full w-full border-0"
              sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-top-navigation"
            />

            {!isAutomating &&
              !isComplete &&
              currentField &&
              iframeReady &&
              currentFieldState?.status === "failed" && (
                <div className="absolute bottom-0 left-0 right-0 z-20 flex items-center gap-3 border-t border-zinc-200 bg-white/95 p-3 backdrop-blur">
                  <XCircle className="h-5 w-5 shrink-0 text-rose-500" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-zinc-800">
                      Failed: {currentField.field_label}
                    </p>
                    <p className="truncate text-xs text-zinc-500">{currentFieldState.error}</p>
                  </div>
                  <button
                    onClick={handleResume}
                    className="flex shrink-0 items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-xs font-bold text-white transition hover:bg-violet-500"
                  >
                    <Play className="h-3.5 w-3.5 fill-white" /> Resume
                  </button>
                </div>
              )}

            {isComplete && iframeReady && (
              <div className="absolute bottom-0 left-0 right-0 z-20 flex items-center gap-3 border-t border-emerald-200 bg-emerald-50/95 p-3 backdrop-blur">
                <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-600" />
                <div className="flex-1">
                  <p className="text-sm font-extrabold text-emerald-800">Automation finished</p>
                  <p className="text-xs text-emerald-600">
                    Review the embedded form and submit when everything looks right.
                  </p>
                </div>
                <button
                  onClick={() => router.push("/form/new")}
                  className="rounded-lg bg-violet-600 px-4 py-2 text-xs font-bold text-white transition hover:bg-violet-500"
                >
                  Scan Another
                </button>
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}