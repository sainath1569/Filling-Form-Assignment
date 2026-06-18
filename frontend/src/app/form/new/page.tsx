"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Globe, ArrowLeft, Loader2, User, AlertTriangle, Sparkles, Zap } from "lucide-react";
import { useProfileStore } from "@/store/profileStore";
import { useFormStore } from "@/store/formStore";

import { API_BASE } from "@/lib/api";

export default function FormNewPage() {
  const router = useRouter();
  const { profileId, profile } = useProfileStore();
  const { setFormAnalysis , isLoading, setLoading, error, setError } = useFormStore();

  const [urlInput, setUrlInput] = useState("");

  // Redirect if no profile
  useEffect(() => {
    if (!profileId || !profile) {
      const t = setTimeout(() => { if (!profileId || !profile) router.push("/upload"); }, 1000);
      return () => clearTimeout(t);
    }
  }, [profileId, profile, router]);

  if (!profileId || !profile) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center min-h-screen bg-background p-6">
        <Loader2 className="w-10 h-10 animate-spin text-violet-600 mb-4" />
        <p className="text-muted-text font-semibold">Checking active resume session...</p>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlInput.trim()) { setError("Please paste a valid form URL."); return; }

    setLoading(true);
    setError(null);

    try {
      // Step 1: Scan & map the form
      const analyzeRes = await fetch(`${API_BASE}/api/forms/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile_id: profileId, target_url: urlInput.trim() }),
      });
      if (!analyzeRes.ok) {
        const errorBody = await analyzeRes.json().catch(() => ({}));
        throw new Error(errorBody.detail || "Failed to scan the form.");
      }
      const analyzeData = await analyzeRes.json();
      setFormAnalysis(analyzeData.form_id, urlInput.trim(), analyzeData.detected_fields, analyzeData.mapping_plan);

      // Step 2: Confirm & create run (automation starts immediately on the review page)
      const confirmRes = await fetch(`${API_BASE}/api/forms/confirm-run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          form_id: analyzeData.form_id,
          profile_id: profileId,
          mapping_plan: analyzeData.mapping_plan,
        }),
      });
      if (!confirmRes.ok) {
        const errorBody = await confirmRes.json().catch(() => ({}));
        throw new Error(errorBody.detail || "Failed to start autofill session.");
      }
      const { run_id } = await confirmRes.json();

      // Step 3: Go straight to automation console
      router.push(`/run/${run_id}/review`);
    } catch (error) {
      setError(error instanceof Error ? error.message : "An unexpected error occurred.");
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-background relative overflow-x-hidden">
      <div className="absolute top-[-15%] left-[-10%] w-[50%] h-[50%] rounded-full bg-violet-300/25 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-15%] right-[-10%] w-[50%] h-[50%] rounded-full bg-purple-300/25 blur-[120px] pointer-events-none" />

      {/* Header */}
      <header className="sticky top-0 bg-white/70 backdrop-blur-md border-b border-border z-30 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold bg-gradient-to-r from-violet-700 to-purple-600 bg-clip-text text-transparent">FormPilot</span>
          <span className="text-xs bg-violet-100 text-violet-700 font-semibold px-2 py-0.5 rounded-full">Workspace</span>
        </div>
        <button
          onClick={() => router.push("/profile/review")}
          className="flex items-center gap-1.5 text-sm font-semibold text-muted-text hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Profile
        </button>
      </header>

      <main className="flex-1 flex items-center justify-center p-6 z-10">
        <div className="w-full max-w-lg flex flex-col gap-6">

          {/* Hero text */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center flex flex-col gap-2"
          >
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-foreground">
              Paste a Job URL
            </h1>
            <p className="text-muted-text font-medium text-sm">
              FormPilot will scan the form, open it inside the workspace, and fill mapped fields while you stay in control.
            </p>
          </motion.div>

          {/* Card */}
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.08 }}
            className="glass-card p-6 md:p-8 bg-white"
          >
            {/* Active profile pill */}
            <div className="flex items-center gap-2.5 p-3 bg-violet-50/50 border border-violet-100/80 rounded-xl mb-6 text-xs font-semibold text-violet-800">
              <div className="w-7 h-7 rounded-full bg-violet-100 flex items-center justify-center text-violet-700">
                <User className="w-4 h-4" />
              </div>
              <div>
                <p className="font-bold text-foreground">
                  {profile.personal_info.first_name || "N/A"} {profile.personal_info.last_name || ""}
                </p>
                <p className="text-[10px] text-muted-text mt-0.5">{profile.personal_info.email || "No email"}</p>
              </div>
              <span className="ml-auto bg-white border border-violet-200 px-2 py-1 rounded-lg">Session Active</span>
            </div>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-muted-text">Job Application URL</label>
                <div className="relative">
                  <Globe className="absolute left-3.5 top-3.5 text-zinc-400 w-4 h-4" />
                  <input
                    type="url"
                    required
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    disabled={isLoading}
                    placeholder="https://company.greenhouse.io/jobs/..."
                    className="w-full pl-10 pr-4 py-3 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors disabled:opacity-60"
                  />
                </div>
              </div>

              {/* Quick suggestions */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] font-bold text-muted-text">QUICK SUGGESTIONS:</span>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setUrlInput("https://job-boards.greenhouse.io/thinkingmachines/jobs/5111543008")}
                    className="px-2.5 py-1.5 bg-zinc-50 border border-border hover:border-violet-300 text-foreground text-[11px] font-bold rounded-lg transition-colors"
                  >
                    Thinking Machines (Greenhouse)
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="btn-primary w-full py-3.5 mt-1 text-sm flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Scanning &amp; Opening Workspace...
                  </>
                ) : (
                  <>
                    <Zap className="w-4 h-4" />
                    Open In-App Browser
                  </>
                )}
              </button>
            </form>
          </motion.div>

          {/* Loading status */}
          <AnimatePresence>
            {isLoading && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="p-4 bg-violet-50 border border-violet-100 rounded-xl text-violet-800 text-xs font-semibold flex gap-3 items-center"
              >
                <Sparkles className="w-5 h-5 text-violet-600 animate-pulse shrink-0" />
                <span>
                  <strong>FormPilot is working:</strong> Headless Chromium scanning fields → mapping with Gemini → launching browser. This takes 5–15 seconds.
                </span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Error */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="p-4 bg-red-50 border border-red-100 rounded-xl text-red-700 text-xs font-semibold flex gap-2.5 items-start"
              >
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-bold">Scan Failed</p>
                  <p className="text-red-600/90 font-medium mt-0.5">{error}</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
