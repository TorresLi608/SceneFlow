package handlers

import (
	"net/http"
	"strings"

	"sceneflow/backend/internal/middleware"
	"sceneflow/backend/internal/models"
	"sceneflow/backend/internal/security"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type UserConfigHandler struct {
	DB     *gorm.DB
	AESKey []byte
}

type createUserConfigRequest struct {
	Purpose  string `json:"purpose" binding:"required"`
	Provider string `json:"provider" binding:"required,min=2,max=32"`
	Model    string `json:"model"`
	APIKey   string `json:"apiKey" binding:"required,min=8,max=512"`
	IsActive bool   `json:"isActive"`
}

type updateUserConfigRequest struct {
	Purpose  *string `json:"purpose,omitempty"`
	Provider *string `json:"provider,omitempty"`
	Model    *string `json:"model,omitempty"`
	APIKey   *string `json:"apiKey,omitempty"`
	IsActive *bool   `json:"isActive,omitempty"`
}

func (h *UserConfigHandler) Create(c *gin.Context) {
	userID, ok := middleware.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing user context"})
		return
	}

	var req createUserConfigRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	purpose := normalizePurpose(req.Purpose)
	provider := normalizeProvider(req.Provider)
	model := strings.TrimSpace(req.Model)

	if err := validateConfigFields(purpose, provider, model); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	encrypted, err := security.Encrypt(req.APIKey, h.AESKey)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to encrypt api key"})
		return
	}

	config := models.UserConfig{
		UserID:       userID,
		Purpose:      purpose,
		Provider:     provider,
		ModelName:    model,
		EncryptedKey: encrypted,
		IsActive:     req.IsActive,
	}

	tx := h.DB.Begin()
	if req.IsActive {
		if err := tx.Model(&models.UserConfig{}).
			Where("user_id = ? AND purpose = ?", userID, purpose).
			Update("is_active", false).Error; err != nil {
			tx.Rollback()
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to reset active config"})
			return
		}
	}

	if err := tx.Create(&config).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create config"})
		return
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to commit config"})
		return
	}

	c.JSON(http.StatusCreated, gin.H{"config": serializeConfig(config)})
}

func (h *UserConfigHandler) List(c *gin.Context) {
	userID, ok := middleware.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing user context"})
		return
	}

	var configs []models.UserConfig
	if err := h.DB.Where("user_id = ?", userID).Order("updated_at DESC").Find(&configs).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to load configs"})
		return
	}

	output := make([]gin.H, 0, len(configs))
	for _, config := range configs {
		output = append(output, serializeConfig(config))
	}

	c.JSON(http.StatusOK, gin.H{"configs": output})
}

func (h *UserConfigHandler) Get(c *gin.Context) {
	config, ok := h.findOwnedConfig(c)
	if !ok {
		return
	}

	c.JSON(http.StatusOK, gin.H{"config": serializeConfig(config)})
}

func (h *UserConfigHandler) Update(c *gin.Context) {
	userID, ok := middleware.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing user context"})
		return
	}

	config, ok := h.findOwnedConfig(c)
	if !ok {
		return
	}

	var req updateUserConfigRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	purpose := config.Purpose
	provider := config.Provider
	model := config.ModelName

	updates := map[string]any{}
	activate := false

	if req.Purpose != nil {
		nextPurpose := normalizePurpose(*req.Purpose)
		if !isAllowedPurpose(nextPurpose) {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid purpose"})
			return
		}
		purpose = nextPurpose
		updates["purpose"] = nextPurpose
	}

	if req.Provider != nil {
		nextProvider := normalizeProvider(*req.Provider)
		provider = nextProvider
		updates["provider"] = nextProvider
	}

	if req.Model != nil {
		model = strings.TrimSpace(*req.Model)
		updates["model_name"] = model
	}

	if err := validateConfigFields(purpose, provider, model); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if req.APIKey != nil {
		if len(*req.APIKey) < 8 || len(*req.APIKey) > 512 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "apiKey length must be between 8 and 512"})
			return
		}
		encrypted, err := security.Encrypt(*req.APIKey, h.AESKey)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to encrypt api key"})
			return
		}
		updates["encrypted_key"] = encrypted
	}

	if req.IsActive != nil {
		updates["is_active"] = *req.IsActive
		activate = *req.IsActive
	}

	if len(updates) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no fields to update"})
		return
	}

	tx := h.DB.Begin()
	if activate {
		if err := tx.Model(&models.UserConfig{}).
			Where("user_id = ? AND purpose = ? AND id <> ?", userID, purpose, config.ID).
			Update("is_active", false).Error; err != nil {
			tx.Rollback()
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to reset active config"})
			return
		}
	}

	if err := tx.Model(&config).Updates(updates).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update config"})
		return
	}

	if err := tx.First(&config, config.ID).Error; err != nil {
		tx.Rollback()
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to reload config"})
		return
	}

	if err := tx.Commit().Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to commit config update"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"config": serializeConfig(config)})
}

func (h *UserConfigHandler) Delete(c *gin.Context) {
	config, ok := h.findOwnedConfig(c)
	if !ok {
		return
	}

	if err := h.DB.Delete(&config).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete config"})
		return
	}

	c.Status(http.StatusNoContent)
}

func (h *UserConfigHandler) findOwnedConfig(c *gin.Context) (models.UserConfig, bool) {
	userID, ok := middleware.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing user context"})
		return models.UserConfig{}, false
	}

	configID := c.Param("id")
	var config models.UserConfig
	if err := h.DB.Where("id = ? AND user_id = ?", configID, userID).First(&config).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			c.JSON(http.StatusNotFound, gin.H{"error": "config not found"})
			return models.UserConfig{}, false
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to load config"})
		return models.UserConfig{}, false
	}

	return config, true
}

func serializeConfig(config models.UserConfig) gin.H {
	return gin.H{
		"id":        config.ID,
		"purpose":   config.Purpose,
		"provider":  config.Provider,
		"model":     config.ModelName,
		"isActive":  config.IsActive,
		"createdAt": config.CreatedAt,
		"updatedAt": config.UpdatedAt,
	}
}

func normalizePurpose(value string) string {
	trimmed := strings.ToLower(strings.TrimSpace(value))
	if trimmed == "" {
		return "script"
	}
	return trimmed
}

func normalizeProvider(value string) string {
	return strings.ToLower(strings.TrimSpace(value))
}

func isAllowedPurpose(purpose string) bool {
	switch purpose {
	case "script", "image", "video":
		return true
	default:
		return false
	}
}

func validateConfigFields(purpose, provider, model string) error {
	if !isAllowedPurpose(purpose) {
		return errBadRequest("invalid purpose")
	}

	switch purpose {
	case "video":
		if provider != "seedance2.0" {
			return errBadRequest("video purpose only supports provider seedance2.0")
		}
		if strings.TrimSpace(model) == "" {
			return errBadRequest("video purpose requires model")
		}
	default:
		if provider != "qwen" && provider != "deepseek" && provider != "doubao" && provider != "openai" {
			return errBadRequest("provider must be one of qwen/deepseek/doubao/openai")
		}
	}

	return nil
}

func errBadRequest(message string) error {
	return &requestError{message: message}
}

type requestError struct {
	message string
}

func (e *requestError) Error() string {
	return e.message
}
