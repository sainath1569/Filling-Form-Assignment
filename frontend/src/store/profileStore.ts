import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface PersonalInfo {
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  github: string | null;
  portfolio: string | null;
}

export interface Education {
  school: string | null;
  degree: string | null;
  discipline: string | null;
  start_year: string | null;
  end_year: string | null;
}

export interface Experience {
  company: string | null;
  title: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
}

export interface Project {
  name: string | null;
  description: string | null;
  technologies: string[];
  link: string | null;
}

export interface UserProfile {
  personal_info: PersonalInfo;
  education: Education[];
  experience: Experience[];
  skills: string[];
  projects: Project[];
}

interface ProfileState {
  profileId: string | null;
  resumeFilePath: string | null;
  extractedTextPreview: string | null;
  profile: UserProfile | null;
  /** ISO timestamp of when the profile was last parsed */
  cachedAt: string | null;
  isLoading: boolean;
  error: string | null;

  setProfile: (
    profileId: string,
    resumeFilePath: string,
    extractedTextPreview: string,
    profile: UserProfile
  ) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  updatePersonalInfo: (info: Partial<PersonalInfo>) => void;

  updateEducation: (index: number, education: Partial<Education>) => void;
  addEducation: () => void;
  deleteEducation: (index: number) => void;

  updateExperience: (index: number, experience: Partial<Experience>) => void;
  addExperience: () => void;
  deleteExperience: (index: number) => void;

  updateProject: (index: number, project: Partial<Project>) => void;
  addProject: () => void;
  deleteProject: (index: number) => void;

  updateSkills: (skills: string[]) => void;
  addSkill: (skill: string) => void;
  deleteSkill: (index: number) => void;

  clearProfile: () => void;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({
      profileId: null,
      resumeFilePath: null,
      extractedTextPreview: null,
      profile: null,
      cachedAt: null,
      isLoading: false,
      error: null,

      setProfile: (profileId, resumeFilePath, extractedTextPreview, profile) =>
        set({
          profileId,
          resumeFilePath,
          extractedTextPreview,
          profile,
          cachedAt: new Date().toISOString(),
          error: null,
        }),

      setLoading: (isLoading) => set({ isLoading }),
      setError: (error) => set({ error }),

      updatePersonalInfo: (info) =>
        set((state) => {
          if (!state.profile) return {};
          return {
            profile: {
              ...state.profile,
              personal_info: {
                ...state.profile.personal_info,
                ...info,
              },
            },
          };
        }),

      updateEducation: (index, updatedEd) =>
        set((state) => {
          if (!state.profile) return {};
          const education = [...state.profile.education];
          education[index] = { ...education[index], ...updatedEd };
          return { profile: { ...state.profile, education } };
        }),

      addEducation: () =>
        set((state) => {
          if (!state.profile) return {};
          const newEd: Education = {
            school: "",
            degree: "",
            discipline: "",
            start_year: "",
            end_year: "",
          };
          return {
            profile: {
              ...state.profile,
              education: [...state.profile.education, newEd],
            },
          };
        }),

      deleteEducation: (index) =>
        set((state) => {
          if (!state.profile) return {};
          return {
            profile: {
              ...state.profile,
              education: state.profile.education.filter((_, i) => i !== index),
            },
          };
        }),

      updateExperience: (index, updatedExp) =>
        set((state) => {
          if (!state.profile) return {};
          const experience = [...state.profile.experience];
          experience[index] = { ...experience[index], ...updatedExp };
          return { profile: { ...state.profile, experience } };
        }),

      addExperience: () =>
        set((state) => {
          if (!state.profile) return {};
          const newExp: Experience = {
            company: "",
            title: "",
            start_date: "",
            end_date: "",
            description: "",
          };
          return {
            profile: {
              ...state.profile,
              experience: [...state.profile.experience, newExp],
            },
          };
        }),

      deleteExperience: (index) =>
        set((state) => {
          if (!state.profile) return {};
          return {
            profile: {
              ...state.profile,
              experience: state.profile.experience.filter((_, i) => i !== index),
            },
          };
        }),

      updateProject: (index, updatedProj) =>
        set((state) => {
          if (!state.profile) return {};
          const projects = [...state.profile.projects];
          projects[index] = { ...projects[index], ...updatedProj };
          return { profile: { ...state.profile, projects } };
        }),

      addProject: () =>
        set((state) => {
          if (!state.profile) return {};
          const newProj: Project = {
            name: "",
            description: "",
            technologies: [],
            link: "",
          };
          return {
            profile: {
              ...state.profile,
              projects: [...state.profile.projects, newProj],
            },
          };
        }),

      deleteProject: (index) =>
        set((state) => {
          if (!state.profile) return {};
          return {
            profile: {
              ...state.profile,
              projects: state.profile.projects.filter((_, i) => i !== index),
            },
          };
        }),

      updateSkills: (skills) =>
        set((state) => {
          if (!state.profile) return {};
          return { profile: { ...state.profile, skills } };
        }),

      addSkill: (skill) =>
        set((state) => {
          if (!state.profile) return {};
          const trimmedSkill = skill.trim();
          if (!trimmedSkill || state.profile.skills.includes(trimmedSkill))
            return {};
          return {
            profile: {
              ...state.profile,
              skills: [...state.profile.skills, trimmedSkill],
            },
          };
        }),

      deleteSkill: (index) =>
        set((state) => {
          if (!state.profile) return {};
          return {
            profile: {
              ...state.profile,
              skills: state.profile.skills.filter((_, i) => i !== index),
            },
          };
        }),

      clearProfile: () =>
        set({
          profileId: null,
          resumeFilePath: null,
          extractedTextPreview: null,
          profile: null,
          cachedAt: null,
          isLoading: false,
          error: null,
        }),
    }),
    {
      name: "formpilot-profile", // localStorage key
      // Only persist the data fields, not loading/error UI state
      partialize: (state) => ({
        profileId: state.profileId,
        resumeFilePath: state.resumeFilePath,
        extractedTextPreview: state.extractedTextPreview,
        profile: state.profile,
        cachedAt: state.cachedAt,
      }),
    }
  )
);
