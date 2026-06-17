"use client";

import { useState, useRef, DragEvent, ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  User,
  RefreshCw,
  ArrowRight,
  Clock,
} from "lucide-react";
import { useProfileStore } from "@/store/profileStore";
import { API_BASE } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const {
    profileId,
    profile,
    cachedAt,
    setProfile,
    clearProfile,
    isLoading,
    error,
    setLoading,
    setError,
  } = useProfileStore();

  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [showReupload, setShowReupload] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Format cached timestamp
  const cachedDate = cachedAt
    ? new Date(cachedAt).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  // Drag handlers
  const handleDrag = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const processFile = (selectedFile: File) => {
    if (selectedFile.type !== "application/pdf") {
      setError("Only PDF files are supported.");
      setFile(null);
      return;
    }
    setError(null);
    setFile(selectedFile);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  const handleUpload = async () => {
    if (!file) return;

    setLoading(true);
    setProgress(10);
    setError(null);

    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 85) {
          clearInterval(progressInterval);
          return 85;
        }
        return prev + Math.floor(Math.random() * 10) + 2;
      });
    }, 200);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${API_BASE}/api/resume/upload`, {
        method: "POST",
        body: formData,
      });

      clearInterval(progressInterval);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to process the resume.");
      }

      const result = await response.json();
      setProgress(100);

      // Save parsed data to Zustand (automatically persisted to localStorage)
      setProfile(
        result.profile_id,
        result.resume_file_path,
        result.extracted_text_preview,
        result.profile
      );

      setTimeout(() => {
        router.push("/profile/review");
        setLoading(false);
        setProgress(0);
        setFile(null);
      }, 800);
    } catch (err: any) {
      clearInterval(progressInterval);
      setLoading(false);
      setProgress(0);
      setError(err.message || "An unexpected error occurred during upload.");
    }
  };

  const handleUseCached = async () => {
    if (!profileId || !profile) return;

    // Re-register cached profile with backend (it may have restarted)
    try {
      const res = await fetch(`${API_BASE}/api/profile/${profileId}`);
      if (!res.ok) {
        // Backend doesn't have it — re-sync the cached profile
        await fetch(`${API_BASE}/api/profile/${profileId}/restore`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ profile_id: profileId, profile }),
        });
      }
    } catch {
      // Backend may be down or profile missing; proceed anyway — form/new will handle it
    }

    router.push("/profile/review");
  };

  // --- CACHED PROFILE VIEW ---
  if (profileId && profile && !showReupload) {
    const fullName =
      [profile.personal_info.first_name, profile.personal_info.last_name]
        .filter(Boolean)
        .join(" ") || "Unknown";

    return (
      <div className="flex flex-col flex-1 items-center justify-center min-h-screen px-4 py-12 relative overflow-hidden bg-background">
        <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-violet-300/20 blur-[120px] pointer-events-none" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-purple-300/20 blur-[120px] pointer-events-none" />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-md z-10 flex flex-col gap-5"
        >
          {/* Header */}
          <div className="text-center">
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-violet-600 to-purple-500 bg-clip-text text-transparent mb-2">
              Resume on File
            </h1>
            <p className="text-muted-text text-sm font-medium">
              FormPilot found a cached profile — no need to re-upload.
            </p>
          </div>

          {/* Cached Profile Card */}
          <div className="glass-card bg-white p-6 flex flex-col gap-4">
            {/* Profile Identity */}
            <div className="flex items-center gap-4 pb-4 border-b border-border">
              <div className="w-12 h-12 rounded-full bg-violet-100 flex items-center justify-center text-violet-700 shrink-0">
                <User className="w-6 h-6" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-extrabold text-foreground text-base truncate">
                  {fullName}
                </p>
                <p className="text-xs text-muted-text truncate">
                  {profile.personal_info.email || "No email"}
                </p>
              </div>
              <span className="shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-extrabold bg-emerald-50 text-emerald-700 border border-emerald-200">
                <CheckCircle2 className="w-3 h-3" /> Cached
              </span>
            </div>

            {/* Profile Stats */}
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3 bg-zinc-50 rounded-xl border border-border">
                <p className="text-lg font-extrabold text-violet-700">
                  {profile.experience.length}
                </p>
                <p className="text-[10px] font-bold text-muted-text mt-0.5">
                  Jobs
                </p>
              </div>
              <div className="p-3 bg-zinc-50 rounded-xl border border-border">
                <p className="text-lg font-extrabold text-violet-700">
                  {profile.education.length}
                </p>
                <p className="text-[10px] font-bold text-muted-text mt-0.5">
                  Degrees
                </p>
              </div>
              <div className="p-3 bg-zinc-50 rounded-xl border border-border">
                <p className="text-lg font-extrabold text-violet-700">
                  {profile.skills.length}
                </p>
                <p className="text-[10px] font-bold text-muted-text mt-0.5">
                  Skills
                </p>
              </div>
            </div>

            {/* Cached timestamp */}
            {cachedDate && (
              <div className="flex items-center gap-1.5 text-[11px] text-zinc-400 font-medium">
                <Clock className="w-3 h-3" />
                Parsed on {cachedDate}
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-col gap-2.5 pt-2">
              <button
                onClick={handleUseCached}
                className="btn-primary w-full py-3 text-sm flex items-center justify-center gap-2"
              >
                Use This Profile
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                onClick={() => {
                  clearProfile();
                  setShowReupload(true);
                }}
                className="w-full py-2.5 px-4 border border-border hover:border-violet-300 hover:bg-zinc-50 text-foreground font-semibold text-sm rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                <RefreshCw className="w-4 h-4 text-zinc-400" />
                Upload a Different Resume
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    );
  }

  // --- UPLOAD VIEW ---
  return (
    <div className="flex flex-col flex-1 items-center justify-center min-h-screen px-4 py-12 relative overflow-hidden bg-background">
      <div className="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] rounded-full bg-violet-300/20 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-10%] w-[50%] h-[50%] rounded-full bg-purple-300/20 blur-[120px] pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-xl text-center z-10"
      >
        <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-violet-600 to-purple-500 bg-clip-text text-transparent mb-3">
          Upload Your Resume
        </h1>
        <p className="text-muted-text font-medium mb-8 max-w-md mx-auto">
          Drag and drop your PDF resume. FormPilot will parse its content and
          extract a structured profile in seconds.
        </p>

        <div
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
          className={`glass-card p-10 flex flex-col items-center justify-center border-2 border-dashed transition-all duration-300 ${
            dragActive
              ? "border-violet-500 bg-violet-50/50 scale-[1.01]"
              : "border-border hover:border-violet-300"
          } relative`}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf"
            onChange={handleChange}
            disabled={isLoading}
          />

          <AnimatePresence mode="wait">
            {!file ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex flex-col items-center"
              >
                <div className="w-16 h-16 rounded-full bg-violet-100 flex items-center justify-center mb-4 text-violet-600">
                  <Upload className="w-8 h-8" />
                </div>
                <p className="text-base font-semibold text-foreground mb-1">
                  Drag &amp; drop your PDF resume here
                </p>
                <p className="text-xs text-muted-text mb-4">
                  Supports PDF format only (max 10MB)
                </p>
                <button
                  type="button"
                  onClick={handleButtonClick}
                  disabled={isLoading}
                  className="px-4 py-2 border border-violet-200 hover:border-violet-400 bg-white hover:bg-violet-50/30 text-violet-700 text-sm font-semibold rounded-lg shadow-sm transition-all duration-200"
                >
                  Browse Files
                </button>
              </motion.div>
            ) : (
              <motion.div
                key="selected"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="w-full flex flex-col items-center"
              >
                <div className="w-16 h-16 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4">
                  <FileText className="w-8 h-8" />
                </div>
                <h3 className="text-base font-semibold text-foreground truncate max-w-xs mb-1">
                  {file.name}
                </h3>
                <p className="text-xs text-muted-text mb-6">
                  {(file.size / (1024 * 1024)).toFixed(2)} MB
                </p>

                {isLoading ? (
                  <div className="w-full max-w-xs mb-4">
                    <div className="flex justify-between items-center text-xs font-semibold text-violet-700 mb-1">
                      <span className="flex items-center gap-1.5">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Extracting profile...
                      </span>
                      <span>{progress}%</span>
                    </div>
                    <div className="w-full bg-violet-100 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-gradient-to-r from-violet-600 to-purple-500 h-2 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => setFile(null)}
                      className="px-4 py-2 bg-white border border-border text-foreground hover:bg-zinc-50 font-semibold text-sm rounded-lg shadow-sm transition-colors duration-150"
                    >
                      Clear File
                    </button>
                    <button
                      type="button"
                      onClick={handleUpload}
                      className="btn-primary px-6 py-2 text-sm"
                    >
                      Parse Resume
                    </button>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Error Feedback */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mt-4 p-4 rounded-xl border border-red-100 bg-red-50 text-red-700 flex items-start gap-3 text-left"
            >
              <AlertCircle className="w-5 h-5 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-semibold">Parsing Error</p>
                <p className="text-xs font-medium text-red-600/95 mt-0.5">
                  {error}
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
