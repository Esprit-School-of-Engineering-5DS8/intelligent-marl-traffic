import { useMutation } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "./backend";

export const SimulationState = z
  .object({
    status: z.string(),
    scenario: z.string(),
  })
  .passthrough();

export type SimulationState = z.infer<typeof SimulationState>;

const SIMULATION_SCENARIOS: Record<string, string> = {
  grid2x2: "grid-2x2",
  grid3x3: "grid-3x3",
  monaco: "monaco",
  tunis: "tunis",
};

export function simulationScenario(network: string): string {
  return SIMULATION_SCENARIOS[network] ?? network;
}

export function useStartSimulation() {
  return useMutation({
    mutationFn: ({ network, speed = 1 }: { network: string; speed?: number }) =>
      api("simulation/start", SimulationState, {
        method: "POST",
        body: JSON.stringify({ scenario: simulationScenario(network), speed }),
      }),
  });
}
