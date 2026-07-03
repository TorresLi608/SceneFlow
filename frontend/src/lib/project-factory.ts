import type { Scene } from "@/types/project";

const nowISO = () => new Date().toISOString();

export const normalizeOrder = (scenes: Scene[]) =>
  scenes.map((scene, index) => ({
    ...scene,
    order: index + 1,
  }));

export { nowISO };
