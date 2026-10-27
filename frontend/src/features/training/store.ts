import { create } from "zustand";

type TrainingDraft = {
  network: string | null;
  recipe: string | null;
  request: number;
};

type TrainingDraftStore = TrainingDraft & {
  setDraft: (draft: Pick<TrainingDraft, "network" | "recipe">) => void;
};

export const useTrainingDraft = create<TrainingDraftStore>()((set) => ({
  network: null,
  recipe: null,
  request: 0,
  setDraft: ({ network, recipe }) =>
    set((state) => ({ network, recipe, request: state.request + 1 })),
}));
