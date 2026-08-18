export interface VideoReferenceInput {
  data?: string;
  name?: string;
  url?: string;
}

export type VideoAspectRatio = "21:9" | "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "adaptive";
export type VideoFps = 24 | 30 | 60;
export type VideoQuality = "480p" | "720p" | "1080p" | "2K" | "4K";

export interface GenerateVideoInput {
  prompt: string;
  aspectRatio?: VideoAspectRatio;
  fps?: VideoFps;
  quality?: VideoQuality;
  promptExtend?: boolean;
  duration: number;
  configId?: number;
  officialConfigId?: number;
  references?: VideoReferenceInput[];
  referenceVideo?: VideoReferenceInput;
  referenceAudio?: VideoReferenceInput;
  referenceVideos?: VideoReferenceInput[];
  referenceAudios?: VideoReferenceInput[];
}

export interface GenerateVideoResponse {
  video: {
    url: string;
    model: string;
    source: "text-to-video" | "image-to-video" | "video-to-video";
    fps?: number;
    quality?: VideoQuality;
  };
}
