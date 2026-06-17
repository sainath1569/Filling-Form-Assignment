"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCheck,
  Check,
  X,
  Play,
  ArrowLeft,
  AlertCircle,
  HelpCircle,
  TrendingUp,
  Settings2,
  Loader2,
  ExternalLink,
} from "lucide-react";
import { useFormStore, FieldMapping, ScannedFormField } from "@/store/formStore";
import { useProfileStore } from "@/store/profileStore";
import { API_BASE } from "@/lib/api";

export default function FormReviewPage() {
  const router = useRouter();
  const {
    formId,
    targetUrl,
    detectedFields,
    mappingPlan,
    updateMappingValue,
    updateSelectedOption,
    updateSelectedOptions,
    updateMappingStatus,
    approveMapping,
    skipMapping,
    approveAllHighConfidence,
  } = useFormStore();
  const { profileId, resumeFilePath } = useProfileStore();

  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  useEffect(() => {
    if (!formId || !mappingPlan.length) {
      const timer = setTimeout(() => {
        if (!formId || !mappingPlan.length) {
          router.push("/form/new");
        }
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [formId, mappingPlan, router]);

  if (!formId || !mappingPlan.length) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center min-h-screen bg-background p-6">
        <Loader2 className="w-10 h-10 animate-spin text-violet-600 mb-4" />
        <p className="text-muted-text font-semibold">Loading mapping review workspace...</p>
      </div>
    );
  }

  // Calculate statistics
  const totalFields = mappingPlan.length;
  const approvedCount = mappingPlan.filter((m) => m.status === "approved").length;
  const skippedCount = mappingPlan.filter((m) => m.status === "skipped").length;
  const reviewCount = mappingPlan.filter((m) => m.status === "needs_review").length;

  const handleStartAutofill = async () => {
    setIsSyncing(true);
    setSyncError(null);
    try {
      // 1. Sync the final approved mapping plan back to the backend
      const response = await fetch(`${API_BASE}/api/mappings/${formId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(mappingPlan),
      });

      if (!response.ok) {
        throw new Error("Failed to save final mapping configurations to the server.");
      }

      // 2. Create iframe-mode run session with the approved mapping plan
      const runResponse = await fetch(`${API_BASE}/api/forms/confirm-run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          form_id: formId,
          profile_id: profileId,
          mapping_plan: mappingPlan,
        }),
      });

      if (!runResponse.ok) {
        throw new Error("Failed to initialize active autofill run on the server.");
      }

      const runData = await runResponse.json();
      const runId = runData.run_id;

      // 3. Open the in-app automation console
      router.push(`/run/${runId}/review`);
    } catch (err: any) {
      setSyncError(err.message || "Failed to finalize mappings.");
    } finally {
      setIsSyncing(false);
    }
  };

  const getConfidenceBadge = (m: FieldMapping) => {
    if (m.status === "skipped") {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-zinc-100 text-zinc-500 border border-zinc-200">
          Skipped
        </span>
      );
    }
    
    const score = m.confidence_score;
    if (score >= 0.85) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
          High Match ({(score * 100).toFixed(0)}%)
        </span>
      );
    } else if (score >= 0.50) {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200">
          Review Needed ({(score * 100).toFixed(0)}%)
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200 animate-pulse">
          <AlertCircle className="w-3 h-3" />
          Low Confidence ({(score * 100).toFixed(0)}%)
        </span>
      );
    }
  };
  
  const getStrategyBadge = (strategy: string) => {
    const labels: Record<string, string> = {
      rule: "Rule",
      normalized: "Normalized",
      fuzzy: "Fuzzy",
      gemini: "Gemini",
      safety_skip: "Safety Skip"
    };
    const colors: Record<string, string> = {
      rule: "bg-blue-50 text-blue-700 border-blue-200",
      normalized: "bg-teal-50 text-teal-700 border-teal-200",
      fuzzy: "bg-amber-50 text-amber-700 border-amber-200",
      gemini: "bg-purple-50 text-purple-700 border-purple-200",
      safety_skip: "bg-rose-50 text-rose-700 border-rose-200"
    };
    const label = labels[strategy] || strategy;
    const color = colors[strategy] || "bg-zinc-50 text-zinc-700 border-zinc-200";
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold border ${color}`}>
        {label}
      </span>
    );
  };

  const getActionBadge = (action: string) => {
    const labels: Record<string, string> = {
      fill: "Fill",
      select: "Select",
      multi_select: "Multi Select",
      upload_file: "Upload File",
      skip: "Skip"
    };
    const colors: Record<string, string> = {
      fill: "bg-indigo-50 text-indigo-700 border-indigo-200",
      select: "bg-sky-50 text-sky-700 border-sky-200",
      multi_select: "bg-emerald-50 text-emerald-700 border-emerald-200",
      upload_file: "bg-orange-50 text-orange-700 border-orange-200",
      skip: "bg-zinc-100 text-zinc-750 border-zinc-300"
    };
    const label = labels[action] || action;
    const color = colors[action] || "bg-zinc-50 text-zinc-700 border-zinc-200";
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold border ${color}`}>
        {label}
      </span>
    );
  };

  // Find original scraped field options
  const getFieldOptions = (fieldId: string) => {
    const field = detectedFields.find((f) => f.field_id === fieldId);
    return field?.options || [];
  };

  // Find original scraped field type
  const getFieldType = (fieldId: string) => {
    const field = detectedFields.find((f) => f.field_id === fieldId);
    return field?.type || "text";
  };

  return (
    <div className="flex flex-col min-h-screen bg-background relative overflow-x-hidden">
      {/* Background gradients */}
      <div className="absolute top-[-10%] right-[-10%] w-[45%] h-[45%] rounded-full bg-violet-200/20 blur-[100px] pointer-events-none" />
      <div className="absolute bottom-[-10%] left-[-10%] w-[45%] h-[45%] rounded-full bg-purple-200/20 blur-[100px] pointer-events-none" />

      {/* Header */}
      <header className="sticky top-0 bg-white/70 backdrop-blur-md border-b border-border z-30 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold bg-gradient-to-r from-violet-700 to-purple-600 bg-clip-text text-transparent">
            FormPilot
          </span>
          <span className="text-xs bg-violet-100 text-violet-700 font-semibold px-2 py-0.5 rounded-full">
            Workspace
          </span>
        </div>

        {/* Wizard progress */}
        <div className="hidden md:flex items-center gap-4 text-xs font-semibold text-muted-text">
          <span className="text-emerald-600">Upload Resume</span>
          <span className="text-border">/</span>
          <span className="text-emerald-600">Review Profile</span>
          <span className="text-border">/</span>
          <span className="text-violet-700 underline underline-offset-4 decoration-2">Configure Autofill</span>
        </div>

        <button
          onClick={() => router.push("/form/new")}
          className="flex items-center gap-1.5 text-sm font-semibold text-muted-text hover:text-foreground transition-colors duration-150"
        >
          <ArrowLeft className="w-4 h-4" />
          Rescan Form
        </button>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-8 flex flex-col gap-6 z-10">
        
        {/* Title block */}
        <div className="flex flex-col gap-1.5">
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-foreground flex items-center gap-2">
            <Settings2 className="w-7 h-7 text-violet-600" />
            Field Mapping Review
          </h1>
          <p className="text-sm text-muted-text font-medium flex items-center gap-1.5">
            URL: 
            <a 
              href={targetUrl || "#"} 
              target="_blank" 
              rel="noopener noreferrer" 
              className="text-violet-700 font-bold hover:underline flex items-center gap-0.5"
            >
              {targetUrl}
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </p>
        </div>

        {syncError && (
          <div className="p-4 bg-red-50 border border-red-100 text-red-700 text-sm font-medium rounded-xl">
            {syncError}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* Left Summary Panel */}
          <div className="lg:col-span-3 flex flex-col gap-5">
            
            {/* Stats card */}
            <div className="glass-card p-5 bg-white flex flex-col gap-4">
              <h3 className="text-xs font-bold text-muted-text tracking-wider uppercase">
                Form Mappings
              </h3>
              
              <div className="flex flex-col gap-3">
                <div className="flex justify-between items-center text-sm border-b border-border/50 pb-2">
                  <span className="font-semibold text-muted-text">Total Fields</span>
                  <span className="font-bold text-foreground">{totalFields}</span>
                </div>
                <div className="flex justify-between items-center text-sm border-b border-border/50 pb-2">
                  <span className="font-semibold text-emerald-600 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                    Approved
                  </span>
                  <span className="font-bold text-emerald-700">{approvedCount}</span>
                </div>
                <div className="flex justify-between items-center text-sm border-b border-border/50 pb-2">
                  <span className="font-semibold text-amber-600 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                    Needs Review
                  </span>
                  <span className="font-bold text-amber-700">{reviewCount}</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="font-semibold text-zinc-500 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-zinc-400" />
                    Skipped
                  </span>
                  <span className="font-bold text-zinc-600">{skippedCount}</span>
                </div>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-zinc-100 h-2.5 rounded-full overflow-hidden mt-1 flex">
                <div
                  className="bg-emerald-500 h-full transition-all duration-300"
                  style={{ width: `${(approvedCount / totalFields) * 100}%` }}
                />
                <div
                  className="bg-amber-400 h-full transition-all duration-300"
                  style={{ width: `${(reviewCount / totalFields) * 100}%` }}
                />
              </div>
            </div>

            {/* Quick action buttons */}
            <button
              onClick={approveAllHighConfidence}
              className="w-full px-4 py-3 bg-violet-50 hover:bg-violet-100 border border-violet-200 text-violet-700 font-bold text-sm rounded-xl shadow-sm transition-colors duration-150 flex items-center justify-center gap-2"
            >
              <FileCheck className="w-4 h-4" />
              Approve High-Confidence
            </button>
            
            <button
              onClick={handleStartAutofill}
              disabled={isSyncing || approvedCount === 0}
              className="btn-primary w-full py-4 text-base flex items-center justify-center gap-2"
            >
              {isSyncing ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Saving plan...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-white" />
                  Start Autofill
                </>
              )}
            </button>
            
            {approvedCount === 0 && (
              <p className="text-[10px] text-red-500 font-bold text-center">
                * You must approve at least one mapping to start filling.
              </p>
            )}
          </div>

          {/* Right Mappings List */}
          <div className="lg:col-span-9 flex flex-col gap-4">
            <h3 className="text-sm font-extrabold text-foreground mb-1">Detected Inputs</h3>

            <div className="flex flex-col gap-4 max-h-[600px] overflow-y-auto pr-2">
              {mappingPlan.map((m) => {
                const fType = getFieldType(m.field_id);
                const opts = getFieldOptions(m.field_id);
                const isApproved = m.status === "approved";
                const isSkipped = m.status === "skipped";

                return (
                  <div
                    key={m.mapping_id}
                    className={`glass-card p-5 bg-white border transition-all duration-200 relative group ${
                      isApproved
                        ? "border-emerald-200 bg-emerald-50/5 hover:bg-emerald-50/10"
                        : isSkipped
                        ? "border-zinc-200 bg-zinc-50/10 opacity-70"
                        : "border-amber-200 bg-amber-50/5 hover:bg-amber-50/10"
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row justify-between items-start gap-3 border-b border-border/40 pb-3 mb-3">
                      <div>
                        <h4 className="font-extrabold text-foreground text-sm flex items-center gap-1.5">
                          {m.field_label || m.field_id}
                          {m.selector && (
                            <span className="font-mono text-[10px] font-semibold text-muted-text bg-zinc-100 px-1.5 py-0.5 rounded border border-border">
                              {m.selector}
                            </span>
                          )}
                        </h4>
                        <p className="text-xs text-muted-text font-semibold mt-1">
                          Mapped to profile path:{" "}
                          <span className="font-mono text-violet-700 bg-violet-50/80 border border-violet-100 px-1 rounded font-bold">
                            {m.profile_path || "None / Hand-written"}
                          </span>
                        </p>
                      </div>
                      
                      <div className="shrink-0 flex flex-wrap gap-1.5 justify-end items-center">
                        {getStrategyBadge(m.strategy)}
                        {getActionBadge(m.action)}
                        {getConfidenceBadge(m)}
                      </div>
                    </div>

                    {/* Value Input Area */}
                    <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
                      <div className="md:col-span-8 flex flex-col gap-1">
                        <label className="text-[10px] font-bold text-muted-text uppercase">
                          Autofill Value
                        </label>
                        
                        {/* Render input based on mapping action */}
                        {m.action === "upload_file" ? (
                          <div className="flex flex-col gap-1.5 p-3 bg-zinc-50 border border-zinc-200 rounded-xl">
                            <span className="text-xs font-bold text-zinc-600 flex items-center gap-1.5">
                              📎 Resume file will be attached
                            </span>
                            {(m.value || resumeFilePath) && (
                              <span className="text-[10px] font-mono text-zinc-500 bg-white border border-zinc-200 px-2 py-1 rounded-md self-start">
                                📄 {(m.value || resumeFilePath || "").split(/[\\/]/).pop()}
                              </span>
                            )}
                          </div>
                        ) : m.action === "select" ? (
                          <select
                            value={m.selected_option ?? m.value ?? ""}
                            onChange={(e) => updateSelectedOption(m.mapping_id, e.target.value)}
                            disabled={isSkipped}
                            className="px-3 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-semibold bg-white disabled:bg-zinc-50 disabled:cursor-not-allowed"
                          >
                            <option value="">-- Select Option --</option>
                            {(m.options || opts || []).map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        ) : m.action === "multi_select" ? (
                          <div className="flex flex-col gap-2 py-1">
                            {(m.options || opts || []).map((o) => {
                              const isChecked = (m.selected_options || []).includes(o.value);
                              return (
                                <label key={o.value} className="flex items-center gap-2 text-xs font-semibold cursor-pointer">
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={(e) => {
                                      const currentSelected = m.selected_options || [];
                                      let newSelected;
                                      if (e.target.checked) {
                                        newSelected = [...currentSelected, o.value];
                                      } else {
                                        newSelected = currentSelected.filter((v) => v !== o.value);
                                      }
                                      updateSelectedOptions(m.mapping_id, newSelected);
                                    }}
                                    disabled={isSkipped}
                                    className="w-4 h-4 text-violet-600 focus:ring-violet-500 border-gray-300 rounded"
                                  />
                                  {o.label}
                                </label>
                              );
                            })}
                          </div>
                        ) : m.action === "skip" ? (
                          <div className="text-xs font-semibold text-zinc-500 italic bg-zinc-50 p-2.5 rounded-xl border border-zinc-200">
                            🚫 {m.reason || "No matching value found (field skipped)"}
                          </div>
                        ) : (
                          /* Fallback for fill / standard inputs based on element type */
                          fType === "textarea" ? (
                            <textarea
                              value={m.value || ""}
                              onChange={(e) => updateMappingValue(m.mapping_id, e.target.value)}
                              disabled={isSkipped}
                              rows={2}
                              className="px-3 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-semibold disabled:bg-zinc-50 disabled:cursor-not-allowed resize-y"
                              placeholder="Type a custom description..."
                            />
                          ) : fType === "checkbox" ? (
                            <div className="flex items-center gap-2 py-1">
                              <input
                                type="checkbox"
                                checked={m.value === "true" || m.value === "checked"}
                                onChange={(e) =>
                                  updateMappingValue(m.mapping_id, e.target.checked ? "true" : "false")
                                }
                                disabled={isSkipped}
                                className="w-4 h-4 text-violet-600 focus:ring-violet-500 border-gray-300 rounded"
                              />
                              <span className="text-xs font-semibold text-foreground">Checked</span>
                            </div>
                          ) : fType === "radio" && opts.length > 0 ? (
                            <div className="flex flex-wrap gap-3 py-1">
                              {opts.map((o) => (
                                <label key={o.value} className="flex items-center gap-1.5 text-xs font-semibold cursor-pointer">
                                  <input
                                    type="radio"
                                    name={`radio-${m.mapping_id}`}
                                    value={o.value}
                                    checked={m.value === o.value}
                                    onChange={(e) => updateMappingValue(m.mapping_id, e.target.value)}
                                    disabled={isSkipped}
                                    className="w-3.5 h-3.5 text-violet-600 focus:ring-violet-500"
                                  />
                                  {o.label}
                                </label>
                              ))}
                            </div>
                          ) : (
                            <input
                              type="text"
                              value={m.value || ""}
                              onChange={(e) => updateMappingValue(m.mapping_id, e.target.value)}
                              disabled={isSkipped}
                              className="px-3 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-semibold disabled:bg-zinc-50 disabled:cursor-not-allowed"
                              placeholder="Empty field value"
                            />
                          )
                        )}
                      </div>

                      {/* Mapping actions */}
                      <div className="md:col-span-4 flex justify-end gap-2 mt-2 md:mt-0 pt-2 md:pt-0 border-t md:border-t-0 border-border/40">
                        {isSkipped ? (
                          <button
                            onClick={() => approveMapping(m.mapping_id)}
                            className="px-3 py-1.5 bg-white border border-border hover:border-violet-300 text-foreground text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5"
                          >
                            <Check className="w-3.5 h-3.5" />
                            Enable Field
                          </button>
                        ) : (
                          <>
                            <button
                              onClick={() => skipMapping(m.mapping_id)}
                              className="px-3 py-1.5 bg-white border border-border hover:border-red-300 text-red-600 text-xs font-bold rounded-lg hover:bg-red-50/50 transition-colors flex items-center gap-1.5"
                            >
                              <X className="w-3.5 h-3.5" />
                              Skip Element
                            </button>
                            
                            {!isApproved && (
                              <button
                                onClick={() => approveMapping(m.mapping_id)}
                                className="px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs font-bold rounded-lg shadow-sm transition-colors flex items-center gap-1.5 animate-pulse hover:animate-none"
                              >
                                <Check className="w-3.5 h-3.5" />
                                Approve
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}
