 import { create } from "zustand";

export interface FormFieldOption {
  value: string;
  label: string;
  selector?: string;
}

export interface ScannedFormField {
  field_id: string;
  selector: string;
  label: string;
  placeholder: string;
  type: string;
  required: boolean;
  options: FormFieldOption[];
  nearby_text: string;
}

export type MappingAction = "fill" | "select" | "multi_select" | "upload_file" | "skip";
export type MappingStrategy = "rule" | "normalized" | "fuzzy" | "gemini" | "safety_skip";
export type MappingStatus = "ready" | "needs_review" | "skipped" | "approved";

export interface FieldMapping {
  mapping_id: string;
  field_id: string;
  selector: string;
  field_label: string;
  type: string;
  action: MappingAction;
  profile_path: string | null;
  value: string | null;
  selected_option: string | null;
  selected_option_label?: string | null;
  selected_options: string[];
  options?: FormFieldOption[];
  confidence_score: number;
  strategy: MappingStrategy;
  reason: string;
  status: MappingStatus;
}

interface FormState {
  formId: string | null;
  targetUrl: string | null;
  detectedFields: ScannedFormField[];
  mappingPlan: FieldMapping[];
  isLoading: boolean;
  error: string | null;

  setFormAnalysis: (
    formId: string,
    targetUrl: string,
    detectedFields: ScannedFormField[],
    mappingPlan: FieldMapping[]
  ) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  updateMappingValue: (mappingId: string, value: string | null) => void;
  updateSelectedOption: (mappingId: string, selectedOption: string | null) => void;
  updateSelectedOptions: (mappingId: string, selectedOptions: string[]) => void;
  updateMappingStatus: (mappingId: string, status: MappingStatus) => void;
  approveMapping: (mappingId: string) => void;
  skipMapping: (mappingId: string) => void;
  approveAllHighConfidence: () => void;

  clearFormStore: () => void;
}

export const useFormStore = create<FormState>((set) => ({
  formId: null,
  targetUrl: null,
  detectedFields: [],
  mappingPlan: [],
  isLoading: false,
  error: null,

  setFormAnalysis: (formId, targetUrl, detectedFields, mappingPlan) =>
    set({
      formId,
      targetUrl,
      detectedFields,
      mappingPlan,
      error: null,
    }),

  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),

  updateMappingValue: (mappingId, value) =>
    set((state) => {
      const mappingPlan = state.mappingPlan.map((m) => {
        if (m.mapping_id === mappingId) {
          const hasVal = value !== null && value.trim() !== "";
          const status = hasVal ? ("approved" as const) : ("needs_review" as const);
          let selected_options = m.selected_options || [];
          if (m.action === "multi_select") {
            selected_options = value ? value.split(",").map((s) => s.trim()).filter(Boolean) : [];
          }
          return {
            ...m,
            value,
            selected_options,
            status,
          };
        }
        return m;
      });
      return { mappingPlan };
    }),

  updateSelectedOption: (mappingId, selectedOption) =>
    set((state) => {
      const mappingPlan = state.mappingPlan.map((m) => {
        if (m.mapping_id === mappingId) {
          const hasVal = selectedOption !== null && selectedOption.trim() !== "";
          const status = hasVal ? ("approved" as const) : ("needs_review" as const);
          let selected_option_label = selectedOption;
          if (m.options) {
            const opt = m.options.find((o) => o.value === selectedOption);
            if (opt) {
              selected_option_label = opt.label;
            }
          }
          return {
            ...m,
            selected_option: selectedOption,
            selected_option_label,
            value: selectedOption,
            status,
          };
        }
        return m;
      });
      return { mappingPlan };
    }),

  updateSelectedOptions: (mappingId, selectedOptions) =>
    set((state) => {
      const mappingPlan = state.mappingPlan.map((m) => {
        if (m.mapping_id === mappingId) {
          const hasVal = selectedOptions && selectedOptions.length > 0;
          const status = hasVal ? ("approved" as const) : ("needs_review" as const);
          return {
            ...m,
            selected_options: selectedOptions,
            value: selectedOptions.join(","),
            status,
          };
        }
        return m;
      });
      return { mappingPlan };
    }),

  updateMappingStatus: (mappingId, status) =>
    set((state) => {
      const mappingPlan = state.mappingPlan.map((m) => {
        if (m.mapping_id === mappingId) {
          return {
            ...m,
            status,
          };
        }
        return m;
      });
      return { mappingPlan };
    }),

  approveMapping: (mappingId) =>
    set((state) => {
      const mappingPlan = state.mappingPlan.map((m) => {
        if (m.mapping_id === mappingId) {
          return {
            ...m,
            status: "approved" as const,
          };
        }
        return m;
      });
      return { mappingPlan };
    }),

  skipMapping: (mappingId) =>
    set((state) => {
      const mappingPlan = state.mappingPlan.map((m) => {
        if (m.mapping_id === mappingId) {
          return {
            ...m,
            status: "skipped" as const,
          };
        }
        return m;
      });
      return { mappingPlan };
    }),

  approveAllHighConfidence: () =>
    set((state) => {
      const mappingPlan = state.mappingPlan.map((m) => {
        // Approve matches with confidence score >= 0.85 and status isn't already skipped
        if (m.confidence_score >= 0.85 && m.status !== "skipped" && m.value !== null) {
          return {
            ...m,
            status: "approved" as const,
          };
        }
        return m;
      });
      return { mappingPlan };
    }),

  clearFormStore: () =>
    set({
      formId: null,
      targetUrl: null,
      detectedFields: [],
      mappingPlan: [],
      isLoading: false,
      error: null,
    }),
}));
