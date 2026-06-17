"use client";

import type { ReactElement } from "react";
import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  HelpCircle,
  Play,
  Pause,
  StopCircle,
  ArrowLeft,
  ExternalLink,
  Info,
  Radio,
  FileCheck,
  RefreshCw,
  PlayCircle,
  Ban,
} from "lucide-react";
import { useFormStore } from "@/store/formStore";
import { API_BASE, getRunWebSocketUrl } from "@/lib/api";

interface RunEvent {
  event: string;
  run_id?: string;
  timestamp: string;
  target_url?: string;
  field_id?: string;
  label?: string;
  value?: string;
  error?: string;
  message?: string;
  paused_at_index?: number;
  resumed_at_index?: number;
  stopped_at_index?: number;
}

type RunStatus = "pending" | "running" | "paused" | "cancelled" | "completed" | "failed";

export default function RunWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.id as string;

  const { targetUrl } = useFormStore();

  const [connectionStatus, setConnectionStatus] = useState<
    "Connected" | "Reconnecting" | "Disconnected"
  >("Disconnected");
  const [runStatus, setRunStatus] = useState<RunStatus>("pending");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [currentField, setCurrentField] = useState<{
    field_id: string;
    label: string;
    selector: string;
  } | null>(null);
  const [isControlLoading, setIsControlLoading] = useState<"pause" | "resume" | "cancel" | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const timelineEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll timeline
  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  // Connect to WebSocket
  useEffect(() => {
    if (!runId) return;

    const wsUrl = getRunWebSocketUrl(runId);
    let socket: WebSocket;

    const connectWS = () => {
      setConnectionStatus("Reconnecting");
      socket = new WebSocket(wsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        setConnectionStatus("Connected");
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data) as RunEvent;
        handleIncomingEvent(data);
      };

      socket.onerror = () => {
        setConnectionStatus("Disconnected");
      };

      socket.onclose = () => {
        setConnectionStatus("Disconnected");
        startFallbackPolling();
      };
    };

    connectWS();

    return () => {
      socketRef.current?.close();
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [runId]);

  const handleIncomingEvent = (event: RunEvent) => {
    setEvents((prev) => {
      const exists = prev.some(
        (e) =>
          e.event === event.event &&
          e.field_id === event.field_id &&
          e.timestamp === event.timestamp
      );
      if (exists) return prev;
      return [...prev, event];
    });

    switch (event.event) {
      case "run_started":
        setRunStatus("running");
        break;
      case "field_filling":
        if (event.field_id && event.label) {
          setCurrentField({
            field_id: event.field_id,
            label: event.label,
            selector: (event as any).selector || "",
          });
        }
        break;
      case "field_completed":
      case "field_failed":
      case "field_skipped":
        setCurrentField((curr) =>
          curr?.field_id === event.field_id ? null : curr
        );
        break;
      case "agent_paused":
        setRunStatus("paused");
        setCurrentField(null);
        break;
      case "agent_resumed":
        setRunStatus("running");
        break;
      case "run_cancelled":
        setRunStatus("cancelled");
        setCurrentField(null);
        break;
      case "run_completed":
        setRunStatus("completed");
        setCurrentField(null);
        break;
      case "error":
        setRunStatus("failed");
        setCurrentField(null);
        break;
    }
  };

  const startFallbackPolling = () => {
    if (pollIntervalRef.current) return;
    pollStatus();
    pollIntervalRef.current = setInterval(pollStatus, 1500);
  };

  const pollStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/runs/${runId}`);
      if (!res.ok) return;
      const runData = await res.json();
      setRunStatus(runData.status);
      const serverEvents = runData.events || [];
      setEvents(serverEvents);

      const lastFillingEvent = [...serverEvents]
        .reverse()
        .find((e: RunEvent) => e.event === "field_filling");
      if (lastFillingEvent?.field_id) {
        const resolved = serverEvents.some(
          (e: RunEvent) =>
            ["field_completed", "field_failed", "field_skipped"].includes(e.event) &&
            e.field_id === lastFillingEvent.field_id
        );
        setCurrentField(
          resolved
            ? null
            : { field_id: lastFillingEvent.field_id, label: lastFillingEvent.label || "", selector: "" }
        );
      } else {
        setCurrentField(null);
      }
    } catch {}
  };

  // --- Control actions ---
  const sendControl = async (action: "pause" | "resume" | "cancel") => {
    setIsControlLoading(action);
    try {
      await fetch(`${API_BASE}/api/runs/${runId}/${action}`, {
        method: "POST",
      });
    } catch (e) {
      console.error(`[RunWorkspace] ${action} failed`, e);
    } finally {
      setIsControlLoading(null);
    }
  };

  // Derived stats
  const completedFields = events.filter((e) => e.event === "field_completed");
  const failedFields = events.filter((e) => e.event === "field_failed");
  const skippedFields = events.filter((e) => e.event === "field_skipped");
  const isTerminal = ["completed", "cancelled", "failed"].includes(runStatus);

  const getStatusBadge = () => {
    const badges: Record<RunStatus, ReactElement> = {
      completed: (
        <span className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <CheckCircle2 className="w-4 h-4" /> Completed
        </span>
      ),
      failed: (
        <span className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200 animate-pulse">
          <XCircle className="w-4 h-4" /> Execution Failed
        </span>
      ),
      running: (
        <span className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-violet-50 text-violet-700 border border-violet-200">
          <Loader2 className="w-4 h-4 animate-spin" /> Running
        </span>
      ),
      paused: (
        <span className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200 animate-pulse">
          <Pause className="w-4 h-4" /> Paused
        </span>
      ),
      cancelled: (
        <span className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-zinc-100 text-zinc-600 border border-zinc-200">
          <Ban className="w-4 h-4" /> Cancelled
        </span>
      ),
      pending: (
        <span className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-bold bg-zinc-50 text-zinc-600 border border-zinc-200">
          <Loader2 className="w-4 h-4 animate-spin text-zinc-400" /> Initializing...
        </span>
      ),
    };
    return badges[runStatus];
  };

  const getConnectionBadge = () => {
    if (connectionStatus === "Connected")
      return (
        <div className="flex items-center gap-2 text-xs font-bold text-emerald-600">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          WS Connected
        </div>
      );
    if (connectionStatus === "Reconnecting")
      return (
        <div className="flex items-center gap-2 text-xs font-bold text-amber-500">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
          </span>
          WS Reconnecting...
        </div>
      );
    return (
      <div className="flex items-center gap-2 text-xs font-bold text-zinc-500">
        <span className="relative flex h-2 w-2">
          <span className="relative inline-flex rounded-full h-2 w-2 bg-zinc-400" />
        </span>
        HTTP Polling Fallback
      </div>
    );
  };

  const renderTimelineEvent = (e: RunEvent, idx: number) => {
    let icon = <HelpCircle className="w-4 h-4 text-zinc-500" />;
    let circleBg = "bg-zinc-100 border-zinc-200 text-zinc-600";
    let content: ReactElement | null = null;

    switch (e.event) {
      case "run_started":
        icon = <Play className="w-3.5 h-3.5 fill-violet-600 text-violet-600" />;
        circleBg = "bg-violet-100 border-violet-200 text-violet-700";
        content = (
          <div>
            <p className="font-bold text-foreground text-sm">Autofill run started</p>
            <p className="text-xs text-muted-text font-semibold mt-0.5">
              Navigated to:{" "}
              <span className="font-semibold text-zinc-700 truncate">{e.target_url}</span>
            </p>
          </div>
        );
        break;

      case "field_filling":
        icon = <Loader2 className="w-4 h-4 animate-spin text-violet-600" />;
        circleBg = "bg-violet-50 border-violet-200 text-violet-700";
        content = (
          <div>
            <p className="font-bold text-foreground text-sm">
              Filling field: <span className="text-violet-700 font-extrabold">'{e.label}'</span>
            </p>
            <p className="text-xs text-muted-text font-mono mt-0.5 bg-zinc-50 border border-zinc-100 px-1.5 py-0.5 rounded inline-block">
              {e.field_id}
            </p>
          </div>
        );
        break;

      case "field_completed":
        icon = <CheckCircle2 className="w-4 h-4 text-emerald-600" />;
        circleBg = "bg-emerald-50 border-emerald-200 text-emerald-700";
        content = (
          <div>
            <p className="font-bold text-foreground text-sm">Filled: '{e.label}'</p>
            <p className="text-xs text-muted-text font-semibold mt-0.5">
              Value:{" "}
              <span className="font-mono text-zinc-700 bg-zinc-50 border border-zinc-100 px-1 rounded font-bold">
                {e.value || "empty"}
              </span>
            </p>
          </div>
        );
        break;

      case "field_failed":
        icon = <XCircle className="w-4 h-4 text-rose-600" />;
        circleBg = "bg-rose-50 border-rose-200 text-rose-700";
        content = (
          <div>
            <p className="font-bold text-rose-800 text-sm">Failed to fill: '{e.label}'</p>
            <p className="text-xs text-rose-600 font-bold mt-1 bg-rose-50/50 border border-rose-100/80 p-2 rounded-xl flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-rose-500" />
              {e.error || "Unknown error occurred"}
            </p>
          </div>
        );
        break;

      case "field_skipped":
        icon = <HelpCircle className="w-4 h-4 text-zinc-400" />;
        circleBg = "bg-zinc-50 border-zinc-200 text-zinc-400";
        content = (
          <div>
            <p className="font-bold text-zinc-500 text-sm">Skipped: '{e.label}'</p>
            <p className="text-xs text-muted-text font-semibold mt-0.5">Not approved or EEO field.</p>
          </div>
        );
        break;

      case "agent_paused":
        icon = <Pause className="w-4 h-4 text-amber-600" />;
        circleBg = "bg-amber-50 border-amber-300 text-amber-700";
        content = (
          <div>
            <p className="font-bold text-amber-800 text-sm">Agent paused</p>
            <p className="text-xs text-amber-600 font-semibold mt-0.5">
              Stopped before field #{(e.paused_at_index ?? 0) + 1}. Waiting for resume.
            </p>
          </div>
        );
        break;

      case "agent_resumed":
        icon = <PlayCircle className="w-4 h-4 text-violet-600" />;
        circleBg = "bg-violet-50 border-violet-300 text-violet-700";
        content = (
          <div>
            <p className="font-bold text-violet-800 text-sm">Agent resumed</p>
            <p className="text-xs text-violet-600 font-semibold mt-0.5">
              Continuing from field #{(e.resumed_at_index ?? 0) + 1}.
            </p>
          </div>
        );
        break;

      case "run_cancelled":
        icon = <Ban className="w-4 h-4 text-white" />;
        circleBg = "bg-zinc-500 border-zinc-600 text-white shadow-md";
        content = (
          <div>
            <p className="font-extrabold text-zinc-800 text-sm">Run cancelled</p>
            <p className="text-xs text-zinc-500 font-semibold mt-0.5">
              Execution stopped at field #{(e.stopped_at_index ?? 0) + 1}.
            </p>
          </div>
        );
        break;

      case "run_completed":
        icon = <CheckCircle2 className="w-4 h-4 text-white" />;
        circleBg = "bg-emerald-500 border-emerald-600 text-white shadow-md";
        content = (
          <div>
            <p className="font-extrabold text-foreground text-sm">Autofill completed successfully!</p>
            <p className="text-xs text-muted-text font-semibold mt-0.5">
              All approved form inputs have been populated.
            </p>
          </div>
        );
        break;

      case "error":
        icon = <AlertCircle className="w-4 h-4 text-white" />;
        circleBg = "bg-rose-500 border-rose-600 text-white shadow-md";
        content = (
          <div>
            <p className="font-extrabold text-rose-800 text-sm">General Run Failure</p>
            <p className="text-xs text-rose-600 font-semibold mt-1">{e.message}</p>
          </div>
        );
        break;

      default:
        return null;
    }

    return (
      <motion.div
        key={idx}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="flex items-start gap-4 relative"
      >
        <div className={`w-8 h-8 rounded-full border flex items-center justify-center shrink-0 z-10 ${circleBg}`}>
          {icon}
        </div>
        <div className="flex-1 pt-0.5">{content}</div>
        <span className="text-[10px] text-muted-text font-bold pt-1 shrink-0">
          {new Date(e.timestamp).toLocaleTimeString()}
        </span>
      </motion.div>
    );
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
            Autofill Engine
          </span>
        </div>

        <div className="hidden md:flex items-center gap-4 text-xs font-semibold text-muted-text">
          <span className="text-emerald-600">Upload Resume</span>
          <span className="text-border">/</span>
          <span className="text-emerald-600">Review Profile</span>
          <span className="text-border">/</span>
          <span className="text-emerald-600">Configure Autofill</span>
          <span className="text-border">/</span>
          <span className="text-violet-700 underline underline-offset-4 decoration-2">Live Execution</span>
        </div>

        <div className="flex items-center gap-4">
          {getConnectionBadge()}
          <button
            onClick={() => router.push("/form/review")}
            className="flex items-center gap-1.5 text-sm font-semibold text-muted-text hover:text-foreground transition-colors duration-150"
          >
            <ArrowLeft className="w-4 h-4" />
            Review Mappings
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-5xl w-full mx-auto p-4 md:p-8 flex flex-col gap-6 z-10">

        {/* Title Block */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-border pb-5">
          <div className="flex flex-col gap-1.5">
            <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-foreground flex items-center gap-2">
              <Radio className="w-7 h-7 text-violet-600 animate-pulse" />
              Live Workspace Runner
            </h1>
            <p className="text-sm text-muted-text font-semibold flex items-center gap-1">
              Target URL:
              <span className="text-foreground font-bold truncate max-w-md ml-1">
                {targetUrl || "Form Application"}
              </span>
            </p>
          </div>
          <div className="shrink-0 flex items-center gap-3">
            {getStatusBadge()}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

          {/* Left Panel */}
          <div className="lg:col-span-4 flex flex-col gap-5">

            {/* Run Controls — Phase 6 */}
            <div className="glass-card p-5 bg-white flex flex-col gap-4">
              <h3 className="text-xs font-bold text-muted-text tracking-wider uppercase border-b border-border/50 pb-2">
                Run Controls
              </h3>
              <div className="flex flex-col gap-2.5">

                {/* Pause button — only when running */}
                {runStatus === "running" && (
                  <motion.button
                    id="btn-pause-run"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    onClick={() => sendControl("pause")}
                    disabled={isControlLoading === "pause"}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-800 font-bold text-sm transition-colors duration-150 disabled:opacity-60"
                  >
                    {isControlLoading === "pause" ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Pause className="w-4 h-4" />
                    )}
                    Pause
                  </motion.button>
                )}

                {/* Resume button — only when paused */}
                {runStatus === "paused" && (
                  <motion.button
                    id="btn-resume-run"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    onClick={() => sendControl("resume")}
                    disabled={isControlLoading === "resume"}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-violet-50 hover:bg-violet-100 border border-violet-200 text-violet-800 font-bold text-sm transition-colors duration-150 disabled:opacity-60"
                  >
                    {isControlLoading === "resume" ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <PlayCircle className="w-4 h-4" />
                    )}
                    Resume
                  </motion.button>
                )}

                {/* Cancel button — always visible until terminal */}
                {!isTerminal && (
                  <motion.button
                    id="btn-cancel-run"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    onClick={() => sendControl("cancel")}
                    disabled={isControlLoading === "cancel"}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 font-bold text-sm transition-colors duration-150 disabled:opacity-60"
                  >
                    {isControlLoading === "cancel" ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <StopCircle className="w-4 h-4" />
                    )}
                    Cancel
                  </motion.button>
                )}

                {isTerminal && (
                  <p className="text-xs text-center text-muted-text font-semibold pt-1">
                    Run ended · No controls available
                  </p>
                )}
              </div>
            </div>

            {/* Statistics */}
            <div className="glass-card p-5 bg-white flex flex-col gap-4">
              <h3 className="text-xs font-bold text-muted-text tracking-wider uppercase border-b border-border/50 pb-2">
                Execution Statistics
              </h3>
              <div className="flex flex-col gap-3">
                <div className="flex justify-between items-center text-sm border-b border-border/40 pb-2">
                  <span className="font-semibold text-muted-text">Completed</span>
                  <span className="font-bold text-emerald-600">{completedFields.length}</span>
                </div>
                <div className="flex justify-between items-center text-sm border-b border-border/40 pb-2">
                  <span className="font-semibold text-muted-text">Failed</span>
                  <span className="font-bold text-rose-600">{failedFields.length}</span>
                </div>
                <div className="flex justify-between items-center text-sm">
                  <span className="font-semibold text-muted-text">Skipped</span>
                  <span className="font-bold text-zinc-500">{skippedFields.length}</span>
                </div>
              </div>
            </div>

            {/* Completed card */}
            {runStatus === "completed" && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="p-5 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-2xl flex flex-col gap-3"
              >
                <div className="flex gap-2.5 items-start">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-sm text-emerald-900">Autofill Completed!</h4>
                    <p className="text-xs text-emerald-700 mt-1 leading-relaxed">
                      All approved field mappings have been successfully injected.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => router.push("/")}
                  className="w-full mt-2 py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs rounded-xl shadow transition-colors duration-150 flex items-center justify-center gap-1.5"
                >
                  <FileCheck className="w-3.5 h-3.5" />
                  Return Home
                </button>
              </motion.div>
            )}

            {/* Cancelled card */}
            {runStatus === "cancelled" && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="p-5 bg-zinc-50 border border-zinc-200 text-zinc-700 rounded-2xl flex flex-col gap-3"
              >
                <div className="flex gap-2.5 items-start">
                  <Ban className="w-5 h-5 text-zinc-500 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-sm text-zinc-800">Run Cancelled</h4>
                    <p className="text-xs text-zinc-600 mt-1 leading-relaxed">
                      The autofill agent was stopped before completing all fields.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => router.push("/form/review")}
                  className="w-full mt-2 py-2.5 px-4 bg-zinc-700 hover:bg-zinc-800 text-white font-bold text-xs rounded-xl shadow transition-colors duration-150 flex items-center justify-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Back to Mapping Review
                </button>
              </motion.div>
            )}

            {/* Failed card */}
            {runStatus === "failed" && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="p-5 bg-red-50 border border-red-200 text-red-800 rounded-2xl flex flex-col gap-3"
              >
                <div className="flex gap-2.5 items-start">
                  <XCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-sm text-red-900">Execution Error</h4>
                    <p className="text-xs text-red-700 mt-1 leading-relaxed">
                      The execution ended prematurely due to a browser crash or timeout.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => router.push("/form/review")}
                  className="w-full mt-2 py-2.5 px-4 bg-red-600 hover:bg-red-700 text-white font-bold text-xs rounded-xl shadow transition-colors duration-150 flex items-center justify-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Retry Setup
                </button>
              </motion.div>
            )}

            {/* Paused hint card */}
            {runStatus === "paused" && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="p-4 bg-amber-50 border border-amber-200 rounded-2xl"
              >
                <div className="flex gap-2.5 items-start">
                  <Pause className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold text-sm text-amber-900">Agent is paused</p>
                    <p className="text-xs text-amber-700 mt-1 leading-relaxed">
                      The browser is still open. Press Resume to continue filling, or Cancel to stop.
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
          </div>

          {/* Right Panel: Timeline */}
          <div className="lg:col-span-8 flex flex-col gap-4">
            <h3 className="text-sm font-extrabold text-foreground mb-1">Live Action Feed</h3>

            <div className="flex flex-col gap-4 bg-white border border-border/70 rounded-2xl p-6 min-h-[400px] max-h-[600px] overflow-y-auto relative shadow-sm">
              <div className="absolute left-[39px] top-8 bottom-8 w-0.5 bg-zinc-100" />

              <div className="flex flex-col gap-6 z-10 relative">
                {events.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <Loader2 className="w-8 h-8 text-violet-500 animate-spin mb-3" />
                    <span className="text-sm text-muted-text font-semibold">
                      Connecting to live execution logs...
                    </span>
                  </div>
                )}

                <AnimatePresence initial={false}>
                  {events.map((e, idx) => renderTimelineEvent(e, idx))}
                </AnimatePresence>

                {/* Active field pulse */}
                {currentField && runStatus === "running" && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex items-start gap-4 relative pl-1"
                  >
                    <div className="w-8 h-8 rounded-full border border-violet-200 bg-violet-50 text-violet-700 flex items-center justify-center shrink-0 z-10 animate-pulse">
                      <Loader2 className="w-4 h-4 animate-spin" />
                    </div>
                    <div className="flex-1 pt-0.5">
                      <p className="font-bold text-foreground text-sm animate-pulse">
                        Injecting data into '{currentField.label}'...
                      </p>
                      <p className="text-[10px] text-muted-text font-mono mt-0.5">
                        Selector: {currentField.selector}
                      </p>
                    </div>
                  </motion.div>
                )}

                {/* Paused pulse indicator */}
                {runStatus === "paused" && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex items-start gap-4 relative pl-1"
                  >
                    <div className="w-8 h-8 rounded-full border border-amber-200 bg-amber-50 text-amber-700 flex items-center justify-center shrink-0 z-10">
                      <Pause className="w-4 h-4" />
                    </div>
                    <div className="flex-1 pt-0.5">
                      <p className="font-bold text-amber-700 text-sm animate-pulse">
                        Agent is waiting for resume signal...
                      </p>
                    </div>
                  </motion.div>
                )}

                <div ref={timelineEndRef} />
              </div>
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}
