export interface ImageReferenceInput {
  data: string;
  name: string;
}

export interface GenerateImageInput {
  prompt: string;
  resolution: "1K" | "2K" | "4K";
  ratio: "auto" | "1:1" | "2:3" | "3:2" | "3:4" | "4:3" | "16:9" | "9:16" | "21:9" | "9:21";
  configId?: number;
  officialConfigId?: number;
  references?: ImageReferenceInput[];
}

export interface GenerateImageResponse {
  image: {
    url: string;
    model: string;
    source: "text-to-image" | "image-to-image";
  };
}
