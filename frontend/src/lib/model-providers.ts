import type { ConfigPurpose, UserConfig } from "@/types/auth";

export interface ProviderOption {
  value: string;
  label: string;
  modelSeries: string;
  modelPlaceholder: string;
  baseUrl?: string;
  docsUrl?: string;
}

export type ConnectionMode = "direct" | "relay";

const chatProviderOptions: ProviderOption[] = [
  {
    value: "qwen",
    label: "通义千问",
    modelSeries: "",
    modelPlaceholder: "qwen-max",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    docsUrl: "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
  },
  {
    value: "doubao",
    label: "豆包",
    modelSeries: "",
    modelPlaceholder: "doubao-seed-2",
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    docsUrl: "https://www.volcengine.com/docs/82379/1263482",
  },
  {
    value: "deepseek",
    label: "DeepSeek",
    modelSeries: "",
    modelPlaceholder: "deepseek-chat",
    baseUrl: "https://api.deepseek.com",
    docsUrl: "https://api-docs.deepseek.com/",
  },
  {
    value: "anthropic",
    label: "Claude",
    modelSeries: "",
    modelPlaceholder: "claude-3-5-sonnet-20240620",
    baseUrl: "https://api.anthropic.com",
    docsUrl: "https://docs.anthropic.com/en/api/messages",
  },
  {
    value: "openai",
    label: "OpenAI",
    modelSeries: "",
    modelPlaceholder: "gpt-5.5",
    baseUrl: "https://api.openai.com/v1",
    docsUrl: "https://platform.openai.com/docs/api-reference/chat",
  },
  {
    value: "gemini",
    label: "Gemini",
    modelSeries: "",
    modelPlaceholder: "gemini-3.6-flash",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    docsUrl: "https://ai.google.dev/gemini-api/docs/openai",
  },
  {
    value: "custom",
    label: "其他",
    modelSeries: "",
    modelPlaceholder: "gpt-4o-mini",
    baseUrl: "",
  },
];

export const providerOptions: Record<ConfigPurpose, ProviderOption[]> = {
  general: chatProviderOptions,
  script: chatProviderOptions,
  image: [
    {
      value: "openai",
      label: "OpenAI",
      modelSeries: "",
      modelPlaceholder: "gpt-image-2",
      baseUrl: "https://api.openai.com/v1",
      docsUrl: "https://platform.openai.com/docs/api-reference/images",
    },
    {
      value: "gemini",
      label: "Gemini",
      modelSeries: "",
      modelPlaceholder: "gemini-3.1-flash-image",
      baseUrl: "https://generativelanguage.googleapis.com/v1beta",
      docsUrl: "https://ai.google.dev/gemini-api/docs/image-generation",
    },
  ],
  video: [
    {
      value: "doubao",
      label: "豆包",
      modelSeries: "seedance-2.0",
      modelPlaceholder: "seedance-2.0",
      baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
      docsUrl: "https://www.volcengine.com/docs/82379",
    },
  ],
};

export const providerLabelMap = Object.fromEntries(
  Object.values(providerOptions)
    .flat()
    .map((option) => [option.value, option.label])
) as Record<string, string>;

export function defaultProviderOption(purpose: ConfigPurpose = "script") {
  return providerOptions[purpose][0] ?? chatProviderOptions[0]!;
}

export function providerOption(purpose: ConfigPurpose, provider: string) {
  return providerOptions[purpose].find((option) => option.value === provider);
}

export function isRelayConnection(provider: string, mode: ConnectionMode) {
  return provider === "custom" || mode === "relay";
}

export function providerBaseUrl(purpose: ConfigPurpose, provider: string) {
  return providerOption(purpose, provider)?.baseUrl ?? "";
}

export function connectionModeFromConfig(config: UserConfig): ConnectionMode {
  if (config.provider === "custom") {
    return "relay";
  }
  return config.baseUrl && config.baseUrl !== providerBaseUrl(config.purpose, config.provider) ? "relay" : "direct";
}

export function baseUrlForConnection(purpose: ConfigPurpose, provider: string, mode: ConnectionMode) {
  return isRelayConnection(provider, mode) ? "" : providerBaseUrl(purpose, provider);
}

export function configsByPurpose(
  configs: readonly UserConfig[],
  isMatch: (config: UserConfig) => boolean
) {
  return configs.reduce<Partial<Record<ConfigPurpose, UserConfig>>>((acc, config) => {
    if (isMatch(config) && !acc[config.purpose]) {
      acc[config.purpose] = config;
    }
    return acc;
  }, {});
}
