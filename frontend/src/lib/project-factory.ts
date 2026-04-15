import type { Project, Scene } from "@/types/project";

function randomId(prefix: string) {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}_${crypto.randomUUID()}`;
  }

  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

const nowISO = () => new Date().toISOString();

export const makeScene = (index: number, narration: string, visualPrompt: string): Scene => ({
  id: randomId("scene"),
  order: index + 1,
  narration,
  visualPrompt,
  image: { url: null, status: "idle", progress: 0 },
  audio: { url: null, status: "idle", duration: 0 },
});

export const normalizeOrder = (scenes: Scene[]) =>
  scenes.map((scene, index) => ({
    ...scene,
    order: index + 1,
  }));

export const scriptToScenes = (script: string) => {
  const lines = script
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 12);

  if (lines.length === 0) {
    return [
      makeScene(
        0,
        "主角在深夜的城市街头停下脚步，远处霓虹开始闪烁。",
        "cinematic anime frame, night city street, neon reflection, dramatic perspective"
      ),
      makeScene(
        1,
        "镜头推进到主角特写，耳边传来第一句旁白。",
        "close-up anime portrait, emotional eyes, cool-tone lighting, shallow depth of field"
      ),
    ];
  }

  return lines.map((line, index) =>
    makeScene(
      index,
      line,
      `anime storyboard frame ${index + 1}, ${line.slice(0, 90)}, cinematic composition, high detail`
    )
  );
};

export const createTemplateProjects = (): Project[] => {
  const launchScript =
    "午夜，城市广告屏统一熄灭。\n少女骑着机车冲进主干道，背后是追击无人机。\n她掏出旧式磁带机，播放一段被禁播的旋律。";
  const brandScript =
    "画面从黑场淡入，工位灯一盏盏亮起。\n产品原型在转台上缓慢旋转。\n字幕出现：每一次迭代，都在逼近理想。";

  return [
    {
      id: "proj_launch_trailer",
      title: "赛博追光 预告片",
      originalScript: launchScript,
      status: "idle",
      updatedAt: nowISO(),
      scenes: scriptToScenes(launchScript),
    },
    {
      id: "proj_brand_story",
      title: "品牌短片 - 开场",
      originalScript: brandScript,
      status: "idle",
      updatedAt: nowISO(),
      scenes: scriptToScenes(brandScript),
    },
  ];
};

export const createEmptyProject = (sequence: number): Project => ({
  id: randomId("proj"),
  title: `新项目 ${sequence}`,
  originalScript: "",
  status: "idle",
  updatedAt: nowISO(),
  scenes: scriptToScenes(""),
});

export { nowISO };
