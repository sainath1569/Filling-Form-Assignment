"use client";

import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowRight, Sparkles, Zap, Shield, Cpu } from "lucide-react";

export default function Home() {
  const router = useRouter();

  return (
    <div className="flex flex-col flex-1 min-h-screen bg-background relative overflow-hidden">
      {/* Visual background elements */}
      <div className="absolute top-[-30%] left-[-10%] w-[60%] h-[60%] rounded-full bg-violet-300/25 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-30%] right-[-10%] w-[60%] h-[60%] rounded-full bg-purple-300/25 blur-[120px] pointer-events-none" />

      {/* Main Container */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-16 md:py-28 flex flex-col items-center justify-center text-center z-10 gap-10">
        
        {/* Sparkle badge */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex items-center gap-1.5 px-3 py-1 bg-violet-100/70 border border-violet-200/50 rounded-full text-violet-800 text-xs font-bold shadow-sm"
        >
          <Sparkles className="w-3.5 h-3.5" />
          Autonomous Autofill Copilot
        </motion.div>

        {/* Hero title */}
        <div className="flex flex-col gap-4 max-w-3xl">
          <motion.h1
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="text-4xl md:text-6xl font-extrabold tracking-tight leading-tight text-foreground"
          >
            Welcome to{" "}
            <span className="bg-gradient-to-r from-violet-600 to-purple-500 bg-clip-text text-transparent">
              FormPilot
            </span>
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 }}
            className="text-base md:text-lg text-muted-text font-medium max-w-xl mx-auto leading-relaxed"
          >
            FormPilot converts plain resume files into rich profile mappings and executes automated filling commands to save you hours of manual input.
          </motion.p>
        </div>

        {/* CTA Button */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.3 }}
          className="flex flex-col sm:flex-row gap-4 items-center justify-center w-full"
        >
          <button
            onClick={() => router.push("/upload")}
            className="btn-primary px-8 py-3.5 text-base flex items-center justify-center gap-2 group w-full sm:w-auto"
          >
            Get Started
            <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform duration-200" />
          </button>
        </motion.div>

        {/* Feature Cards Grid */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
          className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full mt-10"
        >
          {/* Feature 1 */}
          <div className="glass-card p-6 flex flex-col items-center md:items-start text-center md:text-left bg-white">
            <div className="w-10 h-10 rounded-xl bg-violet-100 text-violet-700 flex items-center justify-center mb-4">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-foreground mb-1.5">Resume Extraction</h3>
            <p className="text-xs text-muted-text font-medium leading-relaxed">
              Accepts PDF resumes, extracts plain text content, and structured-parses it via Groq Llama 3 models into a clean schema.
            </p>
          </div>

          {/* Feature 2 */}
          <div className="glass-card p-6 flex flex-col items-center md:items-start text-center md:text-left bg-white">
            <div className="w-10 h-10 rounded-xl bg-violet-100 text-violet-700 flex items-center justify-center mb-4">
              <Zap className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-foreground mb-1.5">Interactive Review</h3>
            <p className="text-xs text-muted-text font-medium leading-relaxed">
              Allows full interactive profile visualization and real-time frontend/backend editing of education, projects, skills, and experience lists.
            </p>
          </div>

          {/* Feature 3 */}
          <div className="glass-card p-6 flex flex-col items-center md:items-start text-center md:text-left bg-white">
            <div className="w-10 h-10 rounded-xl bg-violet-100 text-violet-700 flex items-center justify-center mb-4">
              <Shield className="w-5 h-5" />
            </div>
            <h3 className="text-base font-bold text-foreground mb-1.5">Human-in-the-Loop</h3>
            <p className="text-xs text-muted-text font-medium leading-relaxed">
              Provides robust mapping reviews and guarantees playbooks pause before final submit, protecting private endpoint safety.
            </p>
          </div>
        </motion.div>

      </main>
    </div>
  );
}
