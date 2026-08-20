export type AudioFormat = "mp3_24000" | "wav_24000";

export interface GenerateAudioInput {
  text: string;
  voice: string;
  configId?: number;
  officialConfigId?: number;
}

export interface UserVoice {
  id: string;
  voiceId: string;
  targetModel: string;
  name: string;
  voicePrompt: string;
  previewText: string;
  previewAudioUrl: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface GenerateAudioResponse {
  audio: {
    url: string;
    model: string;
    voice: string;
    duration: number;
    format: AudioFormat;
  };
}
