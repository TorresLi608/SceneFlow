package handlers

import (
	"context"
	"fmt"
	"strings"
	"time"

	"sceneflow/backend/internal/models"
	"sceneflow/backend/internal/security"

	"gorm.io/gorm"
)

type resolvedModelConfig struct {
	Purpose  string
	Provider string
	Model    string
	APIKey   string
}

func (h *ProjectHandler) preflightModelConfig(
	ctx context.Context,
	userID uint,
	purpose string,
	stageName string,
) (resolvedModelConfig, error) {
	purpose = normalizePurpose(purpose)

	config, err := h.loadActiveModelConfig(userID, purpose)
	if err != nil {
		return resolvedModelConfig{}, err
	}

	if config == nil {
		return resolvedModelConfig{}, errBadRequest(fmt.Sprintf(
			"%s未配置可用的默认模型。请前往设置，为“%s”完成校验并激活默认配置后重试。",
			stageName,
			purposeDisplayName(purpose),
		))
	}

	provider := normalizeProvider(config.Provider)
	model := normalizeModelSeriesForProvider(provider, config.ModelName)
	resolvedModel := strings.TrimSpace(resolveDefaultModel(provider, model))

	if err := validateConfigFields(purpose, provider, model); err != nil {
		return resolvedModelConfig{}, errBadRequest(fmt.Sprintf(
			"%s当前映射的默认模型无效。请前往设置修复“%s”默认配置后重试：%s。",
			stageName,
			purposeDisplayName(purpose),
			err.Error(),
		))
	}

	if !config.IsVerified {
		return resolvedModelConfig{}, errBadRequest(fmt.Sprintf(
			"%s当前默认模型尚未通过校验。请前往设置重新验证并激活“%s”默认配置后重试。",
			stageName,
			purposeDisplayName(purpose),
		))
	}

	plainKey, err := security.Decrypt(config.EncryptedKey, h.AESKey)
	if err != nil {
		return resolvedModelConfig{}, fmt.Errorf("failed to decrypt %s config key: %w", purpose, err)
	}

	if strings.TrimSpace(plainKey) == "" {
		return resolvedModelConfig{}, errBadRequest(fmt.Sprintf(
			"%s当前默认模型缺少 API Key。请前往设置补充“%s”配置的密钥并重新校验后重试。",
			stageName,
			purposeDisplayName(purpose),
		))
	}

	if resolvedModel == "" {
		return resolvedModelConfig{}, errBadRequest(fmt.Sprintf(
			"%s未解析出默认模型。请前往设置补充“%s”的模型系列并重新保存后重试。",
			stageName,
			purposeDisplayName(purpose),
		))
	}

	if purpose != "video" {
		if h.Parser == nil {
			return resolvedModelConfig{}, fmt.Errorf("%s validator unavailable", stageName)
		}

		validateCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
		defer cancel()

		var validateErr error
		if purpose == "image" {
			validateErr = h.Parser.ValidateImageModel(validateCtx, provider, plainKey, resolvedModel)
		} else {
			validateErr = h.Parser.ValidateProviderModel(validateCtx, provider, plainKey, resolvedModel)
		}

		if err := validateErr; err != nil {
			return resolvedModelConfig{}, errBadRequest(fmt.Sprintf(
				"%s默认模型不可用：%s / %s。请前往设置重新验证或切换“%s”默认模型后重试。详细原因：%s",
				stageName,
				provider,
				resolvedModel,
				purposeDisplayName(purpose),
				trimPreflightReason(err),
			))
		}
	}

	return resolvedModelConfig{
		Purpose:  purpose,
		Provider: provider,
		Model:    resolvedModel,
		APIKey:   strings.TrimSpace(plainKey),
	}, nil
}

func (h *ProjectHandler) preflightShotPromptModel(
	ctx context.Context,
	userID uint,
) (resolvedModelConfig, string, error) {
	imageConfig, imageErr := h.preflightModelConfig(ctx, userID, "image", "镜头提示词生成")
	if imageErr == nil {
		return imageConfig, "", nil
	}

	scriptConfig, scriptErr := h.preflightModelConfig(ctx, userID, "script", "镜头提示词生成回退")
	if scriptErr == nil {
		warning := fmt.Sprintf(
			"图片生成默认模型当前不可用，已回退到剧本/提示词默认模型 %s / %s。请前往设置修复图片生成默认模型。原始原因：%s",
			scriptConfig.Provider,
			scriptConfig.Model,
			trimPreflightReason(imageErr),
		)
		return scriptConfig, warning, nil
	}

	return resolvedModelConfig{}, "", errBadRequest(fmt.Sprintf(
		"镜头提示词生成前置校验失败。图片生成默认模型不可用：%s；剧本/提示词回退模型也不可用：%s。请前往设置至少修复一个默认模型后重试。",
		trimPreflightReason(imageErr),
		trimPreflightReason(scriptErr),
	))
}

func (h *ProjectHandler) loadActiveModelConfig(userID uint, purpose string) (*models.UserConfig, error) {
	var config models.UserConfig
	if err := h.DB.Where("user_id = ? AND purpose = ? AND is_active = ?", userID, purpose, true).
		Order("updated_at DESC").
		First(&config).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return nil, nil
		}
		return nil, err
	}

	return &config, nil
}

func purposeDisplayName(purpose string) string {
	switch normalizePurpose(purpose) {
	case "script":
		return "剧本/提示词"
	case "image":
		return "图片生成"
	case "video":
		return "视频生成"
	default:
		return purpose
	}
}

func trimPreflightReason(err error) string {
	if err == nil {
		return ""
	}

	message := strings.TrimSpace(err.Error())
	if len(message) > 220 {
		return message[:220] + "..."
	}

	return message
}

func resolveDefaultModel(provider string, requested string) string {
	trimmed := strings.TrimSpace(requested)
	if trimmed != "" {
		switch provider {
		case "qwen", "deepseek", "doubao", "openai":
			return strings.ToLower(trimmed)
		default:
			return trimmed
		}
	}

	switch provider {
	case "deepseek":
		return "deepseek-chat"
	case "qwen":
		return "qwen-plus"
	case "doubao":
		return "doubao-seed-1-6-250615"
	default:
		return "gpt-4o-mini"
	}
}
