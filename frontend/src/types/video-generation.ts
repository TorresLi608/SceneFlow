export interface VideoReferenceInput {
  data: string;
  name: string;
}

export type VideoResolution = "1280x720" | "720x1280" | "1024x1024" | "1920x1080";
export type VideoFps = 24 | 30 | 60;
export type VideoQuality = "480p" | "720p" | "1080p";

export interface GenerateVideoInput {
  prompt: string;
  resolution?: VideoResolution;
  fps?: VideoFps;
  quality?: VideoQuality;
  duration: number;
  configId?: number;
  officialConfigId?: number;
  reference?: VideoReferenceInput;
}

export interface GenerateVideoResponse {
  video: {
    url: string;
    model: string;
    source: "text-to-video" | "image-to-video";
    fps?: number;
    quality?: VideoQuality;
  };
}
