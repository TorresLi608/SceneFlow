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
