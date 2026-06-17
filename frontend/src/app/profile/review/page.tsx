"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  User,
  GraduationCap,
  Briefcase,
  Wrench,
  FolderGit2,
  Plus,
  Trash2,
  ArrowRight,
  ArrowLeft,
  Save,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { useProfileStore } from "@/store/profileStore";
import { API_BASE } from "@/lib/api";

type TabType = "personal" | "education" | "experience" | "skills" | "projects";

export default function ProfileReviewPage() {
  const router = useRouter();
  const {
    profileId,
    profile,
    updatePersonalInfo,
    updateEducation,
    addEducation,
    deleteEducation,
    updateExperience,
    addExperience,
    deleteExperience,
    updateProject,
    addProject,
    deleteProject,
    addSkill,
    deleteSkill,
  } = useProfileStore();

  const [activeTab, setActiveTab] = useState<TabType>("personal");
  const [newSkillInput, setNewSkillInput] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // If no profile is loaded, redirect to upload page or show warning
  useEffect(() => {
    if (!profileId || !profile) {
      // Small delay in case store is hydrating
      const timer = setTimeout(() => {
        if (!profileId || !profile) {
          router.push("/upload");
        }
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [profileId, profile, router]);

  if (!profileId || !profile) {
    return (
      <div className="flex flex-col flex-1 items-center justify-center min-h-screen bg-background p-6">
        <Loader2 className="w-10 h-10 animate-spin text-violet-600 mb-4" />
        <p className="text-muted-text font-semibold">Loading profile review workspace...</p>
      </div>
    );
  }

  const handleAddSkill = (e: React.FormEvent) => {
    e.preventDefault();
    if (newSkillInput.trim()) {
      addSkill(newSkillInput);
      setNewSkillInput("");
    }
  };

  const handleContinue = async () => {
    setIsSaving(true);
    setSaveError(null);

    try {
      // Send the current edited profile to the backend to sync active_profiles[profile_id]
      const response = await fetch(`${API_BASE}/api/profile/${profileId}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(profile),
      });

      if (!response.ok) {
        throw new Error("Failed to sync profile updates to server.");
      }

      router.push("/form/new");
    } catch (err: any) {
      setSaveError(err.message || "Could not save profile updates.");
    } finally {
      setIsSaving(false);
    }
  };

  const tabs = [
    { id: "personal" as TabType, label: "Personal Info", icon: User },
    { id: "education" as TabType, label: "Education", icon: GraduationCap },
    { id: "experience" as TabType, label: "Experience", icon: Briefcase },
    { id: "skills" as TabType, label: "Skills", icon: Wrench },
    { id: "projects" as TabType, label: "Projects", icon: FolderGit2 },
  ];

  return (
    <div className="flex flex-col min-h-screen bg-background relative overflow-x-hidden">
      {/* Background decoration */}
      <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-violet-200/20 blur-[100px] pointer-events-none" />
      <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-purple-200/20 blur-[100px] pointer-events-none" />

      {/* Premium Top Navigation Header */}
      <header className="sticky top-0 bg-white/70 backdrop-blur-md border-b border-border z-30 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold bg-gradient-to-r from-violet-700 to-purple-600 bg-clip-text text-transparent">
            FormPilot
          </span>
          <span className="text-xs bg-violet-100 text-violet-700 font-semibold px-2 py-0.5 rounded-full">
            Workspace
          </span>
        </div>

        {/* Wizard Progress Indicator */}
        <div className="hidden md:flex items-center gap-4 text-xs font-semibold text-muted-text">
          <span className="text-emerald-600 flex items-center gap-1">Upload Resume</span>
          <span className="text-border">/</span>
          <span className="text-violet-700 underline underline-offset-4 decoration-2">Review Profile</span>
          <span className="text-border">/</span>
          <span>Configure Autofill</span>
        </div>

        <button
          onClick={() => router.push("/upload")}
          className="flex items-center gap-1.5 text-sm font-semibold text-muted-text hover:text-foreground transition-colors duration-150"
        >
          <ArrowLeft className="w-4 h-4" />
          Re-upload
        </button>
      </header>

      {/* Workspace Area */}
      <main className="flex-1 max-w-6xl w-full mx-auto p-4 md:p-8 flex flex-col gap-6 z-10">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-foreground">
            Review Extracted Profile
          </h1>
          <p className="text-sm text-muted-text font-medium">
            FormPilot extracted these fields from your resume. Ensure details are correct before connecting a form.
          </p>
        </div>

        {saveError && (
          <div className="p-4 bg-red-50 border border-red-100 text-red-700 text-sm font-medium rounded-xl flex items-start gap-2.5">
            <AlertTriangle className="w-5 h-5 shrink-0" />
            <div>{saveError}</div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Navigation Tabs */}
          <nav className="lg:col-span-3 flex lg:flex-col overflow-x-auto lg:overflow-x-visible pb-2 lg:pb-0 gap-1.5 border-b lg:border-b-0 border-border">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-3 px-4 py-3 text-sm font-bold rounded-xl whitespace-nowrap transition-all duration-200 ${
                    isActive
                      ? "bg-violet-600 text-white shadow-md shadow-violet-600/10"
                      : "bg-white/60 hover:bg-white text-muted-text hover:text-foreground border border-border/50"
                  }`}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  {tab.label}
                </button>
              );
            })}
          </nav>

          {/* Right Editor Section */}
          <div className="lg:col-span-9 glass-card p-6 md:p-8 bg-white min-h-[450px] flex flex-col justify-between">
            <AnimatePresence mode="wait">
              {activeTab === "personal" && (
                <motion.div
                  key="personal"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.15 }}
                  className="flex flex-col gap-6"
                >
                  <h2 className="text-lg font-bold border-b border-border pb-2 flex items-center gap-2">
                    <User className="w-5 h-5 text-violet-600" />
                    Personal Information
                  </h2>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-bold text-muted-text">First Name</label>
                      <input
                        type="text"
                        value={profile.personal_info.first_name || ""}
                        onChange={(e) => updatePersonalInfo({ first_name: e.target.value })}
                        className="px-3.5 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors"
                        placeholder="First Name"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-bold text-muted-text">Last Name</label>
                      <input
                        type="text"
                        value={profile.personal_info.last_name || ""}
                        onChange={(e) => updatePersonalInfo({ last_name: e.target.value })}
                        className="px-3.5 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors"
                        placeholder="Last Name"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-bold text-muted-text">Email</label>
                      <input
                        type="email"
                        value={profile.personal_info.email || ""}
                        onChange={(e) => updatePersonalInfo({ email: e.target.value })}
                        className="px-3.5 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors"
                        placeholder="email@example.com"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-bold text-muted-text">Phone</label>
                      <input
                        type="text"
                        value={profile.personal_info.phone || ""}
                        onChange={(e) => updatePersonalInfo({ phone: e.target.value })}
                        className="px-3.5 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors"
                        placeholder="+1 (555) 012-3456"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-bold text-muted-text">LinkedIn URL</label>
                      <input
                        type="text"
                        value={profile.personal_info.linkedin || ""}
                        onChange={(e) => updatePersonalInfo({ linkedin: e.target.value })}
                        className="px-3.5 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors"
                        placeholder="https://linkedin.com/in/username"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-bold text-muted-text">GitHub URL</label>
                      <input
                        type="text"
                        value={profile.personal_info.github || ""}
                        onChange={(e) => updatePersonalInfo({ github: e.target.value })}
                        className="px-3.5 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors"
                        placeholder="https://github.com/username"
                      />
                    </div>
                    <div className="flex flex-col gap-1.5 md:col-span-2">
                      <label className="text-xs font-bold text-muted-text">Portfolio / Website</label>
                      <input
                        type="text"
                        value={profile.personal_info.portfolio || ""}
                        onChange={(e) => updatePersonalInfo({ portfolio: e.target.value })}
                        className="px-3.5 py-2 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors"
                        placeholder="https://portfolio.com"
                      />
                    </div>
                  </div>
                </motion.div>
              )}

              {activeTab === "education" && (
                <motion.div
                  key="education"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.15 }}
                  className="flex flex-col gap-6"
                >
                  <div className="flex items-center justify-between border-b border-border pb-2">
                    <h2 className="text-lg font-bold flex items-center gap-2">
                      <GraduationCap className="w-5 h-5 text-violet-600" />
                      Education
                    </h2>
                    <button
                      onClick={addEducation}
                      className="flex items-center gap-1 text-xs font-bold text-violet-700 hover:text-violet-900 border border-violet-200 hover:border-violet-400 bg-violet-50/50 hover:bg-violet-50 px-2.5 py-1.5 rounded-lg transition-colors"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add School
                    </button>
                  </div>

                  {profile.education.length === 0 ? (
                    <div className="text-center py-8 text-muted-text font-medium text-sm">
                      No education items found. Click "Add School" to add.
                    </div>
                  ) : (
                    <div className="flex flex-col gap-6 max-h-[380px] overflow-y-auto pr-1">
                      {profile.education.map((edu, idx) => (
                        <div
                          key={idx}
                          className="p-4 rounded-xl border border-border bg-zinc-50/50 hover:bg-zinc-50 relative group transition-colors"
                        >
                          <button
                            onClick={() => deleteEducation(idx)}
                            className="absolute top-4 right-4 text-zinc-400 hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">School / University</label>
                              <input
                                type="text"
                                value={edu.school || ""}
                                onChange={(e) => updateEducation(idx, { school: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="e.g. Stanford University"
                              />
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">Degree</label>
                              <input
                                type="text"
                                value={edu.degree || ""}
                                onChange={(e) => updateEducation(idx, { degree: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="e.g. Bachelor of Science"
                              />
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">Discipline / Major</label>
                              <input
                                type="text"
                                value={edu.discipline || ""}
                                onChange={(e) => updateEducation(idx, { discipline: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="e.g. Computer Science"
                              />
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                              <div className="flex flex-col gap-1">
                                <label className="text-xs font-bold text-muted-text">Start Year</label>
                                <input
                                  type="text"
                                  value={edu.start_year || ""}
                                  onChange={(e) => updateEducation(idx, { start_year: e.target.value })}
                                  className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                  placeholder="YYYY"
                                />
                              </div>
                              <div className="flex flex-col gap-1">
                                <label className="text-xs font-bold text-muted-text">End Year</label>
                                <input
                                  type="text"
                                  value={edu.end_year || ""}
                                  onChange={(e) => updateEducation(idx, { end_year: e.target.value })}
                                  className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                  placeholder="YYYY"
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </motion.div>
              )}

              {activeTab === "experience" && (
                <motion.div
                  key="experience"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.15 }}
                  className="flex flex-col gap-6"
                >
                  <div className="flex items-center justify-between border-b border-border pb-2">
                    <h2 className="text-lg font-bold flex items-center gap-2">
                      <Briefcase className="w-5 h-5 text-violet-600" />
                      Work Experience
                    </h2>
                    <button
                      onClick={addExperience}
                      className="flex items-center gap-1 text-xs font-bold text-violet-700 hover:text-violet-900 border border-violet-200 hover:border-violet-400 bg-violet-50/50 hover:bg-violet-50 px-2.5 py-1.5 rounded-lg transition-colors"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Job
                    </button>
                  </div>

                  {profile.experience.length === 0 ? (
                    <div className="text-center py-8 text-muted-text font-medium text-sm">
                      No experience items found. Click "Add Job" to add.
                    </div>
                  ) : (
                    <div className="flex flex-col gap-6 max-h-[380px] overflow-y-auto pr-1">
                      {profile.experience.map((exp, idx) => (
                        <div
                          key={idx}
                          className="p-4 rounded-xl border border-border bg-zinc-50/50 hover:bg-zinc-50 relative group transition-colors"
                        >
                          <button
                            onClick={() => deleteExperience(idx)}
                            className="absolute top-4 right-4 text-zinc-400 hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">Company Name</label>
                              <input
                                type="text"
                                value={exp.company || ""}
                                onChange={(e) => updateExperience(idx, { company: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="e.g. Google"
                              />
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">Job Title</label>
                              <input
                                type="text"
                                value={exp.title || ""}
                                onChange={(e) => updateExperience(idx, { title: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="e.g. Software Engineer"
                              />
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">Start Date</label>
                              <input
                                type="text"
                                value={exp.start_date || ""}
                                onChange={(e) => updateExperience(idx, { start_date: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="e.g. June 2021"
                              />
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">End Date</label>
                              <input
                                type="text"
                                value={exp.end_date || ""}
                                onChange={(e) => updateExperience(idx, { end_date: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="e.g. Present or Dec 2022"
                              />
                            </div>
                            <div className="flex flex-col gap-1 md:col-span-2">
                              <label className="text-xs font-bold text-muted-text">Description</label>
                              <textarea
                                value={exp.description || ""}
                                onChange={(e) => updateExperience(idx, { description: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors min-h-[90px] resize-y"
                                placeholder="Describe your achievements and duties..."
                              />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </motion.div>
              )}

              {activeTab === "skills" && (
                <motion.div
                  key="skills"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.15 }}
                  className="flex flex-col gap-6"
                >
                  <h2 className="text-lg font-bold border-b border-border pb-2 flex items-center gap-2">
                    <Wrench className="w-5 h-5 text-violet-600" />
                    Skills Tags
                  </h2>

                  <form onSubmit={handleAddSkill} className="flex gap-2">
                    <input
                      type="text"
                      value={newSkillInput}
                      onChange={(e) => setNewSkillInput(e.target.value)}
                      className="px-3.5 py-2.5 flex-1 border border-border focus:border-violet-500 focus:outline-none rounded-xl text-sm font-medium transition-colors"
                      placeholder="Type a skill and press Enter (e.g. TailwindCSS)"
                    />
                    <button
                      type="submit"
                      className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white font-bold rounded-xl text-sm transition-colors flex items-center gap-1.5 shrink-0"
                    >
                      <Plus className="w-4 h-4" />
                      Add Tag
                    </button>
                  </form>

                  <div>
                    <h3 className="text-xs font-bold text-muted-text mb-3">Extracted Skills</h3>
                    {profile.skills.length === 0 ? (
                      <div className="text-center py-6 text-muted-text font-medium text-sm">
                        No skills listed yet. Add some tags above.
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-2.5 max-h-[280px] overflow-y-auto p-1.5 bg-zinc-50/50 border border-border rounded-xl">
                        {profile.skills.map((skill, idx) => (
                          <span
                            key={idx}
                            className="flex items-center gap-1.5 bg-white border border-border text-foreground hover:border-violet-400 font-semibold px-3 py-1.5 rounded-lg text-sm shadow-sm transition-all duration-150"
                          >
                            {skill}
                            <button
                              type="button"
                              onClick={() => deleteSkill(idx)}
                              className="text-muted-text hover:text-red-500 transition-colors inline-flex justify-center items-center w-4 h-4 rounded-full hover:bg-zinc-100"
                              title="Delete skill"
                            >
                              &times;
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.div>
              )}

              {activeTab === "projects" && (
                <motion.div
                  key="projects"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.15 }}
                  className="flex flex-col gap-6"
                >
                  <div className="flex items-center justify-between border-b border-border pb-2">
                    <h2 className="text-lg font-bold flex items-center gap-2">
                      <FolderGit2 className="w-5 h-5 text-violet-600" />
                      Projects
                    </h2>
                    <button
                      onClick={addProject}
                      className="flex items-center gap-1 text-xs font-bold text-violet-700 hover:text-violet-900 border border-violet-200 hover:border-violet-400 bg-violet-50/50 hover:bg-violet-50 px-2.5 py-1.5 rounded-lg transition-colors"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Project
                    </button>
                  </div>

                  {profile.projects.length === 0 ? (
                    <div className="text-center py-8 text-muted-text font-medium text-sm">
                      No project items found. Click "Add Project" to add.
                    </div>
                  ) : (
                    <div className="flex flex-col gap-6 max-h-[380px] overflow-y-auto pr-1">
                      {profile.projects.map((proj, idx) => (
                        <div
                          key={idx}
                          className="p-4 rounded-xl border border-border bg-zinc-50/50 hover:bg-zinc-50 relative group transition-colors"
                        >
                          <button
                            onClick={() => deleteProject(idx)}
                            className="absolute top-4 right-4 text-zinc-400 hover:text-red-600 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="flex flex-col gap-1 md:col-span-2">
                              <label className="text-xs font-bold text-muted-text">Project Name</label>
                              <input
                                type="text"
                                value={proj.name || ""}
                                onChange={(e) => updateProject(idx, { name: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="e.g. FormPilot"
                              />
                            </div>
                            <div className="flex flex-col gap-1 md:col-span-2">
                              <label className="text-xs font-bold text-muted-text">Description</label>
                              <textarea
                                value={proj.description || ""}
                                onChange={(e) => updateProject(idx, { description: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors min-h-[70px] resize-y"
                                placeholder="Describe the project goal and scope..."
                              />
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">Technologies (Comma-separated)</label>
                              <input
                                type="text"
                                value={proj.technologies ? proj.technologies.join(", ") : ""}
                                onChange={(e) => {
                                  const list = e.target.value.split(",").map((t) => t.trim()).filter(Boolean);
                                  updateProject(idx, { technologies: list });
                                }}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="React, Python, FastAPI"
                              />
                            </div>
                            <div className="flex flex-col gap-1">
                              <label className="text-xs font-bold text-muted-text">Project URL / Link</label>
                              <input
                                type="text"
                                value={proj.link || ""}
                                onChange={(e) => updateProject(idx, { link: e.target.value })}
                                className="px-3.5 py-1.5 bg-white border border-border focus:border-violet-500 focus:outline-none rounded-lg text-sm font-medium transition-colors"
                                placeholder="https://github.com/username/project"
                              />
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Bottom Actions inside the container */}
            <div className="mt-8 pt-4 border-t border-border flex flex-col sm:flex-row gap-3 justify-between items-center">
              <span className="text-xs text-muted-text font-semibold">
                Profile edits are saved automatically to the local state.
              </span>
              <div className="flex gap-2.5 w-full sm:w-auto">
                <button
                  onClick={async () => {
                    setIsSaving(true);
                    try {
                      await fetch(`${API_BASE}/api/profile/${profileId}`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(profile),
                      });
                      alert("Successfully saved profile metadata to in-memory server state!");
                    } catch (e) {
                      alert("Error updating profile on the backend.");
                    } finally {
                      setIsSaving(false);
                    }
                  }}
                  disabled={isSaving}
                  className="px-4 py-2 border border-border hover:border-violet-300 hover:bg-zinc-50 text-foreground text-sm font-semibold rounded-lg shadow-sm transition-colors duration-150 flex items-center justify-center gap-1.5 flex-1 sm:flex-none"
                >
                  {isSaving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4" />
                  )}
                  Save Changes
                </button>
                
                <button
                  onClick={handleContinue}
                  disabled={isSaving}
                  className="btn-primary px-6 py-2.5 text-sm flex items-center justify-center gap-2 flex-1 sm:flex-none"
                >
                  {isSaving ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      Continue to Form URL
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
