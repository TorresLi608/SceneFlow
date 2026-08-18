export type AudioFormat = "mp3_24000" | "wav_24000";

export interface GenerateAudioInput {
  text: string;
  voice: string;
  format: AudioFormat;
  volume: number;
  speechRate: number;
  pitchRate: number;
  seed: number;
  instruction?: string;
  languageHints?: ("zh" | "en")[];
  configId?: number;
  officialConfigId?: number;
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
