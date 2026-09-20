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

export interface UserVoiceListResponse {
  voices: UserVoice[];
  /** Admin retention window for the voice menu in whole days; 0 means voices are kept forever. */
  retentionDays: number;
}
